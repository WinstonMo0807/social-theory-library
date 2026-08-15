from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from common.models import UUIDTimeStampedModel


class DocumentType(models.TextChoices):
    BOOK = "book", "图书"
    JOURNAL_ARTICLE = "journal_article", "期刊论文"
    THESIS = "thesis", "学位论文"
    REPORT = "report", "研究报告"


class PublicationState(models.TextChoices):
    DRAFT = "draft", "草稿"
    READY = "ready", "待发布"
    PUBLISHED = "published", "已发布"
    WITHDRAWN = "withdrawn", "已下架"


class OcrStatus(models.TextChoices):
    NOT_REQUIRED = "not_required", "无需 OCR"
    PENDING = "pending", "等待 OCR"
    RUNNING = "running", "OCR 处理中"
    SUCCEEDED = "succeeded", "OCR 已完成"
    FAILED = "failed", "OCR 失败"
    DISABLED = "disabled", "OCR 已停用"


class SemanticIndexStatus(models.TextChoices):
    NOT_INDEXED = "not_indexed", "尚未建立"
    PENDING = "pending", "等待建立"
    RUNNING = "running", "正在建立"
    READY = "ready", "已就绪"
    FAILED = "failed", "建立失败"


class PageLabelStatus(models.TextChoices):
    PENDING = "pending", "等待识别"
    READY = "ready", "已就绪"
    NEEDS_REVIEW = "needs_review", "需要校对"


class ReviewStatus(models.TextChoices):
    NOT_STARTED = "not_started", "尚未复核"
    IN_PROGRESS = "in_progress", "复核中"
    COMPLETED = "completed", "复核完成"


class ReaderRenditionPolicy(models.TextChoices):
    AUTO = "auto", "自动选择"
    ORIGINAL = "original", "强制原始 PDF"
    OCR = "ocr", "强制 OCR PDF"


class RelationReviewStatus(models.TextChoices):
    SUGGESTED = "suggested", "系统建议"
    APPROVED = "approved", "人工确认"
    REJECTED = "rejected", "人工拒绝"


class RelationStrength(models.TextChoices):
    HIGH = "high", "高"
    MEDIUM = "medium", "中"
    LOW = "low", "低"


class WorkTheoryRole(models.TextChoices):
    FOUNDATIONAL = "foundational", "奠基文献"
    DEVELOPMENT = "development", "理论发展"
    INTRODUCTION = "introduction", "入门综述"
    EMPIRICAL = "empirical_application", "经验应用"
    METHOD = "method_use", "方法使用"
    CRITICISM = "criticism", "理论批评"
    HISTORY = "theory_history", "理论史研究"
    MENTION = "local_mention", "局部提及"


class KnowledgePublicationStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PENDING = "pending", "待审核"
    PUBLISHED = "published", "已发布"
    REJECTED = "rejected", "已拒绝"
    ARCHIVED = "archived", "已归档"


class Work(UUIDTimeStampedModel):
    document_type = models.CharField(max_length=32, choices=DocumentType.choices, db_index=True)
    title = models.CharField(max_length=600)
    subtitle = models.CharField(max_length=600, blank=True)
    original_title = models.CharField(max_length=600, blank=True)
    uniform_title = models.CharField(max_length=600, blank=True)
    normalized_title = models.CharField(max_length=600, blank=True, db_index=True)
    search_aliases = models.JSONField(default=list, blank=True)
    abstract = models.TextField(blank=True)
    language = models.CharField(max_length=16, default="zh-CN")
    original_language = models.CharField(max_length=32, blank=True)
    first_publication_date = models.DateField(null=True, blank=True, db_index=True)
    translation_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="translations",
    )
    cover = models.ImageField(upload_to="public/covers/%Y/%m/", blank=True)
    recommendation_image = models.ImageField(
        upload_to="public/recommendations/%Y/%m/",
        blank=True,
    )
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["title"]
        indexes = [models.Index(fields=["document_type", "normalized_title"])]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("translation_of_id")),
                name="work_translation_not_self",
            ),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        from catalog.services.aliases import search_aliases

        self.normalized_title = self.title.casefold().strip()
        self.search_aliases = search_aliases(
            self.title,
            self.subtitle,
            self.original_title,
            self.uniform_title,
            *self.search_aliases,
        )
        super().save(*args, **kwargs)

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        current = self.translation_of
        seen = {self.pk} if self.pk else set()
        while current is not None:
            if current.pk in seen:
                raise ValidationError({"translation_of": "译作关系不能形成循环。"})
            seen.add(current.pk)
            current = current.translation_of


class Edition(UUIDTimeStampedModel):
    work = models.ForeignKey(Work, on_delete=models.PROTECT, related_name="editions")
    version_label = models.CharField(max_length=120, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    publisher = models.CharField(max_length=300, blank=True)
    publication_place = models.CharField(max_length=200, blank=True)
    publisher_authority = models.ForeignKey(
        "PublisherAuthority",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="editions",
    )
    distribution_place = models.CharField(max_length=200, blank=True)
    distributor = models.CharField(max_length=300, blank=True)
    manufacture_place = models.CharField(max_length=200, blank=True)
    manufacturer = models.CharField(max_length=300, blank=True)
    journal_title = models.CharField(max_length=300, blank=True)
    volume = models.CharField(max_length=40, blank=True)
    issue = models.CharField(max_length=40, blank=True)
    page_range = models.CharField(max_length=80, blank=True)
    degree_institution = models.CharField(max_length=300, blank=True)
    degree_type = models.CharField(max_length=120, blank=True)
    report_institution = models.CharField(max_length=300, blank=True)
    isbn = models.CharField(max_length=32, blank=True, db_index=True)
    isbn10 = models.CharField(max_length=20, blank=True, db_index=True)
    isbn13 = models.CharField(max_length=20, blank=True, db_index=True)
    doi = models.CharField(max_length=255, blank=True, db_index=True)
    series = models.CharField(max_length=300, blank=True)
    extent = models.CharField(max_length=160, blank=True)
    responsibility_statement = models.TextField(blank=True)
    metadata_confidence = models.FloatField(default=0)
    citation_data = models.JSONField(default=dict, blank=True)
    canonical_filename = models.CharField(max_length=800, blank=True)
    public_slug = models.SlugField(max_length=180, unique=True, null=True, blank=True)
    state = models.CharField(
        max_length=20,
        choices=PublicationState.choices,
        default=PublicationState.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    first_published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    search_indexed_at = models.DateTimeField(null=True, blank=True)
    public_asset_prepared_at = models.DateTimeField(null=True, blank=True)
    ocr_status = models.CharField(
        max_length=20,
        choices=OcrStatus.choices,
        default=OcrStatus.PENDING,
        db_index=True,
    )
    semantic_index_status = models.CharField(
        max_length=20,
        choices=SemanticIndexStatus.choices,
        default=SemanticIndexStatus.NOT_INDEXED,
        db_index=True,
    )
    page_label_status = models.CharField(
        max_length=20,
        choices=PageLabelStatus.choices,
        default=PageLabelStatus.PENDING,
        db_index=True,
    )
    review_status = models.CharField(
        max_length=20,
        choices=ReviewStatus.choices,
        default=ReviewStatus.NOT_STARTED,
        db_index=True,
    )
    review_progress = models.PositiveSmallIntegerField(default=0)
    reader_rendition_policy = models.CharField(
        max_length=20,
        choices=ReaderRenditionPolicy.choices,
        default=ReaderRenditionPolicy.AUTO,
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        ordering = ["-publication_year", "work__title"]

    def __str__(self):
        return f"{self.work.title} ({self.publication_year or '未定年'})"

    @property
    def edition_statement(self):
        """Compatibility name for the existing version-label storage."""

        return self.version_label

    @edition_statement.setter
    def edition_statement(self, value):
        self.version_label = value

    @property
    def publisher_verbatim(self):
        """The legacy publisher field already stores the transcribed value."""

        return self.publisher

    @publisher_verbatim.setter
    def publisher_verbatim(self, value):
        self.publisher = value

    @property
    def publication_place_verbatim(self):
        """The legacy publication-place field already stores the transcribed value."""

        return self.publication_place

    @publication_place_verbatim.setter
    def publication_place_verbatim(self, value):
        self.publication_place = value


def asset_upload_path(instance, filename):
    root = "archive" if instance.kind == Asset.Kind.ORIGINAL else "public"
    return f"{root}/{instance.edition_id}/{filename}"


class Asset(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "原始文件"
        NORMALIZED = "normalized", "规范阅读文件"
        OCR_PDF = "ocr_pdf", "OCR 阅读文件"
        WEB_DERIVATIVE = "web_derivative", "网页阅读派生文件"

    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "等待验证"
        VALID = "valid", "验证通过"
        INVALID = "invalid", "验证失败"

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        PROCESSING = "processing", "处理中"
        READY = "ready", "就绪"
        FAILED = "failed", "失败"
        WITHDRAWN = "withdrawn", "已下架"

    class AccessStatus(models.TextChoices):
        INHERIT = "inherit", "继承版本权限"
        PRIVATE = "private", "仅后台可用"
        REGISTERED = "registered", "登录读者"
        RESTRICTED = "restricted", "受限访问"
        PUBLIC = "public", "公开访问"

    edition = models.ForeignKey(Edition, on_delete=models.PROTECT, related_name="assets")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    file = models.FileField(upload_to=asset_upload_path, max_length=1000)
    original_filename = models.CharField(max_length=1000, blank=True)
    mime_type = models.CharField(max_length=255, blank=True)
    sha256 = models.CharField(max_length=64, db_index=True)
    byte_size = models.BigIntegerField(default=0)
    page_count = models.PositiveIntegerField(default=0)
    text_layer_quality = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    language_guess = models.CharField(max_length=32, blank=True)
    access_status = models.CharField(
        max_length=20,
        choices=AccessStatus.choices,
        default=AccessStatus.INHERIT,
        db_index=True,
    )
    rights_note = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    extraction_method = models.CharField(max_length=30, blank=True)
    is_current = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    source_asset = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="derivatives",
    )
    processor = models.CharField(max_length=120, blank=True)
    processor_version = models.CharField(max_length=120, blank=True)
    validation_status = models.CharField(
        max_length=20,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
        db_index=True,
    )
    validation_details = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["sha256", "kind"], name="unique_asset_hash_per_kind"),
        ]
        indexes = [models.Index(fields=["edition", "kind", "is_current"])]


class Page(UUIDTimeStampedModel):
    class TextSource(models.TextChoices):
        NONE = "none", "尚无文字"
        EMBEDDED = "embedded", "PDF 原生文本"
        OCR = "ocr", "OCR"
        HYBRID = "hybrid", "混合"

    class LabelSource(models.TextChoices):
        MANUAL = "manual", "人工校对"
        PDF_PAGE_LABELS = "pdf_page_labels", "PDF PageLabels"
        EMBEDDED_TEXT = "embedded_text", "PDF 原生页眉页脚"
        OCR = "ocr", "OCR 识别"
        SEQUENCE = "sequence", "序列推算"
        FILE_INDEX = "file_index", "PDF 页序回退"
        UNKNOWN = "unknown", "未知"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="pages")
    index = models.PositiveIntegerField(help_text="从 1 开始的 PDF 页序")
    printed_label = models.CharField(max_length=40, blank=True)
    chapter_title = models.CharField(max_length=600, blank=True)
    text = models.TextField(blank=True)
    normalized_text = models.TextField(blank=True)
    text_source = models.CharField(max_length=16, choices=TextSource.choices)
    confidence = models.FloatField(default=1)
    label_source = models.CharField(
        max_length=24,
        choices=LabelSource.choices,
        default=LabelSource.UNKNOWN,
        db_index=True,
    )
    label_confidence = models.FloatField(default=0)
    is_label_manual = models.BooleanField(default=False)
    is_label_anchor = models.BooleanField(default=False)
    label_segment = models.CharField(max_length=80, blank=True)
    width = models.FloatField(default=0)
    height = models.FloatField(default=0)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["asset", "index"], name="unique_page_index_per_asset"),
        ]


class TextBlock(UUIDTimeStampedModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="blocks")
    order = models.PositiveIntegerField()
    block_type = models.CharField(max_length=30, default="paragraph")
    text = models.TextField()
    normalized_text = models.TextField(blank=True)
    bbox = models.JSONField(default=list)
    confidence = models.FloatField(default=1)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["page", "order"], name="unique_block_order_per_page"),
        ]


class Passage(UUIDTimeStampedModel):
    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="passages")
    order = models.PositiveIntegerField()
    text = models.TextField()
    normalized_text = models.TextField(blank=True, db_index=True)
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    bbox_union = models.JSONField(default=list)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["page", "order"], name="unique_passage_order_per_page"),
        ]


class SemanticChunk(UUIDTimeStampedModel):
    class IndexStatus(models.TextChoices):
        PENDING = "pending", "待建立"
        INDEXING = "indexing", "索引中"
        READY = "ready", "已建立"
        FAILED = "failed", "失败"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="semantic_chunks")
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="semantic_chunks")
    order = models.PositiveIntegerField()
    page_start = models.PositiveIntegerField()
    page_end = models.PositiveIntegerField()
    chapter_title = models.CharField(max_length=600, blank=True)
    section_title = models.CharField(max_length=600, blank=True)
    paragraph_index = models.PositiveIntegerField(default=0)
    original_text = models.TextField()
    normalized_text = models.TextField(db_index=True)
    context_before = models.TextField(blank=True)
    context_after = models.TextField(blank=True)
    language = models.CharField(max_length=16, blank=True)
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    parser_version = models.CharField(max_length=40)
    chunk_version = models.CharField(max_length=40)
    embedding_model = models.CharField(max_length=240, blank=True)
    embedding_version = models.CharField(max_length=80, blank=True)
    document_id = models.CharField(max_length=64, unique=True, editable=False)
    content_hash = models.CharField(max_length=64, db_index=True)
    locators = models.JSONField(default=list, blank=True)
    quality_flags = models.JSONField(default=list, blank=True)
    index_status = models.CharField(
        max_length=20,
        choices=IndexStatus.choices,
        default=IndexStatus.PENDING,
        db_index=True,
    )
    index_error = models.TextField(blank=True)
    indexed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "chunk_version", "order"],
                name="unique_semantic_chunk_order",
            ),
        ]
        indexes = [
            models.Index(fields=["asset", "index_status"]),
            models.Index(fields=["work", "page_start"]),
        ]


class SemanticIndexJob(UUIDTimeStampedModel):
    class Operation(models.TextChoices):
        BUILD = "build", "建立索引"
        REBUILD = "rebuild", "重新建立"
        CLEAN = "clean", "清理孤立索引"
        TEST = "test", "测试查询"

    class Status(models.TextChoices):
        QUEUED = "queued", "等待处理"
        RUNNING = "running", "处理中"
        PAUSED = "paused", "已暂停"
        COMPLETED = "completed", "完成"
        PARTIAL = "partial", "部分完成"
        FAILED = "failed", "失败"
        CANCELED = "canceled", "已取消"

    operation = models.CharField(max_length=20, choices=Operation.choices)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="semantic_index_jobs",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    index_version = models.ForeignKey(
        "SemanticIndexVersion",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="jobs",
    )
    task_id = models.CharField(max_length=255, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    attempts = models.PositiveSmallIntegerField(default=0)
    model_name = models.CharField(max_length=240, blank=True)
    chunk_version = models.CharField(max_length=40, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    stats = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    pause_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "created_at"])]


class SemanticIndexVersion(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        BUILDING = "building", "正在建立"
        READY = "ready", "等待切换"
        ACTIVE = "active", "生产使用中"
        FAILED = "failed", "建立失败"
        RETIRED = "retired", "已停用"

    uid = models.CharField(max_length=255, unique=True)
    provider = models.CharField(max_length=40)
    model_repo_id = models.CharField(max_length=300, blank=True)
    model_local_path = models.CharField(max_length=1000, blank=True)
    model_revision = models.CharField(max_length=160, blank=True)
    dimensions = models.PositiveIntegerField(null=True, blank=True)
    pooling = models.CharField(max_length=40, blank=True)
    document_template = models.TextField(blank=True)
    config_snapshot = models.JSONField(default=dict, blank=True)
    document_count = models.PositiveIntegerField(default=0)
    expected_document_count = models.PositiveIntegerField(default=0)
    validation_details = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.BUILDING,
        db_index=True,
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class PageLabelSegment(UUIDTimeStampedModel):
    class Style(models.TextChoices):
        ARABIC = "arabic", "阿拉伯数字"
        ROMAN_LOWER = "roman_lower", "小写罗马数字"
        ROMAN_UPPER = "roman_upper", "大写罗马数字"
        CUSTOM = "custom", "自定义"
        NONE = "none", "无页码"

    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="page_label_segments")
    start_file_page_index = models.PositiveIntegerField()
    end_file_page_index = models.PositiveIntegerField(null=True, blank=True)
    start_label = models.CharField(max_length=40, blank=True)
    style = models.CharField(max_length=20, choices=Style.choices, default=Style.ARABIC)
    source = models.CharField(
        max_length=24,
        choices=Page.LabelSource.choices,
        default=Page.LabelSource.MANUAL,
    )
    confidence = models.FloatField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_page_label_segments",
    )

    class Meta:
        ordering = ["start_file_page_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "start_file_page_index"],
                name="unique_page_label_segment_start",
            ),
        ]


class SemanticSearchFeedback(UUIDTimeStampedModel):
    chunk = models.ForeignKey(
        SemanticChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    query_hash = models.CharField(max_length=64, db_index=True)
    # Empty values are retained for historical records whose actor cannot be
    # reconstructed. New public feedback stores an irreversible per-actor,
    # per-query and per-result key so repeated clicks update one vote instead
    # of inflating the calibration sample.
    feedback_key = models.CharField(max_length=64, blank=True, db_index=True)
    query_text = models.TextField(blank=True)
    chunk_document_id = models.CharField(max_length=64, blank=True, db_index=True)
    relevant = models.BooleanField()
    result_rank = models.PositiveSmallIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["query_hash", "relevant"])]
        constraints = [
            models.UniqueConstraint(
                fields=["feedback_key"],
                condition=~models.Q(feedback_key=""),
                name="unique_nonempty_semantic_feedback_key",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.chunk_id:
            self.chunk_document_id = self.chunk.document_id
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"chunk_document_id"}
        super().save(*args, **kwargs)


class SearchEvaluationSet(UUIDTimeStampedModel):
    name = models.CharField(max_length=240, unique=True)
    description = models.TextField(blank=True)
    language = models.CharField(max_length=32, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_search_evaluation_sets",
    )

    class Meta:
        ordering = ["name"]


class SearchEvaluationQuery(UUIDTimeStampedModel):
    evaluation_set = models.ForeignKey(
        SearchEvaluationSet,
        on_delete=models.CASCADE,
        related_name="queries",
    )
    query_text = models.TextField()
    normalized_query = models.TextField(blank=True)
    filters = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation_set", "order"],
                name="unique_search_eval_query_order",
            ),
        ]


class SearchEvaluationJudgment(UUIDTimeStampedModel):
    class Relevance(models.IntegerChoices):
        NOT_RELEVANT = 0, "不相关"
        TOPIC_ONLY = 1, "同主题但未回应"
        RELEVANT = 2, "具有实质证据价值"
        HIGHLY_RELEVANT = 3, "直接回应问题"

    query = models.ForeignKey(
        SearchEvaluationQuery,
        on_delete=models.CASCADE,
        related_name="judgments",
    )
    chunk = models.ForeignKey(
        SemanticChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluation_judgments",
    )
    chunk_document_id = models.CharField(max_length=64, db_index=True)
    relevance = models.PositiveSmallIntegerField(
        choices=Relevance.choices,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
    )
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_search_evaluation_judgments",
    )

    class Meta:
        ordering = ["query__order", "-relevance"]
        constraints = [
            models.UniqueConstraint(
                fields=["query", "chunk_document_id"],
                name="unique_search_eval_judgment",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.chunk_id:
            self.chunk_document_id = self.chunk.document_id
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"chunk_document_id"}
        super().save(*args, **kwargs)


class SearchEvaluationRun(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "等待运行"
        RUNNING = "running", "运行中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"

    evaluation_set = models.ForeignKey(
        SearchEvaluationSet,
        on_delete=models.PROTECT,
        related_name="runs",
    )
    index_version = models.ForeignKey(
        SemanticIndexVersion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluation_runs",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    engine = models.CharField(max_length=80, blank=True)
    semantic_ratio = models.FloatField(
        default=0.72,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    config_snapshot = models.JSONField(default=dict, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    query_count = models.PositiveIntegerField(default=0)
    completed_query_count = models.PositiveIntegerField(default=0)
    task_id = models.CharField(max_length=255, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_search_evaluation_runs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["evaluation_set", "status", "created_at"])]


class SearchEvaluationResult(UUIDTimeStampedModel):
    run = models.ForeignKey(
        SearchEvaluationRun,
        on_delete=models.CASCADE,
        related_name="results",
    )
    query = models.ForeignKey(
        SearchEvaluationQuery,
        on_delete=models.PROTECT,
        related_name="results",
    )
    retrieved_chunk = models.ForeignKey(
        SemanticChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evaluation_results",
    )
    retrieved_document_id = models.CharField(max_length=64, blank=True, db_index=True)
    rank = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    keyword_score = models.FloatField(null=True, blank=True)
    semantic_score = models.FloatField(null=True, blank=True)
    final_score = models.FloatField(null=True, blank=True)
    relevance_grade = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
    )
    latency_ms = models.PositiveIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["query__order", "rank"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "query", "rank"],
                name="unique_search_eval_result_rank",
            ),
        ]
        indexes = [models.Index(fields=["run", "query", "rank"])]

    def save(self, *args, **kwargs):
        if self.retrieved_chunk_id:
            self.retrieved_document_id = self.retrieved_chunk.document_id
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {"retrieved_document_id"}
        super().save(*args, **kwargs)


class PublisherAuthority(UUIDTimeStampedModel):
    canonical_name = models.CharField(max_length=300, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    possible_places = models.JSONField(default=list, blank=True)
    country = models.CharField(max_length=120, blank=True)
    valid_from = models.PositiveSmallIntegerField(null=True, blank=True)
    valid_to = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["canonical_name"]


class OrganizationAuthority(UUIDTimeStampedModel):
    class OrganizationType(models.TextChoices):
        UNIVERSITY = "university", "高校"
        RESEARCH_INSTITUTE = "research_institute", "研究机构"
        ASSOCIATION = "association", "学会或协会"
        GOVERNMENT = "government", "政府机构"
        ARCHIVE = "archive", "档案或收藏机构"
        OTHER = "other", "其他机构"

    class AuthorityStatus(models.TextChoices):
        DRAFT = "draft", "草稿"
        NEEDS_REVIEW = "needs_review", "待消歧"
        VERIFIED = "verified", "已核验"
        REJECTED = "rejected", "已拒绝"
        MERGED = "merged", "已合并"
        ARCHIVED = "archived", "已归档"

    preferred_name = models.CharField(max_length=300, db_index=True)
    original_name = models.CharField(max_length=300, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    organization_type = models.CharField(
        max_length=32,
        choices=OrganizationType.choices,
        default=OrganizationType.OTHER,
        db_index=True,
    )
    country = models.CharField(max_length=120, blank=True)
    external_ids = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    authority_status = models.CharField(
        max_length=20,
        choices=AuthorityStatus.choices,
        default=AuthorityStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ["preferred_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["preferred_name", "organization_type"],
                name="unique_organization_authority_name_type",
            ),
        ]


class OrganizationContribution(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        DEGREE_GRANTING = "degree_granting", "学位授予单位"
        REPORT_ISSUER = "report_issuer", "报告发布机构"
        SPONSOR = "sponsor", "主办机构"
        ISSUING_BODY = "issuing_body", "责任机构"
        ARCHIVE = "archive", "收藏机构"

    edition = models.ForeignKey(
        Edition,
        on_delete=models.CASCADE,
        related_name="organization_contributions",
    )
    organization = models.ForeignKey(
        OrganizationAuthority,
        on_delete=models.PROTECT,
        related_name="contributions",
    )
    role = models.CharField(max_length=32, choices=Role.choices)
    verbatim_name = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=1)
    approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["role", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "organization", "role"],
                name="unique_organization_contribution",
            ),
        ]


class PublicationPlaceEvidence(UUIDTimeStampedModel):
    class PlaceType(models.TextChoices):
        PUBLICATION = "publication_place", "出版地"
        PRODUCTION = "production_place", "制作地"
        DISTRIBUTION = "distribution_place", "发行地"
        PRINTING = "printing_place", "印刷地"
        PUBLISHER_ADDRESS = "publisher_address", "出版社地址"
        DEGREE = "degree_place", "学位授予单位所在地"
        ARCHIVE = "archive_location", "档案收藏地"

    class VerificationStatus(models.TextChoices):
        AUTO_CONFIRMED = "auto_confirmed", "自动确认"
        NEEDS_REVIEW = "needs_review", "待人工确认"
        MANUALLY_CONFIRMED = "manually_confirmed", "人工确认"
        MANUALLY_CORRECTED = "manually_corrected", "人工修改"
        UNKNOWN = "unknown", "未知"

    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="publication_place_evidence")
    asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="publication_place_evidence",
    )
    raw_value = models.CharField(max_length=300, blank=True)
    normalized_value = models.CharField(max_length=300, blank=True)
    city = models.CharField(max_length=200, blank=True)
    province_or_state = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=16, blank=True)
    place_type = models.CharField(max_length=32, choices=PlaceType.choices)
    source_type = models.CharField(max_length=80)
    source_provider = models.CharField(max_length=120, blank=True)
    source_record_id = models.CharField(max_length=255, blank=True)
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_text = models.TextField(blank=True)
    confidence = models.FloatField(default=0)
    verification_status = models.CharField(
        max_length=32,
        choices=VerificationStatus.choices,
        default=VerificationStatus.NEEDS_REVIEW,
        db_index=True,
    )
    is_primary = models.BooleanField(default=False)
    display_order = models.PositiveSmallIntegerField(default=0)
    publisher_raw = models.CharField(max_length=300, blank=True)
    publication_year = models.PositiveSmallIntegerField(null=True, blank=True)
    relation = models.CharField(max_length=40, default="publication")
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["display_order", "-confidence", "created_at"]
        indexes = [
            models.Index(fields=["edition", "place_type", "verification_status"]),
        ]


class PublicationMetadataRevision(UUIDTimeStampedModel):
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="publication_metadata_revisions")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


def cover_candidate_upload_path(instance, filename):
    return f"incoming/cover-candidates/{instance.work_id}/{instance.asset_id}/{filename}"


class CoverCandidate(UUIDTimeStampedModel):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="cover_candidates")
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="cover_candidates")
    page_index = models.PositiveIntegerField()
    thumbnail = models.ImageField(upload_to=cover_candidate_upload_path, max_length=1000)
    score = models.FloatField(default=0)
    reasons = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    selected = models.BooleanField(default=False)

    class Meta:
        ordering = ["-score", "page_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "page_index"],
                name="unique_cover_candidate_page",
            ),
        ]


class Person(UUIDTimeStampedModel):
    class AuthorityStatus(models.TextChoices):
        DRAFT = "draft", "草稿"
        NEEDS_REVIEW = "needs_review", "待消歧"
        VERIFIED = "verified", "已核验"
        REJECTED = "rejected", "已拒绝"
        MERGED = "merged", "已合并"
        ARCHIVED = "archived", "已归档"

    preferred_name = models.CharField(max_length=240, db_index=True)
    sort_name = models.CharField(max_length=240, blank=True)
    original_name = models.CharField(max_length=240, blank=True)
    aliases = models.JSONField(default=list, blank=True)
    birth_year = models.PositiveSmallIntegerField(null=True, blank=True)
    death_year = models.PositiveSmallIntegerField(null=True, blank=True)
    biography = models.TextField(blank=True)
    portrait = models.ImageField(upload_to="public/people/%Y/%m/", blank=True)
    external_ids = models.JSONField(default=dict, blank=True)
    authority_status = models.CharField(
        max_length=20,
        choices=AuthorityStatus.choices,
        default=AuthorityStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ["sort_name", "preferred_name"]

    def __str__(self):
        return self.preferred_name

    def save(self, *args, **kwargs):
        from catalog.services.aliases import search_aliases

        self.aliases = search_aliases(
            self.preferred_name,
            self.original_name,
            *self.aliases,
        )
        super().save(*args, **kwargs)


class ScholarProfile(UUIDTimeStampedModel):
    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="scholar_profile")
    slug = models.SlugField(max_length=180, unique=True)
    short_description = models.CharField(max_length=400, blank=True)
    affiliations = models.JSONField(default=list, blank=True)
    key_concerns = models.JSONField(default=list, blank=True)
    timeline = models.JSONField(default=list, blank=True)
    featured_quote = models.TextField(blank=True)
    quote_source = models.CharField(max_length=500, blank=True)
    curation = models.JSONField(default=dict, blank=True)
    editorial_status = models.CharField(max_length=20, default="draft")


class Contribution(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        AUTHOR = "author", "作者"
        EDITOR = "editor", "编者"
        TRANSLATOR = "translator", "译者"
        ADVISOR = "advisor", "导师"
        SUBJECT = "subject", "研究对象"

    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="contributions")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="contributions")
    role = models.CharField(max_length=20, choices=Role.choices)
    order = models.PositiveSmallIntegerField(default=0)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=1)
    approved = models.BooleanField(default=False)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["edition", "person", "role"], name="unique_contribution"),
        ]


class NamedKnowledgeObject(UUIDTimeStampedModel):
    name = models.CharField(max_length=240, unique=True)
    slug = models.SlugField(max_length=180, unique=True)
    search_aliases = models.JSONField(default=list, blank=True)
    description = models.TextField(blank=True)
    hero_image = models.ImageField(upload_to="public/knowledge/%Y/%m/", blank=True)
    editorial_status = models.CharField(max_length=20, default="draft")

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from catalog.services.aliases import search_aliases

        self.search_aliases = search_aliases(self.name, *self.search_aliases)
        super().save(*args, **kwargs)


class Discipline(NamedKnowledgeObject):
    code = models.SlugField(max_length=80, unique=True)
    foreign_name = models.CharField(max_length=240, blank=True)
    introduction = models.TextField(blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    curation_level = models.PositiveSmallIntegerField(default=0)

    class Meta(NamedKnowledgeObject.Meta):
        ordering = ["sort_order", "name"]


class TheorySchool(NamedKnowledgeObject):
    class EntityLevel(models.TextChoices):
        TRADITION = "tradition", "理论传统"
        SCHOOL = "school", "流派"
        BRANCH = "branch", "分支"

    symbol = models.CharField(max_length=80, blank=True)
    foreign_name = models.CharField(max_length=240, blank=True)
    entity_level = models.CharField(
        max_length=20,
        choices=EntityLevel.choices,
        default=EntityLevel.TRADITION,
    )
    formation_period = models.CharField(max_length=160, blank=True)
    core_questions = models.JSONField(default=list, blank=True)
    key_themes = models.JSONField(default=list, blank=True)
    curation_level = models.PositiveSmallIntegerField(default=0)
    curation = models.JSONField(default=dict, blank=True)


class Topic(NamedKnowledgeObject):
    problem_statement = models.TextField(blank=True)
    core_questions = models.JSONField(default=list, blank=True)
    research_dimensions = models.JSONField(default=list, blank=True)
    methods = models.JSONField(default=list, blank=True)
    formation_context = models.TextField(blank=True)
    key_concepts = models.JSONField(default=list, blank=True)
    timeline = models.JSONField(default=list, blank=True)
    curation_level = models.PositiveSmallIntegerField(default=0)
    curation = models.JSONField(default=dict, blank=True)


class Concept(NamedKnowledgeObject):
    definition = models.TextField(blank=True)


class Subdiscipline(NamedKnowledgeObject):
    discipline = models.ForeignKey(
        Discipline,
        on_delete=models.PROTECT,
        related_name="subdisciplines",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    foreign_name = models.CharField(max_length=240, blank=True)
    research_object = models.TextField(blank=True)
    core_questions = models.JSONField(default=list, blank=True)
    formation_period = models.CharField(max_length=160, blank=True)
    research_directions = models.JSONField(default=list, blank=True)
    methods = models.JSONField(default=list, blank=True)
    representative_issues = models.JSONField(default=list, blank=True)
    curation_level = models.PositiveSmallIntegerField(default=0)


class TheoryDisciplineRelation(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "主要学科"
        RELATED = "related", "相关学科"

    theory_school = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="discipline_relations",
    )
    discipline = models.ForeignKey(
        Discipline,
        on_delete=models.CASCADE,
        related_name="theory_relations",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RELATED)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_theory_disciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["theory_school", "discipline"],
                name="unique_theory_discipline",
            ),
        ]


class TheoryHierarchyRelation(UUIDTimeStampedModel):
    parent = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="child_relations",
    )
    child = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="parent_relations",
    )
    source = models.CharField(max_length=120, blank=True)
    evidence_text = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_theory_hierarchies",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "child"],
                name="unique_theory_hierarchy",
            ),
        ]


class TheoryRelation(UUIDTimeStampedModel):
    class RelationType(models.TextChoices):
        INFLUENCE = "influence", "影响"
        CONTINUATION = "continuation", "继承"
        SPLIT = "split", "分化"
        CRITIQUE = "critique", "批评"
        SYNTHESIS = "synthesis", "综合"
        ADJACENT = "adjacent", "相邻"

    source_theory = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="outgoing_relations",
    )
    target_theory = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="incoming_relations",
    )
    relation_type = models.CharField(max_length=24, choices=RelationType.choices)
    strength = models.CharField(
        max_length=16,
        choices=RelationStrength.choices,
        default=RelationStrength.MEDIUM,
    )
    source = models.CharField(max_length=120, blank=True)
    evidence_work = models.ForeignKey(
        Work,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theory_relation_evidence",
    )
    evidence_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theory_relation_evidence",
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_printed_label = models.CharField(max_length=40, blank=True)
    evidence_text = models.TextField(blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_theory_relations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["source_theory", "target_theory", "relation_type"],
                name="unique_theory_relation",
            ),
        ]


class TheorySubdisciplineRelation(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        CORE = "core", "核心理论"
        RELATED = "related", "相关理论"
        APPLIED = "applied", "常用理论"

    theory_school = models.ForeignKey(
        TheorySchool,
        on_delete=models.CASCADE,
        related_name="subdiscipline_relations",
    )
    subdiscipline = models.ForeignKey(
        Subdiscipline,
        on_delete=models.CASCADE,
        related_name="theory_relations",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.RELATED)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_theory_subdisciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["theory_school", "subdiscipline"],
                name="unique_theory_subdiscipline",
            ),
        ]


class TopicDisciplineRelation(UUIDTimeStampedModel):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="discipline_relations")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="topic_relations")
    is_primary = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_topic_disciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["topic", "discipline"], name="unique_topic_discipline"),
        ]


class TopicTheoryRelation(UUIDTimeStampedModel):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="theory_relations")
    theory_school = models.ForeignKey(TheorySchool, on_delete=models.CASCADE, related_name="topic_relations")
    relation_label = models.CharField(max_length=120, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_topic_theories",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["topic", "theory_school"], name="unique_topic_theory"),
        ]


class TopicSubdisciplineRelation(UUIDTimeStampedModel):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="subdiscipline_relations")
    subdiscipline = models.ForeignKey(Subdiscipline, on_delete=models.CASCADE, related_name="topic_relations")
    relation_label = models.CharField(max_length=120, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_topic_subdisciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["topic", "subdiscipline"], name="unique_topic_subdiscipline"),
        ]


class WorkKnowledgeRelation(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        THEORY_SCHOOL = "theory_school", "理论流派"
        TOPIC = "topic", "主题"
        CONCEPT = "concept", "概念"

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="knowledge_relations")
    kind = models.CharField(max_length=24, choices=Kind.choices)
    theory_school = models.ForeignKey(TheorySchool, null=True, blank=True, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.CASCADE)
    concept = models.ForeignKey(Concept, null=True, blank=True, on_delete=models.CASCADE)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    approved = models.BooleanField(default=False)
    is_primary = models.BooleanField(default=False)
    role = models.CharField(max_length=32, choices=WorkTheoryRole.choices, blank=True)
    strength = models.CharField(
        max_length=16,
        choices=RelationStrength.choices,
        default=RelationStrength.MEDIUM,
    )
    evidence_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_knowledge_evidence",
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_printed_label = models.CharField(max_length=40, blank=True)
    evidence_text = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_work_knowledge_relations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["work", "kind", "approved"])]


class PersonKnowledgeRelation(UUIDTimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="knowledge_relations")
    theory_school = models.ForeignKey(TheorySchool, null=True, blank=True, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.CASCADE)
    concept = models.ForeignKey(Concept, null=True, blank=True, on_delete=models.CASCADE)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    approved = models.BooleanField(default=False)
    relation_label = models.CharField(max_length=120, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_person_knowledge_relations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)


class WorkSubdisciplineRelation(UUIDTimeStampedModel):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="subdiscipline_relations")
    subdiscipline = models.ForeignKey(Subdiscipline, on_delete=models.CASCADE, related_name="work_relations")
    is_primary = models.BooleanField(default=False)
    strength = models.CharField(
        max_length=16,
        choices=RelationStrength.choices,
        default=RelationStrength.MEDIUM,
    )
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    evidence_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_subdiscipline_evidence",
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_printed_label = models.CharField(max_length=40, blank=True)
    evidence_text = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_work_subdisciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work", "subdiscipline"], name="unique_work_subdiscipline"),
        ]


class WorkDisciplineRelation(UUIDTimeStampedModel):
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="discipline_relations")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="work_relations")
    is_primary = models.BooleanField(default=False)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    evidence_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_discipline_evidence",
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_printed_label = models.CharField(max_length=40, blank=True)
    evidence_text = models.TextField(blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_work_disciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work", "discipline"], name="unique_work_discipline"),
        ]


class PersonSubdisciplineRelation(UUIDTimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="subdiscipline_relations")
    subdiscipline = models.ForeignKey(Subdiscipline, on_delete=models.CASCADE, related_name="person_relations")
    relation_label = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_person_subdisciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person", "subdiscipline"], name="unique_person_subdiscipline"),
        ]


class PersonDisciplineRelation(UUIDTimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="discipline_relations")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="person_relations")
    is_primary = models.BooleanField(default=False)
    relation_label = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=120, blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_person_disciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person", "discipline"], name="unique_person_discipline"),
        ]


class TheoryTimelineEvent(UUIDTimeStampedModel):
    class EventType(models.TextChoices):
        SCHOLAR = "scholar", "学者"
        PUBLICATION = "publication", "重要发表"
        CONCEPT_PROPOSED = "concept_proposed", "理论概念提出"
        SCHOOL_FORMATION = "school_formation", "学派形成"
        DEBATE = "debate", "争论"
        INSTITUTION = "institution", "机构"
        THEORETICAL_TURN = "theoretical_turn", "理论转向"
        TRANSLATION = "translation", "重要译介"
        CHINA_RECEPTION = "china_reception", "进入中国学界"
        INSTITUTIONALIZATION = "institutionalization", "学科制度化"
        # 保留旧值，确保历史事件在迁移和回滚时仍可读取。
        FORMATION = "formation", "形成"
        DEVELOPMENT = "development", "发展"

    discipline = models.ForeignKey(
        Discipline,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timeline_events",
    )
    theory_school = models.ForeignKey(
        TheorySchool,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timeline_events",
    )
    subdiscipline = models.ForeignKey(
        Subdiscipline,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timeline_events",
    )
    scholar = models.ForeignKey(
        ScholarProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theory_timeline_events",
    )
    work = models.ForeignKey(
        Work,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="theory_timeline_events",
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="public/knowledge/timeline/%Y/%m/", blank=True)
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    start_year = models.SmallIntegerField(null=True, blank=True, db_index=True)
    end_year = models.SmallIntegerField(null=True, blank=True)
    date_label = models.CharField(max_length=120, blank=True)
    orientation = models.CharField(max_length=20, default="neutral")
    source = models.CharField(max_length=120, blank=True)
    evidence_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="timeline_evidence",
    )
    evidence_page = models.PositiveIntegerField(null=True, blank=True)
    evidence_printed_label = models.CharField(max_length=40, blank=True)
    evidence_text = models.TextField(blank=True)
    confidence = models.FloatField(default=0)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_theory_timeline_events",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["start_year", "display_order", "title"]


class KnowledgeNode(UUIDTimeStampedModel):
    class NodeType(models.TextChoices):
        DISCIPLINE = "discipline", "学科"
        THEORY_TRADITION = "theory_tradition", "理论传统"
        SUBDISCIPLINE = "subdiscipline", "子学科"
        CONCEPT = "concept", "核心概念"
        DEBATE = "debate", "理论争论"
        RESEARCH_PROBLEM = "research_problem", "研究问题"
        TOPIC = "topic", "主题"

    node_type = models.CharField(max_length=32, choices=NodeType.choices, db_index=True)
    canonical_name_zh = models.CharField(max_length=240)
    canonical_name_en = models.CharField(max_length=240, blank=True)
    slug = models.SlugField(max_length=180, unique=True)
    summary = models.TextField(blank=True)
    definition = models.TextField(blank=True)
    core_questions = models.JSONField(default=list, blank=True)
    basic_propositions = models.JSONField(default=list, blank=True)
    theoretical_boundary = models.TextField(blank=True)
    start_year = models.SmallIntegerField(null=True, blank=True, db_index=True)
    end_year = models.SmallIntegerField(null=True, blank=True)
    period_label = models.CharField(max_length=160, blank=True)
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    primary_discipline = models.ForeignKey(
        Discipline,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="primary_knowledge_nodes",
    )
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.DRAFT,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    cover_asset = models.ImageField(upload_to="public/knowledge/nodes/%Y/%m/", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_knowledge_nodes",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_knowledge_nodes",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "canonical_name_zh"]
        indexes = [
            models.Index(fields=["node_type", "status", "sort_order"]),
            models.Index(fields=["primary_discipline", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("parent_id")),
                name="knowledge_node_parent_not_self",
            ),
        ]

    def __str__(self):
        return self.canonical_name_zh

    @property
    def scope_note(self):
        """Compatibility name for the existing theoretical-boundary field."""

        return self.theoretical_boundary

    @scope_note.setter
    def scope_note(self, value):
        self.theoretical_boundary = value

    def clean(self):
        from django.core.exceptions import ValidationError

        super().clean()
        current = self.parent
        seen = {self.pk} if self.pk else set()
        while current is not None:
            if current.pk in seen:
                raise ValidationError({"parent": "知识节点层级不能形成循环。"})
            seen.add(current.pk)
            current = current.parent


class KnowledgeNodeAlias(UUIDTimeStampedModel):
    class AliasType(models.TextChoices):
        ALIAS = "alias", "别名"
        TRANSLATION = "translation", "译名"
        ABBREVIATION = "abbreviation", "简称"
        HISTORICAL = "historical", "历史名称"

    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=240)
    language = models.CharField(max_length=16, default="zh-CN")
    alias_type = models.CharField(max_length=20, choices=AliasType.choices, default=AliasType.ALIAS)
    normalized_alias = models.CharField(max_length=240, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_knowledge_aliases",
    )

    class Meta:
        ordering = ["alias"]
        constraints = [
            models.UniqueConstraint(
                fields=["node", "normalized_alias"],
                name="unique_knowledge_node_alias",
            ),
        ]

    def save(self, *args, **kwargs):
        self.normalized_alias = " ".join(self.alias.casefold().split())
        super().save(*args, **kwargs)


class KnowledgeNodeDiscipline(UUIDTimeStampedModel):
    class RelationType(models.TextChoices):
        PRIMARY = "primary", "主要学科"
        RELATED = "related", "关联学科"
        TRANSFERRED = "transferred", "跨学科传播"

    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="discipline_links")
    discipline = models.ForeignKey(Discipline, on_delete=models.CASCADE, related_name="knowledge_node_links")
    relation_type = models.CharField(max_length=20, choices=RelationType.choices, default=RelationType.RELATED)
    discipline_specific_summary = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.PENDING,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_knowledge_node_disciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "discipline__sort_order", "discipline__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["node", "discipline"],
                name="unique_knowledge_node_discipline",
            ),
        ]


class KnowledgeRelation(UUIDTimeStampedModel):
    class RelationType(models.TextChoices):
        INHERITED_FROM = "inherited_from", "继承"
        REVISES = "revises", "修正"
        CRITICIZES = "criticizes", "批判"
        COMPETES_WITH = "competes_with", "竞争"
        SYNTHESIZES = "synthesizes", "综合"
        BRANCHES_FROM = "branches_from", "分化"
        BORROWS_CONCEPT_FROM = "borrows_concept_from", "概念借用"
        TRANSFERRED_TO = "transferred_to", "跨学科传播"
        INFLUENCED_BY = "influenced_by", "受到影响"
        OVERLAPS_WITH = "overlaps_with", "部分重叠"

    class Direction(models.TextChoices):
        DIRECTED = "directed", "有方向"
        UNDIRECTED = "undirected", "无方向"

    source_node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="outgoing_relations")
    target_node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="incoming_relations")
    relation_type = models.CharField(max_length=32, choices=RelationType.choices, db_index=True)
    direction = models.CharField(max_length=16, choices=Direction.choices, default=Direction.DIRECTED)
    description = models.TextField(blank=True)
    evidence_source = models.CharField(max_length=300, blank=True)
    confidence = models.FloatField(default=0)
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.PENDING,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_knowledge_relations",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_knowledge_relations",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["source_node", "status"]),
            models.Index(fields=["target_node", "status"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(source_node=models.F("target_node")),
                name="knowledge_relation_distinct_nodes",
            ),
            models.UniqueConstraint(
                fields=["source_node", "target_node", "relation_type"],
                name="unique_knowledge_relation",
            ),
        ]


class WorkNodeRelation(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        FOUNDATIONAL = "foundational_work", "奠基性原著"
        SYSTEMATIC_EXPOSITION = "systematic_exposition", "系统阐释"
        THEORETICAL_DEVELOPMENT = "theoretical_development", "理论发展"
        EMPIRICAL_APPLICATION = "empirical_application", "经验应用"
        COMPARATIVE_STUDY = "comparative_study", "比较研究"
        CRITIQUE = "critique", "批评反思"
        GENERAL_MENTION = "general_mention", "一般提及"

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="node_relations")
    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="work_relations")
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.GENERAL_MENTION, db_index=True)
    is_primary = models.BooleanField(default=False)
    strength = models.CharField(max_length=16, choices=RelationStrength.choices, default=RelationStrength.MEDIUM)
    confidence = models.FloatField(default=0)
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.PENDING,
        db_index=True,
    )
    source = models.CharField(max_length=160, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_work_node_relations",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_work_node_relations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["work", "status"]),
            models.Index(fields=["node", "role", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(fields=["work", "node", "role"], name="unique_work_node_role"),
        ]


class PersonNodeRelation(UUIDTimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="node_relations")
    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="person_relations")
    relation_label = models.CharField(max_length=120, blank=True)
    is_representative = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    confidence = models.FloatField(default=0)
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.PENDING,
        db_index=True,
    )
    source = models.CharField(max_length=160, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_person_node_relations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "person__sort_name", "person__preferred_name"]
        constraints = [
            models.UniqueConstraint(fields=["person", "node"], name="unique_person_knowledge_node"),
        ]


class EvidenceSnippet(UUIDTimeStampedModel):
    class ExtractionMethod(models.TextChoices):
        TEXT_LAYER = "text_layer", "PDF 文本层"
        OCR = "ocr", "OCR"
        MANUAL = "manual", "人工录入"
        EXTERNAL = "external", "外部来源"

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="knowledge_evidence")
    file = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="knowledge_evidence")
    node = models.ForeignKey(KnowledgeNode, null=True, blank=True, on_delete=models.CASCADE, related_name="evidence")
    work_node_relation = models.ForeignKey(
        WorkNodeRelation,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    knowledge_relation = models.ForeignKey(
        KnowledgeRelation,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence",
    )
    page_number = models.PositiveIntegerField(db_index=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    printed_page_label = models.CharField(max_length=40, blank=True)
    quote = models.TextField()
    bounding_box = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(
        max_length=20,
        choices=ExtractionMethod.choices,
        default=ExtractionMethod.TEXT_LAYER,
    )
    ocr_confidence = models.FloatField(null=True, blank=True)
    semantic_confidence = models.FloatField(null=True, blank=True)
    review_status = models.CharField(
        max_length=20,
        choices=RelationReviewStatus.choices,
        default=RelationReviewStatus.SUGGESTED,
        db_index=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_evidence_snippets",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["work_id", "page_number", "created_at"]
        indexes = [
            models.Index(fields=["node", "review_status"]),
            models.Index(fields=["file", "page_number"]),
        ]


class TimelineEventRelation(UUIDTimeStampedModel):
    class RelationType(models.TextChoices):
        SUBJECT = "subject", "事件主体"
        CONTEXT = "context", "相关背景"
        EVIDENCE = "evidence", "馆藏证据"

    event = models.ForeignKey(TheoryTimelineEvent, on_delete=models.CASCADE, related_name="normalized_relations")
    relation_type = models.CharField(max_length=20, choices=RelationType.choices, default=RelationType.SUBJECT)
    node = models.ForeignKey(KnowledgeNode, null=True, blank=True, on_delete=models.CASCADE, related_name="timeline_links")
    discipline = models.ForeignKey(Discipline, null=True, blank=True, on_delete=models.CASCADE, related_name="timeline_links")
    scholar = models.ForeignKey(ScholarProfile, null=True, blank=True, on_delete=models.CASCADE, related_name="timeline_links")
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE, related_name="timeline_links")
    evidence = models.ForeignKey(EvidenceSnippet, null=True, blank=True, on_delete=models.SET_NULL, related_name="timeline_links")
    description = models.CharField(max_length=400, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "created_at"]


class ReadingPath(UUIDTimeStampedModel):
    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "入门"
        INTERMEDIATE = "intermediate", "进阶"
        ADVANCED = "advanced", "深入"

    title = models.CharField(max_length=300)
    slug = models.SlugField(max_length=180, unique=True)
    introduction = models.TextField(blank=True)
    primary_discipline = models.ForeignKey(
        Discipline,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reading_paths",
    )
    audience = models.CharField(max_length=240, blank=True)
    difficulty = models.CharField(max_length=20, choices=Difficulty.choices, default=Difficulty.BEGINNER)
    estimated_reading = models.CharField(max_length=120, blank=True)
    cover_asset = models.ImageField(upload_to="public/knowledge/reading-paths/%Y/%m/", blank=True)
    status = models.CharField(
        max_length=20,
        choices=KnowledgePublicationStatus.choices,
        default=KnowledgePublicationStatus.DRAFT,
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_reading_paths",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_reading_paths",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "title"]
        indexes = [models.Index(fields=["status", "sort_order"])]


class ReadingPathItem(UUIDTimeStampedModel):
    reading_path = models.ForeignKey(ReadingPath, on_delete=models.CASCADE, related_name="items")
    stage_name = models.CharField(max_length=160)
    stage_description = models.TextField(blank=True)
    node = models.ForeignKey(KnowledgeNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="reading_path_items")
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.SET_NULL, related_name="reading_path_items")
    recommendation_reason = models.TextField(blank=True)
    reading_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)
    editorial_note = models.TextField(blank=True)

    class Meta:
        ordering = ["reading_order", "created_at"]
        indexes = [models.Index(fields=["reading_path", "reading_order"])]


class TheoryReviewTask(UUIDTimeStampedModel):
    class TaskType(models.TextChoices):
        WORK_NODE = "work_node", "文献与节点关系"
        NODE_RELATION = "node_relation", "节点关系"
        NEW_NODE = "new_node", "建议新增节点"
        TIMELINE = "timeline", "时间轴事件"

    class TaskStatus(models.TextChoices):
        PENDING = "pending", "待审核"
        NEEDS_CHANGES = "needs_changes", "待修改"
        CONFIRMED = "confirmed", "已确认"
        REJECTED = "rejected", "已拒绝"
        DEFERRED = "deferred", "延后处理"
        INSUFFICIENT_EVIDENCE = "insufficient_evidence", "证据不足"

    task_type = models.CharField(max_length=24, choices=TaskType.choices, db_index=True)
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE, related_name="theory_review_tasks")
    file = models.ForeignKey(Asset, null=True, blank=True, on_delete=models.CASCADE, related_name="theory_review_tasks")
    candidate_node = models.ForeignKey(KnowledgeNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="review_tasks")
    suggested_node_name = models.CharField(max_length=240, blank=True)
    suggested_relation_type = models.CharField(max_length=40, blank=True)
    confidence = models.FloatField(default=0)
    evidence_pages = models.JSONField(default=list, blank=True)
    evidence_text = models.TextField(blank=True)
    status = models.CharField(max_length=32, choices=TaskStatus.choices, default=TaskStatus.PENDING, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_theory_review_tasks",
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "task_type", "created_at"])]


class KnowledgeNodeVersion(UUIDTimeStampedModel):
    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    change_note = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_knowledge_node_versions",
    )

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["node", "version_number"], name="unique_knowledge_node_version"),
        ]


class KnowledgeRelationVersion(UUIDTimeStampedModel):
    relation = models.ForeignKey(KnowledgeRelation, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    change_note = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_knowledge_relation_versions",
    )

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.UniqueConstraint(fields=["relation", "version_number"], name="unique_knowledge_relation_version"),
        ]


class LegacyKnowledgeMapping(UUIDTimeStampedModel):
    class MigrationStatus(models.TextChoices):
        MAPPED = "mapped", "已映射"
        NEEDS_REVIEW = "needs_review", "待审核"
        DUPLICATE = "duplicate", "疑似重复"
        REJECTED = "rejected", "不迁移"

    legacy_model = models.CharField(max_length=80, db_index=True)
    legacy_id = models.UUIDField(db_index=True)
    node = models.ForeignKey(KnowledgeNode, on_delete=models.PROTECT, related_name="legacy_mappings")
    migration_status = models.CharField(
        max_length=20,
        choices=MigrationStatus.choices,
        default=MigrationStatus.MAPPED,
        db_index=True,
    )
    migration_note = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["legacy_model", "legacy_id"], name="unique_legacy_knowledge_mapping"),
        ]


class KnowledgeNodeMergeRecord(UUIDTimeStampedModel):
    source_node = models.ForeignKey(KnowledgeNode, on_delete=models.PROTECT, related_name="merge_source_records")
    target_node = models.ForeignKey(KnowledgeNode, on_delete=models.PROTECT, related_name="merge_target_records")
    source_snapshot = models.JSONField(default=dict)
    target_snapshot = models.JSONField(default=dict)
    affected_counts = models.JSONField(default=dict)
    rollback_payload = models.JSONField(default=dict)
    merged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_node_merges",
    )
    rolled_back_at = models.DateTimeField(null=True, blank=True)
    rolled_back_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="rolled_back_knowledge_node_merges",
    )

    class Meta:
        ordering = ["-created_at"]


class PublicationEvent(UUIDTimeStampedModel):
    class EventType(models.TextChoices):
        PUBLISH = "publish", "发布"
        UPDATE = "update", "更新"
        WITHDRAW = "withdraw", "下架"
        REPUBLISH = "republish", "重新发布"

    edition = models.ForeignKey(Edition, on_delete=models.PROTECT, related_name="publication_events")
    event_type = models.CharField(max_length=16, choices=EventType.choices)
    idempotency_key = models.CharField(max_length=120, unique=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    payload = models.JSONField(default=dict, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class AnonymousUsageEvent(UUIDTimeStampedModel):
    class EventType(models.TextChoices):
        READER_OPEN = "reader_open", "打开阅读器"
        SEARCH_SUBMIT = "search_submit", "提交检索"
        SEARCH_RESULT_CLICK = "search_result_click", "点击检索结果"
        DOWNLOAD = "download", "下载"

    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    session_hash = models.CharField(max_length=64, db_index=True)
    work = models.ForeignKey(
        Work,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="anonymous_usage_events",
    )
    asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="anonymous_usage_events",
    )
    normalized_query = models.CharField(max_length=500, blank=True, db_index=True)
    result_count = models.PositiveIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["normalized_query", "created_at"]),
        ]


class SearchQueryAggregate(UUIDTimeStampedModel):
    period_start = models.DateField(db_index=True)
    period = models.CharField(max_length=16, default="day")
    normalized_query = models.CharField(max_length=500)
    search_count = models.PositiveIntegerField(default=0)
    unique_sessions = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    zero_result_count = models.PositiveIntegerField(default=0)
    excluded = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["-period_start", "-search_count", "normalized_query"]
        constraints = [
            models.UniqueConstraint(
                fields=["period_start", "period", "normalized_query"],
                name="unique_search_query_aggregate_period",
            ),
        ]


class SiteSetting(UUIDTimeStampedModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict)
    public = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class FeaturedSlot(UUIDTimeStampedModel):
    key = models.CharField(max_length=120, unique=True)
    title = models.CharField(max_length=240, blank=True)
    configuration = models.JSONField(default=dict)
    active = models.BooleanField(default=True)


class RecommendationPolicy(UUIDTimeStampedModel):
    class Placement(models.TextChoices):
        HOME_FEATURED = "home_featured", "首页精选馆藏"
        HOME_THEORIES = "home_theories", "首页理论传统"
        HOME_SCHOLARS = "home_scholars", "首页学者"
        HOME_TOPICS = "home_topics", "首页问题主题"
        HOME_RANDOM = "home_random", "首页随机推荐"
        THEORY_WEEKLY = "theory_weekly", "理论页本周馆藏"

    placement = models.CharField(max_length=40, choices=Placement.choices, unique=True)
    title = models.CharField(max_length=240)
    item_count = models.PositiveSmallIntegerField(default=4)
    rotation_days = models.PositiveSmallIntegerField(default=3)
    rules = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    last_generated_at = models.DateTimeField(null=True, blank=True)
    next_refresh_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_recommendation_policies",
    )

    class Meta:
        ordering = ["placement"]

    def __str__(self):
        return self.title


class RecommendationSnapshot(UUIDTimeStampedModel):
    class Source(models.TextChoices):
        AUTOMATIC = "automatic", "系统轮换"
        MANUAL = "manual", "管理员更新"

    policy = models.ForeignKey(
        RecommendationPolicy,
        on_delete=models.CASCADE,
        related_name="snapshots",
    )
    starts_at = models.DateTimeField(db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    source = models.CharField(max_length=16, choices=Source.choices, default=Source.AUTOMATIC)
    seed = models.CharField(max_length=120, blank=True)
    is_current = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_recommendation_snapshots",
    )

    class Meta:
        ordering = ["-starts_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["policy"],
                condition=models.Q(is_current=True),
                name="unique_current_recommendation_snapshot",
            ),
        ]


class RecommendationTargetMixin(models.Model):
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.CASCADE)
    theory_school = models.ForeignKey(TheorySchool, null=True, blank=True, on_delete=models.CASCADE)
    topic = models.ForeignKey(Topic, null=True, blank=True, on_delete=models.CASCADE)
    scholar = models.ForeignKey(ScholarProfile, null=True, blank=True, on_delete=models.CASCADE)
    discipline = models.ForeignKey(Discipline, null=True, blank=True, on_delete=models.CASCADE)
    subdiscipline = models.ForeignKey(Subdiscipline, null=True, blank=True, on_delete=models.CASCADE)

    class Meta:
        abstract = True

    def target_count(self):
        return sum(
            value is not None
            for value in (
                self.work_id,
                self.theory_school_id,
                self.topic_id,
                self.scholar_id,
                self.discipline_id,
                self.subdiscipline_id,
            )
        )

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.target_count() != 1:
            raise ValidationError("推荐项必须且只能关联一个馆藏或知识实体。")


class RecommendationItem(UUIDTimeStampedModel, RecommendationTargetMixin):
    snapshot = models.ForeignKey(
        RecommendationSnapshot,
        on_delete=models.CASCADE,
        related_name="items",
    )
    position = models.PositiveSmallIntegerField(default=0)
    reason = models.CharField(max_length=300, blank=True)
    image_override = models.ImageField(upload_to="public/recommendations/overrides/%Y/%m/", blank=True)

    class Meta:
        ordering = ["position", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["snapshot", "position"], name="unique_recommendation_position"),
        ]


class RecommendationOverride(UUIDTimeStampedModel, RecommendationTargetMixin):
    class Action(models.TextChoices):
        PIN = "pin", "固定展示"
        EXCLUDE = "exclude", "排除展示"

    policy = models.ForeignKey(
        RecommendationPolicy,
        on_delete=models.CASCADE,
        related_name="overrides",
    )
    action = models.CharField(max_length=12, choices=Action.choices)
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    active = models.BooleanField(default=True)
    note = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recommendation_overrides",
    )

    class Meta:
        ordering = ["policy", "position", "created_at"]


class AboutPageBlock(UUIDTimeStampedModel):
    class BlockType(models.TextChoices):
        INTRO = "intro", "简介"
        STAT = "stat", "数据"
        FEATURE = "feature", "功能"
        PROCESS = "process", "入库步骤"
        PRINCIPLE = "principle", "开放原则"
        NOTICE = "notice", "提示"
        ACTION = "action", "操作入口"
        FOOTER = "footer", "页脚信息"

    key = models.CharField(max_length=120, unique=True)
    block_type = models.CharField(max_length=20, choices=BlockType.choices)
    title = models.CharField(max_length=240, blank=True)
    body = models.TextField(blank=True)
    icon = models.CharField(max_length=80, blank=True)
    action_label = models.CharField(max_length=120, blank=True)
    action_href = models.CharField(max_length=400, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    visible = models.BooleanField(default=True)
    configuration = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_about_blocks",
    )

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return self.title or self.key
