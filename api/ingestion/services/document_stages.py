"""Current document stages, selected in SQL before bounded page hydration."""
from django.db.models import OuterRef, Q, Subquery

from catalog.models import SemanticIndexJob
from ingestion.models import ProcessingAttempt, ProcessingJob


def with_document_stage_ids(queryset):
    related = (
        Q(upload_item_id=OuterRef("pk"))
        | Q(edition_id=OuterRef("edition_id"), asset__isnull=True)
        | Q(asset_id=OuterRef("asset_id"))
        | Q(asset__edition_id=OuterRef("edition_id"), asset__is_current=True)
    )
    jobs = ProcessingJob.objects.filter(related).order_by("-created_at", "-id")
    semantic = SemanticIndexJob.objects.filter(
        Q(asset_id=OuterRef("asset_id"))
        | Q(asset__edition_id=OuterRef("edition_id"), asset__is_current=True),
        operation__in=["build", "rebuild"],
    ).order_by("-created_at", "-id")
    attempts = ProcessingAttempt.objects.filter(upload_item_id=OuterRef("pk"), invalidated_at__isnull=True).order_by("-started_at", "-id")
    return queryset.annotate(
        document_file_job_id=Subquery(jobs.filter(job_type__in=["text_extraction", "r2_staging"]).values("pk")[:1]),
        document_ocr_job_id=Subquery(jobs.filter(job_type="ocr").values("pk")[:1]),
        document_index_job_id=Subquery(jobs.filter(job_type="semantic_index").values("pk")[:1]),
        document_semantic_job_id=Subquery(semantic.values("pk")[:1]),
        document_file_attempt_id=Subquery(attempts.filter(stage__in=["validate", "asset", "text_extraction"]).values("pk")[:1]),
        document_index_attempt_id=Subquery(attempts.filter(stage__in=["search_index", "review_reindex"]).values("pk")[:1]),
    )


def attach_document_stages(items):
    """Load at most four jobs and two stage attempts per paginated item."""
    items = list(items)
    if not items:
        return items
    processing_ids = {getattr(item, f"document_{stage}_job_id", None) for item in items for stage in ("file", "ocr", "index")}
    semantic_ids = {getattr(item, "document_semantic_job_id", None) for item in items}
    jobs = ProcessingJob.objects.in_bulk(processing_ids - {None})
    semantic_jobs = SemanticIndexJob.objects.in_bulk(semantic_ids - {None})
    attempt_ids = {getattr(item, f"document_{stage}_attempt_id", None) for item in items for stage in ("file", "index")}
    attempts = ProcessingAttempt.objects.in_bulk(attempt_ids - {None})

    def stage(job, source):
        if job is None:
            return None
        return {"status": job.status, "job_id": str(job.pk), "progress": job.progress,
            "updated_at": job.updated_at.isoformat(), "error": job.error_message or job.error_code,
            "kind": job.job_type if source == "processing_job" else "semantic_index", "source": source}

    def attempt_stage(attempt):
        return {"status": "running" if attempt.status == "started" else attempt.status,
            "job_id": None, "attempt_id": str(attempt.pk), "progress": None,
            "updated_at": attempt.updated_at.isoformat(), "error": attempt.error_message or attempt.error_code,
            "kind": attempt.stage, "source": "processing_attempt"}

    for item in items:
        file_job = jobs.get(item.document_file_job_id)
        index_job = jobs.get(item.document_index_job_id)
        semantic_job = semantic_jobs.get(item.document_semantic_job_id)
        file_attempt = attempts.get(item.document_file_attempt_id)
        index_attempt = attempts.get(item.document_index_attempt_id)
        # These two ledgers describe the same stage. Pick the actual latest
        # request, not whichever ledger happens to be in the tasks UI page.
        index_source = "processing_job"
        if semantic_job and (not index_job or semantic_job.created_at > index_job.created_at):
            index_job, index_source = semantic_job, "semantic_index_job"
        file_stage = stage(file_job, "processing_job")
        if file_attempt and (not file_job or file_attempt.started_at > file_job.created_at):
            file_stage = attempt_stage(file_attempt)
        if file_stage is None:
            file_stage = {"status": item.status, "job_id": None, "progress": item.stage_progress,
                "updated_at": item.updated_at.isoformat(), "error": item.error_message or item.error_code,
                "kind": "file", "source": "upload_item"}
        index_stage = stage(index_job, index_source)
        if index_attempt and (not index_job or index_attempt.started_at > index_job.created_at):
            index_stage = attempt_stage(index_attempt)
        item.document_stages = {"file": file_stage, "ocr": stage(jobs.get(item.document_ocr_job_id), "processing_job"),
            "index": index_stage}
    return items
