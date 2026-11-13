"""Curation products and review decisions; scheduling stays in task_runtime."""
from django.conf import settings
from django.db import models
from common.models import UUIDTimeStampedModel


class CurationRun(UUIDTimeStampedModel):
    work = models.ForeignKey("catalog.Work", on_delete=models.PROTECT)
    edition = models.ForeignKey("catalog.Edition", on_delete=models.PROTECT)
    document_revision = models.ForeignKey("catalog.DocumentRevision", on_delete=models.PROTECT)
    structure = models.ForeignKey("catalog.DocumentStructure", null=True, on_delete=models.PROTECT)
    scope = models.JSONField(default=dict)
    status = models.CharField(max_length=32, default="waiting", db_index=True)
    stage = models.PositiveSmallIntegerField(default=1)
    coverage = models.JSONField(default=dict)
    profile_key = models.CharField(max_length=80, blank=True)
    execution_mode = models.CharField(max_length=16, default="provider", choices=[("provider", "Provider"), ("agent", "Interactive agent")])
    # Pin execution semantics. Deploying a new planner must not invalidate old runs.
    plan_version = models.PositiveSmallIntegerField(default=1, choices=[(1, "Window fold"), (2, "Ordered chapter batches")])
    model_identity = models.JSONField(default=dict)
    input_hash = models.CharField(max_length=64)
    request_id = models.UUIDField(unique=True)
    version = models.PositiveIntegerField(default=1)
    demand = models.ForeignKey("catalog.CapabilityDemand", null=True, on_delete=models.PROTECT)
    error = models.JSONField(default=dict)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class CurationArtifact(UUIDTimeStampedModel):
    run = models.ForeignKey(CurationRun, on_delete=models.PROTECT, related_name="artifacts")
    stage = models.PositiveSmallIntegerField()
    unit = models.CharField(max_length=160)
    cache_key = models.CharField(max_length=64, db_index=True)
    schema_version = models.CharField(max_length=80)
    status = models.CharField(max_length=24, default="waiting")
    input_manifest = models.JSONField(default=dict)
    execution_request = models.JSONField(default=dict)
    output = models.JSONField(default=dict)
    output_hash = models.CharField(max_length=64, blank=True)
    usage = models.JSONField(default=dict)
    elapsed_ms = models.PositiveIntegerField(default=0)
    model_identity = models.JSONField(default=dict)
    executor_id = models.CharField(max_length=160, blank=True)
    error = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["run", "stage", "unit"], name="intelligence_artifact_unit_unique")]
        ordering = ["stage", "created_at"]


class ChangeSet(UUIDTimeStampedModel):
    run = models.OneToOneField(CurationRun, null=True, on_delete=models.PROTECT, related_name="changeset")
    document_revision = models.ForeignKey("catalog.DocumentRevision", null=True, on_delete=models.PROTECT)
    subject_work = models.ForeignKey("catalog.Work", null=True, on_delete=models.PROTECT)
    subject_entity = models.ForeignKey("catalog.Entity", null=True, on_delete=models.PROTECT)
    subject_page = models.ForeignKey("catalog.KnowledgePage", null=True, on_delete=models.PROTECT)
    origin = models.CharField(max_length=24, default="intelligence")
    status = models.CharField(max_length=24, default="review")
    version = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    request_id = models.UUIDField(unique=True)
    input_hash = models.CharField(max_length=64)

    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(document_revision__isnull=False)
            | models.Q(subject_work__isnull=False) | models.Q(subject_entity__isnull=False)
            | models.Q(subject_page__isnull=False)), name="knowledge_changeset_has_subject")]


class ChangeItem(UUIDTimeStampedModel):
    changeset = models.ForeignKey(ChangeSet, on_delete=models.PROTECT, related_name="items")
    kind = models.CharField(max_length=24, choices=[(s, s) for s in ("entity", "alias", "assertion", "wiki_patch")])
    fingerprint = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict)
    dependencies = models.JSONField(default=list)
    source_artifact = models.ForeignKey(CurationArtifact, null=True, on_delete=models.PROTECT)
    decision = models.CharField(max_length=24, default="pending")
    decision_note = models.CharField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.PROTECT)
    reviewed_at = models.DateTimeField(null=True)
    application = models.JSONField(default=dict)
    conflict = models.JSONField(default=dict)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["changeset", "fingerprint"], name="intelligence_change_unique")]
        ordering = ["created_at", "id"]


class ChangeReceipt(UUIDTimeStampedModel):
    changeset = models.ForeignKey(ChangeSet, on_delete=models.PROTECT, related_name="receipts")
    request_id = models.UUIDField(unique=True)
    input_hash = models.CharField(max_length=64)
    result = models.JSONField(default=dict)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)


class KnowledgeCompilation(UUIDTimeStampedModel):
    """Opt-in source subscription; execution and products stay in CurationRun."""
    edition = models.OneToOneField("catalog.Edition", on_delete=models.PROTECT, related_name="knowledge_compilation")
    enabled = models.BooleanField(default=True, db_index=True)
    pending_refresh = models.BooleanField(default=False, db_index=True)
    next_refresh_at = models.DateTimeField(null=True, blank=True, db_index=True)
    refresh_failures = models.PositiveSmallIntegerField(default=0)
    last_error = models.JSONField(default=dict)
    scope = models.JSONField(default=dict)
    profile_key = models.CharField(max_length=80, blank=True)
    execution_mode = models.CharField(max_length=16, default="provider", choices=[("provider", "Provider"), ("agent", "Interactive agent")])
    target_pages = models.ManyToManyField("catalog.KnowledgePage", blank=True, related_name="compilation_sources")
    latest_run = models.ForeignKey(CurationRun, null=True, on_delete=models.PROTECT, related_name="compilation_subscriptions")
    requested_hash = models.CharField(max_length=64, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
