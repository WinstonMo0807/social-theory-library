from __future__ import annotations

from collections import Counter
import uuid

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import (
    Discipline,
    KnowledgeNode,
    Subdiscipline,
    TheorySchool,
    Person,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    Topic,
)
from catalog.services.query_lexicon.sync import dry_run_reconciliation, rebuild_query_lexicon
from ingestion.models import ProcessingJob


def _entry_label(row: QueryLexiconEntry) -> str:
    model = {
        QueryLexiconEntry.EntityType.PERSON: Person,
        QueryLexiconEntry.EntityType.KNOWLEDGE_NODE: KnowledgeNode,
        QueryLexiconEntry.EntityType.TOPIC: Topic,
        QueryLexiconEntry.EntityType.DISCIPLINE: Discipline,
        QueryLexiconEntry.EntityType.SUBDISCIPLINE: Subdiscipline,
        QueryLexiconEntry.EntityType.THEORY_SCHOOL: TheorySchool,
    }.get(row.entity_type)
    if model is None:
        return str(row.entity_id)
    try:
        target = model.objects.get(pk=row.entity_id)
    except model.DoesNotExist:
        return f"{row.entity_type}:{row.entity_id}"
    if isinstance(target, Person):
        return target.preferred_name
    if isinstance(target, KnowledgeNode):
        return target.canonical_name_zh
    return getattr(target, "name", str(target))


def query_lexicon_workspace(*, query: str = "", entity_type: str = "", limit: int = 60) -> dict:
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 60
    state = QueryLexiconState.objects.select_related("active_generation").first()
    if state is None:
        return {
            "initialized": False,
            "revision": None,
            "generation": None,
            "entries": 0,
            "public_active_entries": 0,
            "admin_resolvable_entries": 0,
            "entities": [],
            "terms": [],
            "pending_events": 0,
            "failed_events": 0,
            "last_reconciliation": None,
        }
    generation = state.active_generation
    entries = QueryLexiconEntry.objects.filter(generation=generation)
    if entity_type:
        entries = entries.filter(entity_type=entity_type)
    query = str(query or "").strip()
    if query:
        entries = entries.filter(Q(term__icontains=query) | Q(normalized_term__icontains=query))
    rows = []
    for row in entries.order_by("entity_type", "normalized_term")[:limit]:
        rows.append(
            {
                "id": str(row.id),
                "term": row.term,
                "normalized_term": row.normalized_term,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id),
                "entity_label": _entry_label(row),
                "language": row.language,
                "term_type": row.term_type,
                "trust_level": row.trust_level,
                "source_kind": row.source_kind,
                "displayable": row.displayable,
                "public_active": row.public_active,
                "admin_resolvable": row.admin_resolvable,
                "source_ref": row.source_ref,
                "generation": str(generation.id),
                "revision": state.revision,
                "provenance": row.provenance,
            }
        )
    by_entity = list(
        QueryLexiconEntry.objects.filter(generation=generation)
        .values("entity_type")
        .annotate(
            entries=Count("id"),
            public_active_entries=Count("id", filter=Q(public_active=True)),
            admin_resolvable_entries=Count("id", filter=Q(admin_resolvable=True)),
        )
        .order_by("entity_type")
    )
    pending_events = QueryLexiconChangeEvent.objects.filter(
        processed_at__isnull=True,
        dead_lettered_at__isnull=True,
    ).count()
    failed_events = QueryLexiconChangeEvent.objects.filter(
        Q(dead_lettered_at__isnull=False) | Q(last_error_code__gt="")
    ).count()
    return {
        "initialized": True,
        "revision": state.revision,
        "generation": {
            "id": str(generation.id),
            "status": generation.status,
            "entry_count": generation.entry_count,
            "content_hash": generation.effective_content_hash,
            "activated_at": generation.activated_at,
            "built_at": generation.built_at,
        },
        "entries": generation.entry_count,
        "public_active_entries": entries.filter(public_active=True).count() if not query and not entity_type else QueryLexiconEntry.objects.filter(generation=generation, public_active=True).count(),
        "admin_resolvable_entries": entries.filter(admin_resolvable=True).count() if not query and not entity_type else QueryLexiconEntry.objects.filter(generation=generation, admin_resolvable=True).count(),
        "entities": by_entity,
        "terms": rows,
        "pending_events": pending_events,
        "failed_events": failed_events,
        "last_reconciliation": {
            "at": state.last_reconciled_at,
            "revision": state.last_reconciled_revision,
            "content_hash": state.last_reconciled_content_hash,
        },
    }


def _job_payload(job: ProcessingJob) -> dict:
    return {
        "job_id": str(job.id),
        "job_type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "attempt": job.attempt,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "stats": job.stats,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


@transaction.atomic
def enqueue_query_lexicon_reconciliation(*, actor=None) -> ProcessingJob:
    existing = ProcessingJob.objects.select_for_update().filter(
        job_type=ProcessingJob.JobType.QUERY_LEXICON_RECONCILE,
        status__in=[ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING],
    ).order_by("-created_at").first()
    if existing:
        return existing
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.QUERY_LEXICON_RECONCILE,
        status=ProcessingJob.Status.PENDING,
        engine="query-lexicon-reconciliation-v1",
        settings_version="query-lexicon-registry-v1",
        task_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        created_by=actor,
    )
    from catalog.tasks import run_query_lexicon_reconciliation

    task_id = job.task_id
    transaction.on_commit(
        lambda: run_query_lexicon_reconciliation.apply_async(
            args=[str(job.id), task_id],
            task_id=task_id,
            queue="query_lexicon",
        )
    )
    return job


def run_query_lexicon_reconciliation(*, job_id: str, task_id: str = "") -> ProcessingJob:
    job = ProcessingJob.objects.select_for_update().get(pk=job_id)
    if task_id and job.task_id != task_id:
        return job
    if job.status not in {ProcessingJob.Status.PENDING, ProcessingJob.Status.FAILED}:
        return job
    job.status = ProcessingJob.Status.RUNNING
    job.attempt += 1
    job.progress = 10
    job.started_at = timezone.now()
    job.error_code = ""
    job.error_message = ""
    job.save(update_fields=["status", "attempt", "progress", "started_at", "error_code", "error_message", "updated_at"])
    try:
        result = rebuild_query_lexicon()
    except Exception as exc:
        job.status = ProcessingJob.Status.FAILED
        job.progress = 100
        job.error_code = "reconciliation_failed"
        job.error_message = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "progress", "error_code", "error_message", "finished_at", "updated_at"])
        return job
    job.status = ProcessingJob.Status.SUCCEEDED
    job.progress = 100
    job.stats = result
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "progress", "stats", "finished_at", "updated_at"])
    return job


def reconcile_preview() -> dict:
    return dry_run_reconciliation()


def serialize_job(job: ProcessingJob) -> dict:
    return _job_payload(job)
