import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from common.models import UUIDTimeStampedModel


class DocumentType(models.TextChoices):
    BOOK = "book", "图书"
    JOURNAL_ARTICLE = "journal_article", "期刊论文"
    JOURNAL_ISSUE = "journal_issue", "整期期刊"
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


class IntelligenceStatus(models.TextChoices):
    DRAFT = "draft", "草稿"
    PROCESSING = "processing", "智能内容处理中"
    ACTIVE = "active", "已进入智能检索"
    FAILED = "failed", "智能处理异常"
    WITHDRAWN = "withdrawn", "已退出智能检索"


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
    publication_date = models.DateField(null=True, blank=True, db_index=True)
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
    metadata_ready_at = models.DateTimeField(null=True, blank=True, db_index=True)
    fulltext_ready_at = models.DateTimeField(null=True, blank=True, db_index=True)
    intelligence_status = models.CharField(
        max_length=24,
        choices=IntelligenceStatus.choices,
        default=IntelligenceStatus.DRAFT,
        db_index=True,
    )
    active_catalog_revision = models.ForeignKey(
        "CatalogPublicationRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="active_for_editions",
    )
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


class JournalIssueArticle(UUIDTimeStampedModel):
    """Editorial issue contents, optionally linked to an independently catalogued article."""

    issue = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="journal_articles")
    article_work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.PROTECT, related_name="journal_issue_entries")
    title = models.CharField(max_length=600)
    author_display = models.CharField(max_length=600, blank=True)
    page_range = models.CharField(max_length=80, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at", "id"]
        constraints = [models.UniqueConstraint(fields=["issue", "article_work"], condition=models.Q(article_work__isnull=False), name="unique_issue_article_work")]


class EditionWorkflowDecision(UUIDTimeStampedModel):
    class Step(models.TextChoices):
        WORK = "work", "作品识别"
        BIBLIOGRAPHY = "bibliography", "书目与出版"
        CONTRIBUTORS = "contributors", "作者与责任者"
        CLASSIFICATION = "classification", "社科分类"
        KNOWLEDGE = "knowledge", "理论、主题与知识关系"
        READER = "reader", "文本与阅读文件"
        CURATION = "curation", "知识策展与前台联动"

    class Decision(models.TextChoices):
        CONFIRMED = "confirmed", "已确认"
        SKIPPED = "skipped", "已跳过"

    edition = models.ForeignKey(
        Edition,
        on_delete=models.CASCADE,
        related_name="workflow_decisions",
    )
    step_key = models.CharField(max_length=24, choices=Step.choices)
    decision = models.CharField(
        max_length=16,
        choices=Decision.choices,
        default=Decision.CONFIRMED,
    )
    content_fingerprint = models.CharField(max_length=64)
    note = models.TextField(blank=True)
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_edition_workflow_steps",
    )
    confirmed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["edition_id", "step_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "step_key"],
                name="unique_edition_workflow_step",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(step_key="curation")
                    | models.Q(decision="confirmed")
                ),
                name="workflow_skip_only_curation",
            ),
        ]


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
    text_revision = models.PositiveIntegerField(default=0, db_index=True)
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
            models.UniqueConstraint(
                fields=["sha256", "kind"], condition=models.Q(text_revision=0),
                name="unique_asset_hash_per_kind",
            ),
            models.UniqueConstraint(
                fields=["edition", "kind", "text_revision"],
                condition=models.Q(text_revision__gt=0),
                name="unique_asset_text_revision",
            ),
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


class DocumentRevision(UUIDTimeStampedModel):
    """Versioned provenance for a document interpretation.

    Page remains anchored directly to Asset.  A revision records how the
    current text was produced without becoming a new parent for Page rows.
    """

    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="document_revisions")
    revision = models.PositiveIntegerField()
    parser_name = models.CharField(max_length=120, blank=True)
    parser_version = models.CharField(max_length=120, blank=True)
    extraction_method = models.CharField(max_length=120, blank=True)
    extraction_version = models.CharField(max_length=120, blank=True)
    ocr_provider = models.CharField(max_length=120, blank=True)
    ocr_model = models.CharField(max_length=240, blank=True)
    ocr_version = models.CharField(max_length=160, blank=True)
    source_checksum = models.CharField(max_length=64, db_index=True)
    text_checksum = models.CharField(max_length=64, db_index=True)
    quality_summary = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_document_revisions",
    )

    class Meta:
        ordering = ["asset_id", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["asset", "revision"],
                name="unique_document_revision_number",
            ),
            models.UniqueConstraint(
                fields=["asset"],
                condition=models.Q(is_active=True),
                name="unique_active_document_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["asset", "is_active", "-revision"]),
        ]


class DocumentQualityAssessment(UUIDTimeStampedModel):
    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.CASCADE,
        related_name="quality_assessments",
    )
    assessor = models.CharField(max_length=120, default="deterministic")
    assessor_version = models.CharField(max_length=120)
    reader_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    fulltext_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    semantic_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    claim_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    structure_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    ocr_quality = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    critical_pages = models.JSONField(default=list, blank=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_revision", "assessor", "assessor_version"],
                name="unique_document_quality_assessment",
            ),
        ]


class EvidenceSpan(UUIDTimeStampedModel):
    """A locator-backed span of source text from the library collection."""

    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.PROTECT,
        related_name="evidence_spans",
    )
    page = models.ForeignKey(Page, on_delete=models.PROTECT, related_name="evidence_spans")
    text_block = models.ForeignKey(
        TextBlock,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_spans",
    )
    passage = models.ForeignKey(
        Passage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_spans",
    )
    page_number = models.PositiveIntegerField(db_index=True)
    printed_page_label = models.CharField(max_length=40, blank=True)
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    bbox = models.JSONField(default=list, blank=True)
    original_text = models.TextField()
    normalized_text = models.TextField(blank=True)
    language = models.CharField(max_length=32, blank=True)
    section = models.CharField(max_length=600, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    quality = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    extraction_method = models.CharField(max_length=120, blank=True)
    ocr_provenance = models.JSONField(default=dict, blank=True)
    is_stale = models.BooleanField(default=False, db_index=True)
    stale_reason = models.CharField(max_length=240, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        errors = {}
        if self.document_revision_id and self.page_id:
            if self.document_revision.asset_id != self.page.asset_id:
                errors["page"] = "EvidenceSpan Page 必须属于 DocumentRevision 的 Asset。"
            if self.page_number != self.page.index:
                errors["page_number"] = "EvidenceSpan 页码必须与稳定 Page identity 一致。"
        if self.text_block_id and self.text_block.page_id != self.page_id:
            errors["text_block"] = "TextBlock 必须属于 EvidenceSpan 的 Page。"
        if self.passage_id and self.passage.page_id != self.page_id:
            errors["passage"] = "Passage 必须属于 EvidenceSpan 的 Page。"
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["page_number", "start_offset"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_revision", "page", "content_hash", "start_offset", "end_offset"],
                name="unique_revision_evidence_span",
            ),
            models.CheckConstraint(
                condition=models.Q(end_offset__gte=models.F("start_offset")),
                name="evidence_span_offsets_ordered",
            ),
        ]
        indexes = [
            models.Index(fields=["document_revision", "page_number", "is_stale"]),
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


class ClaimBenchmarkJudgment(UUIDTimeStampedModel):
    """Human gold labels layered on the existing retrieval benchmark corpus."""

    class Relation(models.TextChoices):
        DIRECT = "direct", "直接回应"
        SUPPORT = "support", "支持"
        OPPOSE = "oppose", "相斥"
        QUALIFY = "qualify", "限定"
        CRITIQUE = "critique", "批评"
        EXTEND = "extend", "延伸"
        REFRAME = "reframe", "重构问题"

    class Attribution(models.TextChoices):
        AUTHOR_CLAIM = "author_claim", "作者主张"
        QUOTED_CLAIM = "quoted_claim", "引述主张"
        REPORTED_CLAIM = "reported_claim", "转述主张"
        CRITICIZED_CLAIM = "criticized_claim", "被批评主张"
        HISTORICAL_DESCRIPTION = "historical_description", "历史描述"
        UNCERTAIN = "uncertain", "归因不确定"

    query = models.ForeignKey(
        SearchEvaluationQuery,
        on_delete=models.CASCADE,
        related_name="claim_judgments",
    )
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        on_delete=models.PROTECT,
        related_name="benchmark_judgments",
    )
    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.PROTECT,
        related_name="benchmark_judgments",
    )
    work = models.ForeignKey(
        Work,
        on_delete=models.PROTECT,
        related_name="claim_benchmark_judgments",
    )
    expected_relation = models.CharField(max_length=20, choices=Relation.choices, db_index=True)
    expected_attribution = models.CharField(
        max_length=32,
        choices=Attribution.choices,
        default=Attribution.UNCERTAIN,
    )
    relevance = models.PositiveSmallIntegerField(
        default=2,
        validators=[MinValueValidator(0), MaxValueValidator(3)],
    )
    locator_verified = models.BooleanField(default=False, db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_claim_benchmark_judgments",
    )

    class Meta:
        ordering = ["query__order", "-relevance", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["query", "evidence_span"],
                name="unique_claim_benchmark_judgment",
            ),
        ]
        indexes = [
            models.Index(fields=["query", "expected_relation", "relevance"]),
        ]

    def save(self, *args, **kwargs):
        if self.evidence_span_id:
            span = self.evidence_span
            self.document_revision_id = span.document_revision_id
            self.work_id = span.document_revision.asset.edition.work_id
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "document_revision",
                    "work",
                }
        super().save(*args, **kwargs)


class PublisherAuthority(UUIDTimeStampedModel):
    canonical_name = models.CharField(max_length=300, unique=True)
    aliases = models.JSONField(default=list, blank=True)
    possible_places = models.JSONField(default=list, blank=True)
    country = models.CharField(max_length=120, blank=True)
    valid_from = models.PositiveSmallIntegerField(null=True, blank=True)
    valid_to = models.PositiveSmallIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    editorial_status = models.CharField(
        max_length=20,
        default="draft",
        db_index=True,
    )

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


class QueryLexiconAuthorityQuerySet(models.QuerySet):
    """Keep bulk authority writes in the same transaction as lexicon outbox events."""

    def update(self, **kwargs):
        from catalog.services.query_lexicon.mutations import (
            mutate_authority_queryset,
            nested_queryset_mutation_is_suppressed,
        )

        if nested_queryset_mutation_is_suppressed():
            return super().update(**kwargs)

        pk_names = {self.model._meta.pk.name, self.model._meta.pk.attname, "pk"}
        if pk_names.intersection(kwargs):
            raise ValueError("QueryLexicon authority 不允许通过 QuerySet.update 修改主键。")
        label = self.model._meta.label_lower
        if label == "catalog.personnamevariant" and "name" in kwargs:
            from catalog.services.query_lexicon.normalization import normalize_term

            if not isinstance(kwargs["name"], str):
                raise ValueError("人物名称的批量更新只接受字符串，请改用逐条 save。")
            kwargs["normalized_name"] = normalize_term(kwargs["name"])
        elif label == "catalog.knowledgenodealias" and "alias" in kwargs:
            if not isinstance(kwargs["alias"], str):
                raise ValueError("知识别名的批量更新只接受字符串，请改用逐条 save。")
            kwargs["normalized_alias"] = " ".join(kwargs["alias"].casefold().split())
        elif label == "catalog.person" and {
            "preferred_name",
            "original_name",
            "aliases",
        }.intersection(kwargs):
            raise ValueError("人物名称字段请使用逐条 save 或 bulk_update，以同步 legacy aliases。")
        elif label in {
            "catalog.discipline",
            "catalog.theoryschool",
            "catalog.topic",
            "catalog.concept",
            "catalog.subdiscipline",
        } and {"name", "search_aliases"}.intersection(kwargs):
            raise ValueError("知识名称字段请使用逐条 save 或 bulk_update，以同步 search_aliases。")

        parent_update = super().update
        return mutate_authority_queryset(
            self,
            action="update",
            operation=lambda: parent_update(**kwargs),
        )

    def delete(self):
        from catalog.services.query_lexicon.mutations import mutate_authority_queryset

        parent_delete = super().delete
        return mutate_authority_queryset(
            self,
            action="delete",
            operation=parent_delete,
            include_after=False,
        )

    def bulk_create(self, objs, **kwargs):
        from catalog.services.query_lexicon.mutations import mutate_authority_objects

        objects = list(objs)
        parent_bulk_create = super().bulk_create
        return mutate_authority_objects(
            objects,
            action="create",
            operation=lambda: parent_bulk_create(objects, **kwargs),
            include_before=False,
        )

    def bulk_update(self, objs, fields, **kwargs):
        from catalog.services.query_lexicon.mutations import (
            mutate_authority_objects,
            suppress_nested_queryset_mutation,
        )

        objects = list(objs)
        fields = list(fields)
        label = self.model._meta.label_lower
        if label == "catalog.personnamevariant" and "name" in fields:
            fields.append("normalized_name")
        elif label == "catalog.knowledgenodealias" and "alias" in fields:
            fields.append("normalized_alias")
        elif label == "catalog.person":
            if {
                "preferred_name",
                "original_name",
                "aliases",
            }.intersection(fields):
                fields.append("aliases")
            if {
                "authority_status",
                "merged_into",
                "merged_into_id",
            }.intersection(fields):
                fields = [field for field in fields if field != "merged_into_id"]
                fields.extend(["authority_status", "merged_into"])
        elif label in {
            "catalog.discipline",
            "catalog.theoryschool",
            "catalog.topic",
            "catalog.concept",
            "catalog.subdiscipline",
        } and {"name", "search_aliases"}.intersection(fields):
            fields.append("search_aliases")
        fields = list(dict.fromkeys(fields))
        parent_bulk_update = super().bulk_update

        def operation():
            with suppress_nested_queryset_mutation():
                return parent_bulk_update(objects, fields, **kwargs)

        return mutate_authority_objects(
            objects,
            action="update",
            operation=operation,
        )


QueryLexiconAuthorityManager = models.Manager.from_queryset(QueryLexiconAuthorityQuerySet)


class QueryLexiconAuthorityMixin(models.Model):
    """Wrap one authority mutation and its durable event in one DB transaction."""

    objects = QueryLexiconAuthorityManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        from catalog.services.query_lexicon.mutations import mutate_authority_instance

        parent_save = super().save
        return mutate_authority_instance(
            self,
            action="create" if self._state.adding else "update",
            operation=lambda: parent_save(*args, **kwargs),
        )

    def delete(self, *args, **kwargs):
        from catalog.services.query_lexicon.mutations import mutate_authority_instance

        parent_delete = super().delete
        return mutate_authority_instance(
            self,
            action="delete",
            operation=lambda: parent_delete(*args, **kwargs),
            include_after=False,
        )


class Person(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
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
    merged_into = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="merged_people",
    )
    authority_status = models.CharField(
        max_length=20,
        choices=AuthorityStatus.choices,
        default=AuthorityStatus.DRAFT,
        db_index=True,
    )

    class Meta:
        ordering = ["sort_name", "preferred_name"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(id=models.F("merged_into_id")),
                name="person_merge_target_not_self",
            ),
        ]

    def __str__(self):
        return self.preferred_name

    def validate_query_lexicon_authority_state(self):
        from django.core.exceptions import ValidationError

        if self.authority_status == self.AuthorityStatus.MERGED:
            if not self.merged_into_id:
                raise ValidationError({"merged_into": "已合并人物必须指定保留人物。"})
        elif self.merged_into_id:
            raise ValidationError({"merged_into": "只有已合并人物可以指定保留人物。"})
        if self.pk and self.merged_into_id == self.pk:
            raise ValidationError({"merged_into": "人物不能合并到自身。"})
        if not self.merged_into_id:
            return
        current = self.merged_into
        seen = {self.pk} if self.pk else set()
        depth = 0
        while current is not None:
            if current.pk in seen:
                raise ValidationError({"merged_into": "人物合并关系不能形成循环。"})
            if current.authority_status in {
                self.AuthorityStatus.REJECTED,
                self.AuthorityStatus.ARCHIVED,
            }:
                raise ValidationError({"merged_into": "保留人物不能是已拒绝或已归档记录。"})
            seen.add(current.pk)
            depth += 1
            if depth > 32:
                raise ValidationError({"merged_into": "人物合并关系过深。"})
            if current.authority_status != self.AuthorityStatus.MERGED:
                break
            if not current.merged_into_id:
                raise ValidationError({"merged_into": "合并目标缺少最终保留人物。"})
            current = current.merged_into

    def save(self, *args, **kwargs):
        self.prepare_query_lexicon_bulk_object()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None:
            fields = list(update_fields)
            if {
                "preferred_name",
                "original_name",
                "aliases",
            }.intersection(fields):
                fields.append("aliases")
            if {
                "authority_status",
                "merged_into",
                "merged_into_id",
            }.intersection(fields):
                fields = [field for field in fields if field != "merged_into_id"]
                fields.extend(["authority_status", "merged_into"])
            kwargs["update_fields"] = tuple(dict.fromkeys(fields))
        super().save(*args, **kwargs)

    def prepare_query_lexicon_bulk_object(self):
        from catalog.services.aliases import search_aliases

        self.validate_query_lexicon_authority_state()
        self.aliases = search_aliases(
            self.preferred_name,
            self.original_name,
            *self.aliases,
        )


class PersonNameVariant(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
    class VariantType(models.TextChoices):
        TRANSLATION = "translation", "译名"
        ALIAS = "alias", "别名"
        ABBREVIATION = "abbreviation", "简称"
        HISTORICAL = "historical", "历史名称"
        TRANSLITERATION = "transliteration", "音译"

    class SourceKind(models.TextChoices):
        EDITORIAL = "editorial", "编辑确认"
        AUTHORITY_IMPORT = "authority_import", "权威库导入"
        LEGACY_REVIEW = "legacy_review", "历史名称复核"
        PDF_EVIDENCE = "pdf_evidence", "馆藏 PDF 证据"
        OTHER = "other", "其他已记录来源"

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="name_variants")
    name = models.CharField(max_length=240)
    normalized_name = models.CharField(max_length=500, db_index=True)
    language = models.CharField(max_length=24, default="und")
    variant_type = models.CharField(max_length=24, choices=VariantType.choices)
    source_kind = models.CharField(
        max_length=32,
        choices=SourceKind.choices,
        default=SourceKind.EDITORIAL,
    )
    source_note = models.TextField(blank=True)
    displayable = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_person_name_variants",
    )

    class Meta:
        ordering = ["person__preferred_name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["person", "normalized_name"],
                name="unique_person_name_variant",
            ),
            models.CheckConstraint(
                condition=models.Q(displayable=False) | models.Q(is_verified=True),
                name="displayable_person_variant_verified",
            ),
            models.CheckConstraint(
                condition=~models.Q(name="") & ~models.Q(normalized_name=""),
                name="person_variant_name_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    variant_type__in=[
                        "translation",
                        "alias",
                        "abbreviation",
                        "historical",
                        "transliteration",
                    ]
                ),
                name="person_variant_type_allowed",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    source_kind__in=[
                        "editorial",
                        "authority_import",
                        "legacy_review",
                        "pdf_evidence",
                        "other",
                    ]
                ),
                name="person_variant_source_allowed",
            ),
        ]

    def __str__(self):
        return self.name

    def validate_query_lexicon_authority_state(self):
        from django.core.exceptions import ValidationError

        if not self.normalized_name:
            raise ValidationError({"name": "人物名称不能为空。"})
        if self.variant_type not in self.VariantType.values:
            raise ValidationError({"variant_type": "人物名称变体类型无效。"})
        if self.source_kind not in self.SourceKind.values:
            raise ValidationError({"source_kind": "人物名称来源类型无效。"})
        if self.displayable and not self.is_verified:
            raise ValidationError({"displayable": "未经确认的人物名称不能公开展示。"})

    def save(self, *args, **kwargs):
        self.prepare_query_lexicon_bulk_object()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "name" in update_fields:
            kwargs["update_fields"] = tuple(
                dict.fromkeys([*update_fields, "normalized_name"])
            )
        super().save(*args, **kwargs)

    def prepare_query_lexicon_bulk_object(self):
        from catalog.services.query_lexicon.normalization import normalize_term

        self.normalized_name = normalize_term(self.name)
        self.validate_query_lexicon_authority_state()


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
        CHIEF_EDITOR = "chief_editor", "主编"
        EDITOR = "editor", "编者"
        TRANSLATOR = "translator", "译者"
        ANNOTATOR = "annotator", "校注"
        PHOTOGRAPHER = "photographer", "摄影"
        ADVISOR = "advisor", "导师"
        SUBJECT = "subject", "研究对象"
        OTHER = "other", "其他贡献者"

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


class NamedKnowledgeObject(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
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
        self.prepare_query_lexicon_bulk_object()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"name", "search_aliases"}.intersection(
            update_fields
        ):
            kwargs["update_fields"] = tuple(
                dict.fromkeys([*update_fields, "search_aliases"])
            )
        super().save(*args, **kwargs)

    def prepare_query_lexicon_bulk_object(self):
        from catalog.services.aliases import search_aliases

        self.search_aliases = search_aliases(self.name, *self.search_aliases)


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


class WorkTopicRelation(UUIDTimeStampedModel):
    """Canonical Work-to-Topic relation replacing legacy kind-based rows."""

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="topic_relations")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="work_relations")
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
        related_name="work_topic_evidence",
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
        related_name="reviewed_work_topics",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["work", "topic"], name="unique_work_topic"),
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


class PersonTopicRelation(UUIDTimeStampedModel):
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="topic_relations")
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="person_relations")
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
        related_name="reviewed_person_topics",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["person", "topic"], name="unique_person_topic"),
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


class KnowledgeNode(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
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


class KnowledgeNodeAlias(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
    class AliasType(models.TextChoices):
        ALIAS = "alias", "别名"
        TRANSLATION = "translation", "译名"
        ABBREVIATION = "abbreviation", "简称"
        HISTORICAL = "historical", "历史名称"
        TRANSLITERATION = "transliteration", "音译"

    class SourceKind(models.TextChoices):
        EDITORIAL = "editorial", "编辑确认"
        AUTHORITY_IMPORT = "authority_import", "权威库导入"
        LEGACY_REVIEW = "legacy_review", "历史名称复核"
        PDF_EVIDENCE = "pdf_evidence", "馆藏 PDF 证据"
        WEB_EVIDENCE = "web_evidence", "联网证据"
        OTHER = "other", "其他已记录来源"

    node = models.ForeignKey(KnowledgeNode, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=240)
    language = models.CharField(max_length=16, default="zh-CN")
    alias_type = models.CharField(max_length=20, choices=AliasType.choices, default=AliasType.ALIAS)
    normalized_alias = models.CharField(max_length=240, db_index=True)
    source_kind = models.CharField(
        max_length=32,
        choices=SourceKind.choices,
        default=SourceKind.EDITORIAL,
    )
    # Existing aliases are promoted by migration for backwards compatibility;
    # newly observed aliases stay unverified until an explicit review decision.
    is_verified = models.BooleanField(default=False, db_index=True)
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
        self.prepare_query_lexicon_bulk_object()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "alias" in update_fields:
            kwargs["update_fields"] = tuple(
                dict.fromkeys([*update_fields, "normalized_alias"])
            )
        super().save(*args, **kwargs)

    def prepare_query_lexicon_bulk_object(self):
        self.normalized_alias = " ".join(self.alias.casefold().split())
        # An explicit editor-created alias is a reviewed authority mutation.
        # PDF/web observations must pass their own review path and set
        # ``is_verified`` explicitly, so they remain unverified here.
        if (
            self._state.adding
            and self.created_by_id
            and self.source_kind
            in {
                self.SourceKind.EDITORIAL,
                self.SourceKind.AUTHORITY_IMPORT,
                self.SourceKind.LEGACY_REVIEW,
                self.SourceKind.OTHER,
            }
        ):
            self.is_verified = True


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


class KnowledgeNodeSubdiscipline(UUIDTimeStampedModel):
    node = models.ForeignKey(
        KnowledgeNode,
        on_delete=models.CASCADE,
        related_name="subdiscipline_links",
    )
    subdiscipline = models.ForeignKey(
        Subdiscipline,
        on_delete=models.CASCADE,
        related_name="knowledge_node_links",
    )
    is_primary = models.BooleanField(default=False)
    relation_role = models.CharField(max_length=20, blank=True)
    source = models.CharField(max_length=160, blank=True)
    confidence = models.FloatField(default=0)
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
        related_name="reviewed_knowledge_node_subdisciplines",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "subdiscipline__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["node", "subdiscipline"],
                name="unique_knowledge_node_subdiscipline",
            ),
        ]


class KnowledgeNodeTopic(UUIDTimeStampedModel):
    node = models.ForeignKey(
        KnowledgeNode,
        on_delete=models.CASCADE,
        related_name="topic_links",
    )
    topic = models.ForeignKey(
        Topic,
        on_delete=models.CASCADE,
        related_name="knowledge_node_links",
    )
    relation_label = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=160, blank=True)
    confidence = models.FloatField(default=0)
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
        related_name="reviewed_knowledge_node_topics",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "topic__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["node", "topic"],
                name="unique_knowledge_node_topic",
            ),
        ]


class KnowledgeRelation(UUIDTimeStampedModel):
    class RelationType(models.TextChoices):
        INHERITED_FROM = "inherited_from", "继承"
        REVISES = "revises", "修正"
        EXTENDS = "extends", "扩展"
        CRITICIZES = "criticizes", "批判"
        RESPONDS_TO = "responds_to", "回应"
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
    learning_goal = models.TextField(blank=True)
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


class ReadingPathStage(UUIDTimeStampedModel):
    reading_path = models.ForeignKey(
        ReadingPath,
        on_delete=models.CASCADE,
        related_name="stages",
    )
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "created_at"]
        indexes = [models.Index(fields=["reading_path", "position"])]


class ReadingPathItem(UUIDTimeStampedModel):
    reading_path = models.ForeignKey(ReadingPath, on_delete=models.CASCADE, related_name="items")
    stage = models.ForeignKey(
        ReadingPathStage,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="items",
    )
    stage_name = models.CharField(max_length=160)
    stage_description = models.TextField(blank=True)
    node = models.ForeignKey(KnowledgeNode, null=True, blank=True, on_delete=models.SET_NULL, related_name="reading_path_items")
    work = models.ForeignKey(Work, null=True, blank=True, on_delete=models.SET_NULL, related_name="reading_path_items")
    recommendation_reason = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    reading_order = models.PositiveIntegerField(default=0)
    is_required = models.BooleanField(default=False)
    editorial_note = models.TextField(blank=True)
    prerequisite = models.TextField(blank=True)

    class Meta:
        ordering = ["reading_order", "created_at"]
        indexes = [models.Index(fields=["reading_path", "reading_order"])]


class DerivedClaim(UUIDTimeStampedModel):
    class Polarity(models.TextChoices):
        POSITIVE = "positive", "肯定"
        NEGATIVE = "negative", "否定"
        MIXED = "mixed", "混合"
        UNCERTAIN = "uncertain", "不确定"

    class Attribution(models.TextChoices):
        AUTHOR_CLAIM = "author_claim", "作者主张"
        QUOTED_CLAIM = "quoted_claim", "引述主张"
        REPORTED_CLAIM = "reported_claim", "转述主张"
        CRITICIZED_CLAIM = "criticized_claim", "被批评主张"
        HISTORICAL_DESCRIPTION = "historical_description", "历史描述"
        UNCERTAIN = "uncertain", "归因不确定"

    class ClaimType(models.TextChoices):
        ASSERTION = "assertion", "论断"
        CAUSAL = "causal", "因果"
        DEFINITION = "definition", "定义"
        EVALUATION = "evaluation", "评价"
        COMPARISON = "comparison", "比较"
        MECHANISM = "mechanism", "机制"
        INTERPRETATION = "interpretation", "解释"
        CRITICISM = "criticism", "批评"
        RESPONSE = "response", "回应"

    class Status(models.TextChoices):
        ACTIVE = "active", "有效"
        STALE = "stale", "待重算"
        SUPERSEDED = "superseded", "已取代"
        REJECTED = "rejected", "已拒绝"

    document_revision = models.ForeignKey(
        DocumentRevision,
        on_delete=models.PROTECT,
        related_name="derived_claims",
    )
    primary_evidence = models.ForeignKey(
        EvidenceSpan,
        on_delete=models.PROTECT,
        related_name="primary_for_claims",
    )
    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="derived_claims")
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="derived_claims")
    proposition = models.TextField()
    subject = models.CharField(max_length=600, blank=True)
    predicate = models.CharField(max_length=300, blank=True)
    object = models.TextField(blank=True)
    polarity = models.CharField(max_length=20, choices=Polarity.choices, default=Polarity.UNCERTAIN)
    modality = models.CharField(max_length=120, blank=True)
    qualifiers = models.JSONField(default=list, blank=True)
    temporal_scope = models.JSONField(default=dict, blank=True)
    geographic_scope = models.JSONField(default=dict, blank=True)
    population_scope = models.JSONField(default=dict, blank=True)
    attribution = models.CharField(
        max_length=32,
        choices=Attribution.choices,
        default=Attribution.UNCERTAIN,
        db_index=True,
    )
    claim_type = models.CharField(max_length=24, choices=ClaimType.choices, db_index=True)
    prompt_key = models.CharField(max_length=160)
    prompt_version = models.CharField(max_length=120)
    model_provider = models.CharField(max_length=120)
    model_name = models.CharField(max_length=240)
    model_revision = models.CharField(max_length=160, blank=True)
    quality_factors = models.JSONField(default=dict, blank=True)
    quality_score = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        db_index=True,
    )
    importance_score = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
        db_index=True,
    )
    cluster_key = models.CharField(max_length=160, blank=True, db_index=True)
    fingerprint = models.CharField(max_length=64)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    shadow = models.BooleanField(default=True, db_index=True)
    stale_reason = models.CharField(max_length=240, blank=True)

    def clean(self):
        errors = {}
        if self.document_revision_id and self.primary_evidence_id:
            if self.primary_evidence.document_revision_id != self.document_revision_id:
                errors["primary_evidence"] = (
                    "DerivedClaim 的主要依据必须属于同一 DocumentRevision。"
                )
        if self.document_revision_id and self.edition_id:
            if self.document_revision.asset.edition_id != self.edition_id:
                errors["edition"] = "DerivedClaim Edition 必须匹配 DocumentRevision Asset。"
        if self.edition_id and self.work_id and self.edition.work_id != self.work_id:
            errors["work"] = "DerivedClaim Work 必须匹配 Edition。"
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["-importance_score", "-quality_score", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_revision", "fingerprint"],
                name="unique_claim_per_document_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["work", "status", "shadow", "-importance_score"]),
            models.Index(fields=["claim_type", "attribution", "polarity"]),
        ]


class CuratedClaim(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        CORE_VIEWPOINT = "core_viewpoint", "核心观点"
        MAJOR_CRITICISM = "major_criticism", "主要批评"
        MAJOR_RESPONSE = "major_response", "主要回应"
        DEBATE_POSITION = "debate_position", "争论立场"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        SUPERSEDED = "superseded", "已取代"

    work = models.ForeignKey(
        Work,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="curated_claims",
    )
    node = models.ForeignKey(
        KnowledgeNode,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="curated_claims",
    )
    scholar = models.ForeignKey(
        ScholarProfile,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="curated_claims",
    )
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="curated_claims",
    )
    kind = models.CharField(max_length=32, choices=Kind.choices, db_index=True)
    title = models.CharField(max_length=300, blank=True)
    proposition = models.TextField()
    editorial_note = models.TextField(blank=True)
    qualifiers = models.JSONField(default=list, blank=True)
    adopted_from = models.ForeignKey(
        DerivedClaim,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="curated_adoptions",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_curated_claims",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_curated_claims",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["kind", "sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(work__isnull=False, node__isnull=True, scholar__isnull=True, topic__isnull=True)
                    | models.Q(work__isnull=True, node__isnull=False, scholar__isnull=True, topic__isnull=True)
                    | models.Q(work__isnull=True, node__isnull=True, scholar__isnull=False, topic__isnull=True)
                    | models.Q(work__isnull=True, node__isnull=True, scholar__isnull=True, topic__isnull=False)
                ),
                name="curated_claim_has_target",
            ),
        ]
        indexes = [
            models.Index(fields=["work", "status", "kind", "sort_order"]),
            models.Index(fields=["node", "status", "kind", "sort_order"]),
        ]


class ClaimEvidence(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        PRIMARY = "primary", "主要依据"
        SUPPORTS = "supports", "支持"
        OPPOSES = "opposes", "相斥"
        QUALIFIES = "qualifies", "限定"
        ATTRIBUTION = "attribution", "归因"

    derived_claim = models.ForeignKey(
        DerivedClaim,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    curated_claim = models.ForeignKey(
        CuratedClaim,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidence_links",
    )
    evidence_span = models.ForeignKey(
        EvidenceSpan,
        on_delete=models.PROTECT,
        related_name="claim_links",
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SUPPORTS)
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    sort_order = models.PositiveIntegerField(default=0)
    validation = models.JSONField(default=dict, blank=True)

    def clean(self):
        if (
            self.derived_claim_id
            and self.evidence_span_id
            and self.derived_claim.document_revision_id
            != self.evidence_span.document_revision_id
        ):
            raise ValidationError(
                {
                    "evidence_span": (
                        "DerivedClaim 的补充依据必须属于同一 DocumentRevision。"
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)

    class Meta:
        ordering = ["sort_order", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(derived_claim__isnull=False) & models.Q(curated_claim__isnull=True))
                    | (models.Q(derived_claim__isnull=True) & models.Q(curated_claim__isnull=False))
                ),
                name="claim_evidence_exactly_one_claim",
            ),
            models.UniqueConstraint(
                fields=["derived_claim", "evidence_span", "role"],
                condition=models.Q(derived_claim__isnull=False),
                name="unique_derived_claim_evidence_role",
            ),
            models.UniqueConstraint(
                fields=["curated_claim", "evidence_span", "role"],
                condition=models.Q(curated_claim__isnull=False),
                name="unique_curated_claim_evidence_role",
            ),
        ]


class EditorialRevision(UUIDTimeStampedModel):
    class TargetType(models.TextChoices):
        WORK = "work", "作品"
        EDITION = "edition", "版本"
        KNOWLEDGE_NODE = "knowledge_node", "知识节点"
        SCHOLAR_PROFILE = "scholar_profile", "学者"
        DISCIPLINE = "discipline", "学科"
        SUBDISCIPLINE = "subdiscipline", "子学科"
        TOPIC = "topic", "主题"
        PUBLISHER = "publisher", "出版社"
        READING_PATH = "reading_path", "阅读路径"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHED = "published", "已发布"
        SUPERSEDED = "superseded", "已取代"

    target_type = models.CharField(max_length=32, choices=TargetType.choices, db_index=True)
    target_id = models.UUIDField(db_index=True)
    base_revision = models.PositiveBigIntegerField(default=0)
    revision = models.PositiveBigIntegerField()
    patch = models.JSONField(default=dict)
    materialized_preview = models.JSONField(default=dict)
    changed_fields = models.JSONField(default=list)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    change_note = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_editorial_revisions",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_editorial_revisions",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["target_type", "target_id", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["target_type", "target_id", "revision"],
                name="unique_editorial_target_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["target_type", "target_id", "status", "-revision"]),
        ]


class PublicationBundle(UUIDTimeStampedModel):
    """One cataloging publication unit, including draft entities created in place."""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PUBLISHING = "publishing", "发布处理中"
        PUBLISHED = "published", "已发布"
        FAILED = "failed", "发布失败"
        ABANDONED = "abandoned", "已放弃"

    context_type = models.CharField(max_length=48, db_index=True)
    context_id = models.UUIDField(db_index=True)
    edition = models.ForeignKey(
        Edition,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="publication_bundles",
    )
    label = models.CharField(max_length=300, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    minimum_completeness = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_publication_bundles",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_publication_bundles",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["context_type", "context_id"],
                condition=models.Q(status="draft"),
                name="one_draft_publication_bundle",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["edition", "status"]),
        ]


class PublicationBundleItem(UUIDTimeStampedModel):
    class Action(models.TextChoices):
        CREATE = "create", "新建"
        UPDATE = "update", "更新"
        LINK = "link", "关联"
        MERGE = "merge", "合并"
        WITHDRAW = "withdraw", "撤回"

    bundle = models.ForeignKey(
        PublicationBundle,
        on_delete=models.CASCADE,
        related_name="items",
    )
    object_type = models.CharField(max_length=48, db_index=True)
    object_id = models.UUIDField(db_index=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    label = models.CharField(max_length=300, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    minimum_complete = models.BooleanField(default=False)
    blockers = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["bundle", "object_type", "object_id"],
                name="unique_publication_bundle_item",
            ),
        ]


class CatalogFieldDecision(UUIDTimeStampedModel):
    """Current editorial state for one field in one cataloging context."""

    class Status(models.TextChoices):
        EMPTY = "empty", "未填写"
        SUGGESTED = "suggested", "有建议"
        NEEDS_REVIEW = "needs_review", "需要确认"
        CONFIRMED = "confirmed", "已确认"
        CONFLICT = "conflict", "存在冲突"
        NOT_APPLICABLE = "not_applicable", "不适用"
        STALE = "stale", "建议重新检查"

    class ConfirmationMethod(models.TextChoices):
        MANUAL = "manual", "人工填写"
        CANDIDATE = "candidate", "采用建议"
        INLINE_CREATE = "inline_create", "新建并关联"
        MIGRATED = "migrated", "历史迁移"

    context_type = models.CharField(max_length=48, db_index=True)
    context_id = models.UUIDField(db_index=True)
    edition = models.ForeignKey(
        Edition,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="field_decisions",
    )
    target_type = models.CharField(max_length=48, db_index=True)
    target_id = models.UUIDField(db_index=True)
    field_name = models.CharField(max_length=120, db_index=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.EMPTY,
        db_index=True,
    )
    value = models.JSONField(null=True, blank=True)
    previous_value = models.JSONField(null=True, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    evidence_summary = models.JSONField(default=list, blank=True)
    candidate_type = models.CharField(max_length=48, blank=True)
    candidate_id = models.UUIDField(null=True, blank=True)
    dependency_fields = models.JSONField(default=list, blank=True)
    dependency_fingerprint = models.CharField(max_length=64, blank=True)
    stale_reason = models.CharField(max_length=500, blank=True)
    confirmation_method = models.CharField(
        max_length=24,
        choices=ConfirmationMethod.choices,
        default=ConfirmationMethod.MANUAL,
    )
    bundle = models.ForeignKey(
        PublicationBundle,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="field_decisions",
    )
    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_field_decisions",
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["context_type", "context_id", "target_type", "field_name"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "context_type",
                    "context_id",
                    "target_type",
                    "target_id",
                    "field_name",
                ],
                name="unique_catalog_field_decision",
            ),
        ]
        indexes = [
            models.Index(fields=["edition", "status"]),
            models.Index(fields=["target_type", "target_id", "status"]),
        ]


class CatalogFieldDecisionLog(UUIDTimeStampedModel):
    decision = models.ForeignKey(
        CatalogFieldDecision,
        on_delete=models.CASCADE,
        related_name="audit_log",
    )
    action = models.CharField(max_length=40)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    candidate_type = models.CharField(max_length=48, blank=True)
    candidate_id = models.UUIDField(null=True, blank=True)
    source_summary = models.JSONField(default=list, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="catalog_field_decision_logs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["decision", "created_at"])]


class CatalogPublicationRevision(UUIDTimeStampedModel):
    """Immutable formal snapshot and serving boundary for one Edition."""

    class Status(models.TextChoices):
        PREPARING = "preparing", "准备中"
        ACTIVE = "active", "活动"
        SUPERSEDED = "superseded", "已取代"
        FAILED = "failed", "处理失败"
        WITHDRAWN = "withdrawn", "已撤回"

    edition = models.ForeignKey(
        Edition,
        on_delete=models.PROTECT,
        related_name="catalog_revisions",
    )
    revision = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PREPARING,
        db_index=True,
    )
    bundle = models.ForeignKey(
        PublicationBundle,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalog_revisions",
    )
    snapshot = models.JSONField(default=dict)
    changed_fields = models.JSONField(default=list, blank=True)
    related_entities = models.JSONField(default=list, blank=True)
    document_revision = models.ForeignKey(
        DocumentRevision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalog_publication_revisions",
    )
    reader_asset = models.ForeignKey(
        Asset,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="catalog_publication_revisions",
    )
    metadata_ready = models.BooleanField(default=False, db_index=True)
    fulltext_ready = models.BooleanField(default=False, db_index=True)
    provenance = models.JSONField(default=dict, blank=True)
    content_fingerprint = models.CharField(max_length=64, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_catalog_publication_revisions",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    superseded_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    failure_code = models.CharField(max_length=120, blank=True)
    failure_message = models.TextField(blank=True)

    class Meta:
        ordering = ["edition_id", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["edition", "revision"],
                name="unique_catalog_publication_revision",
            ),
            models.UniqueConstraint(
                fields=["edition"],
                condition=models.Q(status="active"),
                name="one_active_catalog_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["edition", "status", "-revision"]),
            models.Index(fields=["status", "metadata_ready", "fulltext_ready"]),
        ]


class KnowledgePublicationEvent(UUIDTimeStampedModel):
    class EventType(models.TextChoices):
        CATALOG_PUBLISHED = "catalog_published", "馆藏发布"
        CATALOG_UPDATED = "catalog_updated", "馆藏更新"
        CATALOG_WITHDRAWN = "catalog_withdrawn", "馆藏撤回"
        ENTITY_PUBLISHED = "entity_published", "实体发布"
        ENTITY_UPDATED = "entity_updated", "实体更新"
        ENTITY_MERGED = "entity_merged", "实体合并"

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "处理失败"
        DEAD_LETTER = "dead_letter", "需要人工处理"

    event_type = models.CharField(max_length=32, choices=EventType.choices, db_index=True)
    object_type = models.CharField(max_length=48, db_index=True)
    object_id = models.UUIDField(db_index=True)
    catalog_revision = models.ForeignKey(
        CatalogPublicationRevision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="knowledge_events",
    )
    domain_event = models.OneToOneField(
        "DomainChangeEvent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="knowledge_publication_event",
    )
    changed_fields = models.JSONField(default=list, blank=True)
    related_entities = models.JSONField(default=list, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="knowledge_publication_events",
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "created_at"]),
            models.Index(fields=["object_type", "object_id", "created_at"]),
        ]


class KnowledgeProjectionDelivery(UUIDTimeStampedModel):
    class Consumer(models.TextChoices):
        QUERY_LEXICON = "query_lexicon", "规范词典"
        BIBLIOGRAPHIC_SEARCH = "bibliographic_search", "书目搜索"
        FULLTEXT = "fulltext", "全文搜索"
        SEMANTIC = "semantic", "语义检索"
        RAG = "rag", "馆藏问答材料"
        VIEWPOINT = "viewpoint", "观点检索"
        KNOWLEDGE_GRAPH = "knowledge_graph", "知识关系"
        PERSON_SEARCH = "person_search", "人物搜索"
        RECOMMENDATION = "recommendation", "推荐"
        PUBLIC_CACHE = "public_cache", "公开缓存"

    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        PROCESSING = "processing", "处理中"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "处理失败"
        SKIPPED = "skipped", "无需处理"

    event = models.ForeignKey(
        KnowledgePublicationEvent,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    consumer = models.CharField(max_length=40, choices=Consumer.choices, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    source_revision = models.PositiveBigIntegerField(default=0)
    idempotency_key = models.CharField(max_length=220, unique=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)
    result = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["event_id", "consumer"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "consumer"],
                name="unique_knowledge_projection_delivery",
            ),
        ]
        indexes = [models.Index(fields=["status", "consumer", "updated_at"])]


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


class LegacyKnowledgeMapping(QueryLexiconAuthorityMixin, UUIDTimeStampedModel):
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


class QueryLexiconGeneration(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        STAGING = "staging", "构建中"
        ACTIVE = "active", "活动"
        RETIRED = "retired", "已退役"
        FAILED = "failed", "构建失败"
        DISCARDED = "discarded", "内容未变化"

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.STAGING,
        db_index=True,
    )
    start_event_seq = models.PositiveBigIntegerField(default=0)
    cutover_event_seq = models.PositiveBigIntegerField(default=0)
    normalization_version = models.CharField(max_length=80)
    source_registry_version = models.CharField(max_length=80)
    effective_content_hash = models.CharField(max_length=64, blank=True)
    entry_count = models.PositiveBigIntegerField(default=0)
    build_stats = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    built_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status="active"),
                name="single_active_query_lexicon_generation",
            ),
        ]


class QueryLexiconState(models.Model):
    key = models.CharField(max_length=32, primary_key=True, default="default", editable=False)
    revision = models.PositiveBigIntegerField(default=0)
    active_generation = models.ForeignKey(
        QueryLexiconGeneration,
        on_delete=models.PROTECT,
        related_name="active_states",
    )
    normalization_version = models.CharField(max_length=80)
    source_registry_version = models.CharField(max_length=80)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    last_reconciled_at = models.DateTimeField(null=True, blank=True)
    last_reconciled_content_hash = models.CharField(max_length=64, blank=True)
    last_reconciled_revision = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(key="default"),
                name="query_lexicon_state_default_key",
            ),
        ]


class QueryLexiconEntry(UUIDTimeStampedModel):
    class EntityType(models.TextChoices):
        WORK = "work", "作品"
        PERSON = "person", "人物"
        KNOWLEDGE_NODE = "knowledge_node", "知识节点"
        DISCIPLINE = "discipline", "学科"
        THEORY_SCHOOL = "theory_school", "理论流派"
        TOPIC = "topic", "主题"
        CONCEPT = "concept", "概念"
        SUBDISCIPLINE = "subdiscipline", "子学科"

    class TermType(models.TextChoices):
        CANONICAL = "canonical", "规范名称"
        TRANSLATION = "translation", "译名"
        ALIAS = "alias", "别名"
        ABBREVIATION = "abbreviation", "简称"
        HISTORICAL = "historical", "历史名称"
        TRANSLITERATION = "transliteration", "音译"
        SEARCH_VARIANT = "search_variant", "检索变体"

    class SourceKind(models.TextChoices):
        WORK_FIELD = "work_field", "正式作品字段"
        AUTHORITY_FIELD = "authority_field", "权威字段"
        PERSON_NAME_VARIANT = "person_name_variant", "结构化人物名称"
        KNOWLEDGE_NODE_ALIAS = "knowledge_node_alias", "结构化知识别名"
        LEGACY_AUTHORITY_FIELD = "legacy_authority_field", "旧权威字段"
        LEGACY_MIXED_ALIAS = "legacy_mixed_alias", "历史混合别名"
        GENERATED_SEARCH_VARIANT = "generated_search_variant", "机器检索变体"

    class TrustLevel(models.TextChoices):
        AUTHORITATIVE = "authoritative", "权威规范"
        VERIFIED = "verified", "人工或权威来源确认"
        UNVERIFIED = "unverified", "结构化但未确认"
        LEGACY = "legacy", "历史来源不明"
        GENERATED = "generated", "机器派生"

    generation = models.ForeignKey(
        QueryLexiconGeneration,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    entity_type = models.CharField(max_length=32, choices=EntityType.choices)
    entity_id = models.UUIDField()
    term = models.CharField(max_length=500)
    normalized_term = models.CharField(max_length=500)
    language = models.CharField(max_length=24, default="und")
    term_type = models.CharField(max_length=24, choices=TermType.choices)
    source_kind = models.CharField(max_length=40, choices=SourceKind.choices)
    trust_level = models.CharField(max_length=24, choices=TrustLevel.choices)
    source_ref = models.CharField(max_length=320)
    source_fingerprint = models.CharField(max_length=64)
    provenance = models.JSONField(default=dict, blank=True)
    displayable = models.BooleanField(default=False)
    public_active = models.BooleanField(default=False)
    admin_resolvable = models.BooleanField(default=False)

    class Meta:
        ordering = ["entity_type", "entity_id", "normalized_term"]
        constraints = [
            models.UniqueConstraint(
                fields=["generation", "entity_type", "entity_id", "normalized_term"],
                name="unique_query_lexicon_entity_term",
            ),
            models.CheckConstraint(
                condition=~models.Q(term="") & ~models.Q(normalized_term=""),
                name="query_lexicon_term_not_empty",
            ),
            models.CheckConstraint(
                condition=models.Q(public_active=False) | models.Q(admin_resolvable=True),
                name="public_query_term_admin_resolvable",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(displayable=False)
                    | ~models.Q(
                        source_kind__in=[
                            "legacy_mixed_alias",
                            "generated_search_variant",
                        ]
                    )
                ),
                name="untrusted_query_term_not_displayable",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(source_kind="generated_search_variant")
                    | models.Q(term_type="search_variant", displayable=False)
                ),
                name="generated_query_term_is_search_variant",
            ),
        ]
        indexes = [
            models.Index(
                fields=["generation", "public_active", "normalized_term"],
                name="ql_public_term_idx",
            ),
            models.Index(
                fields=["generation", "admin_resolvable", "normalized_term"],
                name="ql_admin_term_idx",
            ),
            models.Index(
                fields=["generation", "entity_type", "entity_id"],
                name="ql_entity_idx",
            ),
        ]


class QueryLexiconCandidate(UUIDTimeStampedModel):
    """A reviewable PDF-derived proposal; never an authority record itself."""

    class CandidateType(models.TextChoices):
        PERSON_NAME_VARIANT = "person_name_variant", "人物名称变体"
        KNOWLEDGE_NODE_ALIAS = "knowledge_node_alias", "知识节点别名"

    class TargetEntityType(models.TextChoices):
        PERSON = "person", "人物"
        KNOWLEDGE_NODE = "knowledge_node", "知识节点"

    class LinkingStatus(models.TextChoices):
        LINKED = "linked", "已唯一关联"
        AMBIGUOUS = "ambiguous", "存在歧义"
        UNRESOLVED = "unresolved", "未解析"

    class Status(models.TextChoices):
        PENDING = "pending", "待审核"
        ACCEPTED = "accepted", "已接受"
        REJECTED = "rejected", "已拒绝"
        SUPERSEDED = "superseded", "证据已过期"

    class SourceKind(models.TextChoices):
        PDF = "pdf", "馆藏 PDF"

    candidate_type = models.CharField(max_length=32, choices=CandidateType.choices)
    target_entity_type = models.CharField(
        max_length=32,
        choices=TargetEntityType.choices,
        blank=True,
    )
    target_entity_id = models.UUIDField(null=True, blank=True)
    anchor_term = models.CharField(max_length=500)
    normalized_anchor_term = models.CharField(max_length=500, db_index=True)
    proposed_term = models.CharField(max_length=500)
    normalized_term = models.CharField(max_length=500, db_index=True)
    language = models.CharField(max_length=24, default="und")
    proposed_term_type = models.CharField(
        max_length=24,
        choices=[
            ("translation", "译名"),
            ("alias", "别名"),
            ("abbreviation", "简称"),
            ("historical", "历史名称"),
            ("transliteration", "音译"),
        ],
    )
    source_kind = models.CharField(
        max_length=24,
        choices=SourceKind.choices,
        default=SourceKind.PDF,
    )
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_factors = models.JSONField(default=dict, blank=True)
    linking_status = models.CharField(
        max_length=20,
        choices=LinkingStatus.choices,
        default=LinkingStatus.LINKED,
        db_index=True,
    )
    possible_targets = models.JSONField(default=list, blank=True)
    ambiguity = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    displayable = models.BooleanField(default=False)
    extraction_version = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_query_lexicon_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True)
    accepted_authority_model = models.CharField(max_length=120, blank=True)
    accepted_authority_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-confidence", "created_at"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(anchor_term="")
                & ~models.Q(normalized_anchor_term="")
                & ~models.Q(proposed_term="")
                & ~models.Q(normalized_term=""),
                name="ql_candidate_terms_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        linking_status="linked",
                        target_entity_type__in=["person", "knowledge_node"],
                        target_entity_id__isnull=False,
                    )
                    | models.Q(
                        linking_status="ambiguous",
                        target_entity_type__in=["person", "knowledge_node"],
                        target_entity_id__isnull=True,
                    )
                    | models.Q(
                        linking_status="unresolved",
                        target_entity_type="",
                        target_entity_id__isnull=True,
                    )
                ),
                name="ql_candidate_link_target_state",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="accepted")
                    | models.Q(
                        linking_status="linked",
                        target_entity_id__isnull=False,
                    )
                ),
                name="ql_candidate_accept_requires_target",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    proposed_term_type__in=[
                        "translation",
                        "alias",
                        "abbreviation",
                        "historical",
                        "transliteration",
                    ]
                ),
                name="ql_candidate_term_type_allowed",
            ),
            models.CheckConstraint(
                condition=models.Q(source_kind="pdf"),
                name="ql_candidate_source_is_pdf",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "linking_status", "-confidence"],
                name="ql_candidate_status_idx",
            ),
            models.Index(
                fields=["target_entity_type", "target_entity_id"],
                name="ql_candidate_target_idx",
            ),
            models.Index(
                fields=["normalized_term", "language"],
                name="ql_candidate_term_idx",
            ),
        ]

    def __str__(self):
        return self.proposed_term

    def save(self, *args, **kwargs):
        from catalog.services.query_lexicon.normalization import (
            normalize_language,
            normalize_term,
        )

        self.anchor_term = " ".join(str(self.anchor_term or "").split()).strip()
        self.proposed_term = " ".join(str(self.proposed_term or "").split()).strip()
        self.normalized_anchor_term = normalize_term(self.anchor_term)
        self.normalized_term = normalize_term(self.proposed_term)
        self.language = normalize_language(self.language)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {
            "anchor_term",
            "proposed_term",
            "language",
        }.intersection(update_fields):
            kwargs["update_fields"] = tuple(
                dict.fromkeys(
                    [
                        *update_fields,
                        "normalized_anchor_term",
                        "normalized_term",
                        "language",
                    ]
                )
            )
        super().save(*args, **kwargs)


class QueryLexiconCandidateEvidence(UUIDTimeStampedModel):
    candidate = models.ForeignKey(
        QueryLexiconCandidate,
        on_delete=models.CASCADE,
        related_name="evidence_records",
    )
    work = models.ForeignKey(
        Work,
        on_delete=models.PROTECT,
        related_name="query_lexicon_candidate_evidence",
    )
    edition = models.ForeignKey(
        Edition,
        on_delete=models.PROTECT,
        related_name="query_lexicon_candidate_evidence",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="query_lexicon_candidate_evidence",
    )
    page = models.ForeignKey(
        Page,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="query_lexicon_candidate_evidence",
    )
    semantic_chunk = models.ForeignKey(
        SemanticChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="query_lexicon_candidate_evidence",
    )
    document_id = models.CharField(max_length=64, blank=True, db_index=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    printed_page_label = models.CharField(max_length=40, blank=True)
    bbox = models.JSONField(default=list, blank=True)
    evidence_text = models.TextField()
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    left_term = models.CharField(max_length=500)
    right_term = models.CharField(max_length=500)
    detected_pair = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(max_length=80)
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_factors = models.JSONField(default=dict, blank=True)
    ocr_quality = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    quality_flags = models.JSONField(default=list, blank=True)
    source_text_checksum = models.CharField(max_length=64)
    extraction_version = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64, editable=False)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["work__title", "page_number", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "fingerprint"],
                name="unique_ql_candidate_evidence",
            ),
            models.CheckConstraint(
                condition=models.Q(end_offset__gte=models.F("start_offset")),
                name="ql_evidence_offsets_ordered",
            ),
            models.CheckConstraint(
                condition=~models.Q(evidence_text="")
                & ~models.Q(source_text_checksum=""),
                name="ql_evidence_source_not_empty",
            ),
        ]
        indexes = [
            models.Index(
                fields=["candidate", "is_current"],
                name="ql_evidence_current_idx",
            ),
            models.Index(
                fields=["asset", "page_number"],
                name="ql_evidence_asset_idx",
            ),
            models.Index(
                fields=["work", "is_current"],
                name="ql_evidence_work_idx",
            ),
        ]

    def __str__(self):
        return f"{self.candidate.proposed_term} · {self.work.title} · {self.page_number or '-'}"


class NewAuthorityCandidate(UUIDTimeStampedModel):
    """Aggregated unresolved PDF observation requiring an explicit admin choice."""

    class EntityType(models.TextChoices):
        PERSON = "person", "人物"
        KNOWLEDGE_NODE = "knowledge_node", "知识节点"
        TOPIC = "topic", "主题"
        UNKNOWN = "unknown", "待判断"

    class Status(models.TextChoices):
        PENDING = "pending", "待审核"
        MATCHED = "matched", "已关联现有实体"
        DRAFT_CREATED = "draft_created", "已创建草稿"
        REJECTED = "rejected", "已拒绝"
        SUPERSEDED = "superseded", "证据已过期"

    entity_type = models.CharField(
        max_length=32,
        choices=EntityType.choices,
        default=EntityType.UNKNOWN,
        db_index=True,
    )
    primary_term = models.CharField(max_length=500)
    normalized_primary_term = models.CharField(max_length=500, db_index=True)
    terms = models.JSONField(default=list)
    languages = models.JSONField(default=list, blank=True)
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_factors = models.JSONField(default=dict, blank=True)
    possible_matches = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    matched_entity_type = models.CharField(max_length=32, blank=True)
    matched_entity_id = models.UUIDField(null=True, blank=True)
    draft_entity_type = models.CharField(max_length=32, blank=True)
    draft_entity_id = models.UUIDField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_new_authority_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-confidence", "created_at"]
        indexes = [
            models.Index(
                fields=["status", "entity_type", "-confidence"],
                name="new_authority_review_idx",
            ),
            models.Index(
                fields=["normalized_primary_term", "entity_type"],
                name="new_authority_term_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(primary_term="")
                & ~models.Q(normalized_primary_term=""),
                name="new_authority_term_not_empty",
            ),
        ]

    def __str__(self):
        return self.primary_term


class UnknownEntityObservation(UUIDTimeStampedModel):
    """Auditable PDF evidence that did not have a safe canonical anchor."""

    candidate = models.ForeignKey(
        NewAuthorityCandidate,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="observations",
    )
    work = models.ForeignKey(
        Work,
        on_delete=models.PROTECT,
        related_name="unknown_entity_observations",
    )
    edition = models.ForeignKey(
        Edition,
        on_delete=models.PROTECT,
        related_name="unknown_entity_observations",
    )
    asset = models.ForeignKey(
        Asset,
        on_delete=models.PROTECT,
        related_name="unknown_entity_observations",
    )
    page = models.ForeignKey(
        Page,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unknown_entity_observations",
    )
    semantic_chunk = models.ForeignKey(
        SemanticChunk,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="unknown_entity_observations",
    )
    document_id = models.CharField(max_length=64, blank=True, db_index=True)
    page_number = models.PositiveIntegerField(null=True, blank=True)
    printed_page_label = models.CharField(max_length=40, blank=True)
    terms = models.JSONField(default=list)
    languages = models.JSONField(default=list, blank=True)
    entity_guess = models.CharField(
        max_length=32,
        choices=NewAuthorityCandidate.EntityType.choices,
        default=NewAuthorityCandidate.EntityType.UNKNOWN,
        db_index=True,
    )
    evidence_text = models.TextField()
    start_offset = models.PositiveIntegerField(default=0)
    end_offset = models.PositiveIntegerField(default=0)
    extraction_method = models.CharField(max_length=80)
    extraction_version = models.CharField(max_length=80)
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_factors = models.JSONField(default=dict, blank=True)
    source_text_checksum = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["work__title", "page_number", "created_at"]
        indexes = [
            models.Index(
                fields=["candidate", "is_current"],
                name="unknown_obs_current_idx",
            ),
            models.Index(
                fields=["asset", "is_current"],
                name="unknown_observation_asset_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_offset__gte=models.F("start_offset")),
                name="unknown_observation_offsets_ordered",
            ),
            models.CheckConstraint(
                condition=~models.Q(evidence_text="")
                & ~models.Q(source_text_checksum=""),
                name="unknown_observation_source_not_empty",
            ),
        ]

    def __str__(self):
        return f"{self.candidate or self.terms} · {self.work.title}"


class EnrichmentSourceClass(models.TextChoices):
    IDENTIFIER_REGISTRY = "identifier_registry", "标识符注册库"
    PUBLISHER = "publisher", "出版社"
    NATIONAL_LIBRARY = "national_library", "国家图书馆"
    LIBRARY_CATALOG = "library_catalog", "图书馆目录"
    UNIVERSITY = "university", "大学"
    RESEARCH_INSTITUTE = "research_institute", "研究机构"
    ACADEMIC_JOURNAL = "academic_journal", "学术期刊"
    PROFESSIONAL_ASSOCIATION = "professional_association", "专业协会"
    SCHOLARLY_ENCYCLOPEDIA = "scholarly_encyclopedia", "学术百科"
    SCHOLAR_HOMEPAGE = "scholar_homepage", "学者主页"
    SYLLABUS = "syllabus", "课程大纲"
    GENERAL_WEB = "general_web", "一般网页"
    UNKNOWN = "unknown", "未知来源"


class EnrichmentCandidate(UUIDTimeStampedModel):
    """Reviewable field value proposed from structured or fetched sources."""

    class TargetType(models.TextChoices):
        PERSON = "person", "人物"
        WORK = "work", "作品"
        EDITION = "edition", "版本"
        DISCIPLINE = "discipline", "学科"
        SUBDISCIPLINE = "subdiscipline", "子学科"
        KNOWLEDGE_NODE = "knowledge_node", "知识节点"
        TOPIC = "topic", "主题"
        READING_PATH = "reading_path", "阅读路径"

    class CandidateKind(models.TextChoices):
        FACTUAL = "factual", "事实"
        CLASSIFICATION = "classification", "分类"
        INTERPRETIVE = "interpretive", "解释"

    class Status(models.TextChoices):
        PENDING = "pending", "待审核"
        ACCEPTED = "accepted", "已接受"
        REJECTED = "rejected", "已拒绝"
        SUPERSEDED = "superseded", "已被替代"

    class IdentityStatus(models.TextChoices):
        NOT_REQUIRED = "not_required", "无需身份核验"
        CONFIRMED = "confirmed", "身份已确认"
        AMBIGUOUS = "ambiguous", "身份存在歧义"
        CONFLICT = "conflict", "身份冲突"

    class RequestedMode(models.TextChoices):
        STRUCTURED = "structured", "结构化来源"
        WEB = "web", "联网来源"
        FULL = "full", "结构化与联网来源"

    target_type = models.CharField(max_length=32, choices=TargetType.choices, db_index=True)
    target_id = models.UUIDField(db_index=True)
    field_name = models.CharField(max_length=96, db_index=True)
    candidate_kind = models.CharField(max_length=24, choices=CandidateKind.choices, db_index=True)
    proposed_value = models.JSONField()
    normalized_value = models.JSONField(default=dict, blank=True)
    current_value = models.JSONField(default=dict, blank=True, null=True)
    request_context = models.JSONField(default=dict, blank=True)
    source_class = models.CharField(
        max_length=40,
        choices=EnrichmentSourceClass.choices,
        default=EnrichmentSourceClass.UNKNOWN,
        db_index=True,
    )
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    confidence_factors = models.JSONField(default=dict, blank=True)
    conflicts = models.JSONField(default=list, blank=True)
    identity_status = models.CharField(
        max_length=24,
        choices=IdentityStatus.choices,
        default=IdentityStatus.NOT_REQUIRED,
        db_index=True,
    )
    identity_evidence = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    requested_mode = models.CharField(
        max_length=20,
        choices=RequestedMode.choices,
        default=RequestedMode.STRUCTURED,
    )
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    conflict_group = models.CharField(max_length=64, db_index=True)
    policy_version = models.CharField(max_length=80)
    extraction_version = models.CharField(max_length=80)
    fingerprint = models.CharField(max_length=64, unique=True, editable=False)
    refresh_after = models.DateTimeField(null=True, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_enrichment_candidates",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="reviewed_enrichment_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True)
    accepted_authority_model = models.CharField(max_length=120, blank=True)
    accepted_authority_id = models.UUIDField(null=True, blank=True)

    class Meta:
        ordering = ["-confidence", "created_at"]
        indexes = [
            models.Index(
                fields=["target_type", "target_id", "field_name", "status"],
                name="enrich_target_field_idx",
            ),
            models.Index(
                fields=["status", "candidate_kind", "-confidence"],
                name="enrich_review_queue_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(field_name="") & ~models.Q(conflict_group=""),
                name="enrichment_candidate_keys_not_empty",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="accepted")
                    | (
                        ~models.Q(accepted_authority_model="")
                        & models.Q(accepted_authority_id__isnull=False)
                    )
                ),
                name="enrichment_accept_has_authority",
            ),
        ]

    def __str__(self):
        return f"{self.target_type}:{self.target_id} · {self.field_name}"


class EnrichmentEvidence(UUIDTimeStampedModel):
    candidate = models.ForeignKey(
        EnrichmentCandidate,
        on_delete=models.CASCADE,
        related_name="evidence_records",
    )
    source_record = models.ForeignKey(
        "ingestion.SourceRecord",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="enrichment_evidence",
    )
    source_url = models.URLField(max_length=2000)
    canonical_url = models.URLField(max_length=2000)
    source_title = models.CharField(max_length=1000)
    source_domain = models.CharField(max_length=255, db_index=True)
    source_class = models.CharField(
        max_length=40,
        choices=EnrichmentSourceClass.choices,
        db_index=True,
    )
    provider = models.CharField(max_length=120, db_index=True)
    external_identifier = models.CharField(max_length=500, blank=True, db_index=True)
    supporting_text = models.TextField()
    locator = models.JSONField(default=dict, blank=True)
    retrieved_at = models.DateTimeField(db_index=True)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=160, blank=True)
    content_checksum = models.CharField(max_length=64)
    entity_match_evidence = models.JSONField(default=dict, blank=True)
    extraction_method = models.CharField(max_length=80)
    extraction_version = models.CharField(max_length=80)
    confidence = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(1)],
    )
    fingerprint = models.CharField(max_length=64, editable=False)
    is_current = models.BooleanField(default=True, db_index=True)
    superseded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-retrieved_at", "source_title"]
        indexes = [
            models.Index(
                fields=["candidate", "is_current"],
                name="enrich_evidence_current_idx",
            ),
            models.Index(
                fields=["canonical_url", "is_current"],
                name="enrich_evidence_url_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "fingerprint"],
                name="unique_enrichment_evidence",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(source_url="")
                    & ~models.Q(canonical_url="")
                    & ~models.Q(source_title="")
                    & ~models.Q(supporting_text="")
                    & ~models.Q(content_checksum="")
                ),
                name="enrichment_evidence_source_not_empty",
            ),
        ]

    def __str__(self):
        return f"{self.candidate.field_name} · {self.source_title}"


class QueryLexiconChangeEvent(models.Model):
    class Action(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "更新"
        DELETE = "delete", "删除"

    event_seq = models.BigAutoField(primary_key=True)
    entity_type = models.CharField(max_length=32, choices=QueryLexiconEntry.EntityType.choices)
    entity_id = models.UUIDField()
    action = models.CharField(max_length=16, choices=Action.choices)
    source_model = models.CharField(max_length=120)
    source_object_id = models.UUIDField()
    correlation_id = models.UUIDField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    applied_revision = models.PositiveBigIntegerField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)
    dead_lettered_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["event_seq"]
        indexes = [
            models.Index(
                fields=["next_attempt_at", "event_seq"],
                condition=models.Q(processed_at__isnull=True, dead_lettered_at__isnull=True),
                name="ql_event_pending_idx",
            ),
            models.Index(
                fields=["entity_type", "entity_id", "event_seq"],
                name="ql_event_entity_idx",
            ),
        ]


class CanonicalObjectRevision(UUIDTimeStampedModel):
    object_type = models.CharField(max_length=80, db_index=True)
    object_id = models.UUIDField(db_index=True)
    current_revision = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "object_id"],
                name="unique_canonical_object_revision",
            ),
        ]


class DomainChangeEvent(UUIDTimeStampedModel):
    class ChangeKind(models.TextChoices):
        CREATE = "create", "创建"
        UPDATE = "update", "更新"
        PUBLISH = "publish", "发布"
        WITHDRAW = "withdraw", "下架"
        DELETE = "delete", "删除"

    object_type = models.CharField(max_length=80, db_index=True)
    object_id = models.UUIDField(db_index=True)
    canonical_revision = models.PositiveBigIntegerField()
    change_kind = models.CharField(max_length=20, choices=ChangeKind.choices)
    changed_fields = models.JSONField(default=list, blank=True)
    catalog_revision = models.ForeignKey(
        "CatalogPublicationRevision",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="domain_change_events",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="domain_change_events",
    )
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    processed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "object_id", "canonical_revision"],
                name="unique_domain_object_revision",
            ),
        ]
        indexes = [
            models.Index(fields=["processed_at", "next_attempt_at", "created_at"]),
        ]


class ProjectionState(UUIDTimeStampedModel):
    class ProjectionType(models.TextChoices):
        QUERY_LEXICON = "query_lexicon", "QueryLexicon"
        FULLTEXT = "fulltext", "全文"
        SEMANTIC = "semantic", "语义"
        CLAIM_INDEX = "claim_index", "Claim Index"
        KNOWLEDGE_GRAPH = "knowledge_graph", "知识关系"
        TIMELINE = "timeline", "时间轴"
        RECOMMENDATION = "recommendation", "推荐"
        READING_PATH_SUPPORT = "reading_path_support", "阅读路径支持"
        PUBLIC = "public", "公网呈现"

    class Status(models.TextChoices):
        CURRENT = "current", "最新"
        STALE = "stale", "落后"
        PROJECTING = "projecting", "更新中"
        WAITING_FOR_CAPABILITY = "waiting_for_capability", "等待执行能力"
        FAILED = "failed", "失败"
        UNKNOWN = "unknown", "待核实"

    object_type = models.CharField(max_length=80, db_index=True)
    object_id = models.UUIDField(db_index=True)
    projection_type = models.CharField(max_length=40, choices=ProjectionType.choices, db_index=True)
    source_revision = models.PositiveBigIntegerField(default=0)
    projected_revision = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.UNKNOWN, db_index=True)
    stale_reason = models.CharField(max_length=300, blank=True)
    task_owner_type = models.CharField(max_length=80, blank=True)
    task_owner_key = models.CharField(max_length=255, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)
    last_projected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["object_type", "object_id", "projection_type"],
                name="unique_object_projection_state",
            ),
            models.CheckConstraint(
                condition=models.Q(source_revision__gte=models.F("projected_revision")),
                name="projection_revision_not_ahead",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "projection_type", "updated_at"]),
        ]


class CapabilityExecutor(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        NAS = "nas", "NAS"
        REMOTE_GPU = "remote_gpu", "远程 GPU"
        CLOUD = "cloud", "云端"

    class Status(models.TextChoices):
        ONLINE = "online", "在线"
        OFFLINE = "offline", "离线"
        DRAINING = "draining", "停止接单"

    executor_id = models.CharField(max_length=160, unique=True)
    display_name = models.CharField(max_length=240, blank=True)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    capabilities = models.JSONField(default=list)
    model_revisions = models.JSONField(default=dict, blank=True)
    concurrency = models.PositiveSmallIntegerField(default=1)
    current_load = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OFFLINE, db_index=True)
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, db_index=True)
    heartbeat_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "heartbeat_expires_at"])]


class CapabilityDemand(UUIDTimeStampedModel):
    class State(models.TextChoices):
        WAITING_FOR_CAPABILITY = "waiting_for_capability", "等待执行能力"
        READY = "ready", "可领取"
        CLAIMED = "claimed", "已领取"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "失败"
        CANCELED = "canceled", "已取消"

    owner_type = models.CharField(max_length=80, db_index=True)
    owner_key = models.CharField(max_length=255, db_index=True)
    capability = models.CharField(max_length=80, db_index=True)
    state = models.CharField(
        max_length=32,
        choices=State.choices,
        default=State.WAITING_FOR_CAPABILITY,
        db_index=True,
    )
    priority = models.SmallIntegerField(default=0)
    publication_blocking = models.BooleanField(default=False)
    preferred_queue = models.CharField(max_length=120, blank=True)
    idempotency_key = models.CharField(max_length=200, unique=True)
    claimed_by = models.ForeignKey(
        CapabilityExecutor,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="claimed_demands",
    )
    lease_token = models.UUIDField(null=True, blank=True, db_index=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    not_before = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    last_error_code = models.CharField(max_length=120, blank=True)
    last_error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-priority", "created_at"]
        indexes = [
            models.Index(fields=["state", "capability", "-priority", "created_at"]),
            models.Index(fields=["owner_type", "owner_key"]),
        ]


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


class ResearchRun(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待外部研究"
        RUNNING = "running", "研究中"
        COMPLETED = "completed", "完成"
        DEGRADED = "degraded", "部分来源不可用"
        FAILED = "failed", "失败"
        CANCELED = "canceled", "已取消"
        SUPERSEDED = "superseded", "草稿变化后已过期"

    class Trigger(models.TextChoices):
        AUTO_LOAD = "auto_load", "页面自动研究"
        FIELD_CHANGE = "field_change", "字段变化"
        MANUAL = "manual", "人工重新研究"
        HEALTH = "health", "健康探测"

    work = models.ForeignKey(Work, on_delete=models.CASCADE, related_name="research_runs")
    edition = models.ForeignKey(Edition, on_delete=models.CASCADE, related_name="research_runs")
    upload_item_id = models.UUIDField(null=True, blank=True, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="research_runs",
    )
    trigger = models.CharField(max_length=24, choices=Trigger.choices, default=Trigger.AUTO_LOAD)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    idempotency_key = models.CharField(max_length=128, unique=True)
    context_fingerprint = models.CharField(max_length=64, db_index=True)
    canonical_revision = models.JSONField(default=dict, blank=True)
    draft_session_id = models.CharField(max_length=96, blank=True)
    draft_hash = models.CharField(max_length=64, blank=True)
    trigger_input_values = models.JSONField(default=dict, blank=True)
    trigger_input_hash = models.CharField(max_length=64, blank=True)
    is_current = models.BooleanField(default=True)
    superseded_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_runs",
    )
    superseded_at = models.DateTimeField(null=True, blank=True)
    stale_reason = models.CharField(max_length=300, blank=True)
    context_version = models.CharField(max_length=80)
    contract_version = models.CharField(max_length=80)
    planner_version = models.CharField(max_length=80)
    active_step = models.CharField(max_length=40, db_index=True)
    changed_fields = models.JSONField(default=list, blank=True)
    context_snapshot = models.JSONField(default=dict)
    plan = models.JSONField(default=list)
    local_results = models.JSONField(default=dict)
    external_results = models.JSONField(default=dict)
    diagnostics = models.JSONField(default=dict)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    task_id = models.CharField(max_length=255, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["work", "active_step", "created_at"]),
            models.Index(fields=["context_fingerprint", "created_at"]),
            models.Index(fields=["edition", "draft_session_id", "is_current", "created_at"]),
        ]


class ResearchTaskProfile(UUIDTimeStampedModel):
    """Versioned policy describing how the existing orchestrator runs one task."""

    key = models.CharField(max_length=120, db_index=True)
    version = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=240)
    required_context = models.JSONField(default=list)
    retrieval_profile = models.CharField(max_length=80)
    preferred_evidence_sources = models.JSONField(default=list)
    minimum_evidence_policy = models.JSONField(default=dict)
    prompt_key = models.CharField(max_length=160)
    output_schema = models.JSONField(default=dict)
    ranking_policy = models.JSONField(default=dict)
    human_review_policy = models.JSONField(default=dict)
    required_capability = models.CharField(max_length=80, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_research_task_profiles",
    )

    class Meta:
        ordering = ["key", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "version"],
                name="unique_research_task_profile_version",
            ),
            models.UniqueConstraint(
                fields=["key"],
                condition=models.Q(is_active=True),
                name="unique_active_research_task_profile",
            ),
        ]


class PromptRegistryEntry(UUIDTimeStampedModel):
    """Auditable prompt revisions; active entries are configuration, not code."""

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        ACTIVE = "active", "启用"
        RETIRED = "retired", "停用"

    key = models.CharField(max_length=160, db_index=True)
    version = models.PositiveIntegerField(default=1)
    capability = models.CharField(max_length=80, db_index=True)
    task_profile_key = models.CharField(max_length=120, blank=True, db_index=True)
    content = models.TextField()
    output_schema = models.JSONField(default=dict)
    provider_guidance = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, db_index=True)
    schema_hash = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_prompt_registry_entries",
    )
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="activated_prompt_registry_entries",
    )
    activated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["key", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["key", "version"],
                name="unique_prompt_registry_entry_version",
            ),
            models.UniqueConstraint(
                fields=["key"],
                condition=models.Q(status="active"),
                name="unique_active_prompt_registry_entry",
            ),
        ]


class EvidencePack(UUIDTimeStampedModel):
    """Immutable constrained evidence returned to a research task."""

    research_run = models.ForeignKey(
        ResearchRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="evidence_packs",
    )
    task_profile_key = models.CharField(max_length=120, db_index=True)
    task_profile_version = models.PositiveIntegerField(default=1)
    retrieval_profile = models.CharField(max_length=80)
    subject_type = models.CharField(max_length=80, blank=True, db_index=True)
    subject_id = models.CharField(max_length=160, blank=True, db_index=True)
    envelope_snapshot = models.JSONField(default=list)
    retrieval_snapshot = models.JSONField(default=dict)
    query_lexicon_revision = models.CharField(max_length=160, blank=True)
    semantic_index_uid = models.CharField(max_length=255, blank=True)
    document_revisions = models.JSONField(default=list)
    fingerprint = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_evidence_packs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["task_profile_key", "created_at"]),
            models.Index(fields=["subject_type", "subject_id", "created_at"]),
        ]


class DebateCandidate(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        ADOPTED = "adopted", "已采用"
        REJECTED = "rejected", "已拒绝"
        DEFERRED = "deferred", "稍后处理"

    title = models.CharField(max_length=300)
    canonical_question = models.TextField()
    summary = models.TextField(blank=True)
    evidence_pack = models.ForeignKey(
        EvidencePack,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="debate_candidates",
    )
    quality_score = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(1)])
    importance_score = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(1)])
    conflict_score = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(1)])
    corroboration_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    suggested_node = models.ForeignKey(
        KnowledgeNode,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="debate_candidates",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_debate_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-importance_score", "-quality_score", "created_at"]
        indexes = [models.Index(fields=["status", "-importance_score", "created_at"])]


class DebateCandidateClaim(UUIDTimeStampedModel):
    class Stance(models.TextChoices):
        SUPPORT = "support", "支持"
        OPPOSE = "oppose", "相斥"
        QUALIFY = "qualify", "限定"

    candidate = models.ForeignKey(DebateCandidate, on_delete=models.CASCADE, related_name="claim_links")
    claim = models.ForeignKey(DerivedClaim, on_delete=models.PROTECT, related_name="debate_candidate_links")
    stance = models.CharField(max_length=16, choices=Stance.choices)
    rank = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["stance", "rank", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate", "claim"],
                name="unique_debate_candidate_claim",
            ),
        ]


class ReadingPathCandidate(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        ADOPTED = "adopted", "已采用"
        REJECTED = "rejected", "已拒绝"
        DEFERRED = "deferred", "稍后处理"

    title = models.CharField(max_length=300)
    target_audience = models.CharField(max_length=300)
    learning_goal = models.TextField()
    stages = models.JSONField(default=list)
    evidence_pack = models.ForeignKey(
        EvidencePack,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reading_path_candidates",
    )
    quality_score = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(1)])
    importance_score = models.FloatField(default=0, validators=[MinValueValidator(0), MaxValueValidator(1)])
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    adopted_reading_path = models.ForeignKey(
        ReadingPath,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_candidates",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_reading_path_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["-importance_score", "-quality_score", "created_at"]
        indexes = [models.Index(fields=["status", "-importance_score", "created_at"])]


class IntelligenceFeedback(UUIDTimeStampedModel):
    class Decision(models.TextChoices):
        ACCEPT = "accept", "采用"
        ACCEPT_WITH_EDIT = "accept_with_edit", "修改后采用"
        REJECT = "reject", "拒绝"
        DEFER = "defer", "稍后处理"

    task_profile_key = models.CharField(max_length=120, db_index=True)
    task_profile_version = models.PositiveIntegerField(default=1)
    provider = models.CharField(max_length=120, blank=True, db_index=True)
    model = models.CharField(max_length=240, blank=True)
    prompt_key = models.CharField(max_length=160, blank=True, db_index=True)
    prompt_version = models.CharField(max_length=80, blank=True)
    candidate_type = models.CharField(max_length=80, db_index=True)
    candidate_id = models.CharField(max_length=160, db_index=True)
    decision = models.CharField(max_length=24, choices=Decision.choices, db_index=True)
    original_payload = models.JSONField(default=dict, blank=True)
    edited_payload = models.JSONField(default=dict, blank=True)
    field_key = models.CharField(max_length=120, blank=True, db_index=True)
    expertise = models.JSONField(default=list, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="intelligence_feedback",
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["candidate_type", "candidate_id", "reviewed_by"],
                name="unique_intelligence_candidate_feedback",
            ),
        ]
        indexes = [
            models.Index(fields=["task_profile_key", "decision", "created_at"]),
            models.Index(fields=["provider", "prompt_key", "decision"]),
        ]


class HealthCheckRun(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        HEALTHY = "healthy", "正常"
        DEGRADED = "degraded", "降级"
        FAILED = "failed", "故障"
        RECOVERING = "recovering", "恢复中"
        PAUSED = "paused", "已暂停"
        UNKNOWN = "unknown", "未知"

    class Source(models.TextChoices):
        SCHEDULED = "scheduled", "定时检查"
        MANUAL = "manual", "人工检查"
        RECOVERY = "recovery", "恢复复核"

    probe_key = models.CharField(max_length=120, db_index=True)
    capability = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.UNKNOWN, db_index=True)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.SCHEDULED)
    configured = models.BooleanField(null=True)
    reachable = models.BooleanField(null=True)
    functional = models.BooleanField(null=True)
    productive = models.BooleanField(null=True)
    summary = models.CharField(max_length=500, blank=True)
    details = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=120, blank=True, db_index=True)
    error_category = models.CharField(max_length=120, blank=True)
    started_at = models.DateTimeField(default=timezone.now)
    completed_at = models.DateTimeField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="health_check_runs",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["probe_key", "started_at"]),
            models.Index(fields=["capability", "status", "started_at"]),
        ]


class HealthIncident(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "待处理"
        RECOVERING = "recovering", "恢复中"
        RESOLVED = "resolved", "已恢复"

    class Severity(models.TextChoices):
        INFO = "info", "提示"
        WARNING = "warning", "警告"
        CRITICAL = "critical", "严重"

    incident_key = models.CharField(max_length=160, unique=True)
    capability = models.CharField(max_length=120, db_index=True)
    probe_key = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING)
    error_code = models.CharField(max_length=120, blank=True, db_index=True)
    error_category = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)
    recovery_attempt_count = models.PositiveIntegerField(default=0)
    affected_features = models.JSONField(default=list, blank=True)
    probable_causes = models.JSONField(default=list, blank=True)
    safe_recovery_actions = models.JSONField(default=list, blank=True)
    manual_guidance = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    latest_run = models.ForeignKey(
        HealthCheckRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidents",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_health_incidents",
    )

    class Meta:
        ordering = ["-last_seen_at"]
        indexes = [
            models.Index(fields=["status", "severity", "last_seen_at"]),
            models.Index(fields=["capability", "status"]),
        ]


class RecoveryAction(UUIDTimeStampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "等待"
        RUNNING = "running", "执行中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"
        CANCELED = "canceled", "取消"

    incident = models.ForeignKey(HealthIncident, on_delete=models.CASCADE, related_name="recovery_actions")
    action = models.CharField(max_length=120, db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED, db_index=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="recovery_actions",
    )
    attempt = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["incident", "status"]),
        ]


class SiteSetting(UUIDTimeStampedModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict)
    public = models.BooleanField(default=False)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)


class ProviderCredentialSecret(UUIDTimeStampedModel):
    """Server-side encrypted credential addressed only by a safe alias."""

    class Purpose(models.TextChoices):
        RESEARCH_SOURCE = "research_source", "Research Source"
        AI_RUNTIME = "ai_runtime", "AI Runtime"

    alias = models.SlugField(max_length=64, unique=True)
    purpose = models.CharField(max_length=32, choices=Purpose.choices, db_index=True)
    provider_key = models.CharField(max_length=120, blank=True, db_index=True)
    ciphertext = models.BinaryField()
    key_version = models.CharField(max_length=40, default="private-data-fernet-v1")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_provider_credential_secrets",
    )
    last_tested_at = models.DateTimeField(null=True, blank=True)
    last_test_status = models.CharField(max_length=32, blank=True)
    last_test_message = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["purpose", "alias"]
        indexes = [models.Index(fields=["purpose", "provider_key"])]


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
