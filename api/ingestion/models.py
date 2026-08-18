from django.conf import settings
from django.core.files.storage import storages
from django.db import models
from django.utils import timezone

from common.models import UUIDTimeStampedModel


def intake_upload_path(instance, filename):
    return f"incoming/{instance.batch_id}/{filename}"


def intake_storage():
    return storages["intake"]


class UploadBatch(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "已接收"
        PROCESSING = "processing", "处理中"
        PARTIAL = "partial", "部分完成"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    class AccessPolicy(models.TextChoices):
        PUBLIC = "public", "公开访问"
        REGISTERED = "registered", "登录读者"
        RESTRICTED = "restricted", "受限访问"

    class OcrStrategy(models.TextChoices):
        AUTO = "auto", "自动检测"
        FORCE = "force", "强制 OCR"
        SKIP = "skip", "跳过 OCR"

    class DuplicatePolicy(models.TextChoices):
        REVIEW = "review", "发现重复时人工确认"
        BLOCK_EXACT = "block_exact", "阻止完全重复文件"
        ALLOW = "allow", "允许继续入库"

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="upload_batches")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RECEIVED)
    source = models.CharField(max_length=30, default="admin")
    expected_count = models.PositiveIntegerField(default=0)
    completed_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)
    label = models.CharField(max_length=240, blank=True)
    access_policy = models.CharField(
        max_length=20,
        choices=AccessPolicy.choices,
        default=AccessPolicy.PUBLIC,
    )
    ocr_strategy = models.CharField(
        max_length=20,
        choices=OcrStrategy.choices,
        default=OcrStrategy.AUTO,
    )
    duplicate_policy = models.CharField(
        max_length=20,
        choices=DuplicatePolicy.choices,
        default=DuplicatePolicy.REVIEW,
    )
    external_enrichment_enabled = models.BooleanField(default=True)
    ai_suggestions_enabled = models.BooleanField(default=False)


class UploadItem(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        RECEIVED = "received", "已接收"
        VALIDATING = "validating", "校验中"
        DEDUPLICATING = "deduplicating", "查重中"
        EXTRACTING = "extracting", "提取中"
        OCR = "ocr", "OCR 中"
        METADATA = "metadata", "识别元数据"
        LINKING = "linking", "建立关联"
        INDEXING = "indexing", "建立索引"
        PREPARING_PUBLIC_ASSET = "preparing_public_asset", "准备公开文件"
        SYNCING_CLOUD = "syncing_cloud", "同步云端"
        READY = "ready", "可发布"
        PUBLISHED = "published", "已发布"
        NEEDS_REVIEW = "needs_review", "需要处理"
        FAILED = "failed", "失败"
        WITHDRAWN = "withdrawn", "已下架"
        DELETED = "deleted", "已删除"

    class DispatchStatus(models.TextChoices):
        PENDING = "pending", "等待派发"
        QUEUED = "queued", "已进入队列"
        RUNNING = "running", "工作者处理中"
        COMPLETED = "completed", "任务已完成"
        FAILED = "failed", "派发失败"

    class DispatchKind(models.TextChoices):
        INITIAL = "initial", "首次识别"
        REVIEWED = "reviewed", "复核后继续"

    class WorkflowState(models.TextChoices):
        UPLOADED = "uploaded", "已上传"
        PREFLIGHT = "preflight", "预检"
        PARSING = "parsing", "解析"
        ENRICHING = "enriching", "补充元数据"
        RESOLVING = "resolving", "实体消歧"
        NEEDS_REVIEW = "needs_review", "等待审核"
        READY = "ready", "可以批准"
        APPROVED = "approved", "已批准"
        INDEXING = "indexing", "建立索引"
        PUBLISHED = "published", "已发布"
        FAILED = "failed", "失败"
        CANCELLED = "cancelled", "已取消"
        ARCHIVED = "archived", "已归档"

    batch = models.ForeignKey(UploadBatch, on_delete=models.CASCADE, related_name="items")
    source_filename = models.CharField(max_length=800)
    file = models.FileField(
        upload_to=intake_upload_path,
        storage=intake_storage,
        max_length=1000,
        blank=True,
    )
    sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    byte_size = models.BigIntegerField(default=0)
    document_type_hint = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.RECEIVED, db_index=True)
    stage_progress = models.PositiveSmallIntegerField(default=0)
    retry_count = models.PositiveSmallIntegerField(default=0)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    recognized_metadata = models.JSONField(default=dict, blank=True)
    edition = models.ForeignKey("catalog.Edition", null=True, blank=True, on_delete=models.SET_NULL)
    asset = models.ForeignKey("catalog.Asset", null=True, blank=True, on_delete=models.SET_NULL)
    replacement_of_asset = models.ForeignKey(
        "catalog.Asset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="replacement_uploads",
    )
    processing_token = models.CharField(max_length=80, blank=True, db_index=True)
    dispatch_status = models.CharField(
        max_length=20,
        choices=DispatchStatus.choices,
        default=DispatchStatus.PENDING,
        db_index=True,
    )
    dispatch_kind = models.CharField(
        max_length=20,
        choices=DispatchKind.choices,
        default=DispatchKind.INITIAL,
    )
    dispatch_task_id = models.CharField(max_length=80, blank=True, db_index=True)
    dispatch_attempts = models.PositiveSmallIntegerField(default=0)
    last_dispatched_at = models.DateTimeField(null=True, blank=True)
    dispatch_error = models.TextField(blank=True)
    workflow_state = models.CharField(
        max_length=24,
        choices=WorkflowState.choices,
        default=WorkflowState.UPLOADED,
        db_index=True,
    )
    priority = models.PositiveSmallIntegerField(default=0, db_index=True)
    preflight_summary = models.JSONField(default=dict, blank=True)
    workflow_updated_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["batch", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "processing_token"],
                condition=~models.Q(processing_token=""),
                name="unique_batch_processing_token",
            ),
        ]


class ProcessingAttempt(UUIDTimeStampedModel):
    class ErrorKind(models.TextChoices):
        RETRYABLE = "retryable", "可重试"
        MANUAL_INTERVENTION = "manual_intervention", "需要人工修复"
        PERMANENT = "permanent", "永久失败"

    upload_item = models.ForeignKey(UploadItem, on_delete=models.CASCADE, related_name="attempts")
    stage = models.CharField(max_length=40)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    worker_id = models.CharField(max_length=160, blank=True)
    status = models.CharField(max_length=20, default="started")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    input_fingerprint = models.CharField(max_length=128, blank=True)
    output_summary = models.JSONField(default=dict, blank=True)
    log_excerpt = models.TextField(blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    error_kind = models.CharField(
        max_length=24,
        choices=ErrorKind.choices,
        blank=True,
    )
    idempotency_key = models.CharField(max_length=128, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_attempts",
    )

    class Meta:
        ordering = ["-started_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_attempt_idempotency_key",
            ),
        ]

    @property
    def should_run(self) -> bool:
        """Whether the current context must execute the stage body.

        The value is attached by ``processing_attempt`` and deliberately is not
        persisted.  Callers can reuse a completed, non-invalidated attempt
        without repeating its side effects.
        """

        return bool(getattr(self, "_should_run", True))


class ProcessingJob(UUIDTimeStampedModel):
    class JobType(models.TextChoices):
        OCR = "ocr", "OCR"
        EXTERNAL_ENRICHMENT = "external_enrichment", "联网补充"
        TEXT_EXTRACTION = "text_extraction", "文本提取"
        PAGE_LABELS = "page_labels", "页码识别"
        SEMANTIC_INDEX = "semantic_index", "语义索引"
        QUERY_LEXICON_CANDIDATES = "query_lexicon_candidates", "术语候选提取"
        QUERY_LEXICON_RECONCILE = "query_lexicon_reconcile", "QueryLexicon 重建"
        PROJECTION_REFRESH = "projection_refresh", "公开投影刷新"
        THUMBNAIL = "thumbnail", "缩略图"
        CACHE_REFRESH = "cache_refresh", "公开目录刷新"

    class Status(models.TextChoices):
        PENDING = "pending", "等待处理"
        RUNNING = "running", "处理中"
        PAUSED = "paused", "已暂停"
        SUCCEEDED = "succeeded", "完成"
        FAILED = "failed", "失败"
        CANCELED = "canceled", "已取消"

    class ErrorKind(models.TextChoices):
        RETRYABLE = "retryable", "可重试"
        MANUAL_INTERVENTION = "manual_intervention", "需要人工修复"
        PERMANENT = "permanent", "永久失败"

    job_type = models.CharField(max_length=32, choices=JobType.choices, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    upload_item = models.ForeignKey(
        UploadItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processing_jobs",
    )
    edition = models.ForeignKey(
        "catalog.Edition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processing_jobs",
    )
    asset = models.ForeignKey(
        "catalog.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="processing_jobs",
    )
    progress = models.PositiveSmallIntegerField(default=0)
    engine = models.CharField(max_length=120, blank=True)
    attempt = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    settings_version = models.CharField(max_length=80, blank=True)
    task_id = models.CharField(max_length=255, blank=True, db_index=True)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    error_kind = models.CharField(
        max_length=24,
        choices=ErrorKind.choices,
        blank=True,
    )
    idempotency_key = models.CharField(max_length=128, blank=True)
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    stats = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_processing_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    pause_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["job_type", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_job_idempotency_key",
            ),
        ]


class SourceRecord(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "等待获取"
        SUCCEEDED = "succeeded", "获取成功"
        FAILED = "failed", "获取失败"

    upload_item = models.ForeignKey(
        UploadItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_records",
    )
    provider = models.CharField(max_length=80, db_index=True)
    operation = models.CharField(max_length=80)
    query = models.JSONField(default=dict, blank=True)
    request_fingerprint = models.CharField(max_length=128, blank=True)
    external_id = models.CharField(max_length=255, blank=True, db_index=True)
    raw_response = models.JSONField(default=dict, blank=True)
    provider_version = models.CharField(max_length=80, blank=True)
    retrieved_at = models.DateTimeField(default=timezone.now, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-retrieved_at"]
        indexes = [
            models.Index(fields=["provider", "operation", "request_fingerprint"]),
            models.Index(fields=["status", "retrieved_at"]),
        ]


class MetadataCandidate(UUIDTimeStampedModel):
    class Lifecycle(models.TextChoices):
        PROPOSED = "proposed", "待审核"
        ACCEPTED = "accepted", "已接受"
        REJECTED = "rejected", "已拒绝"
        SUPERSEDED = "superseded", "已被替代"

    upload_item = models.ForeignKey(UploadItem, on_delete=models.CASCADE, related_name="metadata_candidates")
    field_name = models.CharField(max_length=80)
    value = models.JSONField()
    source = models.CharField(max_length=120)
    evidence = models.JSONField(default=dict, blank=True)
    confidence = models.FloatField(default=0)
    selected = models.BooleanField(default=False)
    lifecycle = models.CharField(
        max_length=20,
        choices=Lifecycle.choices,
        default=Lifecycle.PROPOSED,
        db_index=True,
    )
    normalized_value = models.JSONField(default=dict, blank=True)
    source_record = models.ForeignKey(
        SourceRecord,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="metadata_candidates",
    )
    conflict_group = models.CharField(max_length=120, blank=True, db_index=True)
    score_factors = models.JSONField(default=dict, blank=True)
    is_locked = models.BooleanField(default=False)
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="accepted_metadata_candidates",
    )
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="rejected_metadata_candidates",
    )
    rejected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["upload_item", "field_name", "-confidence"]),
            models.Index(fields=["upload_item", "lifecycle", "field_name"]),
        ]


class CandidateEvidence(UUIDTimeStampedModel):
    metadata_candidate = models.ForeignKey(
        MetadataCandidate,
        on_delete=models.CASCADE,
        related_name="evidence_records",
    )
    asset = models.ForeignKey(
        "catalog.Asset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="candidate_evidence",
    )
    source_record = models.ForeignKey(
        SourceRecord,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="candidate_evidence",
    )
    page_number = models.PositiveIntegerField(null=True, blank=True)
    bbox = models.JSONField(default=list, blank=True)
    text_quote = models.TextField(blank=True)
    source_kind = models.CharField(max_length=40, db_index=True)
    external_identifier = models.CharField(max_length=400, blank=True)
    extraction_method = models.CharField(max_length=80, blank=True)
    model_name = models.CharField(max_length=160, blank=True)
    model_revision = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["page_number", "created_at"]
        indexes = [
            models.Index(fields=["metadata_candidate", "source_kind"]),
            models.Index(fields=["asset", "page_number"]),
        ]


class EntityResolutionCandidate(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PROPOSED = "proposed", "待判断"
        LINKED = "linked", "已关联现有实体"
        CREATE_DRAFT = "create_draft", "创建新实体草稿"
        UNRESOLVED = "unresolved", "保留未解析名称"
        IGNORED = "ignored", "已忽略"
        REJECTED = "rejected", "已拒绝"

    upload_item = models.ForeignKey(
        UploadItem,
        on_delete=models.CASCADE,
        related_name="entity_resolution_candidates",
    )
    source_record = models.ForeignKey(
        SourceRecord,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="entity_resolution_candidates",
    )
    target_type = models.CharField(max_length=40, db_index=True)
    source_name = models.CharField(max_length=500)
    candidate_entity_type = models.CharField(max_length=80)
    candidate_entity_id = models.CharField(max_length=128, blank=True)
    label = models.CharField(max_length=500)
    aliases = models.JSONField(default=list, blank=True)
    external_ids = models.JSONField(default=dict, blank=True)
    supporting_properties = models.JSONField(default=dict, blank=True)
    match_score = models.FloatField(default=0)
    match_reasons = models.JSONField(default=list, blank=True)
    conflicts = models.JSONField(default=list, blank=True)
    preview_data = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PROPOSED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_entity_resolution_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-match_score", "created_at"]
        indexes = [
            models.Index(fields=["upload_item", "target_type", "status"]),
        ]


class ReviewTask(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "等待处理"
        IN_PROGRESS = "in_progress", "处理中"
        COMPLETED = "completed", "已完成"
        CANCELLED = "cancelled", "已取消"

    upload_item = models.ForeignKey(
        UploadItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="review_tasks",
    )
    task_type = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=128, blank=True)
    title = models.CharField(max_length=500)
    details = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    priority = models.PositiveSmallIntegerField(default=0, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="assigned_ingestion_review_tasks",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="created_ingestion_review_tasks",
    )
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="completed_ingestion_review_tasks",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-priority", "created_at"]
        indexes = [
            models.Index(fields=["status", "-priority", "created_at"]),
            models.Index(fields=["target_type", "target_id"]),
        ]


class DecisionLog(UUIDTimeStampedModel):
    upload_item = models.ForeignKey(
        UploadItem,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="decision_logs",
    )
    review_task = models.ForeignKey(
        ReviewTask,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decisions",
    )
    metadata_candidate = models.ForeignKey(
        MetadataCandidate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decision_logs",
    )
    resolution_candidate = models.ForeignKey(
        EntityResolutionCandidate,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decision_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ingestion_decisions",
    )
    action = models.CharField(max_length=80, db_index=True)
    target_type = models.CharField(max_length=80)
    target_id = models.CharField(max_length=128, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    correlation_id = models.CharField(max_length=128, blank=True, db_index=True)
    reverts_decision = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reversal",
    )
    reverted_at = models.DateTimeField(null=True, blank=True)
    reverted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reverted_ingestion_decisions",
    )
    reversal_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id", "-created_at"]),
        ]


class FieldLock(UUIDTimeStampedModel):
    edition = models.ForeignKey("catalog.Edition", on_delete=models.CASCADE, related_name="field_locks")
    field_name = models.CharField(max_length=80)
    locked_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    locked_value = models.JSONField()
    reason = models.CharField(max_length=400, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["edition", "field_name"], name="unique_edition_field_lock"),
        ]


class AuditEvent(UUIDTimeStampedModel):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=120, db_index=True)
    object_type = models.CharField(max_length=120)
    object_id = models.CharField(max_length=64)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    request_ip = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=120, blank=True, db_index=True)
