import uuid

from django.db import models
from .recycle import ActiveRecordManager


class UUIDTimeStampedModel(models.Model):
    objects = ActiveRecordManager()
    all_objects = models.Manager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
