"""Owner-bound intake directory and recoverable batch reservations.

Files still use the existing local chunk or R2 staging service. This module
does not copy files, start processing jobs, or publish catalog records.
"""
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.crypto import salted_hmac
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.editorial_issues import EditConflict
from common.permissions import CanUpload
from ingestion.models import AuditEvent, UploadBatch
from ingestion.serializers import UploadBatchCreateSerializer, UploadBatchSerializer, UploadItemSerializer

MAX_BATCH_FILES = 50


def owned_batches(actor):
    return UploadBatch.objects.filter(created_by=actor).order_by("-created_at", "-pk")


def batch_summary(batch):
    return {"id": str(batch.pk), "label": batch.label, "expected_count": batch.expected_count,
            "completed_count": batch.completed_count, "failed_count": batch.failed_count, "status": batch.status,
            "version": batch.updated_at.isoformat(), "created_at": batch.created_at}


class UploadBatchSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField(allow_blank=True)
    expected_count = serializers.IntegerField()
    completed_count = serializers.IntegerField()
    failed_count = serializers.IntegerField()
    status = serializers.CharField()
    version = serializers.CharField()
    created_at = serializers.DateTimeField()


class UploadWorkspaceItemSerializer(UploadItemSerializer):
    """The upload table needs a summary, not every catalog edit/history panel."""
    class Meta(UploadItemSerializer.Meta):
        fields = ("id", "source_filename", "byte_size", "status", "stage_progress", "error_code", "error_message",
                  "dispatch_status", "dispatch_task_id", "dispatch_attempts", "recognized_metadata", "preflight_summary",
                  "edition", "metadata_candidates", "review_data", "can_manage_publication", "is_stalled", "suggested_action", "staging", "updated_at")

    def get_review_data(self, obj) -> dict | None:
        if not obj.edition_id:
            return None
        from catalog.services.publication_commands import catalog_publication_state
        edition = obj.edition
        authors = [link.person.preferred_name for link in edition.contributions.all() if link.role == "author"]
        return {"title": edition.work.title, "document_type": edition.work.document_type, "language": edition.work.language,
                "authors": authors, "publication_year": edition.publication_year, "publisher": edition.publisher,
                "publication_place": edition.publication_place, "publication": catalog_publication_state(edition),
                "review_progress": edition.review_progress, "ocr_status": edition.ocr_status, "semantic_index_status": edition.semantic_index_status}


class UploadWorkspaceBatchSerializer(UploadBatchSerializer):
    items = UploadWorkspaceItemSerializer(many=True, read_only=True)


class UploadWorkspaceSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    transport = serializers.ChoiceField(choices=["local", "r2"])
    max_files = serializers.IntegerField()
    max_file_bytes = serializers.IntegerField()
    chunk_bytes = serializers.IntegerField()
    recent = UploadBatchSummarySerializer(many=True)
    batch = UploadWorkspaceBatchSerializer(allow_null=True)
    version = serializers.CharField(allow_blank=True)


class UploadWorkspaceQuerySerializer(serializers.Serializer):
    batch = serializers.UUIDField(required=False)


class UploadBatchCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["reserve", "rename"])
    request_id = serializers.UUIDField()
    batch_id = serializers.UUIDField(required=False)
    expected_version = serializers.CharField(required=False)
    policy = UploadBatchCreateSerializer(required=False)
    label = serializers.CharField(max_length=240, required=False, allow_blank=True)


class UploadBatchReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    batch = UploadBatchSummarySerializer(allow_null=True)


def owner(request, *, lock=False):
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("上传账户已变化，请重新读取当前上传工作区。")
    if not lock:
        return request.user
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version:
        raise PermissionDenied("登录会话已变化，不能继续原上传操作。")
    from common.capabilities import Capability, has_capability
    if not has_capability(actor, Capability.UPLOAD):
        raise PermissionDenied("当前账户没有上传权限。")
    return actor


def receipt_payload(event):
    batch_id = event.after.get("batch_id")
    batch = UploadBatch.objects.filter(pk=batch_id, created_by=event.actor).first() if batch_id else None
    return {"owner_id": str(event.actor_id), "request_id": event.request_id,
            "state": "cancelled" if event.after.get("cancelled") else "applied", "batch": batch_summary(batch) if batch else None}


class UploadWorkspaceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanUpload]

    @extend_schema(parameters=[UploadWorkspaceQuerySerializer], responses=UploadWorkspaceSerializer)
    def get(self, request):
        actor = owner(request)
        query = UploadWorkspaceQuerySerializer(data=request.query_params); query.is_valid(raise_exception=True)
        rows = owned_batches(actor)
        batch = get_object_or_404(rows.prefetch_related("items__edition__work", "items__metadata_candidates", "items__edition__contributions__person"), pk=query.validated_data["batch"]) if query.validated_data.get("batch") else None
        from ingestion.services.r2_staging import _configured
        return Response({"owner_id": str(actor.pk), "transport": "r2" if _configured() else "local",
                         "max_files": MAX_BATCH_FILES, "max_file_bytes": min(settings.MAX_UPLOAD_BYTES, 200 * 1024 * 1024),
                         "chunk_bytes": min(settings.MAX_UPLOAD_CHUNK_BYTES, 2 * 1024 * 1024),
                         "recent": [batch_summary(row) for row in rows[:10]],
                         "batch": UploadWorkspaceBatchSerializer(batch, context={"request": request}).data if batch else None,
                         "version": batch.updated_at.isoformat() if batch else ""})

    @extend_schema(request=UploadBatchCommandSerializer, responses=UploadBatchReceiptSerializer)
    @transaction.atomic
    def post(self, request):
        actor = owner(request, lock=True)
        incoming = UploadBatchCommandSerializer(data=request.data); incoming.is_valid(raise_exception=True)
        data = incoming.validated_data
        if set(request.data) - {"action", "request_id", "batch_id", "expected_version", "policy", "label"}:
            raise ValidationError("上传批次请求包含未知字段。")
        request_id = str(data["request_id"])
        fingerprint = salted_hmac("upload-reservation", json.dumps(request.data, sort_keys=True, ensure_ascii=False)).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action="upload_workspace.command", request_id=request_id).first()
        if prior:
            if prior.after.get("cancelled"):
                raise EditConflict("原批次请求已停止，请重新读取后再操作。")
            if prior.after.get("fingerprint") != fingerprint:
                raise EditConflict("原请求编号不能用于不同的批次操作。")
            return Response(receipt_payload(prior))
        batch = get_object_or_404(UploadBatch.objects.select_for_update(), pk=data["batch_id"], created_by=actor) if data.get("batch_id") else None
        if batch and data.get("expected_version") != batch.updated_at.isoformat():
            raise EditConflict("批次状态已更新，请重新读取后再修改。")
        if data["action"] == "rename":
            if not batch or "label" not in data:
                raise ValidationError("重命名需指定当前批次和名称。")
            batch.label = data["label"]; batch.save(update_fields=["label", "updated_at"])
        else:
            policy = data.get("policy")
            if not policy:
                raise ValidationError("请选择本批文件数量和处理方式。")
            if batch:
                count = batch.expected_count + policy["expected_count"]
                if count > MAX_BATCH_FILES:
                    raise ValidationError("此批次最多50个文件，请另建批次。")
                for field in ("access_policy", "ocr_strategy", "duplicate_policy", "external_enrichment_enabled", "ai_suggestions_enabled"):
                    if getattr(batch, field) != policy[field]:
                        raise EditConflict("追加文件沿用原批次处理方式，请重新读取原批次。")
                batch.expected_count = count; batch.save(update_fields=["expected_count", "updated_at"])
            else:
                batch = UploadBatch.objects.create(created_by=actor, **policy)
        event = AuditEvent.objects.create(actor=actor, action="upload_workspace.command", object_type="UploadBatch",
            object_id=str(batch.pk), request_id=request_id, after={"batch_id": str(batch.pk), "fingerprint": fingerprint, "operation": data["action"]})
        return Response(receipt_payload(event))


class UploadReceiptCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class UploadBatchReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanUpload]

    @extend_schema(responses=UploadBatchReceiptSerializer)
    def get(self, request, request_id):
        actor = owner(request)
        return Response(receipt_payload(get_object_or_404(AuditEvent, actor=actor, action="upload_workspace.command", request_id=str(request_id))))

    @extend_schema(request=UploadReceiptCancelSerializer, responses=UploadBatchReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = owner(request, lock=True)
        if request.data != {"action": "cancel_pending"}:
            raise ValidationError("仅接受停止未执行的原请求。")
        event = AuditEvent.objects.filter(actor=actor, action="upload_workspace.command", request_id=str(request_id)).first()
        if not event:
            event = AuditEvent.objects.create(actor=actor, action="upload_workspace.command", object_type="UploadBatch",
                object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(receipt_payload(event))
