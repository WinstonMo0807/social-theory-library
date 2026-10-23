"""Filtered, paginated read model over the two existing task stores."""
from collections import Counter
from uuid import UUID

from django.db.models import CharField, Count, Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from django.utils.dateparse import parse_date

from catalog.models import KnowledgePublicationEvent, RecommendationIssue, SemanticIndexJob
from common.capabilities import Capability, has_capability
from ingestion.models import ProcessingJob
from .processing_identity import draft_title_work_ids, processing_edition, processing_identity, task_titles


SEMANTIC_STATUS = {
    "queued": "pending", "running": "running", "completed": "succeeded",
    "partial": "failed", "failed": "failed", "canceled": "canceled", "paused": "paused",
}


def page_number(value, default=1, maximum=None):
    try:
        number = int(value or default)
    except (TypeError, ValueError):
        raise ValidationError({"page": "页码和每页数量必须为正整数。"})
    if number < 1:
        raise ValidationError({"page": "页码和每页数量必须为正整数。"})
    return min(number, maximum) if maximum else number


def processing_task_page(params, actor):
    kind = str(params.get("job_type") or "").strip()
    status = str(params.get("status") or "").strip()
    query = str(params.get("q") or "").strip()[:200]
    edition_id = str(params.get("edition_id") or "").strip()
    work_id = str(params.get("work_id") or "").strip()
    size = page_number(params.get("page_size"), 30, 100)
    requested_page = page_number(params.get("page"))
    if status and status not in ProcessingJob.Status.values:
        raise ValidationError({"status": "请选择有效的任务状态。"})
    if kind and kind not in ProcessingJob.JobType.values:
        raise ValidationError({"job_type": "请选择有效的任务类型。"})
    jobs = ProcessingJob.objects.all()
    from catalog.services.curation_projects import visible_issues
    visible_issue_keys = visible_issues(actor).annotate(visible_key=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("visible_key")
    jobs = jobs.annotate(project_issue_key=Replace(KeyTextTransform("issue_id", "stats"), Value("-"), Value(""), output_field=CharField())).filter(
        ~Q(job_type="editorial_assistance") | Q(project_issue_key__in=visible_issue_keys))
    semantic = SemanticIndexJob.objects.all()
    for key, lookup in (("date_from", "created_at__date__gte"), ("date_to", "created_at__date__lte")):
        if params.get(key):
            try:
                value = parse_date(str(params[key]))
            except ValueError:
                value = None
            if value is None: raise ValidationError({key: "日期须为 YYYY-MM-DD。"})
            jobs, semantic = jobs.filter(**{lookup: value}), semantic.filter(**{lookup: value})
    # A dashboard link identifies one record across the two existing stores.
    # Invalid identity never falls back to an unrelated first page.
    task_id = str(params.get("task_id") or "").strip()
    task_source = str(params.get("task_source") or "").strip()
    if task_id or task_source:
        if task_source not in {"processing_job", "semantic_index_job"}:
            raise ValidationError({"task_source": "请选择有效的处理记录来源。"})
        try:
            identifier = UUID(task_id)
        except (ValueError, TypeError):
            raise ValidationError({"task_id": "处理记录编号无效，请从原任务重新打开。"})
        jobs = jobs.filter(pk=identifier) if task_source == "processing_job" else jobs.none()
        semantic = semantic.filter(pk=identifier) if task_source == "semantic_index_job" else semantic.none()
    if query:
        changed_titles = draft_title_work_ids(query)
        # UUIDs are hex in SQLite and hyphenated in PostgreSQL; compare the
        # persisted JSON identity to the same normalized key in either backend.
        issue_keys = RecommendationIssue.objects.filter(title__icontains=query).annotate(
            search_key=Replace(Cast("pk", output_field=CharField()), Value("-"), Value("")),
        ).values("search_key")
        jobs = jobs.annotate(
            issue_search_key=Replace(KeyTextTransform("issue_id", "stats"), Value("-"), Value(""), output_field=CharField()),
        ).filter(
            Q(edition__work__title__icontains=query) | Q(asset__edition__work__title__icontains=query)
            | Q(upload_item__source_filename__icontains=query) | Q(asset__original_filename__icontains=query)
            | Q(edition__work_id__in=changed_titles) | Q(asset__edition__work_id__in=changed_titles)
            | Q(job_type=ProcessingJob.JobType.EDITORIAL_ASSISTANCE, issue_search_key__in=issue_keys)
        )
        semantic = semantic.filter(Q(asset__edition__work__title__icontains=query) | Q(asset__edition__work_id__in=changed_titles) | Q(asset__original_filename__icontains=query))
    if edition_id:
        try:
            UUID(edition_id)
        except ValueError:
            jobs = jobs.none()
            semantic = semantic.none()
        else:
            jobs = jobs.filter(
                Q(edition_id=edition_id)
                | Q(asset__edition_id=edition_id)
                | Q(upload_item__edition_id=edition_id)
            )
            semantic = semantic.filter(asset__edition_id=edition_id)
    if work_id:
        try:
            UUID(work_id)
        except ValueError:
            raise ValidationError({"work_id": "作品编号无效。"})
        jobs = jobs.filter(
            Q(edition__work_id=work_id)
            | Q(asset__edition__work_id=work_id)
            | Q(upload_item__edition__work_id=work_id)
        )
        semantic = semantic.filter(asset__edition__work_id=work_id)
    # Count the complete matching scope, not the current page or a capped sample.
    matrix = Counter()
    for row in jobs.order_by().values("job_type", "status").annotate(total=Count("pk")):
        matrix[(row["job_type"], row["status"])] += row["total"]
    for row in semantic.order_by().values("status").annotate(total=Count("pk")):
        matrix[("semantic_index", SEMANTIC_STATUS[row["status"]])] += row["total"]
    counts = {state: sum(n for (task_kind, task_state), n in matrix.items() if task_state == state and (not kind or task_kind == kind)) for state in ProcessingJob.Status.values}
    types = {task_kind: sum(n for (item_kind, task_state), n in matrix.items() if item_kind == task_kind and (not status or task_state == status)) for task_kind in ProcessingJob.JobType.values}
    totals = {state: sum(n for (_, task_state), n in matrix.items() if task_state == state) for state in ProcessingJob.Status.values}
    if kind:
        jobs = jobs.filter(job_type=kind)
        if kind != "semantic_index":
            semantic = semantic.none()
    if status:
        jobs = jobs.filter(status=status)
        semantic = semantic.filter(status__in=[key for key, value in SEMANTIC_STATUS.items() if value == status])
    count = sum(n for (task_kind, task_state), n in matrix.items() if (not kind or task_kind == kind) and (not status or task_state == status))
    pages = max(1, (count + size - 1) // size)
    page = min(requested_page, pages)
    offset = (page - 1) * size
    # SQL performs the merged ordering and slice. Only this page's objects load.
    refs = list(jobs.order_by().annotate(source=Value("processing_job", output_field=CharField())).values("id", "created_at", "source").union(
        semantic.order_by().annotate(source=Value("semantic_index_job", output_field=CharField())).values("id", "created_at", "source"), all=True,
    ).order_by("-created_at", "-source", "-id")[offset:offset + size])
    job_rows = list(ProcessingJob.objects.filter(pk__in=[row["id"] for row in refs if row["source"] == "processing_job"]).select_related(
        "edition__work", "edition__active_catalog_revision", "asset__edition__work", "asset__edition__active_catalog_revision", "upload_item__edition__work", "upload_item__edition__active_catalog_revision",
    ).prefetch_related("edition__catalog_revisions", "asset__edition__catalog_revisions", "upload_item__edition__catalog_revisions"))
    semantic_rows = list(SemanticIndexJob.objects.filter(pk__in=[row["id"] for row in refs if row["source"] == "semantic_index_job"]).select_related("asset__edition__work"))
    titles = task_titles([*job_rows, *semantic_rows])
    events = {str(event.pk): event for event in KnowledgePublicationEvent.objects.filter(
        pk__in=[(job.stats or {}).get("knowledge_publication_event_id") for job in job_rows if (job.stats or {}).get("knowledge_publication_event_id")],
    ).select_related("catalog_revision")}
    from .catalog_ocr import progress_row
    rows = {}
    for source, objects in (("processing_job", job_rows), ("semantic_index_job", semantic_rows)):
        for job in objects:
            ordinary = source == "processing_job"
            identity = processing_identity(job, titles)
            row = {
                **identity, "id": str(job.pk), "source": source,
                "job_type": job.job_type if ordinary else "semantic_index",
                "item_id": str(job.upload_item_id) if ordinary and job.upload_item_id else None,
                "asset_id": str(job.asset_id) if job.asset_id else None,
                "status": job.status if ordinary else SEMANTIC_STATUS[job.status],
                "progress": job.progress, "engine": job.engine if ordinary else job.model_name,
                "attempt": job.attempt if ordinary else job.attempts,
                "max_attempts": job.max_attempts if ordinary else 3,
                "settings_version": job.settings_version if ordinary else job.chunk_version,
                "created_at": job.created_at, "started_at": job.started_at, "finished_at": job.finished_at,
                "duration_seconds": round(((job.finished_at or timezone.now()) - job.started_at).total_seconds(), 2) if job.started_at else None,
                "last_error": job.error_message, "error_code": job.error_code,
                "stats": job.stats, "ocr_progress": None,
            }
            if ordinary and job.job_type == "ocr":
                row["ocr_progress"] = progress_row(job, actor=actor, event=events.get(str((job.stats or {}).get("knowledge_publication_event_id") or "")), edition=processing_edition(job), legacy_controls=True)
            if params.get("workspace") == "1":
                from .processing_workspace import workspace_task
                row = workspace_task(job, row, actor)
            rows[(source, str(job.pk))] = row
    return {
        "results": [rows[(row["source"], str(row["id"]))] for row in refs if (row["source"], str(row["id"])) in rows],
        "count": count, "page": page, "page_size": size, "pages": pages,
        "next_page": page + 1 if page < pages else None, "previous_page": page - 1 if page > 1 else None,
        "counts": counts, "type_counts": types, "total_counts": totals, "total": sum(matrix.values()),
        "can_manage": has_capability(actor, Capability.RETRY_JOBS),
        "ordering": "-created_at,-source,-id",
    }
