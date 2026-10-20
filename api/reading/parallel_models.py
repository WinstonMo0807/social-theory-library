"""Encrypted parallel-reading work; explicit contributions have their own lifecycle."""
from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel
from .research_models import PrivateResearchRecord


class ParallelReadingTask(PrivateResearchRecord):
    # Source deletion must not erase the reader's decisions or terminology notes.
    left_asset = models.ForeignKey("catalog.Asset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    right_asset = models.ForeignKey("catalog.Asset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="parallel_task_request_unique")]
        indexes = [models.Index(fields=["user", "left_asset", "-updated_at"], name="parallel_owner_left_idx")]


class ParallelReadingReceipt(UUIDTimeStampedModel):
    """Durable nonce lookup, without a second copy of any private content."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    # Retain only a nonce tombstone after erasure, so a delayed old POST cannot
    # recreate deleted private content. No reference, note or term lives here.
    task = models.ForeignKey(ParallelReadingTask, null=True, blank=True, on_delete=models.SET_NULL, related_name="receipts")
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    applied_revision = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="parallel_receipt_request_unique")]


class ParallelCalibration(PrivateResearchRecord):
    # No task FK: deleting personal notes cannot modify an independently submitted contribution.
    left_asset = models.ForeignKey("catalog.Asset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    right_asset = models.ForeignKey("catalog.Asset", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")
    scope = models.CharField(max_length=16, choices=[("bibliography", "Bibliography"), ("passages", "Passages")])
    status = models.CharField(max_length=16, default="submitted", db_index=True,
        choices=[("submitted", "Submitted"), ("reviewed", "Reviewed"), ("published", "Published"), ("rejected", "Rejected")])
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="parallel_calib_request_unique")]
        indexes = [models.Index(fields=["status", "left_asset", "-updated_at"], name="parallel_calib_status_idx")]
