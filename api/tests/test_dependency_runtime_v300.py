from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import (
    CanonicalObjectRevision,
    CapabilityDemand,
    CapabilityExecutor,
    DomainChangeEvent,
    ProjectionState,
    Work,
)
from catalog.services.dependency_engine import (
    ALL_PROJECTIONS,
    claim_domain_change,
    claim_projection,
    complete_projection,
    record_canonical_change,
    release_domain_change,
    renew_domain_change_lease,
    resolve_domain_change,
)
from common.task_runtime import (
    claim_demand,
    complete_demand,
    queue_or_wait,
    reconcile_capability_runtime,
    register_executor_heartbeat,
    renew_demand_lease,
)
from ingestion.models import ProcessingJob


pytestmark = pytest.mark.django_db


def test_canonical_change_is_idempotent_and_marks_bounded_projections_stale():
    work_id = uuid4()
    event = record_canonical_change(
        object_type="catalog.Work",
        object_id=work_id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        changed_fields=["title", "title"],
        idempotency_key="work-edit:one",
    )
    repeated = record_canonical_change(
        object_type="work",
        object_id=work_id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        changed_fields=["ignored-on-retry"],
        idempotency_key="work-edit:one",
    )

    assert repeated.pk == event.pk
    assert event.canonical_revision == 1
    assert event.changed_fields == ["title"]
    assert event.processed_at is not None
    assert CanonicalObjectRevision.objects.get(
        object_type="work", object_id=work_id
    ).current_revision == 1
    states = ProjectionState.objects.filter(object_type="work", object_id=work_id)
    assert states.count() == len(ALL_PROJECTIONS)
    assert set(states.values_list("projection_type", flat=True)) == set(ALL_PROJECTIONS)
    assert set(states.values_list("status", flat=True)) == {ProjectionState.Status.STALE}


def test_new_canonical_revision_invalidates_an_older_projection_lease():
    work_id = uuid4()
    record_canonical_change(
        object_type="work",
        object_id=work_id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="work-edit:first",
    )
    lease = claim_projection(
        object_type="work",
        object_id=work_id,
        projection_type=ProjectionState.ProjectionType.PUBLIC,
        owner_type="ProcessingJob",
        owner_key="job-one",
    )
    assert lease is not None

    record_canonical_change(
        object_type="work",
        object_id=work_id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="work-edit:second",
    )
    state = ProjectionState.objects.get(pk=lease.state_id)
    assert state.source_revision == 2
    assert state.status == ProjectionState.Status.STALE
    assert state.lease_token is None
    with pytest.raises(ValueError, match="no longer active"):
        complete_projection(
            state.pk,
            lease.lease_token,
            projected_revision=lease.source_revision,
        )


def test_unresolved_domain_change_can_be_leased_renewed_and_resolved():
    event = record_canonical_change(
        object_type="topic",
        object_id=uuid4(),
        change_kind=DomainChangeEvent.ChangeKind.PUBLISH,
        idempotency_key="topic-publish:one",
        resolve=False,
    )
    lease = claim_domain_change(lease_seconds=30)
    assert lease is not None
    assert lease.event_id == event.id
    renewed = renew_domain_change_lease(event.id, lease.lease_token, lease_seconds=60)
    assert renewed.lease_expires_at > lease.lease_expires_at
    released = release_domain_change(
        event.id,
        lease.lease_token,
        error_code="temporary_failure",
        error_message="retry safely",
        retry_after_seconds=0,
    )
    assert released.processed_at is None
    assert released.lease_token is None
    reclaimed = claim_domain_change(lease_seconds=30)
    assert reclaimed is not None
    assert reclaimed.event_id == event.id
    assert reclaimed.lease_token != lease.lease_token

    states = resolve_domain_change(event.id, lease_token=reclaimed.lease_token)
    event.refresh_from_db()
    assert event.processed_at is not None
    assert states
    assert all(state.status == ProjectionState.Status.STALE for state in states)


def test_existing_projection_refresh_tracks_query_revision_without_replacing_outbox(monkeypatch):
    from catalog.services.projection_refresh import (
        queue_projection_refresh,
        run_projection_refresh_job,
    )

    work = Work.objects.create(title="依赖投影测试", language="zh-CN")
    record_canonical_change(
        object_type="work",
        object_id=work.id,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        idempotency_key="projection-refresh:source-one",
    )
    monkeypatch.setattr(
        "catalog.services.projection_refresh._refresh_target",
        lambda target_type, target, actor=None: {
            "target_type": target_type,
            "target_id": str(target.pk),
            "query_lexicon": {"claimed": 0, "failed": 0},
            "semantic_jobs": [],
            "candidate_jobs": [],
            "bounded": True,
        },
    )
    job = queue_projection_refresh(target_type="work", target_id=str(work.id))
    query_state = ProjectionState.objects.get(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.QUERY_LEXICON,
    )
    assert query_state.task_owner_type == "ProcessingJob"
    assert query_state.task_owner_key == str(job.id)

    completed = run_projection_refresh_job(str(job.id), task_id=job.task_id)
    query_state.refresh_from_db()
    assert completed.status == "succeeded"
    assert query_state.status == ProjectionState.Status.CURRENT
    assert query_state.projected_revision == query_state.source_revision == 1
    assert completed.stats["projection_tracking"]["semantic"] == "delegated_to_specialist_jobs"


def test_missing_capability_waits_without_broker_dispatch_then_heartbeat_promotes(
    django_capture_on_commit_callbacks,
):
    dispatched = []
    result = queue_or_wait(
        owner_type="ResearchRun",
        owner_key=str(uuid4()),
        capability="llm_large",
        idempotency_key="research:llm-large:one",
        payload={"task": "claim_stance"},
        dispatch=lambda demand: dispatched.append(demand.pk),
    )

    assert result.executor_available is False
    assert result.dispatched is False
    assert result.demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert result.demand.publication_blocking is False
    assert dispatched == []

    register_executor_heartbeat(
        executor_id="laptop-4070",
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        capabilities=["llm_large", "rerank"],
        concurrency=1,
    )
    with django_capture_on_commit_callbacks(execute=True):
        result = queue_or_wait(
            owner_type="ResearchRun",
            owner_key=result.demand.owner_key,
            capability="llm_large",
            idempotency_key="research:llm-large:one",
            dispatch=lambda demand: dispatched.append(demand.pk),
        )
    assert result.executor_available is True
    assert result.dispatched is True
    assert result.demand.state == CapabilityDemand.State.READY
    assert dispatched == [result.demand.pk]


def test_capability_claim_renew_and_complete_updates_executor_load():
    executor = register_executor_heartbeat(
        executor_id="nas-core",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["cpu_light", "projection"],
        concurrency=2,
    )
    scheduled = queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(uuid4()),
        capability="projection",
        idempotency_key="projection:one",
        priority=10,
    )
    assert scheduled.demand.state == CapabilityDemand.State.READY

    lease = claim_demand(executor_id=executor.executor_id, lease_seconds=30)
    assert lease is not None
    executor.refresh_from_db()
    assert executor.current_load == 1
    renewed = renew_demand_lease(
        lease.demand_id,
        lease.lease_token,
        executor_id=executor.executor_id,
        lease_seconds=60,
    )
    assert renewed.lease_expires_at > lease.lease_expires_at

    completed = complete_demand(
        lease.demand_id,
        lease.lease_token,
        executor_id=executor.executor_id,
    )
    executor.refresh_from_db()
    assert completed.state == CapabilityDemand.State.COMPLETED
    assert completed.lease_token is None
    assert executor.current_load == 0


def test_expired_lease_can_be_reclaimed_without_inflating_executor_load():
    executor = register_executor_heartbeat(
        executor_id="nas-reclaim",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["projection"],
        concurrency=1,
    )
    queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(uuid4()),
        capability="projection",
        idempotency_key="projection:reclaim",
    )
    first = claim_demand(executor_id=executor.executor_id)
    assert first is not None
    CapabilityDemand.objects.filter(pk=first.demand_id).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )

    second = claim_demand(executor_id=executor.executor_id)
    executor.refresh_from_db()
    assert second is not None
    assert second.demand_id == first.demand_id
    assert second.lease_token != first.lease_token
    assert executor.current_load == 1


def test_busy_executor_is_present_even_when_it_cannot_claim_another_task():
    executor = register_executor_heartbeat(
        executor_id="nas-busy",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["projection"],
        concurrency=1,
    )
    queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(uuid4()),
        capability="projection",
        idempotency_key="projection:busy:first",
    )
    assert claim_demand(executor_id=executor.executor_id) is not None

    second = queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(uuid4()),
        capability="projection",
        idempotency_key="projection:busy:second",
    )
    assert second.executor_available is True
    assert second.demand.state == CapabilityDemand.State.READY
    assert claim_demand(executor_id=executor.executor_id) is None


def test_offline_remote_executor_returns_unfinished_work_to_waiting_state():
    executor = register_executor_heartbeat(
        executor_id="temporary-4070",
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        capabilities=["llm_large"],
    )
    demand = queue_or_wait(
        owner_type="ResearchRun",
        owner_key=str(uuid4()),
        capability="llm_large",
        idempotency_key="research:offline:one",
    ).demand
    lease = claim_demand(executor_id=executor.executor_id)
    assert lease is not None
    expired_at = timezone.now() - timedelta(seconds=1)
    CapabilityExecutor.objects.filter(pk=executor.pk).update(heartbeat_expires_at=expired_at)

    result = reconcile_capability_runtime(at=timezone.now())
    demand.refresh_from_db()
    executor.refresh_from_db()
    assert result == {
        "executors_offline": 1,
        "demands_ready": 0,
        "demands_waiting": 1,
    }
    assert executor.status == CapabilityExecutor.Status.OFFLINE
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert demand.claimed_by is None
    assert demand.lease_token is None


def test_reconciliation_cancels_waiting_demand_when_specialist_owner_is_terminal():
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
        status=ProcessingJob.Status.CANCELED,
    )
    demand = queue_or_wait(
        owner_type="ProcessingJob",
        owner_key=str(job.id),
        capability="projection",
        idempotency_key=f"projection:stale-owner:{job.id}",
        payload={
            "task_kind": "projection_refresh",
            "processing_job_id": str(job.id),
        },
        publication_blocking=False,
    ).demand
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY

    reconcile_capability_runtime()

    demand.refresh_from_db()
    assert demand.state == CapabilityDemand.State.CANCELED
    assert demand.last_error_code == "source_superseded"
    assert "terminal" in demand.last_error_message
