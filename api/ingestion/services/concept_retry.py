"""Retry only the concept stage, using the original task store and review service."""
import logging
from uuid import uuid4

from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from catalog.models import Asset, Edition
from catalog.services.document_outline import _source_current
from catalog.services.editorial_issues import EditConflict
from ingestion.models import AuditEvent, ProcessingJob

OPERATION = "concept_alignment"


def current_source(job):
    job.asset = Asset.objects.select_for_update(of=("self",)).select_related("edition").get(pk=job.asset_id)
    _source_current(job.asset)
    revision = str(job.asset.document_revisions.filter(is_active=True).values_list("pk", flat=True).first() or "")
    if job.asset.sha256 != job.stats.get("source_sha256") or revision != str(job.stats.get("document_revision_id") or ""):
        raise EditConflict("原文修订已变化，请从当前材料核对概念候选；原处理记录保留。")
    parent = ProcessingJob.objects.filter(pk=job.stats.get("ocr_job_id"), job_type="ocr", status="succeeded",
        asset_id=job.asset_id, edition_id=job.edition_id).first()
    if parent is None or ProcessingJob.objects.filter(edition_id=job.edition_id, job_type="ocr", created_at__gt=parent.created_at).exclude(status="canceled").exists():
        raise EditConflict("此版本已有其他识别记录或原任务已变化，请先核对当前原文。")


def queue_concept_retry(parent, actor):
    # The command already holds the account, Edition and original OCR task locks.
    from .processing_followup import followup_state
    if parent.job_type != "ocr" or parent.status != "succeeded" or followup_state(parent)["state"] != "failed":
        raise EditConflict("只有正文成功而概念对齐失败的任务可以单独重试此阶段。")
    prior = ProcessingJob.objects.filter(idempotency_key=f"concept-retry:{parent.pk}").first()
    if prior:
        return prior
    _source_current(parent.asset)
    original_revision = str((parent.stats.get("document_intelligence") or {}).get("revision_id") or "")
    job = ProcessingJob(job_type="text_extraction", asset=parent.asset, edition_id=parent.edition_id, created_by=actor,
        task_id=str(uuid4()), idempotency_key=f"concept-retry:{parent.pk}",
        stats={"operation": OPERATION, "ocr_job_id": str(parent.pk), "source_sha256": parent.stats.get("source_sha256") or parent.asset.sha256,
               "document_revision_id": original_revision})
    current_source(job)
    job.save()
    parent.stats = {**parent.stats, "concept_retry_job_id": str(job.pk)}
    parent.save(update_fields=["stats", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="processing.concept_retry_created", object_type="processing_job", object_id=str(parent.pk),
        before={"concept_alignment": parent.stats.get("concept_alignment"), "warning": parent.stats.get("theory_suggestion_warning", "")},
        after={"concept_job_id": str(job.pk), "status": job.status})
    transaction.on_commit(lambda: dispatch_concept_job(str(job.pk), job.task_id))
    return job


def dispatch_concept_job(job_id, task_id):
    from ingestion.tasks import process_concept_job
    try:
        process_concept_job.apply_async(args=[job_id], task_id=task_id, ignore_result=True)
        return True
    except (OperationalError, OSError, ConnectionError, TimeoutError):
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").update(status="failed", error_code="queue_unavailable",
            error_message="概念任务未进入队列，请重试。原识别结果保留。", finished_at=timezone.now(), updated_at=timezone.now())
        return False


def concept_job_action(job, *, action, actor):
    # Caller owns Edition -> task locks, also used by the worker's result commit.
    before = {"status": job.status, "attempt": job.attempt, "error_code": job.error_code, "error_message": job.error_message}
    if action == "cancel" and job.status in {"pending", "running", "failed"}:
        job.status, job.task_id, job.finished_at = "canceled", "", timezone.now()
    elif action == "retry" and job.status in {"failed", "canceled"}:
        current_source(job)
        job.status, job.task_id, job.attempt, job.progress = "pending", str(uuid4()), 0, 0
        job.error_code, job.error_message = "", ""
        job.started_at = job.heartbeat_at = job.finished_at = None
    else:
        raise EditConflict("任务状态已变化，请重新读取后操作。")
    job.save(update_fields=["status", "task_id", "attempt", "progress", "error_code", "error_message", "started_at", "heartbeat_at", "finished_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=f"processing.concept.{action}", object_type="processing_job", object_id=str(job.pk), before=before, after={"status": job.status})
    if action == "retry":
        transaction.on_commit(lambda: dispatch_concept_job(str(job.pk), job.task_id))
    return job


def run_concept_job(job_id, *, task_id):
    from .processing import _claim_processing_job
    from catalog.services.theory_suggestions import generate_theory_review_tasks
    target = ProcessingJob.objects.get(pk=job_id, job_type="text_extraction", stats__operation=OPERATION)
    if not task_id:
        return target
    job, claimed = _claim_processing_job(target.pk, task_id=task_id, progress_floor=5)
    if not claimed:
        return job
    try:
        with transaction.atomic():
            Edition.objects.select_for_update().get(pk=job.edition_id)
            parent = ProcessingJob.objects.select_for_update().get(pk=job.stats["ocr_job_id"])
            current = ProcessingJob.objects.select_for_update(of=("self",)).select_related("asset__edition").get(pk=job.pk)
            if current.status != "running" or current.task_id != task_id:
                return current
            current_source(current)
            result = generate_theory_review_tasks(current.asset, actor=current.created_by, force=False)
            current.status, current.progress, current.finished_at = "succeeded", 100, timezone.now()
            current.stats = {**current.stats, **result}
            current.save(update_fields=["status", "progress", "finished_at", "stats", "updated_at"])
            if parent.stats.get("concept_retry_job_id") == str(current.pk):
                parent.stats = {**parent.stats, "theory_suggestions": result,
                    "concept_alignment": {"state": "completed" if result.get("enabled", True) else "disabled", "at": timezone.now().isoformat()}}
                parent.stats.pop("theory_suggestion_warning", None)
                parent.save(update_fields=["stats", "updated_at"])
            AuditEvent.objects.create(actor=current.created_by, action="processing.concept.completed", object_type="processing_job", object_id=str(current.pk),
                after={"status": current.status, "result": result, "ocr_job_id": str(parent.pk)})
            return current
    except Exception as exc:
        logging.getLogger(__name__).exception("Concept follow-up job failed: %s", job.pk)
        ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(status="failed", error_code=type(exc).__name__,
            error_message="概念候选生成未完成。原识别结果和已审核关系保留；请核对来源或处理服务后重试。", finished_at=timezone.now(), updated_at=timezone.now())
        raise
