from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import (
    Asset,
    CapabilityDemand,
    CapabilityExecutor,
    DomainChangeEvent,
    DocumentRevision,
    Edition,
    ProjectionState,
    PublicationState,
    ReadingPath,
    SemanticIndexJob,
    Work,
)
from catalog.services.dependency_engine import record_canonical_change
from catalog.services.processing_center_diagnostics import (
    processing_center_diagnostics,
)
from catalog.services.projection_refresh import (
    _complete_tracked,
    _schedule_job_capability,
    finalize_semantic_projection_bindings,
    queue_projection_refresh,
    run_projection_refresh_job,
)
from common.task_runtime import (
    claim_specific_demand,
    complete_demand,
    queue_or_wait,
    reconcile_capability_runtime,
    register_executor_heartbeat,
    release_demand,
)
from ingestion.models import ProcessingJob


pytestmark = pytest.mark.django_db


def _work_with_asset(title: str = "Projection propagation"):
    work = Work.objects.create(
        document_type="book",
        title=title,
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"projection-{sha256(title.encode()).hexdigest()[:12]}",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{work.id}.pdf",
        sha256=sha256(str(work.id).encode()).hexdigest(),
        byte_size=1024,
        page_count=0,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    return work, edition, asset


def test_canonical_change_schedules_one_waiting_projection_job_without_executor(
    django_capture_on_commit_callbacks,
):
    path = ReadingPath.objects.create(
        title="投影等待测试",
        slug="projection-waiting-test",
    )
    with django_capture_on_commit_callbacks(execute=True):
        event = record_canonical_change(
            object_type="reading_path",
            object_id=path.id,
            change_kind=DomainChangeEvent.ChangeKind.UPDATE,
            idempotency_key="reading-path-projection:one",
        )

    job = ProcessingJob.objects.get(
        idempotency_key=f"projection-refresh:reading_path:{path.id}:r1"
    )
    demand = CapabilityDemand.objects.get(owner_key=str(job.id))
    states = ProjectionState.objects.filter(
        object_type="reading_path",
        object_id=path.id,
    )
    assert event.canonical_revision == 1
    assert job.status == ProcessingJob.Status.PENDING
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert demand.payload["task_kind"] == "projection_refresh"
    assert set(states.values_list("status", flat=True)) == {
        ProjectionState.Status.WAITING_FOR_CAPABILITY
    }

    record_canonical_change(
        object_type="reading_path",
        object_id=path.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="reading-path-projection:one",
    )
    assert ProcessingJob.objects.filter(idempotency_key=job.idempotency_key).count() == 1
    assert CapabilityDemand.objects.filter(owner_key=str(job.id)).count() == 1


def test_unregistered_projection_target_stays_failed_and_visible_in_processing_center(
    django_capture_on_commit_callbacks,
):
    object_id = uuid4()
    with django_capture_on_commit_callbacks(execute=True):
        event = record_canonical_change(
            object_type="unregistered_projection_target",
            object_id=object_id,
            change_kind=DomainChangeEvent.ChangeKind.UPDATE,
            idempotency_key="unsupported-projection-target:one",
        )

    state = ProjectionState.objects.get(
        object_type="unregistered_projection_target",
        object_id=object_id,
        projection_type=ProjectionState.ProjectionType.PUBLIC,
    )
    event.refresh_from_db()
    assert state.status == ProjectionState.Status.FAILED
    assert state.projected_revision == 0
    assert state.last_error_code == "projection_schedule_failed"
    assert event.last_error_code == "projection_schedule_failed"
    assert ProcessingJob.objects.filter(
        stats__target_type="unregistered_projection_target"
    ).exists() is False

    snapshot = processing_center_diagnostics()
    projection_items = next(
        section["items"]
        for section in snapshot["sections"]
        if section["key"] == "projections"
    )
    diagnostic = next(
        row
        for row in projection_items
        if row["details"]["object_id"] == str(object_id)
    )
    assert diagnostic["status"] == ProjectionState.Status.FAILED
    assert diagnostic["details"]["last_error_code"] == "projection_schedule_failed"


def test_executor_matching_uses_task_kind_and_declared_profile():
    executor = register_executor_heartbeat(
        executor_id="profile-aware",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["llm_small"],
        metadata={
            "task_kinds": ["claim_extraction"],
            "task_profiles": {"claim_extraction": ["claims-local-v1"]},
        },
    )
    wrong_kind = queue_or_wait(
        owner_type="ResearchRun",
        owner_key=str(uuid4()),
        capability="llm_small",
        idempotency_key="matching:wrong-kind",
        payload={"task_kind": "claim_stance"},
    ).demand
    wrong_profile = queue_or_wait(
        owner_type="evidence_span",
        owner_key=str(uuid4()),
        capability="llm_small",
        idempotency_key="matching:wrong-profile",
        payload={
            "task_kind": "claim_extraction",
            "profile_key": "claims-cloud-v2",
        },
    ).demand
    matching = queue_or_wait(
        owner_type="evidence_span",
        owner_key=str(uuid4()),
        capability="llm_small",
        idempotency_key="matching:exact",
        payload={
            "task_kind": "claim_extraction",
            "profile_key": "claims-local-v1",
        },
    ).demand

    assert wrong_kind.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert wrong_profile.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert matching.state == CapabilityDemand.State.READY
    assert claim_specific_demand(
        wrong_kind.id,
        executor_id=executor.executor_id,
    ) is None
    assert claim_specific_demand(
        wrong_profile.id,
        executor_id=executor.executor_id,
    ) is None
    assert claim_specific_demand(
        matching.id,
        executor_id=executor.executor_id,
    ) is not None

    CapabilityDemand.objects.filter(pk=wrong_kind.pk).update(
        state=CapabilityDemand.State.READY
    )
    reconciled = reconcile_capability_runtime()
    wrong_kind.refresh_from_db()
    assert wrong_kind.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert reconciled["demands_waiting"] == 1


def test_expired_capability_lease_cannot_complete_or_release():
    executor = register_executor_heartbeat(
        executor_id="lease-expiry",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["projection"],
        concurrency=2,
    )
    demands = []
    for suffix in ("complete", "release"):
        demand = queue_or_wait(
            owner_type="ProcessingJob",
            owner_key=str(uuid4()),
            capability="projection",
            idempotency_key=f"expired:{suffix}",
            payload={"task_kind": "projection_refresh"},
        ).demand
        lease = claim_specific_demand(
            demand.id,
            executor_id=executor.executor_id,
        )
        CapabilityDemand.objects.filter(pk=demand.id).update(
            lease_expires_at=timezone.now() - timedelta(seconds=1)
        )
        demands.append((demand, lease))

    with pytest.raises(ValueError, match="expired"):
        complete_demand(
            demands[0][0].id,
            demands[0][1].lease_token,
            executor_id=executor.executor_id,
        )
    with pytest.raises(ValueError, match="expired"):
        release_demand(
            demands[1][0].id,
            demands[1][1].lease_token,
            executor_id=executor.executor_id,
            error_code="temporary",
            error_message="retry",
        )
    assert CapabilityDemand.objects.filter(
        pk__in=[row[0].id for row in demands],
        state=CapabilityDemand.State.CLAIMED,
    ).count() == 2


def test_direct_postgres_projections_become_current_after_real_coordinator_run(
    django_capture_on_commit_callbacks,
    monkeypatch,
):
    register_executor_heartbeat(
        executor_id="nas-projection",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["projection"],
        metadata={"task_kinds": ["projection_refresh"]},
    )
    monkeypatch.setattr(
        "catalog.tasks.execute_projection_demand.apply_async",
        lambda *args, **kwargs: None,
    )
    path = ReadingPath.objects.create(
        title="直读投影测试",
        slug="direct-projection-test",
    )
    with django_capture_on_commit_callbacks(execute=True):
        record_canonical_change(
            object_type="reading_path",
            object_id=path.id,
            change_kind=DomainChangeEvent.ChangeKind.UPDATE,
            idempotency_key="reading-path-projection:current",
        )
    job = ProcessingJob.objects.get(
        idempotency_key=f"projection-refresh:reading_path:{path.id}:r1"
    )
    completed = run_projection_refresh_job(str(job.id), task_id=job.task_id)
    states = ProjectionState.objects.filter(
        object_type="reading_path",
        object_id=path.id,
    )

    assert completed.status == ProcessingJob.Status.SUCCEEDED
    assert states.count() == 3
    assert set(states.values_list("status", flat=True)) == {
        ProjectionState.Status.CURRENT
    }
    assert all(
        source == projected == 1
        for source, projected in states.values_list(
            "source_revision",
            "projected_revision",
        )
    )


def test_fulltext_fallback_stays_failed_then_bounded_retry_can_finish(
    monkeypatch,
):
    work, _edition, _asset = _work_with_asset()
    record_canonical_change(
        object_type="work",
        object_id=work.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="work-projection:retry",
    )
    job = queue_projection_refresh(target_type="work", target_id=str(work.id))

    def semantic_current(_job, _assets, tracked):
        _complete_tracked(tracked)
        return {"status": "current", "jobs": []}

    monkeypatch.setattr(
        "catalog.services.projection_refresh._semantic_projection",
        semantic_current,
    )
    monkeypatch.setattr(
        "ingestion.services.indexing.index_asset",
        lambda *args, **kwargs: {
            "backend": "database-fallback",
            "warning": "Meilisearch unavailable",
        },
    )
    failed = run_projection_refresh_job(str(job.id), task_id=job.task_id)
    fulltext = ProjectionState.objects.get(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.FULLTEXT,
    )
    assert failed.status == ProcessingJob.Status.FAILED
    assert fulltext.status == ProjectionState.Status.FAILED
    assert fulltext.projected_revision == 0

    register_executor_heartbeat(
        executor_id="nas-projection-retry",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["projection"],
        metadata={"task_kinds": ["projection_refresh"]},
    )
    monkeypatch.setattr(
        "catalog.services.projection_refresh.dispatch_projection_demand",
        lambda demand: True,
    )
    scheduled = _schedule_job_capability(failed)
    assert scheduled.demand.idempotency_key.endswith(":2")
    assert scheduled.demand.state == CapabilityDemand.State.READY

    monkeypatch.setattr(
        "ingestion.services.indexing.index_asset",
        lambda *args, **kwargs: {
            "backend": "meilisearch",
            "documents": 0,
        },
    )
    retried = run_projection_refresh_job(str(job.id), task_id="")
    fulltext.refresh_from_db()
    assert retried.status == ProcessingJob.Status.SUCCEEDED
    assert fulltext.status == ProjectionState.Status.CURRENT
    assert fulltext.projected_revision == fulltext.source_revision == 1


def test_document_revision_claim_index_reuses_coordinator_lease(
    monkeypatch,
):
    _work, _edition, asset = _work_with_asset("Document revision projection")
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        source_checksum=asset.sha256,
        text_checksum=sha256(b"revision-text").hexdigest(),
        is_active=True,
    )
    record_canonical_change(
        object_type="document_revision",
        object_id=revision.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="document-revision-projection:one",
    )
    job = queue_projection_refresh(
        target_type="document_revision",
        target_id=str(revision.id),
    )

    def semantic_current(_job, _assets, tracked):
        _complete_tracked(tracked)
        return {"status": "current", "jobs": []}

    claim_calls = []

    def claim_index(document_revision, *, track_projection=True):
        claim_calls.append((document_revision.id, track_projection))
        return {"status": "completed", "backend": "meilisearch"}

    monkeypatch.setattr(
        "catalog.services.projection_refresh._semantic_projection",
        semantic_current,
    )
    monkeypatch.setattr(
        "ingestion.services.indexing.index_asset",
        lambda *args, **kwargs: {"backend": "no-passages", "documents": 0},
    )
    monkeypatch.setattr(
        "catalog.services.claims.indexing.index_document_revision_claims",
        claim_index,
    )

    completed = run_projection_refresh_job(str(job.id), task_id=job.task_id)
    states = ProjectionState.objects.filter(
        object_type="document_revision",
        object_id=revision.id,
    )
    assert completed.status == ProcessingJob.Status.SUCCEEDED
    assert claim_calls == [(revision.id, False)]
    assert states.count() == 4
    assert set(states.values_list("status", flat=True)) == {
        ProjectionState.Status.CURRENT
    }


def test_coordinator_exception_releases_all_active_projection_leases(
    monkeypatch,
):
    work = Work.objects.create(
        document_type="book",
        title="Projection exception",
        language="zh-CN",
    )
    record_canonical_change(
        object_type="work",
        object_id=work.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="projection-coordinator-exception:one",
    )
    job = queue_projection_refresh(target_type="work", target_id=str(work.id))
    monkeypatch.setattr(
        "catalog.services.projection_refresh._claim_projection",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("index failed")),
    )

    with pytest.raises(RuntimeError, match="index failed"):
        run_projection_refresh_job(str(job.id), task_id=job.task_id)

    job.refresh_from_db()
    states = ProjectionState.objects.filter(object_type="work", object_id=work.id)
    assert job.status == ProcessingJob.Status.FAILED
    assert states.count() == len(ProjectionState.ProjectionType.values)
    assert states.filter(status=ProjectionState.Status.PROJECTING).exists() is False
    assert set(states.values_list("status", flat=True)) == {
        ProjectionState.Status.FAILED
    }
    assert set(states.values_list("last_error_code", flat=True)) == {
        "projection_coordinator_failed"
    }


def test_semantic_specialist_hook_reclaims_expired_projection_lease_for_verified_backend():
    work = Work.objects.create(
        document_type="book",
        title="Semantic hook",
        language="zh-CN",
    )
    record_canonical_change(
        object_type="work",
        object_id=work.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="semantic-hook:source",
    )
    parent = queue_projection_refresh(target_type="work", target_id=str(work.id))
    semantic_state = ProjectionState.objects.get(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.SEMANTIC,
    )
    lease_token = uuid4()
    ProjectionState.objects.filter(pk=semantic_state.pk).update(
        status=ProjectionState.Status.PROJECTING,
        lease_token=lease_token,
        lease_expires_at=timezone.now() - timedelta(seconds=1),
        task_owner_type="ProcessingJob",
        task_owner_key=str(parent.id),
    )
    specialist = SemanticIndexJob.objects.create(
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.COMPLETED,
        stats={
            "backend": "meilisearch",
            "projection_refresh_parent_ids": [str(parent.id)],
        },
    )
    parent.stats = {
        **parent.stats,
        "projection_plan": {
            **parent.stats["projection_plan"],
            "semantic_job_ids": [str(specialist.id)],
            "semantic_state_id": str(semantic_state.id),
            "semantic_source_revision": 1,
        },
        "projection_results": {
            projection_type: {"status": "current"}
            for projection_type in ProjectionState.ProjectionType.values
            if projection_type != ProjectionState.ProjectionType.SEMANTIC
        }
        | {
            ProjectionState.ProjectionType.SEMANTIC: {
                "status": "delegated"
            }
        },
    }
    parent.status = ProcessingJob.Status.RUNNING
    parent.attempt = 1
    parent.save()

    assert finalize_semantic_projection_bindings(specialist) == 1
    semantic_state.refresh_from_db()
    parent.refresh_from_db()
    assert semantic_state.status == ProjectionState.Status.CURRENT
    assert semantic_state.projected_revision == 1
    assert parent.status == ProcessingJob.Status.SUCCEEDED
