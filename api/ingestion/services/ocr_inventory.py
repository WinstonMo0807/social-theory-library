from __future__ import annotations

from dataclasses import asdict, dataclass
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from catalog.models import Asset, DocumentRevision, Page
from ingestion.models import AuditEvent, ProcessingJob


OCR_INVENTORY_CATEGORIES = (
    "obsolete",
    "superseded",
    "completed_by_newer_revision",
    "recoverable",
    "genuinely_failed",
)


class PausedOCRDecisionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PausedOCRInventoryRow:
    job_id: str
    asset_id: str
    category: str
    reasons: tuple[str, ...]
    target_page_indexes: tuple[int, ...]
    remaining_page_indexes: tuple[int, ...]
    newer_job_id: str = ""
    newer_revision_id: str = ""

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        payload["target_page_indexes"] = list(self.target_page_indexes)
        payload["remaining_page_indexes"] = list(self.remaining_page_indexes)
        return payload


def _page_state(asset: Asset) -> tuple[tuple[int, ...], tuple[int, ...]]:
    rows = list(asset.pages.order_by("index").values_list("index", "text_source"))
    page_count = int(asset.page_count or (rows[-1][0] if rows else 0))
    configured = (asset.validation_details or {}).get("ocr_required_page_indexes")
    if isinstance(configured, list):
        targets = tuple(
            sorted(
                {
                    int(value)
                    for value in configured
                    if str(value).isdigit() and 1 <= int(value) <= page_count
                }
            )
        )
    else:
        targets = tuple(range(1, page_count + 1))
    completed = {
        int(index)
        for index, text_source in rows
        if text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}
    }
    return targets, tuple(index for index in targets if index not in completed)


def classify_paused_ocr_job(job: ProcessingJob) -> PausedOCRInventoryRow:
    """Classify one paused OCR job using database facts without mutating it."""

    if job.job_type != ProcessingJob.JobType.OCR:
        raise ValueError("Only OCR jobs can be classified by the paused OCR inventory.")
    if job.status != ProcessingJob.Status.PAUSED:
        raise ValueError("Only paused OCR jobs can be classified by this inventory.")

    asset = job.asset
    if asset is None:
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id="",
            category="obsolete",
            reasons=("asset_missing",),
            target_page_indexes=(),
            remaining_page_indexes=(),
        )

    structural_reasons = []
    if asset.kind != Asset.Kind.NORMALIZED:
        structural_reasons.append("asset_is_not_normalized")
    if int(asset.page_count or 0) <= 0:
        structural_reasons.append("document_has_no_pages")
    if structural_reasons:
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id=str(asset.id),
            category="obsolete",
            reasons=tuple(structural_reasons),
            target_page_indexes=(),
            remaining_page_indexes=(),
        )

    targets, remaining = _page_state(asset)
    newer_job = (
        ProcessingJob.objects.filter(
            job_type=ProcessingJob.JobType.OCR,
            asset_id=asset.id,
            created_at__gt=job.created_at,
        )
        .exclude(pk=job.pk)
        .order_by("-created_at")
        .first()
    )
    newer_revision = (
        DocumentRevision.objects.filter(
            asset_id=asset.id,
            is_active=True,
            extraction_method="selective_ocr",
            created_at__gt=job.created_at,
        )
        .order_by("-revision")
        .first()
    )

    if not remaining and (
        newer_revision is not None
        or (
            newer_job is not None
            and newer_job.status == ProcessingJob.Status.SUCCEEDED
        )
    ):
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id=str(asset.id),
            category="completed_by_newer_revision",
            reasons=("all_target_pages_completed", "newer_ocr_result_present"),
            target_page_indexes=targets,
            remaining_page_indexes=remaining,
            newer_job_id=str(newer_job.id) if newer_job else "",
            newer_revision_id=str(newer_revision.id) if newer_revision else "",
        )

    replacement_exists = Asset.objects.filter(
        edition_id=asset.edition_id,
        kind=Asset.Kind.NORMALIZED,
        is_current=True,
    ).exclude(pk=asset.pk).exists()
    if not asset.is_current or replacement_exists or newer_job is not None:
        reasons = []
        if not asset.is_current or replacement_exists:
            reasons.append("normalized_asset_superseded")
        if newer_job is not None:
            reasons.append("newer_ocr_job_present")
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id=str(asset.id),
            category="superseded",
            reasons=tuple(reasons),
            target_page_indexes=targets,
            remaining_page_indexes=remaining,
            newer_job_id=str(newer_job.id) if newer_job else "",
            newer_revision_id=str(newer_revision.id) if newer_revision else "",
        )

    obsolete_reasons = []
    if not targets:
        obsolete_reasons.append("no_ocr_targets")
    if obsolete_reasons:
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id=str(asset.id),
            category="obsolete",
            reasons=tuple(obsolete_reasons),
            target_page_indexes=targets,
            remaining_page_indexes=remaining,
        )

    permanently_failed = job.error_kind in {
        ProcessingJob.ErrorKind.MANUAL_INTERVENTION,
        ProcessingJob.ErrorKind.PERMANENT,
    }
    attempts_exhausted = int(job.attempt or 0) >= int(job.max_attempts or 0)
    if permanently_failed or attempts_exhausted:
        reasons = []
        if permanently_failed:
            reasons.append("non_retryable_error")
        if attempts_exhausted:
            reasons.append("attempts_exhausted")
        if job.error_code:
            reasons.append(f"error:{job.error_code}")
        return PausedOCRInventoryRow(
            job_id=str(job.id),
            asset_id=str(asset.id),
            category="genuinely_failed",
            reasons=tuple(reasons),
            target_page_indexes=targets,
            remaining_page_indexes=remaining,
        )

    return PausedOCRInventoryRow(
        job_id=str(job.id),
        asset_id=str(asset.id),
        category="recoverable",
        reasons=("current_asset_has_unprocessed_targets",),
        target_page_indexes=targets,
        remaining_page_indexes=remaining,
    )


def paused_ocr_inventory(
    queryset: QuerySet[ProcessingJob] | None = None,
    *,
    limit: int = 500,
) -> dict:
    """Return a bounded, read-only inventory of paused OCR jobs."""

    source = queryset if queryset is not None else ProcessingJob.objects.all()
    paused = source.filter(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PAUSED,
    ).select_related("asset__edition")
    total = paused.count()
    bounded_limit = max(1, min(int(limit), 5000))
    rows = [classify_paused_ocr_job(job) for job in paused[:bounded_limit]]
    counts = {category: 0 for category in OCR_INVENTORY_CATEGORIES}
    for row in rows:
        counts[row.category] += 1
    return {
        "total": total,
        "returned": len(rows),
        "truncated": total > len(rows),
        "counts": counts,
        "items": [row.as_dict() for row in rows],
        "read_only": True,
    }


@transaction.atomic
def decide_paused_ocr_job(
    job: ProcessingJob,
    *,
    decision: str,
    actor,
    reason: str,
) -> tuple[ProcessingJob, PausedOCRInventoryRow]:
    """Resolve exactly one inventoried paused OCR job with an audit trail."""

    locked = (
        ProcessingJob.objects.select_for_update()
        .select_related("asset__edition")
        .get(pk=job.pk)
    )
    if locked.job_type != ProcessingJob.JobType.OCR:
        raise PausedOCRDecisionError("只有 OCR 任务可以使用该处理入口。")
    if locked.status != ProcessingJob.Status.PAUSED:
        raise PausedOCRDecisionError("该 OCR 任务已不再处于暂停状态，请刷新后重试。")

    normalized_decision = str(decision or "").strip().casefold()
    normalized_reason = " ".join(str(reason or "").split()).strip()
    if not normalized_reason:
        raise PausedOCRDecisionError("请填写本次处理理由。")
    classification = classify_paused_ocr_job(locked)
    before = {
        "status": locked.status,
        "category": classification.category,
        "reasons": list(classification.reasons),
        "remaining_page_indexes": list(classification.remaining_page_indexes),
        "error_code": locked.error_code,
    }
    now = timezone.now()

    if normalized_decision == "close":
        if classification.category not in {
            "obsolete",
            "superseded",
            "completed_by_newer_revision",
        }:
            raise PausedOCRDecisionError("当前分类不能安全关闭；请按建议操作处理。")
        locked.status = ProcessingJob.Status.CANCELED
        locked.task_id = ""
        locked.pause_requested_at = None
        locked.finished_at = now
        action = "paused_ocr_closed"
    elif normalized_decision == "resume":
        if classification.category != "recoverable":
            raise PausedOCRDecisionError("只有仍有未处理页面的当前 OCR 任务可以恢复。")
        from ingestion.services.processing import resume_processing_job

        locked = resume_processing_job(locked, actor=actor)
        action = "paused_ocr_resumed"
    elif normalized_decision == "acknowledge_failure":
        if classification.category != "genuinely_failed":
            raise PausedOCRDecisionError("只有确认不可恢复的任务可以标记为失败。")
        locked.status = ProcessingJob.Status.FAILED
        locked.task_id = ""
        locked.pause_requested_at = None
        locked.finished_at = now
        locked.error_code = locked.error_code or "ocr_manual_failure_confirmed"
        locked.error_message = locked.error_message or normalized_reason
        action = "paused_ocr_failure_acknowledged"
    else:
        raise PausedOCRDecisionError("请选择关闭、恢复或确认失败。")

    decision_row = {
        "decision": normalized_decision,
        "category": classification.category,
        "classification_reasons": list(classification.reasons),
        "reason": normalized_reason,
        "actor_id": str(getattr(actor, "pk", "") or ""),
        "decided_at": now.isoformat(),
    }
    stats = dict(locked.stats or {})
    history = list(stats.get("ocr_inventory_decisions") or [])[-9:]
    history.append(decision_row)
    stats["ocr_inventory_decisions"] = history
    stats["latest_ocr_inventory_decision"] = decision_row
    locked.stats = stats
    update_fields = ["stats", "updated_at"]
    if normalized_decision != "resume":
        update_fields.extend(
            [
                "status",
                "task_id",
                "pause_requested_at",
                "finished_at",
                "error_code",
                "error_message",
            ]
        )
    locked.save(update_fields=list(dict.fromkeys(update_fields)))
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type="ProcessingJob",
        object_id=str(locked.id),
        before=before,
        after={
            "status": locked.status,
            **decision_row,
        },
    )
    return locked, classification
