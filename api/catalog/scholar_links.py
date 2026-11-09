"""In-place review of the original Person/node and Person/topic associations."""
from django.core.paginator import Paginator, EmptyPage
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import KnowledgeNode, KnowledgeRelation, Person, PersonNodeRelation, PersonTopicRelation, ScholarProfile, Topic
from catalog.scholar_commands import ScholarCommandMixin, PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.scholar_relation_commands import ScholarRelationReceipt
from catalog.services.canonical_mutations import record_admin_canonical_change
from catalog.services.person_authority import AuthorityConflict, digest
from catalog.relation_source_anchor import RelationAnchorInput, RelationAnchorMaterial, choose_anchor, anchor_material
from common.capabilities import Capability, has_capability
from common.permissions import IsKnowledgeEditor
from ingestion.models import AuditEvent


# Both kinds keep their existing identities, review states and uniqueness rules.
KINDS = {
    "node": (PersonNodeRelation, KnowledgeNode, "node", "status", "published", "pending", "archived", "is_representative"),
    "topic": (PersonTopicRelation, Topic, "topic", "review_status", "approved", "suggested", "rejected", "is_primary"),
}


def configuration(kind):
    if kind not in KINDS:
        raise NotFound("未知学者关联类型。")
    return KINDS[kind]


def link_snapshot(row, kind):
    _, _, field, status, _, _, _, featured = configuration(kind)
    return {"id": str(row.pk), "person_id": str(row.person_id), "target_id": str(getattr(row, f"{field}_id")),
        "relation_label": row.relation_label, "source": row.source, "status": getattr(row, status),
        "featured": getattr(row, featured), "sort_order": getattr(row, "sort_order", 0),
        "relation_type": getattr(row, "relation_type", "related"), "direction": getattr(row, "direction", "undirected"),
        "node_is_source": getattr(row, "node_is_source", False),
        "source_anchor": {"span_id": str(row.evidence_span_id), "document_revision_id": str(row.source_document_revision_id)} if kind == "node" and row.evidence_span_id else None,
        "reviewed_by": row.reviewed_by_id, "reviewed_at": row.reviewed_at, "updated_at": row.updated_at}


def link_payload(row, kind, *, with_source=False):
    _, _, field, _, published, _, _, _ = configuration(kind)
    data = link_snapshot(row, kind)
    target = getattr(row, field)
    available = (target.status if kind == "node" else target.editorial_status) == "published"
    return {**data, "edit_version": digest(data), "kind": kind,
        "person_name": row.person.preferred_name,
        "relation_type_label": row.get_relation_type_display() if kind == "node" else "相关主题",
        "target_name": target.canonical_name_zh if kind == "node" else target.name,
        "target_type": target.node_type if kind == "node" else "topic",
        "target_published": available, "confirmed": data["status"] == published,
        "source_material": anchor_material(row.evidence_span, row.source_document_revision_id) if with_source and kind == "node" and row.evidence_span_id else None,
        "target_href": f"/admin/theories/{target.pk}" if kind == "node" else f"/admin/topics/{target.pk}"}


class ScholarLinkInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["save", "confirm", "withdraw"])
    id = serializers.UUIDField(required=False)
    target_id = serializers.UUIDField(required=False)
    edit_version = serializers.CharField(required=False, max_length=64)
    relation_label = serializers.CharField(max_length=120, allow_blank=True, required=False)
    source = serializers.CharField(max_length=160, allow_blank=True, required=False)
    featured = serializers.BooleanField(required=False)
    sort_order = serializers.IntegerField(min_value=0, max_value=2147483647, required=False)
    relation_type = serializers.ChoiceField(choices=PersonNodeRelation.RelationType.choices, required=False)
    direction = serializers.ChoiceField(choices=KnowledgeRelation.Direction.choices, required=False)
    node_is_source = serializers.BooleanField(required=False)
    source_anchor = RelationAnchorInput(required=False, allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError("关联只能修改标注、出处、展示位置及确认状态。")
        return super().to_internal_value(data)

    def validate(self, data):
        if data["action"] == "withdraw":
            if not data.get("id") or set(data) - {"action", "id", "edit_version"}:
                raise ValidationError("撤回仅接受原记录和当前版本，未保存输入不会随之写入。")
        elif not {"target_id", "relation_label", "source", "featured", "sort_order"}.issubset(data):
            raise ValidationError("请完整核对关联对象、说明、出处与展示位置。")
        if data.get("id") and not data.get("edit_version"):
            raise ValidationError("缺少原记录版本，请重新读取关联。")
        if not data.get("id") and data["action"] != "save":
            raise ValidationError("新关联须先保存待核对记录，再明确确认。")
        return data


class AdminScholarLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    person_id = serializers.UUIDField()
    person_name = serializers.CharField()
    relation_type = serializers.ChoiceField(choices=PersonNodeRelation.RelationType.choices)
    relation_type_label = serializers.CharField()
    direction = serializers.ChoiceField(choices=KnowledgeRelation.Direction.choices)
    node_is_source = serializers.BooleanField()
    source_anchor = RelationAnchorInput(allow_null=True)
    source_material = RelationAnchorMaterial(allow_null=True)
    kind = serializers.ChoiceField(choices=["node", "topic"])
    target_id = serializers.UUIDField()
    target_name = serializers.CharField()
    target_type = serializers.CharField()
    target_href = serializers.CharField()
    target_published = serializers.BooleanField()
    relation_label = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    confirmed = serializers.BooleanField()
    featured = serializers.BooleanField()
    sort_order = serializers.IntegerField()
    reviewed_by = serializers.IntegerField(allow_null=True)
    reviewed_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()
    edit_version = serializers.CharField()
    save_receipt = ScholarRelationReceipt(required=False)
    save_replayed = serializers.BooleanField(required=False)


class ScholarLinkPage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.IntegerField(allow_null=True)
    previous = serializers.IntegerField(allow_null=True)
    results = AdminScholarLinkSerializer(many=True)


class LinkConfiguration:
    def configure(self, kind):
        self.kind = kind
        self.save_model = configuration(kind)[0]
        self.save_action = f"scholar_{kind}_link_command"
        self.save_identity = "relation_id"
        self.save_lock = f"scholar_{kind}_link_request"
        self.save_salt = f"stl4-scholar-{kind}-link"
        self.save_label = "学者关联"


class ScholarLinkView(LinkConfiguration, ScholarCommandMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    def _draft_read_rows(self, rows):
        return [link_payload(row, self.kind, with_source=True) for row in rows]

    @extend_schema(parameters=[OpenApiParameter("page", int), OpenApiParameter("id", str)], responses=ScholarLinkPage)
    def get(self, request, scholar_id, kind):
        model, _, field, *_ = configuration(kind)
        scholar = get_object_or_404(ScholarProfile, pk=scholar_id)
        rows = model.objects.filter(person_id=scholar.person_id).select_related(field, "person")
        if request.query_params.get("id"):
            key = serializers.UUIDField().run_validation(request.query_params["id"])
            rows = rows.filter(pk=key)
        rows = rows.order_by("sort_order", "pk") if kind == "node" else rows.order_by("-is_primary", "created_at", "pk")
        page_number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        try:
            page = Paginator(rows, 24).page(page_number)
        except EmptyPage:
            raise NotFound("这一页已无关联，请返回第一页重新读取。") from None
        return Response(ScholarLinkPage({"count": page.paginator.count,
            "next": page.next_page_number() if page.has_next() else None,
            "previous": page.previous_page_number() if page.has_previous() else None,
            "results": [link_payload(row, kind, with_source=bool(request.query_params.get("id"))) for row in page]}).data)

    @extend_schema(request=ScholarLinkInput, responses=AdminScholarLinkSerializer)
    def post(self, request, scholar_id, kind):
        if kind == "node":
            from catalog.academic_relation_views import relation_response
            scholar = get_object_or_404(ScholarProfile, pk=scholar_id)
            values = {**request.data, "person": scholar.person, "node": request.data.get("target_id")}
            if request.data.get("action") == "withdraw":
                values["operation"] = "withdraw"
            return relation_response(request, "person", values=values, legacy_id=request.data.get("id"))
        self.configure(kind)
        if not request.headers.get("Idempotency-Key"):
            raise ValidationError("请使用固定请求编号，以便查回关联操作。")
        incoming = ScholarLinkInput(data=request.data)
        incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        return self._scholar_write(request, lambda: self.apply(request, scholar_id, data), creating=not data.get("id"))

    def apply(self, request, scholar_id, data):
        kind, actor = self.kind, request.user
        if kind != "topic":
            raise ValidationError("学术陈述须从知识编纂提交同一审核草稿，旧人物与节点写入已退役。")
        model, target_model, field, status, published, pending, withdrawn, featured = configuration(kind)
        # Keep the scholar editor's original lock order, then serialize links on Person.
        scholar = get_object_or_404(ScholarProfile.objects.select_for_update(), pk=scholar_id)
        person = get_object_or_404(Person.objects.select_for_update(), pk=scholar.person_id)
        scholar.person = person
        row = get_object_or_404(model.objects.select_for_update(), pk=data["id"], person=person) if data.get("id") else None
        before = link_snapshot(row, kind) if row else {}
        if row and not constant_time_compare(digest(before), data["edit_version"]):
            raise AuthorityConflict("这条关联已被修改，请保留当前输入并重新读取原记录。")
        action = data["action"]
        if action in {"confirm", "withdraw"} and not has_capability(actor, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("当前账户不能确认或撤回公开关联。")
        if row and action == "save" and getattr(row, status) == published:
            raise ValidationError("这是已确认关联。请明确确认更新，或撤回后再保存待核对内容。")
        target_id = getattr(row, f"{field}_id") if action == "withdraw" else data["target_id"]
        if row and target_id != getattr(row, f"{field}_id"):
            raise ValidationError("原关联对象不能替换；请另建关联并保留原记录。")
        target = get_object_or_404(target_model.objects.select_for_update(), pk=target_id)
        if kind == "topic" and (len(data.get("source", "")) > 120 or data.get("sort_order", 0)):
            raise ValidationError("主题出处最多120字；主题按主要关联展示，不接受概念排序值。")
        if kind == "topic" and (data.get("relation_type", "related") != "related" or data.get("direction", "undirected") != "undirected" or data.get("node_is_source", False)):
            raise ValidationError("主题关联不接受人物与概念的方向字段。")
        if kind == "topic" and data.get("source_anchor"):
            raise ValidationError("请在人物与概念关系中核对材料原文。主题关联不能使用此来源字段。")
        anchor, anchor_revision = (row.evidence_span, row.source_document_revision) if row and kind == "node" else (None, None)
        if kind == "node" and "source_anchor" in data:
            anchor, anchor_revision = choose_anchor(data["source_anchor"])
        relation_type = data.get("relation_type", getattr(row, "relation_type", "related"))
        direction = data.get("direction", getattr(row, "direction", "undirected"))
        reverse = data.get("node_is_source", getattr(row, "node_is_source", False))
        if direction == "undirected" and reverse:
            raise ValidationError("无方向关联不能指定节点为来源，请重新核对方向。")
        if action == "confirm":
            if kind == "node" and relation_type != "related" and direction != "directed":
                raise ValidationError("提出、批判等具体关系须明确来源与目标方向。")
            if kind == "node" and reverse and relation_type in {"proposes", "defines", "develops", "interprets", "uses"}:
                raise ValidationError("提出、定义、发展、解释和运用须以人物为来源。若表示理论影响人物，请选择影响并核对方向。")
            if not data["relation_label"] or not (data["source"] or anchor):
                raise ValidationError("确认前须补充关系说明和可追溯出处。")
            if anchor and not anchor_material(anchor, anchor_revision.pk)["public_eligible"]:
                raise ValidationError("所选原文的准确版本未公开或已经失效，请先核对该材料，不能把其他版本作为相同出处确认。")
            if (target.status if kind == "node" else target.editorial_status) != "published":
                raise ValidationError("关联对象尚未公开。请先发布该对象，再确认关联。")
            if scholar.editorial_status != "published" or person.authority_status != "verified":
                raise ValidationError("学者尚未发布或规范身份未确认。待核对关联已保留，请先完成学者发布。")
        if row is None:
            if model.objects.filter(person=person, **{field: target}).exists():
                raise AuthorityConflict("该对象已有关系记录，包括已撤回记录；请在列表中打开原记录。")
            row = model(person=person, **{field: target})
        if action != "withdraw":
            row.relation_label, row.source = data["relation_label"], data["source"]
            setattr(row, featured, data["featured"])
            if kind == "node":
                row.sort_order = data["sort_order"]
                row.relation_type, row.direction, row.node_is_source = relation_type, direction, reverse
                row.evidence_span, row.source_document_revision = anchor, anchor_revision
        setattr(row, status, published if action == "confirm" else withdrawn if action == "withdraw" else pending)
        row.reviewed_by = actor if action != "save" else None
        row.reviewed_at = timezone.now() if action != "save" else None
        # Retain machine confidence; a human decision is not a calibrated probability.
        try:
            with transaction.atomic():
                row.save()
        except IntegrityError:
            if model.objects.filter(person=person, **{field: target}).exclude(pk=row.pk).exists():
                raise AuthorityConflict("关联身份已变化，请重新读取原记录后再操作。") from None
            raise
        after = link_snapshot(row, kind)
        AuditEvent.objects.create(actor=actor, action="scholar_link_review", object_type=model._meta.label,
            object_id=str(row.pk), before=serializable(before), after={**serializable(after), "operation": action,
                "request_id": request.headers["Idempotency-Key"], "scholar_id": str(scholar.pk)})
        if action in {"confirm", "withdraw"}:
            # Existing durable publication/dependency outbox refreshes the same graph and pages.
            for object_type, parent in (("scholar_profile", scholar), ("knowledge_node" if kind == "node" else "topic", target)):
                record_admin_canonical_change(object_type=object_type, target=parent, change_kind="update",
                    changed_fields=["person_relations"], actor=actor,
                    request_idempotency_key=request.headers["Idempotency-Key"])
        return Response(AdminScholarLinkSerializer(link_payload(row, kind, with_source=True)).data)


def serializable(data):
    from django.core.serializers.json import DjangoJSONEncoder
    import json
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


class ScholarLinkReceiptView(LinkConfiguration, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=ScholarRelationReceipt)
    def get(self, request, kind, request_id):
        self.configure(kind)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(ScholarRelationReceipt(command_receipt(request.user, request_id,
            action=self.save_action, model=self.save_model, identity=self.save_identity)).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=ScholarRelationReceipt)
    def post(self, request, kind, request_id):
        self.configure(kind)
        return Response(ScholarRelationReceipt(stop_pending_save(request, request_id,
            action=self.save_action, model=self.save_model, identity=self.save_identity, lock=self.save_lock)).data)
