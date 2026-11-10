"""Original scholar relations, with the existing editor request receipts."""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import ScholarRelation
from catalog.scholar_commands import ScholarCommandMixin, PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.services.shared_curation import relation_payload
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice
from django.db import transaction
from django.shortcuts import get_object_or_404
from accounts.models import User
from ingestion.models import AuditEvent
from catalog.services.person_authority import AuthorityConflict
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock


@transaction.atomic
def submit_relation_command(request, key, data):
    """Preserve cancellation receipts while the result becomes a ChangeSet."""
    from catalog.services.intelligence_changes import uuid_value
    from catalog.services.shared_curation import save_relation
    request_id = uuid_value(data.get("request_id"))
    actor = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("账户会话或编辑权限已变化。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock("scholar_relation_request", request_id)
    old = AuditEvent.objects.filter(pk=request_id).first()
    if old:
        if old.actor_id != actor.pk or old.action != "scholar_relation_command":
            raise AuthorityConflict("请求编号不属于当前账户的此类保存。")
        if old.after.get("operation") == "cancelled":
            raise AuthorityConflict("原保存请求已停止。请读取当前资料后发起新操作。")
        if not old.after.get("changeset_id"):
            raise AuthorityConflict("原请求已完成旧关系保存，请查回原回执后使用新请求编号。")
    # submit_draft checks the complete content fingerprint on every replay.
    changeset = save_relation(key, data, actor)
    if not old:
        AuditEvent.objects.create(pk=request_id, actor=actor, action="scholar_relation_command",
            object_type="catalog.ChangeSet", object_id=str(changeset.pk),
            after={"operation": "draft", "changeset_id": str(changeset.pk), "saved_version": ""})
    return changeset


def relation_receipt(actor, request_id):
    row = get_object_or_404(AuditEvent, pk=request_id, actor=actor, action="scholar_relation_command")
    if row.after.get("changeset_id"):
        from catalog.models import ChangeSet
        return {"actor_id": str(actor.pk), "request_id": str(row.pk), "relation_id": None,
            "changeset_id": row.after["changeset_id"], "state": "draft", "saved_version": "",
            "exists": ChangeSet.objects.filter(pk=row.after["changeset_id"]).exists(), "created_at": row.created_at}
    return command_receipt(actor, request_id, action="scholar_relation_command", model=ScholarRelation, identity="relation_id")


class ScholarRelationCommandMixin(ScholarCommandMixin):
    save_action = "scholar_relation_command"
    save_model = ScholarRelation
    save_identity = "relation_id"
    save_salt = "stl4-scholar-relation"
    save_lock = "scholar_relation_request"
    save_label = "学者关系"
    relation_publish = False

    def _draft_read_rows(self, rows):
        return [relation_payload(row) for row in rows]

    def _lock_editorial_scope(self):
        if self.relation_publish and not has_capability(self.request.user, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("当前账户已无学者关系发布或撤回权限。")

    def relation_command(self, request, handler, *, creating=False):
        if not request.headers.get("Idempotency-Key"):
            raise ValidationError("请使用固定请求编号保存或发布关系，以便查回操作结果。")
        return self._scholar_write(request, handler, creating=creating)


class ScholarRelationReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    relation_id = serializers.UUIDField(allow_null=True)
    changeset_id = serializers.UUIDField(required=False)
    state = serializers.ChoiceField(choices=["applied", "cancelled", "draft"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ScholarRelationReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ScholarRelationReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(ScholarRelationReceipt(relation_receipt(request.user, request_id)).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=ScholarRelationReceipt)
    def post(self, request, request_id):
        stop_pending_save(request, request_id, action="scholar_relation_command", model=ScholarRelation,
            identity="relation_id", lock="scholar_relation_request")
        return Response(ScholarRelationReceipt(relation_receipt(request.user, request_id)).data)
