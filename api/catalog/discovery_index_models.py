"""Rebuildable search documents; canonical text and publication stay elsewhere."""
from django.db import models
from common.models import UUIDTimeStampedModel


class DiscoveryDocument(UUIDTimeStampedModel):
    generation = models.ForeignKey("catalog.SemanticIndexVersion", on_delete=models.CASCADE, related_name="discovery_documents")
    channel = models.CharField(max_length=16, db_index=True)
    source_type = models.CharField(max_length=32)
    source_id = models.UUIDField()
    source_revision = models.CharField(max_length=64)
    scope_token = models.CharField(max_length=180, db_index=True)
    edition = models.ForeignKey("catalog.Edition", null=True, blank=True, on_delete=models.CASCADE, related_name="discovery_documents")
    document_revision = models.ForeignKey("catalog.DocumentRevision", null=True, blank=True, on_delete=models.PROTECT, related_name="discovery_documents")
    access_status = models.CharField(max_length=20, default="public", db_index=True)
    input_hash = models.CharField(max_length=64, db_index=True)
    text = models.TextField()
    normalized_text = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict)
    keyword_ready = models.BooleanField(default=False, db_index=True)
    vector_ready = models.BooleanField(default=False, db_index=True)
    indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["generation", "source_type", "source_id"], name="discovery_source_generation"),
                   models.Index(fields=["generation", "channel", "scope_token"], name="discovery_channel_scope")]


class DiscoverySourceState(UUIDTimeStampedModel):
    """Completed source fingerprint, using the existing ProcessingJob for work."""
    generation = models.ForeignKey("catalog.SemanticIndexVersion", on_delete=models.CASCADE, related_name="discovery_sources")
    source_type = models.CharField(max_length=32)
    source_id = models.UUIDField()
    source_revision = models.CharField(max_length=64, blank=True)
    job = models.ForeignKey("ingestion.ProcessingJob", null=True, on_delete=models.SET_NULL, related_name="discovery_sources")
    expected_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    indexed_at = models.DateTimeField(null=True, blank=True)
    error = models.CharField(max_length=500, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["generation", "source_type", "source_id"], name="unique_discovery_source_state")]
