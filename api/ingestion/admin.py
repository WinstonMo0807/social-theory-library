from django.contrib import admin

from .models import (
    AuditEvent,
    CandidateEvidence,
    DecisionLog,
    EntityResolutionCandidate,
    FieldLock,
    MetadataCandidate,
    ProcessingAttempt,
    ProcessingJob,
    ReviewTask,
    SourceRecord,
    UploadBatch,
    UploadItem,
)


class UploadItemInline(admin.TabularInline):
    model = UploadItem
    extra = 0
    fields = (
        "source_filename",
        "status",
        "workflow_state",
        "stage_progress",
        "priority",
        "error_code",
        "edition",
    )
    readonly_fields = fields
    show_change_link = True


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "label",
        "created_by",
        "status",
        "ocr_strategy",
        "expected_count",
        "completed_count",
        "failed_count",
        "created_at",
    )
    list_filter = ("status", "access_policy", "ocr_strategy", "duplicate_policy")
    search_fields = ("label", "notes", "created_by__display_name", "created_by__email")
    inlines = (UploadItemInline,)


@admin.register(UploadItem)
class UploadItemAdmin(admin.ModelAdmin):
    list_display = (
        "source_filename",
        "status",
        "workflow_state",
        "priority",
        "stage_progress",
        "retry_count",
        "created_at",
    )
    list_filter = ("status", "workflow_state", "document_type_hint")
    search_fields = ("source_filename", "sha256", "edition__work__title", "error_message")
    readonly_fields = (
        "sha256",
        "byte_size",
        "recognized_metadata",
        "processing_token",
        "workflow_updated_at",
    )


@admin.register(ProcessingAttempt)
class ProcessingAttemptAdmin(admin.ModelAdmin):
    list_display = (
        "upload_item",
        "stage",
        "attempt_number",
        "status",
        "error_kind",
        "started_at",
        "finished_at",
    )
    list_filter = ("stage", "status", "error_kind")
    search_fields = ("idempotency_key", "correlation_id", "error_code", "error_message")
    readonly_fields = (
        "input_fingerprint",
        "output_summary",
        "log_excerpt",
        "error_message",
        "idempotency_key",
        "correlation_id",
        "invalidated_at",
        "superseded_by",
    )


@admin.register(ProcessingJob)
class ProcessingJobAdmin(admin.ModelAdmin):
    list_display = ("job_type", "status", "progress", "error_kind", "created_at")
    list_filter = ("job_type", "status", "error_kind")
    search_fields = ("task_id", "idempotency_key", "correlation_id", "error_code")
    readonly_fields = ("stats", "idempotency_key", "correlation_id")


@admin.register(SourceRecord)
class SourceRecordAdmin(admin.ModelAdmin):
    list_display = ("provider", "operation", "status", "external_id", "retrieved_at", "expires_at")
    list_filter = ("provider", "operation", "status")
    search_fields = ("external_id", "request_fingerprint", "error_code")
    readonly_fields = ("query", "raw_response", "request_fingerprint", "retrieved_at")


@admin.register(MetadataCandidate)
class MetadataCandidateAdmin(admin.ModelAdmin):
    list_display = ("upload_item", "field_name", "source", "lifecycle", "confidence", "is_locked")
    list_filter = ("lifecycle", "source", "is_locked", "selected")
    search_fields = ("field_name", "conflict_group", "upload_item__source_filename")
    readonly_fields = ("score_factors",)


@admin.register(CandidateEvidence)
class CandidateEvidenceAdmin(admin.ModelAdmin):
    list_display = ("metadata_candidate", "source_kind", "page_number", "asset", "created_at")
    list_filter = ("source_kind", "extraction_method")
    search_fields = ("text_quote", "external_identifier", "model_name")


@admin.register(EntityResolutionCandidate)
class EntityResolutionCandidateAdmin(admin.ModelAdmin):
    list_display = ("source_name", "target_type", "label", "match_score", "status", "created_at")
    list_filter = ("target_type", "candidate_entity_type", "status")
    search_fields = ("source_name", "label", "candidate_entity_id")


@admin.register(ReviewTask)
class ReviewTaskAdmin(admin.ModelAdmin):
    list_display = ("title", "task_type", "status", "priority", "assigned_to", "created_at")
    list_filter = ("task_type", "status", "priority")
    search_fields = ("title", "target_id", "upload_item__source_filename")


@admin.register(DecisionLog)
class DecisionLogAdmin(admin.ModelAdmin):
    list_display = ("action", "target_type", "target_id", "actor", "created_at")
    list_filter = ("action", "target_type")
    search_fields = ("target_id", "correlation_id", "reason")
    readonly_fields = (
        "upload_item",
        "review_task",
        "metadata_candidate",
        "resolution_candidate",
        "actor",
        "action",
        "target_type",
        "target_id",
        "before",
        "after",
        "reason",
        "correlation_id",
        "created_at",
        "updated_at",
    )


admin.site.register(FieldLock)
admin.site.register(AuditEvent)
