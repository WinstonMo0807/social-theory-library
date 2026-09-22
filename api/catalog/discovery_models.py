"""Short-lived, access-scoped materialized reader queries, never public history."""

from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel


class DiscoverySearchSession(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待检索"
        RUNNING = "running", "正在检索"
        PARTIAL = "partial", "部分完成"
        COMPLETED = "completed", "检索完成"
        FAILED = "failed", "检索失败"
        CANCELED = "canceled", "已取消"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.CASCADE, related_name="discovery_searches")
    token_hash = models.CharField(max_length=64)
    query = models.TextField()
    filters = models.JSONField(default=dict)
    access_statuses = models.JSONField(default=list)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.QUEUED)
    task_id = models.CharField(max_length=64, blank=True)
    generation = models.PositiveSmallIntegerField(default=1)
    expansion_count = models.PositiveSmallIntegerField(default=0)
    results = models.JSONField(default=dict)
    channels = models.JSONField(default=dict)
    versions = models.JSONField(default=dict)
    warnings = models.JSONField(default=list)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [models.Index(fields=["owner", "status"], name="discovery_owner_status_idx")]
