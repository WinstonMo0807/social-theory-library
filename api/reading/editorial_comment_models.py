"""Explicit reader submissions; publication requires editorial review."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel


class EditorialComment(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    issue = models.ForeignKey("catalog.RecommendationIssue", on_delete=models.CASCADE, related_name="reader_comments")
    public_revision_id = models.UUIDField()
    data_ciphertext = models.BinaryField(default=bytes)
    status = models.CharField(max_length=16, default="pending", choices=[("pending", "待审核"), ("published", "已公开"), ("rejected", "未公开")])
    revision = models.PositiveIntegerField(default=1)
    moderation_reason = models.CharField(max_length=240, blank=True)
    moderated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="moderated_editorial_comments")

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["issue", "public_revision_id", "status", "created_at"], name="editorial_comment_public_idx")]
