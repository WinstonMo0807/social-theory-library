from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from common.permissions import CanEditMetadata
from ingestion.models import AuditEvent


class WorkspaceReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_at = serializers.DateTimeField()


class WorkspaceCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])
    edition_id = serializers.UUIDField()


def actor_for(request, lock=False):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk): raise PermissionDenied("登录账户已变化，请重新打开编辑页。")
    if not lock: return request.user
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.EDIT_METADATA): raise PermissionDenied("当前会话不能处理原请求。")
    return actor


def receipt(row):
    return {"owner_id": str(row.actor_id), "work_id": row.after["work_id"], "edition_id": row.object_id,
            "request_id": row.request_id, "state": "cancelled" if row.after.get("cancelled") else "applied", "saved_at": row.created_at}


class WorkWorkspaceReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=WorkspaceReceiptSerializer)
    def get(self, request, work_id, request_id):
        actor = actor_for(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action="workspace.edits.saved", after__work_id=str(work_id), request_id=str(request_id))))

    @extend_schema(request=WorkspaceCancelSerializer, responses=WorkspaceReceiptSerializer)
    @transaction.atomic
    def post(self, request, work_id, request_id):
        actor = actor_for(request, True)
        data = WorkspaceCancelSerializer(data=request.data); data.is_valid(raise_exception=True)
        if set(request.data) != {"action", "edition_id"}: raise ValidationError("仅接受停止原待定请求。")
        edition = get_object_or_404(Edition, pk=data.validated_data["edition_id"], work_id=work_id)
        row = AuditEvent.objects.filter(actor=actor, action="workspace.edits.saved", request_id=str(request_id)).first()
        if row and (row.after.get("work_id") != str(work_id) or row.object_id != str(edition.pk)): raise EditConflict("原请求不属于当前出版版本。")
        if not row: row = AuditEvent.objects.create(actor=actor, action="workspace.edits.saved", object_type="edition", object_id=str(edition.pk), request_id=str(request_id), after={"work_id": str(work_id), "cancelled": True})
        return Response(receipt(row))
