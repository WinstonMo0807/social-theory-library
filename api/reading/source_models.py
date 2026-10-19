"""Private follows of public sources; no source text or metadata snapshots."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel


class SourceFollow(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="source_follows")
    path = models.CharField(max_length=400)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    state_fingerprint = models.CharField(max_length=64)
    source_status = models.CharField(max_length=32)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    check_error = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "path"], name="unique_owner_source_follow")]
        indexes = [models.Index(fields=["active", "last_checked_at"], name="source_follow_poll_idx")]
        ordering = ["-updated_at", "-id"]


class SourceFollowEvent(UUIDTimeStampedModel):
    follow = models.ForeignKey(SourceFollow, on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.CharField(max_length=20)
    before_status = models.CharField(max_length=32, blank=True)
    after_status = models.CharField(max_length=32, blank=True)
    request_id = models.UUIDField(null=True, blank=True)
    request_fingerprint = models.CharField(max_length=64, blank=True)
    revision = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="unique_owner_source_request")]
        ordering = ["-created_at", "-id"]
