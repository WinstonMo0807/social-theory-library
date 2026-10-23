"""Edition-bound administrative notes and links with recoverable commands."""
from urllib.parse import urlsplit
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.manual_catalog_views import actor_for
from catalog.models import Edition, EditionSupportingMaterial
from catalog.services.editorial_issues import EditConflict
from catalog.services.workspace_edits import _digest
from common.permissions import CanEditMetadata
from ingestion.models import AuditEvent

ACTION = "edition.supporting_material.command"


class SupportingFields(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["note", "link"])
    title = serializers.CharField(max_length=300)
    note = serializers.CharField(max_length=12000, allow_blank=True, default="")
    url = serializers.URLField(max_length=2000, allow_blank=True, default="")

    def validate(self, data):
        if data["kind"] == "link":
            parsed = urlsplit(data["url"])
            if parsed.scheme not in {"https", "http"} or not parsed.netloc or parsed.username or parsed.password:
                raise ValidationError("请输入不含账户密码的完整 HTTP 或 HTTPS 链接。")
        elif data["url"] or not data["note"].strip():
            raise ValidationError("补充说明需填写正文；相关链接请单独选择链接类型。")
        return data


class SupportingInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=64)
    action = serializers.ChoiceField(choices=["create", "update", "archive", "restore"])
    material_id = serializers.UUIDField(required=False, allow_null=True)
    fields = SupportingFields(required=False)

    def validate(self, data):
        if data["action"] in {"create", "update"} and "fields" not in data: raise ValidationError("请填写完整材料。")
        if data["action"] == "create" and data.get("material_id"): raise ValidationError("新材料不能借用已有编号。")
        if data["action"] != "create" and not data.get("material_id"): raise ValidationError("请选择需要处理的材料。")
        if data["action"] in {"archive", "restore"} and "fields" in data: raise ValidationError("归档或恢复不能同时改写材料。")
        return data


class SupportingRow(serializers.ModelSerializer):
    class Meta:
        model = EditionSupportingMaterial
        fields = ["id", "kind", "title", "note", "url", "archived", "updated_at"]


class SupportingQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    archived = serializers.BooleanField(default=False)


class SupportingState(serializers.Serializer):
    owner_id = serializers.CharField()
    edition_id = serializers.UUIDField()
    version = serializers.CharField()
    results = SupportingRow(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()


class SupportingReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    next_url = serializers.CharField(allow_blank=True)
    result = serializers.JSONField(allow_null=True)


class StopInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


def version(edition):
    return _digest([edition.pk, list(edition.supporting_materials.order_by("pk").values_list("pk", "updated_at", "archived"))])


def previous(actor, identifier):
    return AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(identifier)).first()


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "edition_id": row.object_id,
        "state": row.after["state"], "next_url": "", "result": row.after.get("result")}


class SupportingMaterialsView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(parameters=[SupportingQuery], responses=SupportingState)
    def get(self, request, edition_id):
        actor = actor_for(request)
        incoming = SupportingQuery(data=request.query_params); incoming.is_valid(raise_exception=True)
        edition = get_object_or_404(Edition, pk=edition_id)
        rows = Paginator(edition.supporting_materials.filter(archived=incoming.validated_data["archived"]), 20)
        page = rows.get_page(incoming.validated_data["page"])
        return Response({"owner_id": str(actor.pk), "edition_id": str(edition.pk), "version": version(edition),
                         "results": SupportingRow(page, many=True).data, "count": rows.count, "page": page.number, "pages": rows.num_pages})

    @extend_schema(request=SupportingInput, responses=SupportingReceipt)
    @transaction.atomic
    def post(self, request, edition_id):
        actor = actor_for(request, True)
        incoming = SupportingInput(data=request.data); incoming.is_valid(raise_exception=True); data = incoming.validated_data
        fingerprint = _digest(data)
        old = previous(actor, data["request_id"])
        if old:
            if old.object_id != str(edition_id) or old.after.get("fingerprint") != fingerprint or old.after["state"] != "applied": raise EditConflict("原请求已停止或不属于这项修改，请先查回。")
            return Response(receipt(old))
        edition = get_object_or_404(Edition.objects.select_for_update(), pk=edition_id)
        if version(edition) != data["expected_version"]: raise EditConflict("补充材料已经变化，填写仍保留，请刷新后核对。")
        before = {}
        if data["action"] == "create":
            row = EditionSupportingMaterial.objects.create(edition=edition, created_by=actor, updated_by=actor, **data["fields"])
        else:
            row = get_object_or_404(EditionSupportingMaterial.objects.select_for_update(), edition=edition, pk=data["material_id"])
            before = dict(SupportingRow(row).data)
            if data["action"] == "update":
                if row.archived: raise EditConflict("请先恢复归档材料，再修改内容。")
                if data["fields"]["kind"] != row.kind: raise ValidationError("材料类型不能通过修改改变，请另建对应材料。")
                for key, value in data["fields"].items(): setattr(row, key, value)
            else:
                archived = data["action"] == "archive"
                if row.archived == archived: raise EditConflict("材料状态已变化，请重新读取。")
                row.archived = archived
            row.updated_by = actor; row.save()
        audit = AuditEvent.objects.create(actor=actor, action=ACTION, request_id=str(data["request_id"]), object_type="catalog.Edition", object_id=str(edition.pk),
            before=before, after={"state": "applied", "fingerprint": fingerprint, "result": dict(SupportingRow(row).data)})
        return Response(receipt(audit))


class SupportingReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=SupportingReceipt)
    def get(self, request, edition_id, request_id):
        actor = actor_for(request); row = previous(actor, request_id)
        if row is None or row.object_id != str(edition_id): raise NotFound("尚未找到本人的原请求，请稍后查回或停止尚未执行的操作。")
        return Response(receipt(row))

    @extend_schema(request=StopInput, responses=SupportingReceipt)
    @transaction.atomic
    def post(self, request, edition_id, request_id):
        actor = actor_for(request, True)
        if request.data != {"action": "cancel_pending"}: raise ValidationError("仅接受停止尚未执行的原请求。")
        row = previous(actor, request_id)
        if row and row.object_id != str(edition_id): raise EditConflict("原请求属于其他版本。")
        if not row:
            get_object_or_404(Edition, pk=edition_id)
            row = AuditEvent.objects.create(actor=actor, action=ACTION, request_id=str(request_id), object_type="catalog.Edition", object_id=str(edition_id), after={"state": "cancelled"})
        return Response(receipt(row))
