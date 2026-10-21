"""Minimal durable receipts for public-path follows and personal plan copies."""
from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel


class PlanCommandReceipt(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    record = models.ForeignKey("reading.PersonalReadingPlan", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="path_command_receipts")
    request_id = models.UUIDField()
    fingerprint = models.CharField(max_length=64)
    applied_revision = models.PositiveIntegerField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="plan_command_request_unique")]
