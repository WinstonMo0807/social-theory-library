"""Recoverable saves around the existing scholar serializer and draft service."""
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
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice
from common.private_responses import PrivateAccountResponses
from ingestion.models import AuditEvent
from catalog.models import ScholarProfile
from catalog.services.person_authority import AuthorityConflict
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock

ACTION = "scholar_editor_save"


def command_receipt(actor, request_id):
    row = get_object_or_404(AuditEvent, pk=request_id, actor=actor, action=ACTION)
    return {"actor_id": str(actor.pk), "request_id": str(row.pk), "scholar_id": row.object_id,
        "saved_version": row.after.get("saved_version", ""), "exists": ScholarProfile.objects.filter(pk=row.object_id).exists(),
        "created_at": row.created_at}


class ScholarCommandMixin:
    def create(self, request, *args, **kwargs):
        inherited = super().create
        return self._scholar_write(request, lambda: inherited(request, *args, **kwargs), creating=True)

    def _guarded_edit(self, handler, request, *args, **kwargs):
        inherited = super()._guarded_edit
        return self._scholar_write(request, lambda: inherited(handler, request, *args, **kwargs))

    @transaction.atomic
    def _scholar_write(self, request, handler, *, creating=False):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取学者资料。")
        original = request.user
        actor = get_object_or_404(User.objects.select_for_update(), pk=original.pk, is_active=True)
        if actor.token_version != original.token_version or not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
            raise PermissionDenied("账户会话或编辑权限已变化，请重新登录。")
        if creating and not has_capability(actor, Capability.CREATE_AUTHORITY):
            raise PermissionDenied("当前账户不能创建学者档案。")
        request.user = actor
        if request.method == "DELETE":
            # Recycle keeps its existing recovery record; a save key cannot reinterpret it.
            return handler()
        key = request.headers.get("Idempotency-Key", "")
        if not key:
            if creating:
                raise ValidationError("新建学者需要固定请求编号，请重新打开编辑页。")
            # Original publication/portrait operations already carry their own
            # revision or selection recovery. Preserve those existing flows.
            return handler()
        if request.FILES:
            raise ValidationError("肖像请沿原媒体选择流程上传，不与文字保存混合。")
        try:
            request_id = UUID(key)
        except (ValueError, TypeError, AttributeError):
            raise ValidationError("请求编号无效。") from None
        acquire_generation_lock(shared=True)
        acquire_entity_lock("scholar_editor_request", request_id)
        fingerprint = salted_hmac("stl4-scholar-editor", json.dumps({"actor": actor.pk, "method": request.method,
            "path": request.path, "version": request.headers.get("If-Match", ""), "data": request.data},
            cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True), algorithm="sha256").hexdigest()
        old = AuditEvent.objects.filter(pk=request_id).first()
        if old:
            if old.action != ACTION or old.actor_id != actor.pk or old.after.get("fingerprint") != fingerprint:
                raise AuthorityConflict("原请求编号已用于另一项保存。")
            target = ScholarProfile.objects.filter(pk=old.object_id).select_related("person").first()
            if target is None:
                raise AuthorityConflict("原保存已完成，但学者后来已删除。请查回原请求，不要重复创建。")
            return Response({**self._draft_read_rows([target])[0], "save_receipt": command_receipt(actor, request_id), "save_replayed": True})
        response = handler()
        if response.status_code >= 400:
            transaction.set_rollback(True)
            return response
        if not isinstance(response.data, dict) or not response.data.get("id"):
            raise AuthorityConflict("未收到可核对的保存记录，本次保存已回退。")
        AuditEvent.objects.create(pk=request_id, actor=actor, action=ACTION, object_type="catalog.ScholarProfile",
            object_id=str(response.data["id"]), after={"fingerprint": fingerprint, "operation": "create" if creating else "update",
                "saved_version": response.data.get("edit_version", ""), "person_id": str(response.data.get("person_id", ""))})
        response.data["save_receipt"] = command_receipt(actor, request_id)
        return response


class ScholarSaveReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    scholar_id = serializers.UUIDField()
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ScholarSaveReceiptView(PrivateAccountResponses, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ScholarSaveReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(ScholarSaveReceipt(command_receipt(request.user, request_id)).data)
