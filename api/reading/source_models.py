"""Private follows of public sources; no source text or metadata snapshots."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel


class SourceFollow(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="source_follows")
    path = models.CharField(max_length=400)
    # Stable public identity survives slug changes and withdrawal; no cached biography.
    scholar_profile_id = models.UUIDField(null=True, blank=True)
    topic_id = models.UUIDField(null=True, blank=True)
    active = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=1)
    state_fingerprint = models.CharField(max_length=64)
    source_status = models.CharField(max_length=32)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    check_error = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "path"], condition=models.Q(scholar_profile_id__isnull=True, topic_id__isnull=True),
                name="unique_owner_source_follow"),
            models.UniqueConstraint(fields=["user", "scholar_profile_id"], condition=models.Q(scholar_profile_id__isnull=False),
                name="unique_owner_scholar_follow"),
            models.UniqueConstraint(fields=["user", "topic_id"], condition=models.Q(topic_id__isnull=False),
                name="unique_owner_topic_follow"),
            models.CheckConstraint(condition=models.Q(scholar_profile_id__isnull=True) | models.Q(topic_id__isnull=True),
                name="source_follow_single_target")]
        indexes = [models.Index(fields=["active", "last_checked_at"], name="source_follow_poll_idx")]
        ordering = ["-updated_at", "-id"]


class SourceFollowEvent(UUIDTimeStampedModel):
    follow = models.ForeignKey(SourceFollow, null=True, blank=True, on_delete=models.SET_NULL, related_name="events")
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
