from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Asset
from catalog.services.document_outline import OutlineConflict
from catalog.services.page_mapping import (
    MappingConflict, apply_mapping, mapping_state, prepare_mapping, revision_payload, save_mapping,
)


class MappingPageSerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField(min_value=1)
    labels = serializers.ListField(child=serializers.CharField(max_length=40), max_length=2, allow_empty=True)
    page_type = serializers.ChoiceField(choices=["front", "body", "appendix", "other", "blank"])
    confirmed = serializers.BooleanField(default=False)
    note = serializers.CharField(max_length=1000, allow_blank=True, default="")
    source_note = serializers.CharField(max_length=240, allow_blank=True, default="")
    override_manual = serializers.BooleanField(default=False)
    source = serializers.ChoiceField(choices=["manual", "pdf_page_labels", "embedded_text", "ocr", "sequence", "file_index", "unknown"], required=False)
    confidence = serializers.FloatField(min_value=0, max_value=1, required=False)


class MappingSegmentSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=120)
    start = serializers.IntegerField(min_value=1)
    end = serializers.IntegerField(min_value=1)
    start_label = serializers.CharField(max_length=40, allow_blank=True)
    style = serializers.ChoiceField(choices=["arabic", "roman_lower", "roman_upper", "custom", "none"])


class MappingMissingSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["mark", "blank"], default="mark")
    id = serializers.CharField(max_length=80)
    label = serializers.CharField(max_length=40)
    after_pdf_page = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=1000, allow_blank=True, default="")
    confirmed = serializers.BooleanField(default=False)


class MappingDataSerializer(serializers.Serializer):
    pages = MappingPageSerializer(many=True, max_length=20000)
    segments = MappingSegmentSerializer(many=True, max_length=500)
    missing = MappingMissingSerializer(many=True, max_length=1000)


class MappingCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["save", "analyze", "segment", "restore", "prepare", "publish", "export"])
    request_id = serializers.UUIDField(required=False)
    expected_revision = serializers.IntegerField(min_value=0)
    source_fingerprint = serializers.CharField(min_length=64, max_length=64)
    data = MappingDataSerializer(required=False)
    segment = MappingSegmentSerializer(required=False)
    revision_id = serializers.UUIDField(required=False)
    prepared_fingerprint = serializers.CharField(min_length=64, max_length=64, required=False)

    def validate(self, attrs):
        action = attrs["action"]
        required = [] if action == "prepare" else ["request_id"]
        required += {"save": ["data"], "segment": ["segment"], "restore": ["revision_id"],
                     "prepare": ["revision_id"], "export": ["revision_id"], "publish": ["revision_id", "prepared_fingerprint"]}.get(action, [])
        for key in required:
            if key not in attrs:
                raise serializers.ValidationError({key: "此操作需要该字段。"})
        return attrs


class MappingDuplicateSerializer(serializers.Serializer):
    label = serializers.CharField()
    pdf_pages = serializers.ListField(child=serializers.IntegerField())
    acknowledged = serializers.BooleanField()


class MappingDiagnosticsSerializer(serializers.Serializer):
    unconfirmed_pages = serializers.ListField(child=serializers.IntegerField())
    duplicate_labels = MappingDuplicateSerializer(many=True)
    spreads = serializers.ListField(child=serializers.IntegerField())
    unconfirmed_missing = serializers.ListField(child=serializers.CharField())
    missing_present = serializers.ListField(child=serializers.CharField())


class MappingPublicationSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    status = serializers.CharField()
    revision_id = serializers.UUIDField()
    revision_status = serializers.CharField()
    error = serializers.CharField(allow_blank=True)


class MappingRevisionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    origin = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by_id = serializers.IntegerField(allow_null=True)
    restored_from_id = serializers.UUIDField(allow_null=True)
    source_fingerprint = serializers.CharField()
    applied_at = serializers.DateTimeField(allow_null=True)
    applied_asset_id = serializers.UUIDField(allow_null=True)
    publication = MappingPublicationSerializer(allow_null=True)
    data = MappingDataSerializer(required=False)
    diagnostics = MappingDiagnosticsSerializer(required=False)


class MappingAssetSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    edition_label = serializers.CharField(allow_blank=True)
    publication_year = serializers.IntegerField(allow_null=True)
    document_type = serializers.CharField()
    byte_size = serializers.IntegerField()
    page_count = serializers.IntegerField()
    sha256 = serializers.CharField()
    status = serializers.CharField()
    validation_status = serializers.CharField()
    is_current = serializers.BooleanField()
    source_current = serializers.BooleanField()
    source_error = serializers.CharField(allow_blank=True)
    original_filename = serializers.CharField(allow_blank=True)
    document_revision_id = serializers.CharField(allow_blank=True)
    preview_url = serializers.CharField(allow_blank=True)
    reader_url = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    publication_state = serializers.CharField()


class MappingPrecedingRevisionSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    revision_id = serializers.UUIDField()
    revision = serializers.IntegerField()


class MappingCopyJobSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    progress = serializers.IntegerField()
    updated_at = serializers.DateTimeField()
    error = serializers.CharField(allow_blank=True)
    mapping_revision_id = serializers.CharField()
    download_url = serializers.CharField(allow_blank=True)


class MappingStateSerializer(serializers.Serializer):
    jobs = MappingCopyJobSerializer(many=True)
    asset = MappingAssetSerializer()
    asset_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField()
    source_fingerprint = serializers.CharField()
    current = MappingDataSerializer()
    latest = MappingRevisionSerializer(allow_null=True)
    history = MappingRevisionSerializer(many=True)
    history_count = serializers.IntegerField()
    history_page = serializers.IntegerField()
    history_next_page = serializers.IntegerField(allow_null=True)
    preceding_revision = MappingPrecedingRevisionSerializer(allow_null=True)
    result = MappingRevisionSerializer(required=False)


class MappingChangeSerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField()
    before = serializers.ListField(child=serializers.CharField())
    after = serializers.ListField(child=serializers.CharField())
    page_type_before = serializers.CharField()
    page_type_after = serializers.CharField()
    note = serializers.CharField(allow_blank=True)
    source_note_before = serializers.CharField(allow_blank=True)
    source_note_after = serializers.CharField(allow_blank=True)
    manual_before = serializers.BooleanField()


class MappingPreviewSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    source_fingerprint = serializers.CharField()
    prepared_fingerprint = serializers.CharField()
    changes = MappingChangeSerializer(many=True)
    changed_page_count = serializers.IntegerField()
    missing_before = MappingMissingSerializer(many=True)
    missing_after = MappingMissingSerializer(many=True)
    segments_before = MappingSegmentSerializer(many=True)
    segments_after = MappingSegmentSerializer(many=True)
    diagnostics = MappingDiagnosticsSerializer()
    blockers = serializers.ListField(child=serializers.CharField())
    can_apply = serializers.BooleanField()
    mode = serializers.ChoiceField(choices=["publish", "apply_draft"])


class AdminPageMappingWorkspaceView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OpenApiParameter("revision_id", OpenApiTypes.UUID), OpenApiParameter("history_page", OpenApiTypes.INT)],
        responses=PolymorphicProxySerializer(component_name="MappingReadResponse",
            serializers=[MappingStateSerializer, MappingRevisionSerializer], resource_type_field_name=None))
    def get(self, request, asset_id):
        asset = get_object_or_404(Asset.objects.select_related("edition__work"), pk=asset_id, kind="normalized")
        try:
            if request.query_params.get("revision_id"):
                revision = get_object_or_404(asset.page_mapping_revisions.select_related("publication_event__catalog_revision"),
                    pk=UUID(request.query_params["revision_id"]))
                return Response(revision_payload(revision))
            return Response(mapping_state(asset, history_page=int(request.query_params.get("history_page", 1))))
        except (ValueError, TypeError):
            return Response({"detail": "修订标识或历史页码无效。"}, status=400)

    @extend_schema(request=MappingCommandSerializer, responses={
        200: PolymorphicProxySerializer(component_name="MappingCommandResponse", serializers=[MappingStateSerializer, MappingPreviewSerializer], resource_type_field_name=None),
        202: MappingStateSerializer})
    def post(self, request, asset_id):
        command = MappingCommandSerializer(data=request.data)
        command.is_valid(raise_exception=True)
        data = command.validated_data
        capability = Capability.PUBLISH_WORK if data["action"] == "publish" else Capability.EDIT_METADATA
        if not has_capability(request.user, capability):
            return Response({"detail": "当前账户没有执行此页码操作的权限。"}, status=403)
        asset = get_object_or_404(Asset.objects.select_related("edition__work"), pk=asset_id, kind="normalized")
        try:
            if data["action"] == "export":
                if not has_capability(request.user, Capability.RETRY_JOBS) or not has_capability(request.user, Capability.VIEW_EVIDENCE):
                    return Response({"detail": "生成副本需要文件查看及任务操作权限。"}, status=403)
                from catalog.services.page_mapping_exports import queue_export
                queue_export(asset.pk, data=data, actor=request.user)
                return Response(mapping_state(asset), status=202)
            if data["action"] == "prepare":
                from catalog.services.page_mapping import _guard
                _guard(asset, data)
                row = get_object_or_404(asset.page_mapping_revisions, pk=data["revision_id"])
                return Response(prepare_mapping(asset, row))
            row = (apply_mapping if data["action"] == "publish" else save_mapping)(asset.pk, data=data, actor=request.user)
            asset.refresh_from_db()
            result = mapping_state(asset)
            result["result"] = revision_payload(row)
            return Response(result, status=202 if row.publication_event_id and row.publication_event.status in {"pending", "processing"} else 200)
        except (MappingConflict, OutlineConflict) as exc:
            return Response({"detail": str(exc), "code": "page_mapping_conflict"}, status=409)
        except (ValueError, TypeError) as exc:
            return Response({"detail": str(exc)}, status=400)
