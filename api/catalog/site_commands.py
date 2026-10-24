"""Account-bound receipts for the existing website save/publish transaction."""
import json
from uuid import UUID
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.models import User
from common.capabilities import capability_snapshot
from common.permissions import IsLibraryAdmin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services import editorial_issues as service
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock
from catalog.site_layout import HomeSourcePageSerializer, HomeSourceQuerySerializer, source_page
from ingestion.models import AuditEvent

ACTION = "site_content.command"


class SiteReceiptSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    actor_id = serializers.CharField()
    action = serializers.ChoiceField(choices=["save", "publish", "cancelled"])
    saved_version = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()


class SiteStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


def receipt(row):
    return {"request_id": str(row.pk), "actor_id": str(row.actor_id), "action": row.after["operation"],
            "saved_version": row.after.get("saved_version", ""), "created_at": row.created_at}


def lock_actor(request, key):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("编辑账户已变化，请重新读取网站内容。")
    actor = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or capability_snapshot(actor).access_level not in {"admin", "superadmin"}:
        raise PermissionDenied("账户会话或网站管理权限已变化。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock("site_content_request", key)
    return actor


@transaction.atomic
def execute(request, *, publishing=False):
    try:
        key = UUID(request.headers.get("Idempotency-Key", ""))
    except (ValueError, TypeError):
        raise ValidationError("网站保存与发布需要固定请求编号。") from None
    actor = lock_actor(request, key)
    operation = "publish" if publishing else "save"
    fingerprint = salted_hmac("stl4-site-content", json.dumps({"actor": actor.pk, "operation": operation, "data": request.data}, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True), algorithm="sha256").hexdigest()
    previous = AuditEvent.objects.filter(pk=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.action != ACTION or previous.after.get("fingerprint") != fingerprint:
            raise service.EditConflict("该请求编号已完成另一操作或已停止，请查回原结果。")
        return {**service.site_payload(), "receipt": receipt(previous), "replayed": True}
    if publishing and request.data.get("confirm") is not True:
        raise ValidationError("请明确确认后发布网站内容。")
    if publishing and request.data.get("expected_fingerprint"):
        from catalog.site_publication_review import review
        checked = review(request.data.get("edit_version"))
        if checked["fingerprint"] != request.data["expected_fingerprint"]:
            raise service.EditConflict("网站内容或所引来源已变化，请重新读取发布检查再确认。")
    payload = service.publish_site(request.data.get("edit_version"), actor) if publishing else service.save_site(request.data, actor)
    row = AuditEvent.objects.create(pk=key, actor=actor, action=ACTION, object_type="site_content", object_id=payload["site_id"],
        after={"operation": operation, "fingerprint": fingerprint, "saved_version": payload["edit_version"]})
    return {**payload, "receipt": receipt(row), "replayed": False}


class SiteReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(responses=SiteReceiptSerializer)
    def get(self, request, request_id):
        return Response(receipt(get_object_or_404(AuditEvent, pk=request_id, actor=request.user, action=ACTION)))

    @extend_schema(request=SiteStopSerializer, responses=SiteReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        serializer = SiteStopSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = lock_actor(request, request_id)
        row = AuditEvent.objects.filter(pk=request_id).first()
        if row and (row.actor_id != actor.pk or row.action != ACTION):
            raise ValidationError("该请求编号不属于当前账户的网站操作。")
        if not row:
            row = AuditEvent.objects.create(pk=request_id, actor=actor, action=ACTION, object_type="site_content", object_id="",
                after={"operation": "cancelled", "fingerprint": "", "saved_version": ""})
        return Response(receipt(row))


class SiteSourcesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(parameters=[HomeSourceQuerySerializer], responses=HomeSourcePageSerializer)
    def get(self, request):
        return Response(source_page(request.query_params))
