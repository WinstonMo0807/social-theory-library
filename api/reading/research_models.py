"""Owner-scoped research state. No private text enters catalog EvidencePack."""
import uuid

from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel


class PrivateResearchRecord(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    revision = models.PositiveIntegerField(default=1)
    data_ciphertext = models.BinaryField(default=bytes, blank=True)
    request_id = models.UUIDField(default=uuid.uuid4)

    class Meta:
        abstract = True
        ordering = ["-updated_at"]


class ResearchProject(PrivateResearchRecord):
    conversation = models.OneToOneField("reading.LibraryConversation", null=True, blank=True,
                                      on_delete=models.SET_NULL, related_name="research")
    archived = models.BooleanField(default=False)

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        indexes = [models.Index(fields=["user", "archived", "-updated_at"], name="research_owner_archive_idx")]
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="research_project_request_unique")]


class ResearchTurn(UUIDTimeStampedModel):
    project = models.ForeignKey(ResearchProject, on_delete=models.CASCADE, related_name="turns")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="branches")
    request_id = models.UUIDField(default=uuid.uuid4)
    revision = models.PositiveIntegerField(default=1)
    data_ciphertext = models.BinaryField(default=bytes, blank=True)
    # Short-lived Discovery may be purged; durable references live in encrypted data.
    discovery_session_id = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, default="queued", db_index=True)
    generation = models.PositiveIntegerField(default=1)
    task_id = models.CharField(max_length=64, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [models.UniqueConstraint(fields=["project", "request_id"], name="research_turn_request_unique")]


class CitationAudit(PrivateResearchRecord):
    purpose = models.CharField(max_length=20, default="manuscript", choices=[("manuscript", "Manuscript"), ("private_source", "Private source")])
    file_size_bytes = models.PositiveIntegerField(default=0)
    project = models.ForeignKey(ResearchProject, null=True, blank=True, on_delete=models.SET_NULL, related_name="audits")
    request_id = models.UUIDField(default=uuid.uuid4)
    original_ciphertext = models.BinaryField(default=bytes)
    # Disposable owner-only preview; never overwrites the original or report payload.
    preview_ciphertext = models.BinaryField(default=bytes, blank=True)
    preview_state = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default="queued", db_index=True)
    generation = models.PositiveIntegerField(default=1)
    task_id = models.CharField(max_length=64, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    completed_units = models.PositiveIntegerField(default=0)
    total_units = models.PositiveIntegerField(default=0)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        indexes = [models.Index(fields=["user", "purpose", "-updated_at"], name="citation_owner_purpose_idx")]
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="citation_audit_request_unique")]


class PersonalReadingPlan(PrivateResearchRecord):
    project = models.ForeignKey(ResearchProject, null=True, blank=True, on_delete=models.SET_NULL, related_name="plans")
    # Scheduling marker only; private job details remain encrypted. Null means an older row needs classification.
    task_pending = models.BooleanField(null=True, default=None, db_index=True)

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="reading_plan_request_unique")]


class ResearchMemory(PrivateResearchRecord):
    project = models.ForeignKey(ResearchProject, null=True, blank=True, on_delete=models.SET_NULL, related_name="memories")
    state = models.CharField(max_length=16, default="proposed")
    # Encrypted, owner-scoped derived data; deleted with the memory, never indexed publicly.
    embedding_ciphertext = models.BinaryField(default=bytes, blank=True)
    embedding_artifact = models.CharField(max_length=160, blank=True)

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        indexes = [models.Index(fields=["user", "state"], name="memory_owner_state_idx")]
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="research_memory_request_unique")]


class ReaderDataOperation(PrivateResearchRecord):
    """Durable owner-only export preparation / explicitly confirmed erasure."""
    kind = models.CharField(max_length=12, choices=[("export", "Export"), ("erase", "Erase")])
    status = models.CharField(max_length=16, default="preview", db_index=True)
    generation = models.PositiveIntegerField(default=1)
    task_id = models.CharField(max_length=64, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="reader_data_request_unique")]


class ReaderSearchRecord(PrivateResearchRecord):
    """Opt-in encrypted history, independent of short-lived working sessions."""

    class Meta(PrivateResearchRecord.Meta):
        abstract = False
        constraints = [models.UniqueConstraint(fields=["user", "request_id"], name="reader_search_request_unique")]
