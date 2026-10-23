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


def command_receipt(actor, request_id, *, action=ACTION, model=ScholarProfile, identity="scholar_id"):
    row = get_object_or_404(AuditEvent, pk=request_id, actor=actor, action=action)
    return {"actor_id": str(actor.pk), "request_id": str(row.pk), identity: row.object_id or None,
        "state": "cancelled" if row.after.get("operation") == "cancelled" else "applied",
        "saved_version": row.after.get("saved_version", ""), "exists": bool(row.object_id) and model.objects.filter(pk=row.object_id).exists(),
        "created_at": row.created_at}


@transaction.atomic
def stop_pending_save(request, request_id, *, action=ACTION, model=ScholarProfile, identity="scholar_id", lock="scholar_editor_request"):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("请重新核对当前编辑账户。")
    if not isinstance(request.data, dict) or request.data != {"action": "cancel_pending"}:
        raise ValidationError("只接受停止未确认的保存。")
    actor = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("账户会话或编辑权限已变化。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock(lock, request_id)
    old = AuditEvent.objects.filter(pk=request_id).first()
    if old:
        if old.action != action or old.actor_id != actor.pk:
            raise AuthorityConflict("请求编号不属于当前账户的此类保存。")
    else:
        # Same actor/request lock as saving: a late request observes this stop
        # marker; a completed request returns its original outcome unchanged.
        AuditEvent.objects.create(pk=request_id, actor=actor, action=action, object_type=model._meta.label,
            object_id="", after={"operation": "cancelled", "fingerprint": "", "saved_version": ""})
    return command_receipt(actor, request_id, action=action, model=model, identity=identity)


class ScholarCommandMixin:
    save_action = ACTION
    save_model = ScholarProfile
    save_identity = "scholar_id"
    save_salt = "stl4-scholar-editor"
    save_lock = "scholar_editor_request"
    save_label = "学者"

    def _save_receipt(self, actor, request_id):
        return command_receipt(actor, request_id, action=self.save_action, model=self.save_model, identity=self.save_identity)

    def _lock_editorial_scope(self):
        pass

    def create(self, request, *args, **kwargs):
        inherited = super().create
        return self._scholar_write(request, lambda: inherited(request, *args, **kwargs), creating=True)

    def _guarded_edit(self, handler, request, *args, **kwargs):
        inherited = super()._guarded_edit
        return self._scholar_write(request, lambda: inherited(handler, request, *args, **kwargs))

    @transaction.atomic
    def _scholar_write(self, request, handler, *, creating=False):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied(f"编辑账户已变化，请重新读取{self.save_label}资料。")
        original = request.user
        actor = get_object_or_404(User.objects.select_for_update(), pk=original.pk, is_active=True)
        if actor.token_version != original.token_version or not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
            raise PermissionDenied("账户会话或编辑权限已变化，请重新登录。")
        if creating and not has_capability(actor, Capability.CREATE_AUTHORITY):
            raise PermissionDenied(f"当前账户不能创建{self.save_label}档案。")
        request.user = actor
        self._lock_editorial_scope()
        if request.method == "DELETE":
            # Recycle keeps its existing recovery record; a save key cannot reinterpret it.
            return handler()
        key = request.headers.get("Idempotency-Key", "")
        if not key:
            if creating:
                raise ValidationError(f"新建{self.save_label}需要固定请求编号，请重新打开编辑页。")
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
        acquire_entity_lock(self.save_lock, request_id)
        fingerprint = salted_hmac(self.save_salt, json.dumps({"actor": actor.pk, "method": request.method,
            "path": request.path, "version": request.headers.get("If-Match", ""), "data": request.data},
            cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True), algorithm="sha256").hexdigest()
        old = AuditEvent.objects.filter(pk=request_id).first()
        if old:
            if old.action == self.save_action and old.actor_id == actor.pk and old.after.get("operation") == "cancelled":
                raise AuthorityConflict("原保存请求已停止。请读取当前资料后发起新操作。")
            if old.action != self.save_action or old.actor_id != actor.pk or old.after.get("fingerprint") != fingerprint:
                raise AuthorityConflict("原请求编号已用于另一项保存。")
            targets = self.save_model.objects.filter(pk=old.object_id)
            target = (targets.select_related("person") if self.save_model is ScholarProfile else targets).first()
            if target is None:
                raise AuthorityConflict(f"原保存已完成，但{self.save_label}后来已删除。请查回原请求，不要重复创建。")
            return Response({**self._draft_read_rows([target])[0], "save_receipt": self._save_receipt(actor, request_id), "save_replayed": True})
        response = handler()
        if response.status_code >= 400:
            transaction.set_rollback(True)
            return response
        if not isinstance(response.data, dict) or not response.data.get("id"):
            raise AuthorityConflict("未收到可核对的保存记录，本次保存已回退。")
        AuditEvent.objects.create(pk=request_id, actor=actor, action=self.save_action, object_type=self.save_model._meta.label,
            object_id=str(response.data["id"]), after={"fingerprint": fingerprint, "operation": "create" if creating else "update",
                "saved_version": response.data.get("edit_version", ""), "person_id": str(response.data.get("person_id", ""))})
        response.data["save_receipt"] = self._save_receipt(actor, request_id)
        return response


class ScholarSaveReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    scholar_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class PendingSaveStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class ScholarSaveReceiptView(PrivateAccountResponses, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ScholarSaveReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(ScholarSaveReceipt(command_receipt(request.user, request_id)).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=ScholarSaveReceipt)
    def post(self, request, request_id):
        return Response(ScholarSaveReceipt(stop_pending_save(request, request_id)).data)
