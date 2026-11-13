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
    def dispatch():
        from catalog.intelligence_tasks import refresh_source
        try: refresh_source.apply_async(args=[str(job.pk),task_id],task_id=task_id,queue="intelligence")
        except Exception:
            ProcessingJob.objects.filter(pk=job.pk,task_id=task_id).update(status="failed",error_code="queue_unavailable",
                error_message="结构更新已保存，但队列未连接；可从原文工作区重新更新索引。")
    transaction.on_commit(dispatch)
    return job


def execute_source_update(job_id,task_id):
    job=ProcessingJob.objects.filter(pk=job_id,job_type="logical_structure",task_id=task_id,status__in=["pending","running"]).first()
    if not job: return
    try:
        with transaction.atomic():
            revision=m.DocumentRevision.objects.select_for_update().select_related("asset__edition").get(pk=job.stats["revision_id"])
            outline=m.DocumentOutlineRevision.objects.filter(document_revision=revision,is_active=True).first()
            if not revision.is_active or (str(outline.pk) if outline else None)!=job.stats["outline_id"]:
                ProcessingJob.objects.filter(pk=job.pk,task_id=task_id).update(status="canceled",finished_at=timezone.now(),
                    error_code="source_superseded",error_message="目录或正文已有新版本，本次旧更新停止。")
                return
            ProcessingJob.objects.filter(pk=job.pk,task_id=task_id).update(status="running",started_at=timezone.now())
            structure=current_structure(revision,prepare=True)
            from catalog.services.knowledge_workspace import invalidate_source
            invalidate_source("document_revision",revision.pk)
        # Only published source text enters search. Draft structure remains inspectable.
        from catalog.services.discovery_sources import get_source
        from catalog.services.discovery_projection import active_generation
        from catalog.services.discovery_indexing import request_source_reindex
        header=get_source("edition",revision.asset.edition_id)[1]
        index_job=None
        if active_generation() and header and header.get("document_revision_id")==str(revision.pk):
            index_job=request_source_reindex(revision,keyword_only=True)
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
