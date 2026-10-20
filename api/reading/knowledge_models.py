"""Owner-only knowledge bookmarks and minimal receipts that survive erasure."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel


class SavedKnowledgeNode(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    node = models.ForeignKey("catalog.KnowledgeNode", on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "node"], name="unique_saved_knowledge_node")]


class KnowledgeSaveReceipt(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    request_id = models.UUIDField()
    target_key = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    applied_saved = models.BooleanField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="knowledge_save_receipt_unique")]
