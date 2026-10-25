from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel


class CloudProvider(UUIDTimeStampedModel):
    name = models.CharField(max_length=120)
    provider_type = models.CharField(max_length=40, default="s3")
    endpoint_url = models.URLField(blank=True)
    bucket = models.CharField(max_length=255)
    region = models.CharField(max_length=80, blank=True)
    public_base_url = models.URLField(blank=True)
    credential_reference = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=False)
    is_default = models.BooleanField(default=False)


class CloudObject(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待同步"
        SYNCING = "syncing", "同步中"
        READY = "ready", "就绪"
        FAILED = "failed", "失败"
        DELETING = "deleting", "删除中"
        DELETED = "deleted", "已删除"

    asset = models.ForeignKey("catalog.Asset", on_delete=models.CASCADE, related_name="cloud_objects")
    provider = models.ForeignKey(CloudProvider, on_delete=models.PROTECT, related_name="cloud_objects")
    object_key = models.CharField(max_length=1000)
    etag = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64)
    byte_size = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    cdn_enabled = models.BooleanField(default=False)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["provider", "object_key"], name="unique_cloud_object_key"),
        ]


class CloudBudgetPolicy(UUIDTimeStampedModel):
    provider = models.OneToOneField(CloudProvider, on_delete=models.CASCADE, related_name="budget_policy")
    monthly_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    warning_ratio = models.FloatField(default=0.8)
    stop_new_publications_ratio = models.FloatField(default=1.0)
    pause_new_cdn_on_limit = models.BooleanField(default=True)
    preserve_existing_reads = models.BooleanField(default=True)
    notification_emails = models.JSONField(default=list, blank=True)


class CloudUsageSnapshot(UUIDTimeStampedModel):
    provider = models.ForeignKey(CloudProvider, on_delete=models.CASCADE, related_name="usage_snapshots")
    period = models.CharField(max_length=7)
    storage_bytes = models.BigIntegerField(default=0)
    egress_bytes = models.BigIntegerField(default=0)
    request_count = models.BigIntegerField(default=0)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    source_payload = models.JSONField(default=dict, blank=True)


class BackupJob(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待"
        RUNNING = "running", "执行中"
        COMPLETED = "completed", "完成"
        FAILED = "failed", "失败"

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="backup_jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    destination_path = models.CharField(max_length=1000)
    include_originals = models.BooleanField(default=False)
    incremental_base = models.ForeignKey('self', null=True, blank=True, on_delete=models.PROTECT, related_name='incremental_backups')
    archive_path = models.CharField(max_length=1000, blank=True)
    manifest = models.JSONField(default=dict, blank=True)
    checksum = models.CharField(max_length=128, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class BackupVerification(UUIDTimeStampedModel):
    """Archive integrity is independent of backup creation and restore rehearsal."""
    backup = models.ForeignKey(BackupJob, on_delete=models.PROTECT, related_name="verifications")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="backup_verifications")
    status = models.CharField(max_length=20, choices=BackupJob.Status.choices, default=BackupJob.Status.QUEUED, db_index=True)
    expected_checksum = models.CharField(max_length=64)
    report = models.JSONField(default=dict, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class BackupSchedule(UUIDTimeStampedModel):
    """Explicit opt-in schedules over the existing backup job service."""
    scope = models.CharField(max_length=20, unique=True, choices=[("database", "数据库与清单"), ("originals", "数据库、清单与原件"), ("incremental", "数据库与增量原件")])
    incremental_base = models.ForeignKey(BackupJob, null=True, blank=True, on_delete=models.PROTECT, related_name='incremental_schedules')
    enabled = models.BooleanField(default=False)
    interval_hours = models.PositiveIntegerField(default=24)
    next_run_at = models.DateTimeField(null=True, blank=True)
    configured_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="backup_schedules")
    last_job = models.ForeignKey(BackupJob, null=True, blank=True, on_delete=models.SET_NULL, related_name="schedules")
    last_error = models.CharField(max_length=500, blank=True)


class StorageCleanupPlan(UUIDTimeStampedModel):
    """Bounded, explicit local transient-file cleanup over the existing task service."""
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="storage_cleanup_plans")
    status = models.CharField(max_length=20, default="scanned", db_index=True,
        choices=[("scanned", "等待确认"), ("queued", "等待"), ("running", "执行中"),
            ("completed", "完成"), ("partial", "部分完成"), ("failed", "失败"), ("cancelled", "已停止")])
    retention_days = models.PositiveIntegerField()
    policy_version = models.CharField(max_length=100)
    manifest = models.JSONField(default=list)
    selected = models.JSONField(default=list)
    outcomes = models.JSONField(default=dict)
    scan_summary = models.JSONField(default=dict)
    error_message = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
