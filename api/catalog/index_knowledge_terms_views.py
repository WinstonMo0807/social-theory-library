"""M13 edits the existing KnowledgeNode editorial draft, never derived terms."""
from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin, current_editorial_version
from catalog.index_maintenance_views import IndexMaintenanceStopSerializer, locked_actor
from catalog.models import CanonicalObjectRevision, EditorialRevision, KnowledgeNode, KnowledgeNodeAlias
from catalog.services.canonical_identity import INDEPENDENT_IDENTITY_NODE_TYPES
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_issues import EditConflict
from catalog.services.editorial_revision import EditorialRevisionError
from catalog.theory_system_views import TheorySystemFeatureMixin
from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from ingestion.models import AuditEvent

ACTION = "index.knowledge_terms.draft"
FIELDS = ("alias", "language", "alias_type", "source_kind", "is_verified")


class KnowledgeTermInput(serializers.Serializer):
    alias = serializers.CharField(max_length=240)
    language = serializers.CharField(max_length=16)
    alias_type = serializers.ChoiceField(choices=KnowledgeNodeAlias.AliasType.choices)
    source_kind = serializers.ChoiceField(choices=KnowledgeNodeAlias.SourceKind.choices)
    is_verified = serializers.BooleanField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != set(self.fields):
            raise serializers.ValidationError("每条术语须保留完整名称、语言、类别与来源状态。")
        return super().to_internal_value(data)


class KnowledgeTermsCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    node_id = serializers.UUIDField()
    expected_version = serializers.RegexField(r"^[a-f0-9]{64}$")
    aliases = KnowledgeTermInput(many=True, max_length=200)
    reason = serializers.CharField(min_length=2, max_length=1000)
    confirmed = serializers.BooleanField()

    def validate(self, data):
        if set(self.initial_data) != set(self.fields) or data["confirmed"] is not True:
            raise serializers.ValidationError("请核对术语变化并确认保存草稿。")
        names = [normalize(row["alias"]) for row in data["aliases"]]
        if len(names) != len(set(names)):
            raise serializers.ValidationError("同一知识条目的别名不可重复。")
        return data


class KnowledgeTermsSourceSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    node_id = serializers.UUIDField()
    title = serializers.CharField()
    foreign_name = serializers.CharField(allow_blank=True)
    node_type = serializers.CharField()
    status = serializers.CharField()
    version = serializers.CharField()
    aliases = KnowledgeTermInput(many=True)
    saved_aliases = KnowledgeTermInput(many=True)
    revision_id = serializers.UUIDField(allow_null=True)
    can_edit = serializers.BooleanField()
    notice = serializers.CharField(allow_blank=True)
    editor_url = serializers.CharField()


class KnowledgeTermsReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    node_id = serializers.UUIDField(allow_null=True)
    revision_id = serializers.UUIDField(allow_null=True)
    next_url = serializers.CharField(allow_blank=True)


def normalize(value):
    # Same identity normalization as KnowledgeNodeAlias, not fuzzy entity matching.
    return " ".join(value.casefold().split())


def source(node, actor):
    drafts = list(EditorialRevision.objects.filter(target_type="knowledge_node", target_id=node.pk, status="draft").order_by("revision"))
    canonical = CanonicalObjectRevision.objects.filter(object_type="knowledge_node", object_id=node.pk).values_list("current_revision", flat=True).first() or 0
    saved = list(node.aliases.order_by("alias", "id").values(*FIELDS))
    draft = drafts[-1] if drafts else None
    raw_aliases = draft.materialized_preview.get("aliases", saved) if draft else saved
    # Older full-editor drafts omit these fields. Match their original publish defaults.
    aliases = [{"alias": row["alias"], "language": row.get("language") or "zh-CN",
        "alias_type": row.get("alias_type") or "alias", "source_kind": row.get("source_kind") or "other",
        "is_verified": row.get("is_verified", True)} for row in raw_aliases]
    notice = ""
    if node.node_type in INDEPENDENT_IDENTITY_NODE_TYPES or node.status in {"archived", "rejected"}:
        notice = "此记录已退役或使用独立身份，请从原知识编辑页处理。"
    elif len(drafts) > 1 or any(row.base_revision != canonical for row in drafts):
        notice = "存在需要核对的旧草稿，请先在原知识编辑页处理版本。"
    elif len(aliases) > 200:
        notice = "术语超过200项，请从原知识编辑页分批整理。"
    version = sha256(json.dumps({"editorial": current_editorial_version("knowledge_node", node.pk), "aliases": aliases,
        "saved": saved, "drafts": [(str(row.pk), str(row.updated_at), row.base_revision) for row in drafts]}, sort_keys=True, default=str).encode()).hexdigest()
    snapshot = draft.materialized_preview if draft else {}
    return {"owner_id": str(actor.pk), "node_id": str(node.pk), "title": snapshot.get("canonical_name_zh", node.canonical_name_zh),
        "foreign_name": snapshot.get("canonical_name_en", node.canonical_name_en), "node_type": node.node_type, "status": node.status,
        "version": version, "aliases": aliases, "saved_aliases": saved, "revision_id": str(draft.pk) if draft else None,
        "can_edit": has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY) and not notice,
        "notice": notice, "editor_url": f"/admin/theories/{node.pk}"}


def receipt(row):
    node_id = row.after.get("node_id")
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "state": "cancelled" if row.after.get("cancelled") else "applied",
        "node_id": node_id, "revision_id": row.after.get("revision_id"), "next_url": f"/admin/theories/{node_id}" if node_id else ""}


class KnowledgeTermsSourceView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=KnowledgeTermsSourceSerializer)
    def get(self, request, node_id):
        return Response(KnowledgeTermsSourceSerializer(source(get_object_or_404(KnowledgeNode, pk=node_id), request.user)).data)


class KnowledgeTermsCommandView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(request=KnowledgeTermsCommandSerializer, responses=KnowledgeTermsReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = locked_actor(request, capability=Capability.EDIT_DRAFT_AUTHORITY)
        serializer = KnowledgeTermsCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature:
                raise EditConflict("同一次保存不能更换知识对象或术语内容。")
            return Response(receipt(prior))
        node = get_object_or_404(KnowledgeNode.objects.select_for_update(), pk=data["node_id"])
        list(node.aliases.select_for_update())
        current = source(node, actor)
        if not current["can_edit"] or data["expected_version"] != current["version"]:
            raise EditConflict(current["notice"] or "知识来源已变化，请保留输入并重新核对。")
        names = {normalize(row["alias"]) for row in data["aliases"]}
        if any(normalize(row["alias"]) not in names for row in current["aliases"]):
            raise ValidationError("原术语不能省略或改名。更正时保留原词并取消核验，再另添准确名称。")
        if data["aliases"] == current["aliases"]:
            raise ValidationError("没有需要保存的术语变化。")
        try:
            revision = save_object_editorial_patch("knowledge_node", node.pk, {"aliases": [dict(row) for row in data["aliases"]]}, actor=actor,
                request_key=f"index-terms:{actor.pk}:{data['request_id']}", change_note=data["reason"])
        except EditorialRevisionError as error:
            raise EditConflict(str(error)) from error
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="knowledge_node", object_id=str(node.pk), request_id=str(data["request_id"]),
            after={"signature": signature, "node_id": str(node.pk), "revision_id": str(revision.pk) if revision else None})
        return Response(receipt(row))


class KnowledgeTermsReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=KnowledgeTermsReceiptSerializer)
    @transaction.atomic
    def get(self, request, request_id):
        actor = locked_actor(request, capability=Capability.EDIT_DRAFT_AUTHORITY)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=IndexMaintenanceStopSerializer, responses=KnowledgeTermsReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = locked_actor(request, capability=Capability.EDIT_DRAFT_AUTHORITY)
        serializer = IndexMaintenanceStopSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只可停止原待定保存。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row is None:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="knowledge_node", object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))
