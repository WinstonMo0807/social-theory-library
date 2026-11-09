"""Retired task compatibility: no new concept producer or retry dispatch."""
from django.db import transaction
from django.utils import timezone
from catalog.services.editorial_issues import EditConflict
from ingestion.models import AuditEvent, ProcessingJob

OPERATION = "concept_alignment"
MESSAGE = "旧概念生成已退役，请从 Intelligence 选择当前版本进行分析；原任务与人工决定保留。"


def current_source(job):
    raise EditConflict(MESSAGE)


def queue_concept_retry(parent, actor):
    raise EditConflict(MESSAGE)


@transaction.atomic
def run_concept_job(job_id, *, task_id):
    job = ProcessingJob.objects.select_for_update().get(pk=job_id, job_type="text_extraction", stats__operation=OPERATION)
    if not task_id or job.task_id != task_id or job.status in {"succeeded", "canceled"}:
        return job
    job.status, job.task_id, job.finished_at = "canceled", "", timezone.now()
    job.error_code, job.error_message = "knowledge_producer_retired", MESSAGE
    job.save(update_fields=["status", "task_id", "finished_at", "error_code", "error_message", "updated_at"])
    return job


def dispatch_concept_job(job_id, task_id):
    run_concept_job(job_id, task_id=task_id)
    return False


def concept_job_action(job, *, action, actor):
    if action != "cancel" or job.status not in {"pending", "running", "failed", "paused"}:
        raise EditConflict(MESSAGE)
    result = run_concept_job(job.pk, task_id=job.task_id)
    AuditEvent.objects.create(actor=actor, action="processing.concept.cancel", object_type="processing_job",
        object_id=str(job.pk), after={"status": result.status, "reason": "knowledge_producer_retired"})
    return result
