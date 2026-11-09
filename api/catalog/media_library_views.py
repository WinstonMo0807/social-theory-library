"""Source metadata workspace on the existing media library; no publication writes."""
from hashlib import sha256
import json

from django.core.paginator import Paginator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.media_views import MediaAssetSerializer
from catalog.media_workspace_views import MediaRevisionMetadataSerializer, MediaWorkspaceCancelSerializer
from catalog.models import MediaAsset
from catalog.services.editorial_issues import EditConflict
from catalog.services.media import PUBLIC_METADATA_FIELDS, media_reference_inventory, update_media_metadata
from catalog.workspace_receipt_views import actor_for
from common.permissions import CanAccessBackOffice, CanEditMetadata
from ingestion.models import AuditEvent

ACTION = "media.library.command"
FIELDS = (*PUBLIC_METADATA_FIELDS, "focal_x", "focal_y")


class LibraryMediaMetadata(MediaRevisionMetadataSerializer):
    focal_x = serializers.FloatField(min_value=0, max_value=1)
    focal_y = serializers.FloatField(min_value=0, max_value=1)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) != set(FIELDS):
            raise ValidationError("请完整填写图片来源资料；原文件及图片身份不能修改。")
        return super().to_internal_value(data)


class LibraryMediaCommand(serializers.Serializer):
    request_id = serializers.UUIDField()
    expected_updated_at = serializers.DateTimeField()
    metadata = LibraryMediaMetadata()

    def validate(self, value):
        if set(self.initial_data) != {"request_id", "expected_updated_at", "metadata"}:
            raise ValidationError("仅接受当前图片的来源资料保存。")
        return value


class LibraryMediaReceipt(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    media_id = serializers.UUIDField()
    next_url = serializers.CharField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    updated_at = serializers.DateTimeField(allow_null=True)


class LibraryMediaHistoryRow(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    before = serializers.DictField(child=serializers.JSONField())
    after = serializers.DictField(child=serializers.JSONField())


class LibraryMediaHistory(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = LibraryMediaHistoryRow(many=True)


class LibraryMediaState(serializers.Serializer):
    owner_id = serializers.CharField()
    media = MediaAssetSerializer()
    references = serializers.JSONField()
    history = LibraryMediaHistory()


def receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "media_id": row.object_id,
        "next_url": f"/admin/media?media={row.object_id}",
        "state": "cancelled" if row.after.get("cancelled") else "applied", "updated_at": row.after.get("updated_at")}


class MediaLibraryWorkspaceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(parameters=[OpenApiParameter("history_page", int)], responses=LibraryMediaState)
    def get(self, request, media_id):
        actor = actor_for(request)
        media = get_object_or_404(MediaAsset.objects.prefetch_related("renditions"), pk=media_id)
        history = AuditEvent.objects.filter(action="media.metadata", object_type="MediaAsset", object_id=str(media_id)).order_by("-created_at", "-id")
        paginator = Paginator(history, 12)
        number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("history_page", 1))
        page = paginator.get_page(number)
        return Response({"owner_id": str(actor.pk), "media": MediaAssetSerializer(media).data,
            "references": media_reference_inventory(media_id, actor=actor),
            "history": {"count": paginator.count, "page": page.number, "pages": paginator.num_pages,
                "results": [{"id": str(row.pk), "created_at": row.created_at,
                    "before": {key: value for key, value in (row.before or {}).items() if key in FIELDS},
                    "after": {key: value for key, value in (row.after or {}).items() if key in FIELDS}} for row in page.object_list]}})

    @extend_schema(request=LibraryMediaCommand, responses=LibraryMediaReceipt)
    @transaction.atomic
    def post(self, request, media_id):
        actor = actor_for(request, True)
        serializer = LibraryMediaCommand(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(request.data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        previous = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if previous:
            if previous.object_id != str(media_id) or (not previous.after.get("cancelled") and previous.after.get("signature") != signature):
                raise EditConflict("此请求编号已用于其他图片资料，请先查回原结果。")
            return Response(receipt(previous))
        current = get_object_or_404(MediaAsset.objects.select_for_update(), pk=media_id)
        if current.updated_at != data["expected_updated_at"]:
            raise EditConflict("图片来源资料已经变化，当前填写保留。请重新读取并核对差异。")
        try:
            saved = update_media_metadata(media_id, actor=actor, metadata=data["metadata"], expected_updated_at=data["expected_updated_at"])
        except (ValueError, DjangoValidationError) as error:
            raise ValidationError(str(error)) from error
        row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="MediaAsset", object_id=str(media_id),
            request_id=str(data["request_id"]), after={"signature": signature, "updated_at": serializers.DateTimeField().to_representation(saved.updated_at)})
        return Response(receipt(row))


class MediaLibraryReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=LibraryMediaReceipt)
    def get(self, request, media_id, request_id):
        actor = actor_for(request)
        return Response(receipt(get_object_or_404(AuditEvent, actor=actor, action=ACTION, object_id=str(media_id), request_id=str(request_id))))

    @extend_schema(request=MediaWorkspaceCancelSerializer, responses=LibraryMediaReceipt)
    @transaction.atomic
    def post(self, request, media_id, request_id):
        actor = actor_for(request, True)
        serializer = MediaWorkspaceCancelSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("只能停止原待定请求。")
        get_object_or_404(MediaAsset, pk=media_id)
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if row and row.object_id != str(media_id): raise EditConflict("原请求不属于当前图片。")
        if not row:
            row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="MediaAsset", object_id=str(media_id), request_id=str(request_id), after={"cancelled": True})
        return Response(receipt(row))
