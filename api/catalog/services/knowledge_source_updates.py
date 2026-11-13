"""Bounded source updates use the existing processing ledger and queues."""
from uuid import uuid4
from django.db import transaction
from django.utils import timezone
from catalog import models as m
from ingestion.models import ProcessingJob
from catalog.services.knowledge_sources import current_structure, digest


@transaction.atomic
def schedule_source_update(revision, *, structure=None):
    outline=m.DocumentOutlineRevision.objects.filter(document_revision=revision,is_active=True).first()
    key=digest([str(revision.pk),revision.text_checksum,str(outline.pk) if outline else None,structure.input_hash if structure else None])
    job,_=ProcessingJob.objects.get_or_create(idempotency_key="knowledge-source:"+key,defaults={
        "job_type":"logical_structure","asset":revision.asset,"edition":revision.asset.edition,
        "stats":{"revision_id":str(revision.pk),"outline_id":str(outline.pk) if outline else None}})
    if job.status=="succeeded" or job.task_id and job.status in {"pending","running"}: return job
    job.status="pending";job.task_id=str(uuid4());job.error_code="";job.error_message="";job.save()
    task_id=job.task_id
    transaction.on_commit(lambda: dispatch_source_update(str(job.pk), task_id))
    return job


def dispatch_source_update(job_id, task_id):
    """The existing ProcessingJob recovery loop also uses this dispatcher."""
    from catalog.intelligence_tasks import refresh_source
    if not ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").exists():
        return False
    try:
        refresh_source.apply_async(args=[str(job_id), task_id], task_id=task_id, queue="intelligence")
    except Exception:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").update(
            status="failed", error_code="queue_unavailable", updated_at=timezone.now(),
            error_message="结构更新已保存，等待队列恢复后自动接续。")
        return False
    return True


def execute_source_update(job_id,task_id):
    from ingestion.services.processing import _claim_processing_job, _processing_claim_is_current
    if not ProcessingJob.objects.filter(pk=job_id, job_type="logical_structure", task_id=task_id).exists():
        return
    job, claimed = _claim_processing_job(job_id, task_id=task_id)
    if not claimed:
        return
    try:
        with transaction.atomic():
            revision=m.DocumentRevision.objects.select_for_update().select_related("asset__edition").get(pk=job.stats["revision_id"])
            # Recovery skips a locked job. Duplicate/obsolete deliveries cannot
            # rebuild structure, invalidate pages or enqueue downstream work.
            current = ProcessingJob.objects.select_for_update().filter(pk=job.pk, task_id=task_id, status="running").first()
            if not current:
                return
            outline=m.DocumentOutlineRevision.objects.filter(document_revision=revision,is_active=True).first()
            if not revision.is_active or (str(outline.pk) if outline else None)!=job.stats["outline_id"]:
                ProcessingJob.objects.filter(pk=job.pk,task_id=task_id).update(status="canceled",finished_at=timezone.now(),
                    error_code="source_superseded",error_message="目录或正文已有新版本，本次旧更新停止。")
                return
            structure=current_structure(revision,prepare=True)
            from catalog.services.knowledge_workspace import invalidate_source
            invalidate_source("document_revision",revision.pk)
            ProcessingJob.objects.filter(pk=job.pk, task_id=task_id).update(heartbeat_at=timezone.now())
        # Release source locks before entering the existing index/subscription
        # transactions. Each downstream request is revision-guarded/idempotent.
        if not _processing_claim_is_current(job, task_id):
            return
        from catalog.services.discovery_sources import get_source
        from catalog.services.discovery_projection import active_generation
        from catalog.services.discovery_indexing import request_source_reindex
        header=get_source("edition",revision.asset.edition_id)[1]
        index_job=None
        if active_generation() and header and header.get("document_revision_id")==str(revision.pk):
            index_job=request_source_reindex(revision,keyword_only=True)
        if not _processing_claim_is_current(job, task_id):
            return
        from catalog.services.knowledge_automation import enroll
        enroll(revision.asset.edition_id)
        from catalog.services.knowledge_compilation import reconcile
        compilation = reconcile(revision)
        ProcessingJob.objects.filter(pk=job.pk,task_id=task_id,status="running").update(status="succeeded",progress=100,
            finished_at=timezone.now(),stats={**job.stats,"structure_id":str(structure.pk),"model_calls":0,
                "index_job_id":str(index_job.pk) if index_job else None,"index_state":"queued" if index_job else "unpublished_or_no_active_index",
                "compilation_run_id":str(compilation.pk) if compilation else None})
    except Exception as exc:
        ProcessingJob.objects.filter(pk=job.pk,task_id=task_id,status__in=["pending","running"]).update(status="failed",
            finished_at=timezone.now(),error_code=getattr(exc,"code",type(exc).__name__),error_message=str(exc)[:1200])
        raise
