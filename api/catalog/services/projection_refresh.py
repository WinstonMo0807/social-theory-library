"""Bounded projection coordination above existing specialist job types.

Canonical revisions and projection freshness live in PostgreSQL. A
``ProcessingJob`` coordinates one bounded object refresh, while
``CapabilityDemand`` only decides whether an executor can run it. Semantic
indexing keeps its specialist job and QueryLexicon keeps its durable outbox.
"""

from __future__ import annotations

from hashlib import sha256
import uuid

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from catalog.models import (
    Asset,
    CuratedClaim,
    DerivedClaim,
    Discipline,
    DocumentRevision,
    DomainChangeEvent,
    Edition,
    EvidenceSpan,
    KnowledgeNode,
    KnowledgeRelation,
    Page,
    Person,
    PersonNodeRelation,
    ProjectionState,
    ReadingPath,
    ScholarProfile,
    SemanticIndexJob,
    Subdiscipline,
    TextBlock,
    TheorySchool,
    TheoryTimelineEvent,
    Topic,
    Work,
    WorkNodeRelation,
)
from catalog.services.dependency_engine import (
    bind_projection_task,
    claim_projection,
    complete_projection,
    mark_projection_failed,
    mark_projection_waiting,
    projection_types_for,
    reclaim_expired_projection_leases,
)
from ingestion.models import ProcessingJob


TARGET_MODELS = {
    "work": Work,
    "edition": Edition,
    "asset": Asset,
    "document_revision": DocumentRevision,
    "page": Page,
    "text_block": TextBlock,
    "evidence_span": EvidenceSpan,
    "derived_claim": DerivedClaim,
    "curated_claim": CuratedClaim,
    "person": Person,
    "scholar_profile": ScholarProfile,
    "knowledge_node": KnowledgeNode,
    "knowledge_relation": KnowledgeRelation,
    "work_node_relation": WorkNodeRelation,
    "person_node_relation": PersonNodeRelation,
    "discipline": Discipline,
    "subdiscipline": Subdiscipline,
    "topic": Topic,
    "reading_path": ReadingPath,
    "theory_school": TheorySchool,
    "timeline_event": TheoryTimelineEvent,
}

DIRECT_PROJECTIONS = {
    ProjectionState.ProjectionType.KNOWLEDGE_GRAPH,
    ProjectionState.ProjectionType.TIMELINE,
    ProjectionState.ProjectionType.READING_PATH_SUPPORT,
    ProjectionState.ProjectionType.PUBLIC,
}
SEMANTIC_TERMINAL = {
    SemanticIndexJob.Status.COMPLETED,
    SemanticIndexJob.Status.PARTIAL,
    SemanticIndexJob.Status.FAILED,
    SemanticIndexJob.Status.CANCELED,
    SemanticIndexJob.Status.PAUSED,
}
VERIFIED_SEMANTIC_BACKENDS = {"meilisearch", "no-chunks"}
VERIFIED_FULLTEXT_BACKENDS = {"meilisearch", "no-passages"}


def _target(target_type: str, target_id: str):
    model = TARGET_MODELS.get(str(target_type or "").strip().casefold())
    if model is None:
        raise ValueError("不支持的投影目标类型。")
    row = model.objects.filter(pk=target_id).first()
    if row is None:
        raise ValueError("投影目标不存在。")
    return row


def _manual_idempotency_key(target_type: str, target) -> str:
    marker = f"{target_type}:{target.pk}:{target.updated_at.isoformat()}"
    digest = sha256(marker.encode("utf-8")).hexdigest()[:20]
    return f"projection-refresh:{target_type}:{target.pk}:{digest}"[:128]


def _event_idempotency_key(event: DomainChangeEvent) -> str:
    return (
        f"projection-refresh:{event.object_type}:{event.object_id}:"
        f"r{event.canonical_revision}"
    )[:128]


def _captured_states(target_type: str, target_id) -> list[dict]:
    return [
        {
            "state_id": str(row.id),
            "projection_type": row.projection_type,
            "source_revision": row.source_revision,
        }
        for row in ProjectionState.objects.filter(
            object_type=target_type,
            object_id=target_id,
            projection_type__in=projection_types_for(target_type),
        ).order_by("projection_type")
    ]


def _bind_known_projection_states(
    job: ProcessingJob,
    target_type: str,
    target_id,
    tracked_types=None,
) -> None:
    bind_projection_task(
        object_type=target_type,
        object_id=target_id,
        projection_types=tracked_types or projection_types_for(target_type),
        owner_type="ProcessingJob",
        owner_key=str(job.id),
    )


def _mark_job_states_waiting(job: ProcessingJob, *, reason: str) -> None:
    plan = dict((job.stats or {}).get("projection_plan") or {})
    state_ids = [
        row.get("state_id")
        for row in plan.get("states") or []
        if row.get("state_id")
    ]
    ProjectionState.objects.filter(
        pk__in=state_ids,
        projected_revision__lt=F("source_revision"),
    ).exclude(status=ProjectionState.Status.PROJECTING).update(
        status=ProjectionState.Status.WAITING_FOR_CAPABILITY,
        stale_reason=str(reason)[:300],
        task_owner_type="ProcessingJob",
        task_owner_key=str(job.id),
        updated_at=timezone.now(),
    )


def _nas_projection_executor_available() -> bool:
    from catalog.models import CapabilityExecutor
    from common.task_runtime import live_executors

    return any(
        row.kind == CapabilityExecutor.Kind.NAS
        for row in live_executors(
            "projection",
            require_capacity=False,
            task_kind="projection_refresh",
        )
    )


def dispatch_projection_demand(demand) -> bool:
    """Lease one exact demand before putting it on the NAS-consumed queue."""

    from catalog.models import CapabilityExecutor
    from common.task_runtime import (
        claim_specific_demand,
        live_executors,
        release_demand,
    )

    executors = [
        row
        for row in live_executors(
            "projection",
            require_capacity=True,
            task_kind="projection_refresh",
        )
        if row.kind == CapabilityExecutor.Kind.NAS
    ]
    for executor in executors:
        lease = claim_specific_demand(
            demand.id,
            executor_id=executor.executor_id,
            lease_seconds=900,
        )
        if lease is None:
            continue
        job = ProcessingJob.objects.filter(
            pk=demand.owner_key,
            job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
        ).first()
        if job is None:
            release_demand(
                lease.demand_id,
                lease.lease_token,
                executor_id=lease.executor_id,
                error_code="projection_job_missing",
                error_message="Projection ProcessingJob no longer exists.",
                retry=False,
            )
            return False
        task_id = str(uuid.uuid4())
        ProcessingJob.objects.filter(pk=job.pk).update(
            task_id=task_id,
            error_code="",
            error_message="",
            updated_at=timezone.now(),
        )
        try:
            from catalog.tasks import execute_projection_demand

            execute_projection_demand.apply_async(
                args=[
                    str(lease.demand_id),
                    str(lease.lease_token),
                    lease.executor_id,
                ],
                task_id=task_id,
                queue="celery",
            )
        except Exception as exc:
            ProcessingJob.objects.filter(pk=job.pk).update(
                status=ProcessingJob.Status.FAILED,
                error_code="queue_unavailable",
                error_message=str(exc)[:4000],
                finished_at=timezone.now(),
                updated_at=timezone.now(),
            )
            release_demand(
                lease.demand_id,
                lease.lease_token,
                executor_id=lease.executor_id,
                error_code="queue_unavailable",
                error_message=str(exc),
                retry=True,
                retry_after_seconds=30,
            )
            raise
        return True
    return False


def _schedule_job_capability(job: ProcessingJob):
    """Create one sidecar demand for the next durable job attempt."""

    from catalog.models import CapabilityDemand
    from common.task_runtime import queue_or_wait

    job.refresh_from_db()
    if job.status == ProcessingJob.Status.SUCCEEDED:
        return None
    if job.status == ProcessingJob.Status.FAILED and job.attempt >= job.max_attempts:
        return None
    if job.status == ProcessingJob.Status.FAILED:
        ProcessingJob.objects.filter(pk=job.pk).update(
            status=ProcessingJob.Status.PENDING,
            progress=0,
            task_id="",
            started_at=None,
            finished_at=None,
            updated_at=timezone.now(),
        )
        job.refresh_from_db()

    attempt_number = job.attempt + 1
    nas_available = _nas_projection_executor_available()
    result = queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(job.id),
        capability="projection",
        idempotency_key=f"projection-execution:{job.id}:{attempt_number}",
        payload={
            "task_kind": "projection_refresh",
            "processing_job_id": str(job.id),
            "attempt": attempt_number,
        },
        priority=20,
        publication_blocking=False,
        preferred_queue="celery",
        dispatch=dispatch_projection_demand if nas_available else None,
    )
    if not nas_available and result.demand.state == CapabilityDemand.State.READY:
        CapabilityDemand.objects.filter(pk=result.demand.pk).update(
            state=CapabilityDemand.State.WAITING_FOR_CAPABILITY,
            last_error_code="nas_projection_executor_missing",
            last_error_message=(
                "No live NAS executor advertises projection capability."
            ),
            updated_at=timezone.now(),
        )
        result.demand.refresh_from_db()

    with transaction.atomic():
        locked = ProcessingJob.objects.select_for_update().get(pk=job.pk)
        stats = dict(locked.stats or {})
        runtime = dict(stats.get("capability_runtime") or {})
        runtime.update(
            {
                "demand_id": str(result.demand.id),
                "demand_state": result.demand.state,
                "attempt": attempt_number,
                "executor_available": nas_available,
            }
        )
        stats["capability_runtime"] = runtime
        locked.stats = stats
        locked.save(update_fields=["stats", "updated_at"])
    if not nas_available:
        job.refresh_from_db()
        _mark_job_states_waiting(
            job,
            reason="projection capability has no live NAS executor",
        )
    return result


def dispatch_projection_refresh_job(job_id: str, task_id: str = "") -> bool:
    """Compatibility adapter used by ProcessingJob recovery."""

    job = ProcessingJob.objects.get(pk=job_id)
    result = _schedule_job_capability(job)
    return bool(result and result.executor_available)


@transaction.atomic
def queue_projection_refresh(
    *,
    target_type: str,
    target_id: str,
    actor=None,
    force: bool = False,
    source_event: DomainChangeEvent | None = None,
    preserve_attempts: bool = False,
) -> ProcessingJob:
    target_type = str(target_type or "").strip().casefold()
    target = _target(target_type, target_id)
    key = (
        _event_idempotency_key(source_event)
        if source_event is not None
        else _manual_idempotency_key(target_type, target)
    )
    job = (
        ProcessingJob.objects.select_for_update()
        .filter(idempotency_key=key)
        .first()
    )
    captured = _captured_states(target_type, target.pk)
    if job is None:
        job = ProcessingJob.objects.create(
            job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
            status=ProcessingJob.Status.PENDING,
            engine="projection-refresh-v3",
            task_id="",
            idempotency_key=key,
            correlation_id=(
                str(source_event.correlation_id)
                if source_event is not None
                else str(uuid.uuid4())
            ),
            created_by=actor,
            stats={
                "target_type": target_type,
                "target_id": str(target.pk),
                "bounded": True,
                "source_event": (
                    {
                        "id": str(source_event.id),
                        "canonical_revision": source_event.canonical_revision,
                        "catalog_revision_id": (
                            str(source_event.catalog_revision_id)
                            if source_event.catalog_revision_id
                            else None
                        ),
                        "change_kind": source_event.change_kind,
                        "changed_fields": list(source_event.changed_fields or []),
                    }
                    if source_event is not None
                    else None
                ),
                "projection_plan": {
                    "states": captured,
                    "semantic_job_ids": [],
                },
            },
        )
        _bind_known_projection_states(
            job,
            target_type,
            target.pk,
            [row["projection_type"] for row in captured],
        )
        transaction.on_commit(
            lambda job_id=job.id: _schedule_job_capability(
                ProcessingJob.objects.get(pk=job_id)
            )
        )
        return job

    if (
        job.status in {ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING}
        and (not force or preserve_attempts)
    ):
        return job
    if job.status == ProcessingJob.Status.SUCCEEDED and not force:
        return job

    stats = dict(job.stats or {})
    stats["manual_retry"] = {
        "requested_at": timezone.now().isoformat(),
        "previous_status": job.status,
    }
    stats["projection_plan"] = {
        "states": captured,
        "semantic_job_ids": [],
    }
    job.status = ProcessingJob.Status.PENDING
    job.task_id = ""
    if force and not preserve_attempts:
        job.attempt = 0
    job.progress = 0
    job.error_code = ""
    job.error_message = ""
    job.error_kind = ""
    job.started_at = None
    job.finished_at = None
    job.stats = stats
    if actor is not None and job.created_by_id is None:
        job.created_by = actor
    job.save()
    _bind_known_projection_states(
        job,
        target_type,
        target.pk,
        [row["projection_type"] for row in captured],
    )
    transaction.on_commit(
        lambda job_id=job.id: _schedule_job_capability(
            ProcessingJob.objects.get(pk=job_id)
        )
    )
    return job


def schedule_domain_change_projections(event_id) -> ProcessingJob:
    event = DomainChangeEvent.objects.get(pk=event_id)
    if event.processed_at is None:
        raise ValueError(
            "domain change must be resolved before projection scheduling"
        )
    return queue_projection_refresh(
        target_type=event.object_type,
        target_id=str(event.object_id),
        actor=event.actor,
        source_event=event,
    )


def _claim(job_id: str, task_id: str) -> tuple[ProcessingJob, bool]:
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().get(pk=job_id)
        if task_id and job.task_id and job.task_id != task_id:
            return job, False
        if job.status not in {
            ProcessingJob.Status.PENDING,
            ProcessingJob.Status.FAILED,
        }:
            return job, False
        if (
            job.status == ProcessingJob.Status.FAILED
            and job.attempt >= job.max_attempts
        ):
            return job, False
        job.status = ProcessingJob.Status.RUNNING
        job.attempt += 1
        job.progress = max(job.progress, 5)
        job.started_at = timezone.now()
        job.finished_at = None
        job.error_code = ""
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "attempt",
                "progress",
                "started_at",
                "finished_at",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return job, True


def _ready_assets(target_type: str, target) -> list[Asset]:
    ids = []
    if target_type == "asset":
        ids = [target.pk]
    elif target_type == "edition":
        ids = list(target.assets.values_list("pk", flat=True))
    elif target_type == "work":
        ids = list(
            Asset.objects.filter(edition__work=target).values_list(
                "pk", flat=True
            )
        )
    elif target_type == "document_revision":
        ids = [target.asset_id]
    elif target_type == "page":
        ids = [target.asset_id]
    elif target_type == "text_block":
        ids = [target.page.asset_id]
    elif target_type == "evidence_span":
        ids = [target.document_revision.asset_id]
    elif target_type in {"derived_claim", "curated_claim"}:
        if getattr(target, "document_revision_id", None):
            ids = [target.document_revision.asset_id]
        elif getattr(target, "adopted_from_id", None):
            ids = [target.adopted_from.document_revision.asset_id]
        elif getattr(target, "work_id", None):
            ids = list(
                Asset.objects.filter(edition__work_id=target.work_id).values_list(
                    "pk", flat=True
                )
            )
    elif target_type in {"person", "scholar_profile", "person_node_relation"}:
        person_id = (
            target.person_id
            if target_type in {"scholar_profile", "person_node_relation"}
            else target.pk
        )
        ids = list(
            Asset.objects.filter(
                edition__contributions__person_id=person_id,
                edition__contributions__approved=True,
            ).values_list("pk", flat=True)
        )
    elif target_type == "work_node_relation":
        ids = list(
            Asset.objects.filter(edition__work_id=target.work_id).values_list(
                "pk", flat=True
            )
        )
    elif target_type == "knowledge_node":
        ids = list(
            Asset.objects.filter(
                edition__work__node_relations__node=target
            ).values_list("pk", flat=True)
        )
    elif target_type == "knowledge_relation":
        ids = list(
            Asset.objects.filter(
                Q(edition__work__node_relations__node=target.source_node)
                | Q(edition__work__node_relations__node=target.target_node)
            ).values_list("pk", flat=True)
        )
    elif target_type == "discipline":
        ids = list(
            Asset.objects.filter(
                edition__work__discipline_relations__discipline=target
            ).values_list("pk", flat=True)
        )
    elif target_type == "subdiscipline":
        ids = list(
            Asset.objects.filter(
                edition__work__subdiscipline_relations__subdiscipline=target
            ).values_list("pk", flat=True)
        )
    elif target_type == "topic":
        ids = list(
            Asset.objects.filter(
                edition__work__topic_relations__topic=target
            ).values_list("pk", flat=True)
        )
    elif target_type == "reading_path":
        ids = list(
            Asset.objects.filter(
                edition__work__reading_path_items__reading_path=target
            ).values_list("pk", flat=True)
        )
    return list(
        Asset.objects.select_related("edition__work")
        .filter(
            pk__in=list(dict.fromkeys(ids))[:24],
            kind=Asset.Kind.NORMALIZED,
            is_current=True,
            status=Asset.Status.READY,
        )
        .order_by("created_at")[:24]
    )


def _refresh_target(target_type: str, target, actor=None) -> dict:
    """Legacy bounded manual refresh retained for the 2.7 admin contract."""

    from catalog.services.query_lexicon.sync import process_pending_events
    from ingestion.services.processing import queue_query_lexicon_candidate_job
    from catalog.services.semantic_indexing import queue_semantic_job

    result = {
        "target_type": target_type,
        "target_id": str(target.pk),
        "query_lexicon": process_pending_events(limit=100),
        "semantic_jobs": [],
        "candidate_jobs": [],
        "bounded": True,
    }
    for asset in _ready_assets(target_type, target):
        if not asset.semantic_chunks.filter(index_status="ready").exists():
            result["semantic_jobs"].append(
                {
                    "asset_id": str(asset.pk),
                    "status": "skipped_no_ready_chunks",
                }
            )
            result["candidate_jobs"].append(
                {
                    "asset_id": str(asset.pk),
                    "status": "skipped_no_ready_chunks",
                }
            )
            continue
        semantic = queue_semantic_job(asset, force=False, actor=actor)
        result["semantic_jobs"].append(
            {
                "asset_id": str(asset.pk),
                "job_id": str(semantic.id) if semantic else None,
                "status": semantic.status if semantic else "not_created",
            }
        )
        candidate = queue_query_lexicon_candidate_job(
            asset,
            actor=actor,
            force=False,
        )
        result["candidate_jobs"].append(
            {
                "asset_id": str(asset.pk),
                "job_id": str(candidate.id),
                "status": candidate.status,
            }
        )
    return result


def _state_leases(
    job: ProcessingJob,
    target_type: str,
    target_id,
) -> dict[str, dict]:
    plan = dict((job.stats or {}).get("projection_plan") or {})
    output = {}
    for captured in plan.get("states") or []:
        projection_type = captured["projection_type"]
        captured_revision = int(captured["source_revision"])
        state = ProjectionState.objects.get(pk=captured["state_id"])
        if state.source_revision > captured_revision:
            output[projection_type] = {**captured, "status": "superseded"}
            continue
        if state.projected_revision >= captured_revision:
            output[projection_type] = {
                **captured,
                "status": "already_current",
            }
            continue
        if (
            state.status == ProjectionState.Status.PROJECTING
            and state.task_owner_type == "ProcessingJob"
            and state.task_owner_key == str(job.id)
            and state.lease_token
        ):
            output[projection_type] = {
                **captured,
                "status": "claimed",
                "lease_token": str(state.lease_token),
            }
            continue
        lease = claim_projection(
            object_type=target_type,
            object_id=target_id,
            projection_type=projection_type,
            owner_type="ProcessingJob",
            owner_key=str(job.id),
            lease_seconds=7200,
        )
        output[projection_type] = (
            {
                **captured,
                "status": "claimed",
                "lease_token": str(lease.lease_token),
            }
            if lease is not None
            else {**captured, "status": "not_claimed"}
        )
    return output


def _complete_tracked(tracked: dict) -> None:
    if tracked.get("status") != "claimed":
        return
    complete_projection(
        tracked["state_id"],
        tracked["lease_token"],
        projected_revision=int(tracked["source_revision"]),
    )


def _fail_tracked(tracked: dict, *, code: str, message: str) -> None:
    if tracked.get("status") != "claimed":
        return
    mark_projection_failed(
        tracked["state_id"],
        tracked["lease_token"],
        error_code=code,
        error_message=message,
    )


def _query_lexicon_projection(target, tracked: dict) -> dict:
    from catalog.models import QueryLexiconChangeEvent
    from catalog.services.query_lexicon.sync import process_pending_events

    source_model = target._meta.label
    relevant = QueryLexiconChangeEvent.objects.filter(
        source_model=source_model,
        source_object_id=target.pk,
    )
    last_seq = (
        relevant.order_by("-event_seq")
        .values_list("event_seq", flat=True)
        .first()
    )
    runs = []
    if last_seq is not None:
        for _ in range(3):
            if not relevant.filter(
                event_seq__lte=last_seq,
                processed_at__isnull=True,
            ).exists():
                break
            runs.append(process_pending_events(limit=100))
    remaining = (
        relevant.filter(
            event_seq__lte=last_seq,
            processed_at__isnull=True,
        ).count()
        if last_seq is not None
        else 0
    )
    if remaining or any(int(row.get("failed", 0) or 0) for row in runs):
        _fail_tracked(
            tracked,
            code="query_lexicon_pending",
            message=(
                f"{remaining} target outbox events remain after bounded "
                "processing."
            ),
        )
        return {"status": "failed", "remaining": remaining, "runs": runs}
    _complete_tracked(tracked)
    return {
        "status": "current",
        "source_model": source_model,
        "captured_event_seq": last_seq,
        "runs": runs,
    }


def _fulltext_projection(assets: list[Asset], tracked: dict, *, catalog_revision=None) -> dict:
    from ingestion.services.indexing import index_asset

    results = []
    failures = []
    for asset in assets:
        result = index_asset(
            asset,
            is_public=asset.edition.state == "published",
            catalog_revision=catalog_revision if catalog_revision and catalog_revision.edition_id == asset.edition_id else None,
        )
        results.append({"asset_id": str(asset.id), **result})
        if result.get("backend") not in VERIFIED_FULLTEXT_BACKENDS:
            failures.append(
                str(
                    result.get("warning")
                    or result.get("backend")
                    or "unverified"
                )
            )
        else:
            Edition.objects.filter(pk=asset.edition_id).update(
                search_indexed_at=timezone.now(),
                updated_at=timezone.now(),
            )
    if failures:
        _fail_tracked(
            tracked,
            code="fulltext_projection_failed",
            message="; ".join(failures)[:4000],
        )
        return {"status": "failed", "assets": results}
    _complete_tracked(tracked)
    return {"status": "current", "assets": results, "empty": not assets}


def _claim_projection(assets: list[Asset], tracked: dict, *, catalog_revision=None) -> dict:
    from catalog.services.claims.indexing import index_document_revision_claims

    revisions_query = DocumentRevision.objects.filter(
            asset_id__in=[asset.id for asset in assets],
        )
    revisions_query = revisions_query.filter(pk=catalog_revision.document_revision_id) if catalog_revision else revisions_query.filter(is_active=True)
    revisions = list(revisions_query.order_by("asset_id"))
    results = []
    failures = []
    for revision in revisions:
        result = index_document_revision_claims(
            revision,
            track_projection=False,
            catalog_revision=catalog_revision,
        )
        results.append({"document_revision_id": str(revision.id), **result})
        if result.get("status") != "completed":
            failures.append(
                str(
                    result.get("warning")
                    or result.get("error_code")
                    or "unverified"
                )
            )
    if failures:
        _fail_tracked(
            tracked,
            code="claim_index_projection_failed",
            message="; ".join(failures)[:4000],
        )
        return {"status": "failed", "revisions": results}
    _complete_tracked(tracked)
    return {
        "status": "current",
        "revisions": results,
        "empty": not revisions,
    }


def _bind_semantic_job(job: SemanticIndexJob, parent_job_id) -> None:
    with transaction.atomic():
        locked = SemanticIndexJob.objects.select_for_update().get(pk=job.pk)
        stats = dict(locked.stats or {})
        parent_ids = [
            str(value)
            for value in stats.get("projection_refresh_parent_ids") or []
        ]
        if str(parent_job_id) not in parent_ids:
            parent_ids.append(str(parent_job_id))
        stats["projection_refresh_parent_ids"] = parent_ids[-20:]
        locked.stats = stats
        locked.save(update_fields=["stats", "updated_at"])


def _semantic_projection(
    job: ProcessingJob,
    assets: list[Asset],
    tracked: dict,
    *,
    catalog_revision=None,
) -> dict:
    from catalog.services.semantic_indexing import queue_semantic_job

    jobs = []
    waiting = []
    failed = []
    for asset in assets:
        previous = asset.edition.active_catalog_revision
        metadata_only = bool(
            catalog_revision and previous and previous.reader_asset_id == asset.pk
            and previous.fulltext_ready and asset.semantic_chunks.exists()
            and not {"file", "pdf", "ocr", "fulltext", "document_revision", "catalog_publish"}.intersection(catalog_revision.changed_fields or [])
        )
        semantic = queue_semantic_job(
            asset,
            force=False,
            actor=job.created_by,
            projection_parent_id=job.id,
            catalog_revision=catalog_revision,
            metadata_only=metadata_only,
        )
        if semantic is None:
            waiting.append(
                {"asset_id": str(asset.id), "status": "not_created"}
            )
            continue
        _bind_semantic_job(semantic, job.id)
        semantic.refresh_from_db()
        jobs.append(semantic)
        if semantic.status in {
            SemanticIndexJob.Status.FAILED,
            SemanticIndexJob.Status.PARTIAL,
            SemanticIndexJob.Status.CANCELED,
        }:
            failed.append(semantic)
        elif semantic.status == SemanticIndexJob.Status.PAUSED:
            waiting.append(
                {
                    "asset_id": str(asset.id),
                    "job_id": str(semantic.id),
                    "status": semantic.status,
                }
            )

    with transaction.atomic():
        locked = ProcessingJob.objects.select_for_update().get(pk=job.pk)
        stats = dict(locked.stats or {})
        plan = dict(stats.get("projection_plan") or {})
        plan["semantic_job_ids"] = [str(row.id) for row in jobs]
        plan["semantic_state_id"] = tracked.get("state_id")
        plan["semantic_source_revision"] = tracked.get("source_revision")
        stats["projection_plan"] = plan
        locked.stats = stats
        locked.save(update_fields=["stats", "updated_at"])

    if failed:
        _fail_tracked(
            tracked,
            code="semantic_projection_failed",
            message="; ".join(
                f"{row.id}:{row.status}:{row.error_code}" for row in failed
            )[:4000],
        )
        return {"status": "failed", "jobs": [str(row.id) for row in jobs]}
    if waiting:
        if tracked.get("status") == "claimed":
            mark_projection_waiting(
                tracked["state_id"],
                tracked["lease_token"],
                reason="semantic indexing is paused or unavailable",
                owner_type="ProcessingJob",
                owner_key=str(job.id),
            )
        return {
            "status": "waiting",
            "jobs": [str(row.id) for row in jobs],
            "details": waiting,
        }
    if not jobs:
        _complete_tracked(tracked)
        return {"status": "current", "jobs": [], "empty": True}
    if all(row.status == SemanticIndexJob.Status.COMPLETED for row in jobs):
        invalid = [
            row
            for row in jobs
            if (row.stats or {}).get("backend")
            not in VERIFIED_SEMANTIC_BACKENDS
        ]
        if invalid:
            _fail_tracked(
                tracked,
                code="semantic_backend_unverified",
                message=(
                    "Semantic specialist completed without a verified "
                    "external index write."
                ),
            )
            return {
                "status": "failed",
                "jobs": [str(row.id) for row in jobs],
            }
        _complete_tracked(tracked)
        return {"status": "current", "jobs": [str(row.id) for row in jobs]}
    return {"status": "delegated", "jobs": [str(row.id) for row in jobs]}


def _recommendation_projection(
    target_type: str,
    target,
    source_event: dict | None,
    tracked: dict,
) -> dict:
    """Refresh only automatic snapshots whose eligibility can change."""

    from catalog.models import RecommendationSnapshot
    from catalog.services.recommendations import (
        PLACEMENT_TARGETS,
        ensure_default_policies,
        generate_snapshot,
    )

    change_kind = str((source_event or {}).get("change_kind") or "")
    refreshed = []
    preserved = []
    if change_kind in {
        DomainChangeEvent.ChangeKind.PUBLISH,
        DomainChangeEvent.ChangeKind.WITHDRAW,
    }:
        target_family = {
            "work": "work",
            "edition": "work",
            "person": "scholar",
            "scholar_profile": "scholar",
            "topic": "topic",
        }.get(target_type)
        for policy in ensure_default_policies():
            if PLACEMENT_TARGETS.get(policy.placement) != target_family:
                continue
            current = policy.snapshots.filter(is_current=True).first()
            if (
                current is not None
                and current.source == RecommendationSnapshot.Source.MANUAL
            ):
                preserved.append(policy.placement)
                continue
            snapshot = generate_snapshot(policy)
            refreshed.append(
                {
                    "placement": policy.placement,
                    "snapshot": str(snapshot.id),
                }
            )
    _complete_tracked(tracked)
    return {
        "status": "current",
        "refreshed": refreshed,
        "manual_preserved": preserved,
        "storage": "postgresql_snapshot_with_live_relations",
    }


def _direct_projection(target, projection_type: str, tracked: dict) -> dict:
    target.refresh_from_db()
    _complete_tracked(tracked)
    return {
        "status": "current",
        "storage": "postgresql_direct_read",
        "projection_type": projection_type,
    }


def _legacy_run(
    job: ProcessingJob,
    target_type: str,
    target,
) -> ProcessingJob:
    stats = dict(job.stats or {})
    stats.update(_refresh_target(target_type, target, actor=job.created_by))
    job.status = ProcessingJob.Status.SUCCEEDED
    job.progress = 100
    job.stats = stats
    job.finished_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "progress",
            "stats",
            "finished_at",
            "updated_at",
        ]
    )
    return job


def run_projection_refresh_job(
    job_id: str,
    *,
    task_id: str = "",
) -> ProcessingJob:
    job, claimed = _claim(job_id, task_id)
    if not claimed:
        return job
    try:
        stats = dict(job.stats or {})
        target_type = str(stats.get("target_type") or "").strip().casefold()
        target_id = str(stats.get("target_id") or "")
        target = _target(target_type, target_id)
        plan = dict(stats.get("projection_plan") or {})
        if not plan.get("states"):
            return _legacy_run(job, target_type, target)

        tracked = _state_leases(job, target_type, target.pk)
        assets = _ready_assets(target_type, target)
        results = {}
        failures = []
        delegated = False
        waiting = False
        source_event = (
            stats.get("source_event")
            if isinstance(stats.get("source_event"), dict)
            else None
        )
        catalog_revision = None
        if source_event and source_event.get("catalog_revision_id"):
            from catalog.models import CatalogPublicationRevision

            catalog_revision = CatalogPublicationRevision.objects.select_related("reader_asset__edition__work").get(pk=source_event["catalog_revision_id"])
            # A publication consumes the captured file, never whichever file
            # a later upload happened to mark current.
            assets = [catalog_revision.reader_asset] if catalog_revision.reader_asset_id else []
        for projection_type, state in tracked.items():
            if state.get("status") in {
                "already_current",
                "superseded",
                "not_claimed",
            }:
                results[projection_type] = {"status": state["status"]}
                continue
            if catalog_revision and projection_type in {
                ProjectionState.ProjectionType.FULLTEXT, ProjectionState.ProjectionType.SEMANTIC,
                ProjectionState.ProjectionType.CLAIM_INDEX,
            }:
                if catalog_revision.status == "withdrawn":
                    # Public queries recheck the formal pointer. Retain old
                    # immutable namespaces for rollback instead of rebuilding.
                    _complete_tracked(state)
                    results[projection_type] = {"status": "current", "scope": "withdrawn"}
                    continue
                if not (catalog_revision.provenance or {}).get("requested_fulltext_ready"):
                    _complete_tracked(state)
                    results[projection_type] = {"status": "current", "scope": "metadata_only"}
                    continue
            if projection_type == ProjectionState.ProjectionType.QUERY_LEXICON:
                result = _query_lexicon_projection(target, state)
            elif projection_type == ProjectionState.ProjectionType.FULLTEXT:
                result = _fulltext_projection(assets, state, catalog_revision=catalog_revision)
            elif projection_type == ProjectionState.ProjectionType.CLAIM_INDEX:
                result = _claim_projection(assets, state, catalog_revision=catalog_revision)
            elif projection_type == ProjectionState.ProjectionType.SEMANTIC:
                result = _semantic_projection(job, assets, state, catalog_revision=catalog_revision)
            elif (
                projection_type
                == ProjectionState.ProjectionType.RECOMMENDATION
            ):
                result = _recommendation_projection(
                    target_type,
                    target,
                    source_event,
                    state,
                )
            elif projection_type in DIRECT_PROJECTIONS:
                result = _direct_projection(target, projection_type, state)
            else:
                _fail_tracked(
                    state,
                    code="projection_handler_missing",
                    message=(
                        f"No projection handler registered for "
                        f"{projection_type}."
                    ),
                )
                result = {
                    "status": "failed",
                    "error_code": "projection_handler_missing",
                }
            results[projection_type] = result
            failures.extend(
                [projection_type]
                if result.get("status") == "failed"
                else []
            )
            delegated = delegated or result.get("status") == "delegated"
            waiting = waiting or result.get("status") == "waiting"

        job.refresh_from_db()
        stats = dict(job.stats or {})
        stats.update(
            {
                "projection_results": results,
                "affected_assets": [str(asset.id) for asset in assets],
                "bounded": True,
                "projection_tracking": {
                    "query_lexicon_revision": next(
                        (
                            row.get("source_revision")
                            for row in plan.get("states") or []
                            if row.get("projection_type")
                            == ProjectionState.ProjectionType.QUERY_LEXICON
                        ),
                        None,
                    ),
                    "query_lexicon_status": (
                        results.get(
                            ProjectionState.ProjectionType.QUERY_LEXICON,
                            {},
                        ).get("status", "not_tracked")
                    ),
                    "semantic": "delegated_to_specialist_jobs",
                },
            }
        )
        job.stats = stats
        if failures:
            job.status = ProcessingJob.Status.FAILED
            job.progress = 100
            job.error_code = "projection_partial_failure"
            job.error_message = (
                f"投影更新失败：{', '.join(failures)}"[:4000]
            )
            job.finished_at = timezone.now()
        elif waiting:
            job.status = ProcessingJob.Status.PAUSED
            job.progress = 80
            job.error_code = "projection_waiting_for_capability"
            job.error_message = "投影专业任务正在等待执行能力。"
            job.finished_at = None
        elif delegated:
            job.status = ProcessingJob.Status.RUNNING
            job.progress = 80
            job.finished_at = None
        else:
            job.status = ProcessingJob.Status.SUCCEEDED
            job.progress = 100
            job.error_code = ""
            job.error_message = ""
            job.finished_at = timezone.now()
        job.save()
        return job
    except Exception as exc:
        for tracked_state in (locals().get("tracked") or {}).values():
            if tracked_state.get("status") != "claimed":
                continue
            try:
                _fail_tracked(
                    tracked_state,
                    code="projection_coordinator_failed",
                    message=str(exc),
                )
            except ValueError:
                # Completed, superseded or expired tokens cannot be released
                # by this attempt. Expired rows are reclaimed by the bounded
                # projection reconciler before it schedules a retry.
                pass
        job.status = ProcessingJob.Status.FAILED
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "error_code",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        raise


def _semantic_job_verified(job: SemanticIndexJob) -> bool:
    return (
        job.status == SemanticIndexJob.Status.COMPLETED
        and (job.stats or {}).get("backend") in VERIFIED_SEMANTIC_BACKENDS
    )


def _recover_semantic_projection_lease(
    state: ProjectionState,
    parent: ProcessingJob,
    captured_revision: int,
) -> tuple[str, str | None]:
    """Return a valid lease for a terminal specialist result when possible.

    Semantic jobs may outlive the coordinator's original lease. Completion is
    never allowed with that expired token. The reconciliation path instead
    reclaims the same stale projection revision and then records the verified
    specialist result under a fresh lease.
    """

    state.refresh_from_db()
    if state.projected_revision >= captured_revision:
        return "current", None
    if (
        state.source_revision != captured_revision
        or state.task_owner_key != str(parent.id)
    ):
        return "superseded", None
    if (
        state.status == ProjectionState.Status.PROJECTING
        and state.lease_token
        and state.lease_expires_at
        and state.lease_expires_at > timezone.now()
    ):
        return "claimed", str(state.lease_token)
    lease = claim_projection(
        object_type=state.object_type,
        object_id=state.object_id,
        projection_type=state.projection_type,
        owner_type="ProcessingJob",
        owner_key=str(parent.id),
        lease_seconds=7200,
    )
    if lease is not None:
        return "claimed", str(lease.lease_token)
    state.refresh_from_db()
    if state.projected_revision >= captured_revision:
        return "current", None
    return "delegated", None


def reconcile_delegated_projection_job(
    parent_job_id,
) -> ProcessingJob | None:
    """Finish a parent only after every semantic write is terminal."""

    parent = ProcessingJob.objects.filter(
        pk=parent_job_id,
        job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
    ).first()
    if parent is None:
        return None
    stats = dict(parent.stats or {})
    plan = dict(stats.get("projection_plan") or {})
    semantic_ids = plan.get("semantic_job_ids") or []
    if not semantic_ids:
        return parent
    jobs = list(
        SemanticIndexJob.objects.filter(pk__in=semantic_ids).order_by("id")
    )
    if (
        len(jobs) != len(set(semantic_ids))
        or any(row.status not in SEMANTIC_TERMINAL for row in jobs)
    ):
        return parent

    state = ProjectionState.objects.filter(
        pk=plan.get("semantic_state_id")
    ).first()
    captured_revision = int(plan.get("semantic_source_revision") or 0)
    semantic_result = {"jobs": [str(row.id) for row in jobs]}
    if (
        state is not None
        and state.source_revision == captured_revision
        and state.task_owner_key == str(parent.id)
    ):
        lease_status, lease_token = _recover_semantic_projection_lease(
            state,
            parent,
            captured_revision,
        )
        if all(_semantic_job_verified(row) for row in jobs):
            if lease_status == "claimed":
                complete_projection(
                    state.id,
                    lease_token,
                    projected_revision=captured_revision,
                )
                semantic_result["status"] = "current"
            else:
                semantic_result["status"] = lease_status
        elif any(row.status == SemanticIndexJob.Status.PAUSED for row in jobs):
            if lease_status == "claimed":
                mark_projection_waiting(
                    state.id,
                    lease_token,
                    reason="delegated semantic indexing is paused",
                    owner_type="ProcessingJob",
                    owner_key=str(parent.id),
                )
                semantic_result["status"] = "waiting"
            elif state.status == ProjectionState.Status.WAITING_FOR_CAPABILITY:
                semantic_result["status"] = "waiting"
            else:
                semantic_result["status"] = lease_status
        else:
            if lease_status == "claimed":
                mark_projection_failed(
                    state.id,
                    lease_token,
                    error_code="semantic_projection_failed",
                    error_message=(
                        "A delegated SemanticIndexJob did not complete a "
                        "verified Meilisearch write."
                    ),
                )
                semantic_result["status"] = "failed"
            elif state.status == ProjectionState.Status.FAILED:
                semantic_result["status"] = "failed"
            else:
                semantic_result["status"] = lease_status
    else:
        semantic_result["status"] = "superseded"

    with transaction.atomic():
        parent = ProcessingJob.objects.select_for_update().get(pk=parent.pk)
        stats = dict(parent.stats or {})
        results = dict(stats.get("projection_results") or {})
        results[ProjectionState.ProjectionType.SEMANTIC] = semantic_result
        stats["projection_results"] = results
        parent.stats = stats
        failed = [
            name
            for name, value in results.items()
            if value.get("status") == "failed"
        ]
        waiting = [
            name
            for name, value in results.items()
            if value.get("status") == "waiting"
        ]
        delegated = [
            name
            for name, value in results.items()
            if value.get("status") in {"delegated", "projecting"}
        ]
        if failed:
            parent.status = ProcessingJob.Status.FAILED
            parent.error_code = "projection_partial_failure"
            parent.error_message = (
                f"投影更新失败：{', '.join(failed)}"[:4000]
            )
        elif waiting:
            parent.status = ProcessingJob.Status.PAUSED
            parent.error_code = "projection_waiting_for_capability"
            parent.error_message = "投影专业任务正在等待执行能力。"
        elif delegated:
            parent.status = ProcessingJob.Status.RUNNING
            parent.error_code = ""
            parent.error_message = ""
        else:
            parent.status = ProcessingJob.Status.SUCCEEDED
            parent.error_code = ""
            parent.error_message = ""
        parent.progress = (
            80
            if parent.status
            in {ProcessingJob.Status.PAUSED, ProcessingJob.Status.RUNNING}
            else 100
        )
        parent.finished_at = (
            timezone.now()
            if parent.status
            not in {ProcessingJob.Status.PAUSED, ProcessingJob.Status.RUNNING}
            else None
        )
        parent.save()
    if (
        parent.status == ProcessingJob.Status.FAILED
        and parent.attempt < parent.max_attempts
    ):
        _schedule_job_capability(parent)
    return parent


def finalize_semantic_projection_bindings(
    semantic_job: SemanticIndexJob,
) -> int:
    """Minimal specialist completion hook; unrelated jobs are no-ops."""

    parent_ids = [
        str(value)
        for value in (semantic_job.stats or {}).get(
            "projection_refresh_parent_ids"
        )
        or []
    ]
    for parent_id in parent_ids:
        reconcile_delegated_projection_job(parent_id)
    return len(parent_ids)


def dispatch_ready_projection_demands(*, limit: int = 20) -> dict[str, int]:
    from catalog.models import CapabilityDemand

    demands = list(
        CapabilityDemand.objects.filter(
            state=CapabilityDemand.State.READY,
            owner_type="ProcessingJob",
            payload__task_kind="projection_refresh",
        )
        .filter(Q(not_before__isnull=True) | Q(not_before__lte=timezone.now()))
        .order_by("-priority", "created_at")[
            : max(1, min(int(limit), 100))
        ]
    )
    dispatched = 0
    for demand in demands:
        dispatched += int(dispatch_projection_demand(demand))
    return {"candidates": len(demands), "dispatched": dispatched}


def reconcile_projection_runtime(*, limit: int = 50) -> dict[str, int]:
    """Recover missed wakeups, capabilities and delegated completions."""

    from common.task_runtime import reconcile_capability_runtime

    capability = reconcile_capability_runtime()
    projection_leases_reclaimed = reclaim_expired_projection_leases(
        limit=limit,
    )
    delegated = 0
    for job in ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
        status=ProcessingJob.Status.RUNNING,
    ).order_by("updated_at")[: max(1, min(int(limit), 100))]:
        before = job.status
        current = reconcile_delegated_projection_job(job.id)
        delegated += int(current is not None and current.status != before)

    scheduled = 0
    groups = list(
        ProjectionState.objects.filter(
            status__in=[
                ProjectionState.Status.STALE,
                ProjectionState.Status.WAITING_FOR_CAPABILITY,
                ProjectionState.Status.FAILED,
            ],
            source_revision__gt=F("projected_revision"),
        )
        .values_list("object_type", "object_id")
        .distinct()[: max(1, min(int(limit), 100))]
    )
    for object_type, object_id in groups:
        event = (
            DomainChangeEvent.objects.filter(
                object_type=object_type,
                object_id=object_id,
                processed_at__isnull=False,
            )
            .order_by("-canonical_revision")
            .first()
        )
        if event is None or object_type not in TARGET_MODELS:
            continue
        job = schedule_domain_change_projections(event.id)
        if (
            job.status
            in {ProcessingJob.Status.FAILED, ProcessingJob.Status.PAUSED}
            and job.attempt < job.max_attempts
        ):
            _schedule_job_capability(job)
        scheduled += 1
    dispatch = dispatch_ready_projection_demands(limit=limit)
    return {
        "executors_offline": capability["executors_offline"],
        "demands_reclaimed": (
            capability["demands_ready"] + capability["demands_waiting"]
        ),
        "projection_leases_reclaimed": projection_leases_reclaimed,
        "delegated_reconciled": delegated,
        "objects_scheduled": scheduled,
        "demands_dispatched": dispatch["dispatched"],
    }
