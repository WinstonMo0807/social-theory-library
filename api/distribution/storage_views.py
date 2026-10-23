from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanRunBackup, CanViewSystemStatus
from .storage_workspace import storage_snapshot, storage_command, backup_detail


class StorageCommandInput(serializers.Serializer):
    operation = serializers.ChoiceField(choices=["create_backup", "verify_archive", "restore_plan", "close_stalled_verification", "save_schedule", "close_stalled_backup"])
    request_id = serializers.UUIDField()
    include_originals = serializers.BooleanField(required=False)
    retry_from_id = serializers.UUIDField(required=False)
    backup_id = serializers.UUIDField(required=False)
    expected_checksum = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)
    verification_id = serializers.UUIDField(required=False)
    scope = serializers.ChoiceField(choices=["database", "originals"], required=False)
    enabled = serializers.BooleanField(required=False)
    interval_hours = serializers.IntegerField(min_value=6, max_value=720, required=False)
    first_run_at = serializers.DateTimeField(required=False, allow_null=True)
    expected_version = serializers.CharField(max_length=100, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("存储操作包含不支持的字段。")
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["operation"] == "close_stalled_backup":
            if set(attrs) != {"operation", "request_id", "backup_id", "expected_version"}:
                raise serializers.ValidationError("关闭超时备份需明确原任务及当前版本。")
            return attrs
        if attrs["operation"] == "save_schedule":
            required = {"operation", "request_id", "scope", "enabled", "interval_hours", "expected_version"}
            allowed = required | {"first_run_at"}
            if required - set(attrs) or set(attrs) - allowed:
                raise serializers.ValidationError("字段与备份计划操作不匹配。")
            return attrs
        required = {"operation", "request_id"} | ({"include_originals"} if attrs["operation"] == "create_backup" else {"backup_id", "expected_checksum"})
        if attrs["operation"] == "close_stalled_verification":
            required.add("verification_id")
        allowed = required | ({"retry_from_id"} if attrs["operation"] == "create_backup" else set())
        if required - set(attrs) or set(attrs) - allowed:
            raise serializers.ValidationError("字段与本次操作不匹配。")
        return attrs


class BackupVerificationOutput(serializers.Serializer):
    id = serializers.UUIDField()
    backup_id = serializers.UUIDField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    stalled = serializers.BooleanField()
    expected_checksum = serializers.CharField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField()
    error_message = serializers.CharField()
    database_verified = serializers.BooleanField()
    originals_verified = serializers.IntegerField()
    detail = serializers.CharField()
    restore_verified = serializers.BooleanField()


class BackupOutput(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    stalled = serializers.BooleanField()
    version = serializers.CharField()
    include_originals = serializers.BooleanField()
    scope = serializers.CharField()
    archive_name = serializers.CharField()
    location = serializers.CharField()
    archive_bytes = serializers.IntegerField(allow_null=True)
    checksum = serializers.CharField()
    duration_seconds = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    completed_at = serializers.DateTimeField(allow_null=True)
    error_message = serializers.CharField()
    verification = BackupVerificationOutput(allow_null=True)
    restore_status = serializers.CharField()


class BackupPage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = BackupOutput(many=True)


class StorageLocation(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    status = serializers.CharField()
    total_bytes = serializers.IntegerField(allow_null=True)
    used_bytes = serializers.IntegerField(allow_null=True)
    free_bytes = serializers.IntegerField(allow_null=True)
    used_percent = serializers.FloatField(allow_null=True)
    readable = serializers.BooleanField()
    writable = serializers.BooleanField()
    detail = serializers.CharField()


class StorageFileType(serializers.Serializer):
    label = serializers.CharField()
    bytes = serializers.IntegerField()
    count = serializers.IntegerField()


class StorageCategory(serializers.Serializer):
    label = serializers.CharField()
    bytes = serializers.IntegerField(allow_null=True)


class RestoreReport(serializers.Serializer):
    checked_at = serializers.CharField()
    archive_sha256 = serializers.CharField()
    status = serializers.CharField()
    detail = serializers.CharField()


class RetentionRule(serializers.Serializer):
    label = serializers.CharField()
    policy = serializers.CharField()
    detail = serializers.CharField()


class BackupScheduleOutput(serializers.Serializer):
    scope = serializers.CharField()
    label = serializers.CharField()
    enabled = serializers.BooleanField()
    interval_hours = serializers.IntegerField()
    next_run_at = serializers.DateTimeField(allow_null=True)
    version = serializers.CharField()
    last_job_id = serializers.UUIDField(allow_null=True)
    last_job_status = serializers.CharField()
    last_error = serializers.CharField()


class StorageSchedule(serializers.Serializer):
    configured = serializers.BooleanField()
    detail = serializers.CharField()
    plans = BackupScheduleOutput(many=True)


class CleanupPreview(serializers.Serializer):
    status = serializers.CharField()
    can_execute = serializers.BooleanField()
    candidate_count = serializers.IntegerField(allow_null=True)
    candidate_bytes = serializers.IntegerField(allow_null=True)
    protected_count = serializers.IntegerField()
    detail = serializers.CharField()


class StorageSnapshot(serializers.Serializer):
    checked_at = serializers.DateTimeField()
    permissions = serializers.DictField(child=serializers.BooleanField())
    locations = StorageLocation(many=True)
    file_types = StorageFileType(many=True)
    catalog_file_bytes = serializers.IntegerField()
    categories = StorageCategory(many=True)
    file_statistics_notice = serializers.CharField()
    schedule = StorageSchedule()
    backups = BackupPage()
    verifications = BackupVerificationOutput(many=True)
    rehearsals = RestoreReport(many=True)
    rehearsals_limited = serializers.BooleanField()
    retention = RetentionRule(many=True)
    cleanup = CleanupPreview()


class BackupDetailOutput(serializers.Serializer):
    backup = BackupOutput()
    verifications = BackupVerificationOutput(many=True)
    rehearsals = RestoreReport(many=True)
    rehearsals_limited = serializers.BooleanField()
    technical_error = serializers.CharField()


class RestorePlan(serializers.Serializer):
    backup_id = serializers.UUIDField()
    archive_name = serializers.CharField()
    archive_sha256 = serializers.CharField()
    integrity_verified_at = serializers.DateTimeField(allow_null=True)
    restore_executed = serializers.BooleanField()
    ready_for_rehearsal = serializers.BooleanField()
    target = serializers.CharField()
    command = serializers.CharField()
    report_option = serializers.CharField()
    requirements = serializers.ListField(child=serializers.CharField())


class StorageCommandOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    operation = serializers.CharField()
    backup = BackupOutput(required=False)
    verification = BackupVerificationOutput(required=False)
    restore_plan = RestorePlan(required=False)
    schedule_saved = serializers.BooleanField(required=False)


class StorageWorkspaceView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanViewSystemStatus]

    @extend_schema(parameters=[OpenApiParameter("page", int), OpenApiParameter("status", str)], responses=StorageSnapshot)
    def get(self, request):
        class Query(serializers.Serializer):
            page = serializers.IntegerField(default=1, min_value=1, max_value=100000)
            status = serializers.ChoiceField(choices=["", "queued", "running", "completed", "failed"], default="")
        query = Query(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(storage_snapshot(request.user, **query.validated_data))


class StorageCommandView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRunBackup]
    throttle_scope = "storage_maintenance"

    @extend_schema(request=StorageCommandInput, responses=StorageCommandOutput)
    def post(self, request):
        serializer = StorageCommandInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(storage_command(request, serializer.validated_data))


class StorageBackupDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRunBackup]

    @extend_schema(responses=BackupDetailOutput)
    def get(self, request, backup_id):
        return Response(backup_detail(backup_id))
