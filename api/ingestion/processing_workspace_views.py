from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from ingestion.models import AuditEvent, ProcessingJob, UploadBatch
from ingestion.services.processing_center import processing_task_page
from ingestion.services.processing_commands import (ACTION, ProcessingCommandSerializer, command_actor, command_receipt, run_processing_command)
from ingestion.services.processing_creation import ProcessingCreationSerializer, create_processing_task
from ingestion.views import ProcessingCenterView
from ingestion.ocr_workspace_views import OCRTaskOptionsSerializer


class ProcessingFileSerializer(serializers.Serializer):
    filename = serializers.CharField(allow_blank=True)
    pages = serializers.IntegerField(allow_null=True)
    bytes = serializers.IntegerField(allow_null=True)
    is_current = serializers.BooleanField(allow_null=True)


class ProcessingOCRProgressSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    phase = serializers.CharField(allow_blank=True)
    phase_label = serializers.CharField()
    completed_pages = serializers.IntegerField(allow_null=True)
    total_pages = serializers.IntegerField(allow_null=True)
    percent = serializers.FloatField(allow_null=True)
    active_pages = serializers.ListField(child=serializers.IntegerField())
    updated_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    heartbeat_at = serializers.DateTimeField(allow_null=True)
    phase_elapsed_seconds = serializers.IntegerField()
    stale = serializers.BooleanField()
    worker_alive = serializers.BooleanField()
    service_activity = serializers.CharField()
    error = serializers.CharField(allow_blank=True)
    warnings = serializers.ListField(child=serializers.CharField())
    source_asset_id = serializers.CharField(allow_blank=True)
    result_asset_id = serializers.CharField(allow_blank=True)
    public_result = serializers.CharField()
    workbench_url = serializers.CharField(allow_blank=True)
    can_pause = serializers.BooleanField()
    can_resume = serializers.BooleanField()
    can_cancel = serializers.BooleanField()
    resume_reason = serializers.CharField(allow_blank=True)
    task_options = OCRTaskOptionsSerializer(allow_null=True, required=False)
    protected_page_indexes = serializers.ListField(child=serializers.IntegerField(), required=False)
    reviewed_page_indexes = serializers.ListField(child=serializers.IntegerField(), required=False)


class ProcessingFailureLocationSerializer(serializers.Serializer):
    pdf_page = serializers.IntegerField(allow_null=True)
    start_offset = serializers.IntegerField(allow_null=True)
    end_offset = serializers.IntegerField(allow_null=True)


class ProcessingRecoverySerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=["inactive", "unsupported", "waiting_sources", "recoverable", "delayed", "waiting", "active"])
    last_activity_at = serializers.DateTimeField(allow_null=True)
    activity_kind = serializers.ChoiceField(choices=["none", "checkpoint", "heartbeat", "started", "queue"])
    eligible_at = serializers.DateTimeField(allow_null=True)
    can_recover = serializers.BooleanField()
    notice = serializers.CharField()


class ProcessingRetrySelectionSerializer(serializers.Serializer):
    state = serializers.ChoiceField(choices=["active", "completed", "continued"], allow_blank=True)
    pages = serializers.ListField(child=serializers.IntegerField())
    count = serializers.IntegerField()


class ProcessingFollowupSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    state = serializers.ChoiceField(choices=["waiting", "running", "completed", "skipped", "disabled", "failed", "unrecorded"])
    can_configure = serializers.BooleanField()
    result_url = serializers.CharField(allow_blank=True)
    retry_url = serializers.CharField(allow_blank=True)
    retry_status = serializers.CharField(allow_blank=True)
    counts = serializers.DictField(child=serializers.IntegerField())


class ProcessingOutcomeIssueSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()
    message = serializers.CharField()
    url = serializers.CharField(allow_blank=True)


class ProcessingOCRTargetSerializer(serializers.Serializer):
    id = serializers.ChoiceField(choices=["nas", "remote"])
    label = serializers.CharField()
    configured = serializers.BooleanField()
    version = serializers.CharField()
    external = serializers.BooleanField()


class ProcessingOCRTransferSerializer(serializers.Serializer):
    current = serializers.CharField(allow_blank=True)
    current_label = serializers.CharField()
    configuration_changed = serializers.BooleanField()
    can_transfer = serializers.BooleanField()
    targets = ProcessingOCRTargetSerializer(many=True)


class ProcessingWorkspaceTaskSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source = serializers.ChoiceField(choices=["processing_job", "semantic_index_job"])
    title = serializers.CharField()
    title_has_unpublished_changes = serializers.BooleanField()
    edition_label = serializers.CharField()
    edition_id = serializers.UUIDField(allow_null=True)
    work_id = serializers.UUIDField(allow_null=True)
    asset_id = serializers.UUIDField(allow_null=True)
    file_id = serializers.UUIDField(allow_null=True)
    job_type = serializers.CharField()
    status = serializers.CharField()
    partial = serializers.BooleanField()
    progress = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    finished_at = serializers.DateTimeField(allow_null=True)
    heartbeat_at = serializers.DateTimeField(allow_null=True)
    heartbeat_stale = serializers.BooleanField()
    recovery = ProcessingRecoverySerializer()
    retry_selection = ProcessingRetrySelectionSerializer()
    followup = ProcessingFollowupSerializer(allow_null=True)
    transfer = ProcessingOCRTransferSerializer(allow_null=True)
    outcome_issues = ProcessingOutcomeIssueSerializer(many=True)
    pause_requested = serializers.BooleanField()
    last_error = serializers.CharField(allow_blank=True)
    error_code = serializers.CharField(allow_blank=True)
    failure_pages = serializers.ListField(child=serializers.IntegerField())
    failure_page_count = serializers.IntegerField()
    failure_location = ProcessingFailureLocationSerializer(allow_null=True)
    version = serializers.CharField()
    actions = serializers.ListField(child=serializers.ChoiceField(choices=["pause", "resume", "retry", "cancel", "recover", "configure_followup", "retry_followup", "transfer"]))
    permission_reason = serializers.CharField(allow_blank=True)
    retry_url = serializers.CharField(allow_blank=True)
    operation = serializers.CharField(allow_blank=True)
    can_export_results = serializers.BooleanField()
    cover_url = serializers.CharField(allow_blank=True)
    engine = serializers.CharField(allow_blank=True)
    attempt = serializers.IntegerField()
    max_attempts = serializers.IntegerField()
    settings_version = serializers.CharField(allow_blank=True)
    workbench_url = serializers.CharField(allow_blank=True)
    file = ProcessingFileSerializer()
    counts = serializers.DictField(child=serializers.IntegerField())
    ocr_progress = ProcessingOCRProgressSerializer(allow_null=True)
    result_urls = serializers.DictField(child=serializers.CharField(allow_blank=True))


class ProcessingTaskTypeSerializer(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class ProcessingLogSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    status = serializers.CharField(allow_blank=True)


class ProcessingWorkspaceFileSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    edition_label = serializers.CharField()
    filename = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    submitted_at = serializers.DateTimeField()
    has_file = serializers.BooleanField()
    stages = ProcessingWorkspaceTaskSerializer(many=True)
    stage_count = serializers.IntegerField()


class ProcessingWorkspaceSerializer(serializers.Serializer):
    results = ProcessingWorkspaceTaskSerializer(many=True)
    files = ProcessingWorkspaceFileSerializer(many=True, required=False)
    group_by = serializers.ChoiceField(choices=["file", "task"], required=False)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    page_size = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    total_counts = serializers.DictField(child=serializers.IntegerField())
    total = serializers.IntegerField()
    can_manage = serializers.BooleanField()
    job_types = ProcessingTaskTypeSerializer(many=True)
    checked_at = serializers.DateTimeField()
    logs = ProcessingLogSerializer(many=True)
    batch_id = serializers.UUIDField(allow_null=True)
    batch_label = serializers.CharField(allow_blank=True)


class ProcessingReceiptSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    request_id = serializers.UUIDField()
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    job_id = serializers.UUIDField(allow_null=True)
    source = serializers.CharField(allow_blank=True)
    action = serializers.CharField(allow_blank=True)
    next_url = serializers.CharField(allow_blank=True)
    result = serializers.JSONField()


class ProcessingStopSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class ProcessingWorkspaceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(parameters=[OpenApiParameter(name, type=str) for name in ("q", "job_type", "status", "edition_id", "work_id", "file_id", "batch_id", "group_by", "task_id", "task_source", "date_from", "date_to", "page")], responses=ProcessingWorkspaceSerializer)
    def get(self, request):
        if not has_capability(request.user, Capability.VIEW_SYSTEM_STATUS):
            raise PermissionDenied("当前账户不能查看完整处理队列，请从材料页查看所属版本的处理记录。")
        params = request.query_params.copy(); params["workspace"] = "1"; params["page_size"] = "20"
        batch = None
        if params.get("batch_id"):
            identifier = serializers.UUIDField().run_validation(params["batch_id"])
            # The upload workspace is owner-bound even for administrators.
            batch = get_object_or_404(UploadBatch.objects.only("id", "label"), pk=identifier, created_by=request.user)
        if params.get("group_by") not in {None, "file", "task"}: raise ValidationError({"group_by": "请选择文件阶段或任务历史。"})
        if params.get("group_by") == "file" and not params.get("task_id"):
            from ingestion.services.processing_files import processing_file_page
            payload = processing_file_page(params, request.user)
        else:
            payload = processing_task_page(params, request.user)
            payload.update(group_by="task", files=[])
        logs = []
        if params.get("task_id") and payload["results"]:
            for row in AuditEvent.objects.filter(object_id=params["task_id"], object_type__in=["ProcessingJob", "processing_job", "SemanticIndexJob", "semantic_index_job"]).order_by("-created_at", "pk")[:100]:
                # No raw payloads, prompts, exception traces or reader content.
                logs.append({"id": str(row.pk), "at": row.created_at, "action": row.action,
                             "status": (row.after or {}).get("status") or ((row.after or {}).get("result") or {}).get("status") or ""})
        payload.update(job_types=[{"value": value, "label": label} for value, label in ProcessingJob.JobType.choices], checked_at=timezone.now(), logs=logs,
                       batch_id=str(batch.pk) if batch else None, batch_label=batch.label if batch else "")
        return Response(payload)

    @extend_schema(request=PolymorphicProxySerializer(component_name="ProcessingWorkspaceCommand", serializers=[ProcessingCommandSerializer, ProcessingCreationSerializer], resource_type_field_name=None), responses={200: ProcessingReceiptSerializer, 202: ProcessingReceiptSerializer})
    def post(self, request):
        if request.data.get("action") == "create":
            return Response(create_processing_task(request))
        serializer = ProcessingCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        return run_processing_command(request, lambda: ProcessingCenterView()._perform_action(request))


class ProcessingSourceFileSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    filename = serializers.CharField()
    version = serializers.IntegerField()
    page_count = serializers.IntegerField()
    source_version = serializers.CharField()
    can_run = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)


class ProcessingSourceSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    title = serializers.CharField()
    edition_label = serializers.CharField()
    can_run = serializers.BooleanField()
    denied_reason = serializers.CharField(allow_blank=True)
    paused = serializers.BooleanField()
    provider_label = serializers.CharField()
    files = ProcessingSourceFileSerializer(many=True)
    active_job_id = serializers.CharField(allow_blank=True)


class ProcessingSourceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=ProcessingSourceSerializer)
    def get(self, request, edition_id):
        from ingestion.services.catalog_ocr import edition_for, ocr_context
        if not has_capability(request.user, Capability.VIEW_SYSTEM_STATUS):
            raise PermissionDenied("当前账户不能查看处理任务，请从材料页核对文件。")
        return Response(ProcessingSourceSerializer(ocr_context(edition_for(edition_id), request.user)).data)


class ProcessingReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=ProcessingReceiptSerializer)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk) or not has_capability(request.user, Capability.RETRY_JOBS):
            raise PermissionDenied("请使用当前任务管理账户查回原操作。")
        return Response(command_receipt(get_object_or_404(AuditEvent, actor=request.user, action=ACTION, request_id=str(request_id))))

    @extend_schema(request=ProcessingStopSerializer, responses=ProcessingReceiptSerializer)
    @transaction.atomic
    def post(self, request, request_id):
        actor = command_actor(request)
        if request.headers.get("X-Editor-Owner") != str(actor.pk): raise PermissionDenied("登录账户已变化。")
        serializer = ProcessingStopSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        if set(request.data) != {"action"}: raise ValidationError("仅能停止原待定请求。")
        row = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(request_id)).first()
        if not row: row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="processing_command", object_id="", request_id=str(request_id), after={"cancelled": True})
        return Response(command_receipt(row))
