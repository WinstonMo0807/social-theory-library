import uuid

from celery import shared_task

from catalog.services.semantic_indexing import recover_semantic_index_jobs, run_semantic_index_job
from catalog.services.recommendations import current_snapshot, ensure_default_policies
from catalog.services.analytics import aggregate_search_queries
from catalog.models import SearchEvaluationRun
from catalog.services.search_evaluation import (
    SearchEvaluationExecutionError,
    SearchEvaluationValidationError,
    execute_evaluation,
)
from catalog.services.query_lexicon.sync import process_pending_events
from catalog.services.query_lexicon.operations import run_query_lexicon_reconciliation as run_ql_reconciliation


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def build_semantic_index(self, job_id):
    job = run_semantic_index_job(str(job_id), task_id=str(self.request.id or ""))
    return {"id": str(job.id), "status": job.status, "stats": job.stats}


@shared_task(ignore_result=True)
def recover_semantic_index_queue():
    return recover_semantic_index_jobs()


@shared_task(ignore_result=True)
def process_query_lexicon_events():
    return process_pending_events()


@shared_task(ignore_result=True)
def recover_query_lexicon_events():
    return {
        "events": process_pending_events(),
        "reconciliation": recover_query_lexicon_reconciliation_jobs(),
    }


@shared_task(bind=True, ignore_result=True)
def run_query_lexicon_reconciliation(self, job_id, task_id=""):
    job = run_ql_reconciliation(job_id=str(job_id), task_id=str(task_id or self.request.id or ""))
    return {"job_id": str(job.id), "status": job.status, "stats": job.stats}


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def run_projection_refresh(self, job_id):
    from catalog.services.projection_refresh import run_projection_refresh_job

    task_id = str(self.request.id or "")
    job = run_projection_refresh_job(str(job_id), task_id=task_id)
    return {"job_id": str(job.id), "status": job.status, "stats": job.stats}


def recover_query_lexicon_reconciliation_jobs(*, limit: int = 20):
    from django.utils import timezone
    from ingestion.models import ProcessingJob
    from catalog.services.query_lexicon.operations import _job_payload

    jobs = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.QUERY_LEXICON_RECONCILE,
        status=ProcessingJob.Status.FAILED,
        error_code="queue_unavailable",
    ).order_by("created_at")[:limit]
    queued = 0
    for job in jobs:
        job.status = ProcessingJob.Status.PENDING
        job.task_id = str(uuid.uuid4())
        job.error_code = ""
        job.error_message = ""
        job.started_at = None
        job.finished_at = None
        job.save(update_fields=["status", "task_id", "error_code", "error_message", "started_at", "finished_at", "updated_at"])
        run_query_lexicon_reconciliation.apply_async(args=[str(job.id), job.task_id], task_id=job.task_id, queue="query_lexicon")
        queued += 1
    return {"candidates": len(jobs), "requeued": queued}


@shared_task(ignore_result=True)
def rotate_due_recommendations():
    """Keep every public placement on the same durable three-day snapshot."""

    refreshed = []
    for policy in ensure_default_policies():
        if not policy.enabled:
            continue
        snapshot = current_snapshot(policy)
        if snapshot is not None:
            refreshed.append({"placement": policy.placement, "snapshot": str(snapshot.id)})
    return refreshed


@shared_task(ignore_result=True)
def aggregate_anonymous_searches():
    return aggregate_search_queries()


@shared_task(bind=True, ignore_result=True)
def run_search_evaluation(self, run_id):
    run = SearchEvaluationRun.objects.select_related("evaluation_set", "index_version").get(pk=run_id)
    if run.status == SearchEvaluationRun.Status.COMPLETED:
        return {"id": str(run.id), "status": run.status}
    if run.index_version_id is None:
        run.status = SearchEvaluationRun.Status.FAILED
        run.error_message = "候选索引版本已不存在，无法运行评估。"
        run.save(update_fields=["status", "error_message", "updated_at"])
        return {"id": str(run.id), "status": run.status}
    try:
        completed = execute_evaluation(
            run.evaluation_set,
            run.index_version,
            semantic_ratio=run.semantic_ratio,
            actor=run.created_by,
            existing_run=run,
        )
    except SearchEvaluationValidationError as exc:
        run.refresh_from_db()
        run.status = SearchEvaluationRun.Status.FAILED
        run.error_message = "检索评估预检未通过。"
        run.config_snapshot = {**run.config_snapshot, "validation_plan": exc.plan}
        run.save(
            update_fields=["status", "error_message", "config_snapshot", "updated_at"]
        )
        return {"id": str(run.id), "status": run.status}
    except SearchEvaluationExecutionError as exc:
        return {"id": str(exc.run.id), "status": exc.run.status}
    return {"id": str(completed.id), "status": completed.status}
