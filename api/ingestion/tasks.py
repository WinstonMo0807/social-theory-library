from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
import uuid

from .models import ProcessingAttempt, UploadItem
from .services.dispatch import (
    mark_dispatch_finished,
    mark_dispatch_running,
    recover_ingestion_dispatches,
)
from .services.pipeline import resume_reviewed_item_publication, run_pipeline
from .services.ocr_provider import OCRServiceUnavailable
from .services.processing import (
    recover_stalled_processing_jobs,
    run_external_enrichment_job,
    run_ocr_job,
    run_page_label_job,
    run_query_lexicon_candidate_job,
)


def _request_task_id(task, item_id: str) -> str:
    request_id = str(getattr(task.request, "id", "") or "")
    if request_id:
        return request_id
    return str(
        UploadItem.objects.filter(pk=item_id).values_list(
            "dispatch_task_id",
            flat=True,
        ).first()
        or ""
    )


def _run_tracked(task, item_id: str, processor):
    task_id = _request_task_id(task, item_id)
    expected = UploadItem.objects.filter(pk=item_id).values_list(
        "dispatch_task_id",
        flat=True,
    ).first()
    if task_id and expected and task_id != expected:
        return {"id": str(item_id), "status": "superseded"}
    execution_attempt = None
    if task_id:
        with transaction.atomic():
            execution_attempt, created = ProcessingAttempt.objects.select_for_update().get_or_create(
                idempotency_key=f"dispatch:{task_id}"[:128],
                defaults={
                    "upload_item_id": item_id,
                    "stage": "task_execution",
                    "attempt_number": 1,
                    "status": "started",
                    "correlation_id": task_id,
                    "worker_id": str(getattr(task.request, "hostname", "") or ""),
                    "input_fingerprint": task_id,
                },
            )
            if not created and execution_attempt.status == "completed":
                return {"id": str(item_id), "status": "already_completed"}
            if not created and execution_attempt.status == "started":
                return {"id": str(item_id), "status": "already_running"}
            if not created:
                execution_attempt.status = "started"
                execution_attempt.attempt_number += 1
                execution_attempt.error_code = ""
                execution_attempt.error_message = ""
                execution_attempt.error_kind = ""
                execution_attempt.finished_at = None
                execution_attempt.started_at = timezone.now()
                execution_attempt.save(
                    update_fields=[
                        "status",
                        "attempt_number",
                        "error_code",
                        "error_message",
                        "error_kind",
                        "finished_at",
                        "started_at",
                        "updated_at",
                    ]
                )
    lock_key = f"ingestion:item-lock:{item_id}"
    lock_token = str(uuid.uuid4())
    lock_acquired = False
    try:
        lock_acquired = bool(
            cache.add(
                lock_key,
                lock_token,
                timeout=settings.INGESTION_TASK_LOCK_SECONDS,
            )
        )
    except Exception:
        # Redis is also the broker in production.  If a task is already
        # executing, a temporary cache read failure must not destroy it.
        lock_acquired = True
    if not lock_acquired:
        if execution_attempt:
            execution_attempt.status = "failed"
            execution_attempt.error_code = "concurrent_execution"
            execution_attempt.error_message = "另一个工作者已经持有该入库任务。"
            execution_attempt.error_kind = ProcessingAttempt.ErrorKind.RETRYABLE
            execution_attempt.finished_at = timezone.now()
            execution_attempt.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "error_kind",
                    "finished_at",
                    "updated_at",
                ]
            )
        return {"id": str(item_id), "status": "already_running"}
    if task_id:
        mark_dispatch_running(str(item_id), task_id)
    try:
        item = processor(str(item_id))
    except Exception as exc:
        if execution_attempt:
            execution_attempt.status = "failed"
            execution_attempt.error_code = exc.__class__.__name__
            execution_attempt.error_message = str(exc)[:4000]
            execution_attempt.error_kind = ProcessingAttempt.ErrorKind.RETRYABLE
            execution_attempt.finished_at = timezone.now()
            execution_attempt.save(
                update_fields=[
                    "status",
                    "error_code",
                    "error_message",
                    "error_kind",
                    "finished_at",
                    "updated_at",
                ]
            )
        if task_id:
            mark_dispatch_finished(str(item_id), task_id, error=exc)
        raise
    else:
        if execution_attempt:
            execution_attempt.status = "completed"
            execution_attempt.finished_at = timezone.now()
            execution_attempt.output_summary = {"item_status": item.status}
            execution_attempt.save(
                update_fields=["status", "finished_at", "output_summary", "updated_at"]
            )
        if task_id:
            mark_dispatch_finished(str(item_id), task_id)
        return {"id": str(item.id), "status": item.status}
    finally:
        try:
            if cache.get(lock_key) == lock_token:
                cache.delete(lock_key)
        except Exception:
            pass


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
    ignore_result=True,
)
def process_upload_item(self, item_id):
    return _run_tracked(self, str(item_id), run_pipeline)


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=4,
    ignore_result=True,
)
def process_reviewed_upload_item(self, item_id):
    return _run_tracked(self, str(item_id), resume_reviewed_item_publication)


@shared_task(
    bind=True,
    autoretry_for=(OCRServiceUnavailable, OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def process_ocr_job(self, job_id):
    job = run_ocr_job(str(job_id), task_id=str(self.request.id or ""))
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def process_external_enrichment_job(self, job_id):
    job = run_external_enrichment_job(
        str(job_id),
        task_id=str(self.request.id or ""),
    )
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}


@shared_task(bind=True, ignore_result=True)
def process_page_label_job(self, job_id):
    job = run_page_label_job(str(job_id), task_id=str(self.request.id or ""))
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def process_query_lexicon_candidate_job(self, job_id):
    job = run_query_lexicon_candidate_job(
        str(job_id),
        task_id=str(self.request.id or ""),
    )
    return {"id": str(job.id), "status": job.status, "attempt": job.attempt}


@shared_task(ignore_result=True)
def recover_ingestion_queue():
    return {
        "uploads": recover_ingestion_dispatches(limit=100),
        "processing_jobs": recover_stalled_processing_jobs(limit=100),
    }


@shared_task(ignore_result=True)
def record_ingestion_worker_heartbeat():
    cache.set("ingestion:worker-heartbeat", timezone.now().isoformat(), timeout=180)


@shared_task(ignore_result=True)
def record_ingestion_worker_probe(probe_id: str):
    """Record proof that a newly published Celery task reached a worker.

    The deployment check deliberately does not use Celery's result backend.
    Production tasks ignore results, so a short-lived cache marker is enough to
    prove the API, broker and worker are using the same queue and Redis service.
    """

    marker = {
        "probe_id": str(probe_id),
        "executed_at": timezone.now().isoformat(),
    }
    cache.set(
        f"ingestion:pipeline-probe:{probe_id}",
        marker,
        timeout=120,
    )
    return marker
