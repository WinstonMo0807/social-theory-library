"""Encrypted personal graph views; deletion retains only command tombstones."""
from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel
from .research_models import PrivateResearchRecord


class SavedGraphView(PrivateResearchRecord):
    # Public entity identities live inside encrypted data. Removing a public
    # source must not remove the owner's view or silently change its center.
    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        ordering = ["-updated_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="graph_view_request_unique")]
        indexes = [models.Index(fields=["user", "-updated_at"], name="graph_view_owner_updated_idx")]


class GraphViewReceipt(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    record = models.ForeignKey(SavedGraphView, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="command_receipts")
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    applied_revision = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="graph_receipt_request_unique")]
