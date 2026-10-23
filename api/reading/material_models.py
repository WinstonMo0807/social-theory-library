"""Personal list presentation only; authoritative material remains in its original model."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel

MATERIAL_KINDS = ("research", "notes", "bookmarks", "plans", "lists", "audits", "confirmed", "saved")


class ReaderMaterialPreference(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=16, choices=[(value, value) for value in MATERIAL_KINDS])
    object_id = models.UUIDField()
    title_ciphertext = models.BinaryField(blank=True, default=bytes)
    archived = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "kind", "object_id"], name="reader_material_preference_unique")]
        indexes = [models.Index(fields=["user", "kind", "archived"], name="reader_material_archive_idx")]
