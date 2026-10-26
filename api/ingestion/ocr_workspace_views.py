from django.shortcuts import get_object_or_404
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Asset, PageTextRevision
from catalog.page_mapping_views import MappingAssetSerializer
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice
from ingestion.models import ProcessingJob
from ingestion.services.ocr_workspace import (
    OCRWorkspaceConflict, apply_correction, fingerprint, prepare_correction, revision_payload,
    review_pages, save_correction, task_command, workspace_state,
)


class OCRQuerySerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField(min_value=1, default=1)
    list_page = serializers.IntegerField(min_value=1, default=1)
    history_page = serializers.IntegerField(min_value=1, default=1)
    status = serializers.ChoiceField(choices=["all", "issues", "failed", "unread", "needs_review", "completed", "manual", "reviewed"], default="all")
    quality_threshold = serializers.FloatField(min_value=0, max_value=1, default=.75)
    detect_spreads = serializers.BooleanField(default=True)
    detect_garbled = serializers.BooleanField(default=True)


class OCRTaskOptionsSerializer(serializers.Serializer):
    languages = serializers.ListField(child=serializers.ChoiceField(choices=["ch", "en", "chinese_cht"]), min_length=1, max_length=3)
    layout = serializers.BooleanField()
    quality_threshold = serializers.FloatField(min_value=0, max_value=1)
    detect_spreads = serializers.BooleanField()
    detect_garbled = serializers.BooleanField()
    skip_reviewed = serializers.BooleanField()


class OCRReviewPageSerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField(min_value=1)
    source_fingerprint = serializers.CharField(min_length=64, max_length=64)


class OCRCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["save", "prepare", "apply", "start", "pause", "resume", "cancel", "review"])
    request_id = serializers.UUIDField(required=False)
    pdf_page = serializers.IntegerField(min_value=1, required=False)
    expected_revision = serializers.IntegerField(min_value=0, required=False)
    source_fingerprint = serializers.CharField(min_length=64, max_length=64, required=False)
    text = serializers.CharField(max_length=200000, allow_blank=True, trim_whitespace=False, required=False)
    note = serializers.CharField(max_length=2000, allow_blank=True, default="")
    confirmed = serializers.BooleanField(required=False)
    revision_id = serializers.UUIDField(required=False)
    prepared_fingerprint = serializers.CharField(min_length=64, max_length=64, required=False)
    page_indexes = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=20000, allow_empty=False, required=False)
    source_version = serializers.CharField(required=False)
    job_id = serializers.UUIDField(required=False)
    job_version = serializers.CharField(required=False)
    task_options = OCRTaskOptionsSerializer(required=False)
    pages = OCRReviewPageSerializer(many=True, min_length=1, max_length=200, required=False)

    def validate(self, attrs):
        action = attrs["action"]
        required = [] if action == "prepare" else ["request_id"]
        if action in {"save", "prepare", "apply"}:
            required += ["pdf_page", "expected_revision", "source_fingerprint"]
        required += {"save": ["text", "confirmed"], "prepare": ["revision_id"],
                     "apply": ["revision_id", "prepared_fingerprint"], "start": ["source_version", "confirmed"],
                     "pause": ["job_id", "job_version"], "resume": ["job_id", "job_version"], "cancel": ["job_id", "job_version"],
                     "review": ["pages", "expected_revision", "confirmed"]}[action]
        for key in required:
            if key not in attrs:
                raise serializers.ValidationError({key: "此操作需要该字段。"})
        return attrs


class OCRCorrectionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    pdf_page = serializers.IntegerField()
    text = serializers.CharField(allow_blank=True)
    original_text = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    confirmed = serializers.BooleanField()
    review_only = serializers.BooleanField()
    source_fingerprint = serializers.CharField()
    created_at = serializers.DateTimeField()
    applied_at = serializers.DateTimeField(allow_null=True)
    applied_asset_id = serializers.UUIDField(allow_null=True)
    publication = serializers.DictField(allow_null=True)


class OCRPageSerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField()
    printed_label = serializers.CharField(allow_blank=True)
    text_source = serializers.CharField()
    confidence = serializers.FloatField()
    is_text_manual = serializers.BooleanField()
    char_count = serializers.IntegerField()
    status = serializers.CharField()
    reason = serializers.CharField()
    source_fingerprint = serializers.CharField()
    reviewed = serializers.BooleanField()
    width = serializers.FloatField()
    height = serializers.FloatField()
    replacement_character = serializers.BooleanField()


class OCRQualitySpanSerializer(serializers.Serializer):
    start = serializers.IntegerField(min_value=0, help_text="当前文本中从0开始的Unicode码点偏移。")
    end = serializers.IntegerField(min_value=1, help_text="不含末尾的Unicode码点偏移。")
    reason = serializers.CharField()


class OCRPageDetailSerializer(serializers.Serializer):
    quality_spans = OCRQualitySpanSerializer(many=True, read_only=True)
    original_quality_spans = OCRQualitySpanSerializer(many=True, read_only=True)
    pdf_page = serializers.IntegerField()
    text = serializers.CharField(allow_blank=True)
    original_text = serializers.CharField(allow_blank=True)
    parsed = serializers.BooleanField()
    manual = serializers.BooleanField()
    manual_revision_id = serializers.UUIDField(allow_null=True)
    manual_revision = OCRCorrectionSerializer(allow_null=True)
    latest = OCRCorrectionSerializer(allow_null=True)
    source_fingerprint = serializers.CharField()
    history = OCRCorrectionSerializer(many=True)
    history_count = serializers.IntegerField()
    history_page = serializers.IntegerField()
    history_next_page = serializers.IntegerField(allow_null=True)


class OCRWorkspaceSerializer(serializers.Serializer):
    asset = MappingAssetSerializer()
    source_version = serializers.CharField()
    expected_revision = serializers.IntegerField()
    pages = OCRPageSerializer(many=True)
    count = serializers.IntegerField()
    list_page = serializers.IntegerField()
    next_page = serializers.IntegerField(allow_null=True)
    counts = serializers.DictField(child=serializers.IntegerField())
    parsed_page_count = serializers.IntegerField()
    missing_page_count = serializers.IntegerField()
    detail = OCRPageDetailSerializer()
    jobs = serializers.ListField(child=serializers.DictField())
    active_job_id = serializers.CharField(allow_blank=True)
    paused = serializers.BooleanField()
    can_run = serializers.BooleanField()
    denied_reason = serializers.CharField(allow_blank=True)
    provider_label = serializers.CharField()
    checked_at = serializers.DateTimeField()
    settings = serializers.DictField()
    result = OCRCorrectionSerializer(required=False)


class OCRCorrectionPreviewSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField()
    before = serializers.CharField(allow_blank=True)
    after = serializers.CharField(allow_blank=True)
    blockers = serializers.ListField(child=serializers.CharField())
    can_apply = serializers.BooleanField()
    mode = serializers.ChoiceField(choices=["publish", "apply_draft"])
    notice = serializers.CharField()
    prepared_fingerprint = serializers.CharField()


class OCRWorkspaceView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OCRQuerySerializer], responses=OCRWorkspaceSerializer)
    def get(self, request, asset_id):
        asset = get_object_or_404(Asset.objects.select_related("edition__work", "edition__active_catalog_revision"), pk=asset_id, kind="normalized")
        query = OCRQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        if query.validated_data["pdf_page"] > max(1, asset.page_count):
            return Response({"detail": "所选页超出实际 PDF 页数。"}, status=400)
        return Response(workspace_state(asset, request.user, **query.validated_data))

    @extend_schema(request=OCRCommandSerializer, responses=PolymorphicProxySerializer(
        component_name="OCRWorkspaceCommandResult", serializers=[OCRWorkspaceSerializer, OCRCorrectionPreviewSerializer], resource_type_field_name=None))
    def post(self, request, asset_id):
        serializer = OCRCommandSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        action = data["action"]
        capability = Capability.PUBLISH_WORK if action == "apply" else Capability.EDIT_METADATA if action in {"save", "prepare", "review"} else Capability.RETRY_JOBS
        if not has_capability(request.user, capability):
            return Response({"detail": "当前账户无权执行此操作。"}, status=403)
        asset = get_object_or_404(Asset.objects.select_related("edition__work", "edition__active_catalog_revision"), pk=asset_id, kind="normalized")
        try:
            if action == "prepare":
                # Preparation is read-only; apply repeats all locks and source checks.
                row = get_object_or_404(asset.text_corrections, pk=data["revision_id"], page_index=data["pdf_page"])
                if data["expected_revision"] != (asset.text_corrections.values_list("revision", flat=True).first() or 0):
                    raise OCRWorkspaceConflict("人工候选已有新修订，请刷新后重新查看采用影响。")
                if data["source_fingerprint"] != fingerprint(asset, asset.pages.filter(index=data["pdf_page"]).first()):
                    raise OCRWorkspaceConflict("页面来源已有变化，请保留输入并重新读取。")
                return Response(prepare_correction(asset, row))
            result = save_correction(asset_id, data, request.user) if action == "save" else apply_correction(asset_id, data, request.user) if action == "apply" else None
            if action in {"start", "pause", "resume", "cancel"}:
                task_command(asset_id, data, request.user)
            if action == "review":
                review_pages(asset_id, data, request.user)
            asset.refresh_from_db()
            payload = workspace_state(asset, request.user, pdf_page=data.get("pdf_page", 1))
            if result:
                payload["result"] = revision_payload(result)
            return Response(payload)
        except OCRWorkspaceConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except (ValueError, PageTextRevision.DoesNotExist, ProcessingJob.DoesNotExist) as exc:
            return Response({"detail": str(exc) or "所选修订或任务不存在。"}, status=400)
