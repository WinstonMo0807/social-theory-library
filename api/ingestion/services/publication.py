from hashlib import sha256

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    Asset,
    Edition,
    OcrStatus,
    PageLabelStatus,
    PublicationEvent,
    PublicationState,
    RecommendationPolicy,
    RecommendationSnapshot,
    ReviewStatus,
    SemanticIndexStatus,
)
from distribution.models import CloudObject


class PublicationBlocked(RuntimeError):
    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__("；".join(reasons))


class PublicationWarningsRequireConfirmation(RuntimeError):
    def __init__(self, warnings: list[str]):
        self.warnings = warnings
        super().__init__("；".join(warnings))


def _asset_storage_readable(asset: Asset | None) -> bool:
    if asset is None or not asset.file.name or asset.status != Asset.Status.READY:
        return False
    try:
        return bool(asset.file.storage.exists(asset.file.name))
    except Exception:
        return False


def publication_preflight(edition: Edition) -> dict[str, list[str]]:
    """Return technical blockers separately from editorial/process warnings.

    Publication is an administrator decision.  OCR, semantic indexing, page
    labels and editorial completeness are therefore observable warnings and
    background work, not aliases for publication state.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    background_tasks: list[str] = []
    work = edition.work
    original = edition.assets.filter(
        kind=Asset.Kind.ORIGINAL,
        status=Asset.Status.READY,
        is_current=True,
    ).order_by("-version", "-created_at").first()
    normalized = edition.assets.filter(
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
    ).order_by("-version", "-created_at").first()

    if not _asset_storage_readable(original):
        blockers.append("原始 PDF 不存在或当前无法读取")
    if not _asset_storage_readable(normalized):
        blockers.append("公开阅读锚点文件不存在或当前无法读取")
    elif normalized.validation_status == Asset.ValidationStatus.INVALID:
        blockers.append("公开阅读锚点文件验证失败")
    elif settings.REQUIRE_CLOUD_FOR_PUBLICATION and not normalized.cloud_objects.filter(
        status=CloudObject.Status.READY,
    ).exists():
        blockers.append("当前部署要求云端阅读副本，但副本尚未就绪")

    if not work.title.strip():
        warnings.append("题名尚未补全")
    if work.language not in {"zh-CN", "zh-TW", "en"}:
        warnings.append("正文语言尚未确认")
    if edition.publication_year is None:
        warnings.append("出版或完成年份尚未补全")
    if work.document_type == "book" and not edition.publisher.strip():
        warnings.append("图书出版者尚未补全")
    if work.document_type == "journal_article" and not edition.journal_title.strip():
        warnings.append("期刊名尚未补全")
    if work.document_type == "thesis":
        if not edition.degree_institution.strip():
            warnings.append("学位授予单位尚未补全")
        if not edition.degree_type.strip():
            warnings.append("学位类型尚未补全")
    if work.document_type == "report" and not (
        edition.report_institution.strip() or edition.publisher.strip()
    ):
        warnings.append("研究报告责任机构尚未补全")
    if edition.metadata_confidence < settings.AUTO_PUBLISH_MIN_CONFIDENCE:
        warnings.append("元数据置信度低于自动处理阈值")
    if not edition.citation_data:
        warnings.append("引用数据尚未生成")
    if not edition.canonical_filename:
        warnings.append("规范文件名尚未生成")
    if edition.review_status != ReviewStatus.COMPLETED or edition.review_progress < 100:
        warnings.append(f"人工复核尚未完成（{edition.review_progress}%）")
    if edition.ocr_status in {OcrStatus.PENDING, OcrStatus.RUNNING}:
        warnings.append("OCR 尚未完成，扫描件暂时不能选择文字")
        background_tasks.append("OCR")
    elif edition.ocr_status == OcrStatus.FAILED:
        warnings.append("OCR 失败，当前仍使用原始 PDF 阅读")
    elif edition.ocr_status == OcrStatus.DISABLED:
        warnings.append("该扫描文献已按批次策略停用 OCR，当前不能选择或检索正文文字")
    if edition.page_label_status != PageLabelStatus.READY:
        warnings.append("引用页码尚未完成校对")
        background_tasks.append("页码识别")
    if edition.semantic_index_status != SemanticIndexStatus.READY:
        warnings.append("语义索引尚未就绪，观点检索将使用关键词降级")
        background_tasks.append("语义索引")
    if edition.search_indexed_at is None:
        warnings.append("全文索引尚未确认就绪")
        background_tasks.append("全文索引")

    return {
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
        "background_tasks": list(dict.fromkeys(background_tasks)),
    }


def publication_readiness(
    edition: Edition,
    *,
    allow_low_confidence: bool = False,
) -> list[str]:
    # Compatibility entry point retained for the ingestion and existing admin
    # serializers.  Its meaning is now deliberately limited to hard blockers.
    return publication_preflight(edition)["blockers"]


def invalidate_public_recommendations() -> None:
    placements = [
        RecommendationPolicy.Placement.HOME_FEATURED,
        RecommendationPolicy.Placement.HOME_RANDOM,
        RecommendationPolicy.Placement.THEORY_WEEKLY,
    ]
    RecommendationSnapshot.objects.filter(
        policy__placement__in=placements,
        is_current=True,
    ).update(is_current=False, updated_at=timezone.now())


def _publication_event_key(value: str) -> str:
    """Fit a deterministic business key into PublicationEvent.max_length."""

    max_length = PublicationEvent._meta.get_field("idempotency_key").max_length
    if len(value) <= max_length:
        return value
    digest = sha256(value.encode("utf-8")).hexdigest()[:24]
    return f"{value[: max_length - len(digest) - 1]}:{digest}"


@transaction.atomic
def publish_edition(
    edition: Edition,
    actor=None,
    idempotency_key: str | None = None,
    *,
    allow_low_confidence: bool = False,
    confirm_warnings: bool = False,
) -> Edition:
    edition = Edition.objects.select_for_update().select_related("work").get(pk=edition.pk)
    if edition.state == PublicationState.PUBLISHED:
        return edition
    preflight = publication_preflight(edition)
    if preflight["blockers"]:
        raise PublicationBlocked(preflight["blockers"])
    if preflight["warnings"] and not confirm_warnings:
        raise PublicationWarningsRequireConfirmation(preflight["warnings"])
    is_republication = edition.state == PublicationState.WITHDRAWN
    event_type = (
        PublicationEvent.EventType.REPUBLISH
        if is_republication
        else PublicationEvent.EventType.PUBLISH
    )
    event_key = idempotency_key or f"publish:{edition.id}:{edition.updated_at.isoformat()}"
    if is_republication:
        event_key = f"{event_key}:republish:{edition.updated_at.isoformat()}"
    event_key = _publication_event_key(event_key)
    event, created = PublicationEvent.objects.get_or_create(
        idempotency_key=event_key,
        defaults={
            "edition": edition,
            "event_type": event_type,
            "actor": actor,
        },
    )
    now = timezone.now()
    edition.state = PublicationState.PUBLISHED
    edition.published_at = now
    if edition.first_published_at is None:
        edition.first_published_at = now
    edition.last_published_at = now
    edition.withdrawn_at = None
    edition.save(
        update_fields=[
            "state",
            "published_at",
            "first_published_at",
            "last_published_at",
            "withdrawn_at",
            "updated_at",
        ]
    )
    event.completed_at = now
    event.payload = {
        "state": PublicationState.PUBLISHED,
        "preflight": preflight,
        "warnings_confirmed": bool(preflight["warnings"]),
    }
    event.save(update_fields=["completed_at", "payload", "updated_at"])
    transaction.on_commit(invalidate_public_recommendations)
    return edition


@transaction.atomic
def withdraw_edition(edition: Edition, actor=None, reason: str = "") -> Edition:
    edition = Edition.objects.select_for_update().get(pk=edition.pk)
    if edition.state == PublicationState.WITHDRAWN:
        return edition
    now = timezone.now()
    event = PublicationEvent.objects.create(
        edition=edition,
        event_type=PublicationEvent.EventType.WITHDRAW,
        idempotency_key=f"withdraw:{edition.id}:{now.timestamp()}",
        actor=actor,
        payload={"reason": reason},
        completed_at=now,
    )
    edition.state = PublicationState.WITHDRAWN
    edition.withdrawn_at = now
    edition.save(update_fields=["state", "withdrawn_at", "updated_at"])
    transaction.on_commit(invalidate_public_recommendations)
    return edition
