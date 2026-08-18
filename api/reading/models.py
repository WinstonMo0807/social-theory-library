import uuid

from django.conf import settings
from django.db import models

from common.models import UUIDTimeStampedModel


class ReadingProgress(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_progress")
    asset = models.ForeignKey("catalog.Asset", on_delete=models.CASCADE, related_name="reader_progress")
    current_page = models.PositiveIntegerField(default=1)
    progress_ratio = models.FloatField(default=0)
    last_position = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "asset"], name="unique_user_asset_progress"),
        ]
        ordering = ["-updated_at"]


class Annotation(UUIDTimeStampedModel):
    class Kind(models.TextChoices):
        HIGHLIGHT = "highlight", "高亮"
        UNDERLINE = "underline", "划线"
        NOTE = "note", "笔记"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="annotations")
    asset = models.ForeignKey("catalog.Asset", on_delete=models.CASCADE, related_name="annotations")
    page = models.ForeignKey("catalog.Page", on_delete=models.CASCADE, related_name="annotations")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    selector = models.JSONField(default=dict)
    quote = models.TextField(blank=True)
    body_ciphertext = models.BinaryField(blank=True, default=bytes)
    color = models.CharField(max_length=20, default="yellow")
    asset_sha256 = models.CharField(max_length=64)
    orphaned = models.BooleanField(default=False)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["user", "asset", "page"])]


class Bookmark(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookmarks")
    asset = models.ForeignKey("catalog.Asset", on_delete=models.CASCADE, related_name="bookmarks")
    page = models.ForeignKey("catalog.Page", on_delete=models.CASCADE, related_name="bookmarks")
    label = models.CharField(max_length=240, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "asset", "page"], name="unique_page_bookmark"),
        ]


class SavedItem(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_items")
    work = models.ForeignKey("catalog.Work", on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "work"], name="unique_saved_work"),
        ]
        ordering = ["-created_at"]


class SavedTopic(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_topics")
    topic = models.ForeignKey("catalog.Topic", on_delete=models.CASCADE, related_name="saved_by")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "topic"], name="unique_saved_topic"),
        ]
        ordering = ["-created_at"]


class ReadingList(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_lists")
    title = models.CharField(max_length=240)
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)


class ReadingListItem(UUIDTimeStampedModel):
    reading_list = models.ForeignKey(ReadingList, on_delete=models.CASCADE, related_name="items")
    work = models.ForeignKey("catalog.Work", on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "created_at"]
        constraints = [
            models.UniqueConstraint(fields=["reading_list", "work"], name="unique_work_in_reading_list"),
        ]


class ReadingHistory(UUIDTimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reading_history")
    asset = models.ForeignKey("catalog.Asset", on_delete=models.CASCADE, related_name="reading_history")
    page_index = models.PositiveIntegerField(default=1)
    session_seconds = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]


class LibraryConversation(UUIDTimeStampedModel):
    class AssistMode(models.TextChoices):
        AUTO = "auto", "自动判断"
        ON = "on", "只依据书库"
        OFF = "off", "不检索书库"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="library_conversations",
    )
    title = models.CharField(max_length=240, blank=True)
    assist_mode = models.CharField(
        max_length=12,
        choices=AssistMode.choices,
        default=AssistMode.AUTO,
    )
    scope = models.JSONField(default=dict, blank=True)
    archived = models.BooleanField(default=False, db_index=True)
    last_message_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-last_message_at", "-updated_at"]
        indexes = [models.Index(fields=["user", "archived", "last_message_at"])]


class ReaderAIConnection(UUIDTimeStampedModel):
    class Provider(models.TextChoices):
        OPENAI_COMPATIBLE = "openai_compatible", "OpenAI 兼容接口"
        OLLAMA = "ollama", "Ollama"
        VLLM = "vllm", "vLLM"

    class Status(models.TextChoices):
        NOT_TESTED = "not_tested", "尚未测试"
        HEALTHY = "healthy", "可用"
        UNAVAILABLE = "unavailable", "暂不可用"
        INVALID = "invalid", "配置无效"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reader_ai_connection",
    )
    provider = models.CharField(max_length=32, choices=Provider.choices)
    base_url = models.URLField(max_length=2000)
    model = models.CharField(max_length=300)
    api_key_ciphertext = models.BinaryField(blank=True, default=bytes)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NOT_TESTED)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=80, blank=True)
    last_error_message = models.TextField(blank=True)

    class Meta:
        indexes = [models.Index(fields=["user", "enabled", "status"], name="reader_ai_user_status_idx")]


class LibraryMessage(UUIDTimeStampedModel):
    class Role(models.TextChoices):
        USER = "user", "读者"
        ASSISTANT = "assistant", "书库助手"

    class Status(models.TextChoices):
        PENDING = "pending", "等待生成"
        STREAMING = "streaming", "正在生成"
        COMPLETED = "completed", "已完成"
        FAILED = "failed", "生成失败"
        CANCELED = "canceled", "已取消"

    conversation = models.ForeignKey(
        LibraryConversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=Role.choices)
    request_id = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    body_ciphertext = models.BinaryField(blank=True, default=bytes)
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.COMPLETED,
        db_index=True,
    )
    retrieval_used = models.BooleanField(default=False)
    model_provider = models.CharField(max_length=40, blank=True)
    model_name = models.CharField(max_length=240, blank=True)
    runtime_profile_key = models.CharField(max_length=64, blank=True)
    query_type = models.CharField(max_length=32, blank=True)
    retrieval_profile = models.CharField(max_length=32, blank=True)
    prompt_version = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    usage = models.JSONField(default=dict, blank=True)
    cancel_requested_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["conversation", "created_at"])]


class LibraryMessageSource(UUIDTimeStampedModel):
    message = models.ForeignKey(
        LibraryMessage,
        on_delete=models.CASCADE,
        related_name="sources",
    )
    source_key = models.CharField(max_length=24)
    ordinal = models.PositiveSmallIntegerField()
    work = models.ForeignKey(
        "catalog.Work",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="library_answer_sources",
    )
    edition = models.ForeignKey(
        "catalog.Edition",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="library_answer_sources",
    )
    asset = models.ForeignKey(
        "catalog.Asset",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="library_answer_sources",
    )
    page = models.ForeignKey(
        "catalog.Page",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="library_answer_sources",
    )
    source_chunk_id = models.CharField(max_length=120, blank=True)
    document_id = models.CharField(max_length=64, blank=True, db_index=True)
    title_snapshot = models.CharField(max_length=500)
    authors_snapshot = models.JSONField(default=list, blank=True)
    page_index = models.PositiveIntegerField(null=True, blank=True)
    printed_label = models.CharField(max_length=80, blank=True)
    chapter_title = models.CharField(max_length=500, blank=True)
    passage_language = models.CharField(max_length=16, blank=True)
    reader_url_snapshot = models.CharField(max_length=1000, blank=True)
    retrieval_provenance = models.JSONField(default=dict, blank=True)
    quote_ciphertext = models.BinaryField(blank=True, default=bytes)
    cited = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["ordinal"]
        constraints = [
            models.UniqueConstraint(
                fields=["message", "source_key"],
                name="unique_library_message_source_key",
            ),
        ]
        indexes = [models.Index(fields=["message", "cited", "ordinal"])]
