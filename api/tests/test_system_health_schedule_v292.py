from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.conf import settings as django_settings
from django.core.cache import cache
from django.utils import timezone

from catalog.models import (
    HealthIncident,
    QueryLexiconEntry,
    QueryLexiconGeneration,
    QueryLexiconState,
    RecoveryAction,
)

from catalog.services.system_health import (
    HEALTH_CHECKS,
    HEALTH_SCHEDULE_LEASE_KEY,
    HealthProbe,
    ProbeResult,
    _public_catalog_probe,
    _query_lexicon_probe,
    execute_recovery,
    recover_stale_recovery_actions,
    request_recovery,
    run_due_health_probes,
    run_health_probe,
)
from catalog.tasks import execute_health_recovery, run_scheduled_health_probes
from ingestion.models import AuditEvent


pytestmark = pytest.mark.django_db


def _probe(index: int) -> HealthProbe:
    return HealthProbe(
        key=f"test.schedule.{index}",
        capability="research",
        label=f"调度测试 {index}",
        interval_seconds=60,
        runner=lambda: ProbeResult(True, True, True, True, "ok"),
    )


def test_scheduled_health_probes_skip_when_global_lease_is_held():
    cache.set(HEALTH_SCHEDULE_LEASE_KEY, "another-beat", timeout=60)
    try:
        with patch("catalog.services.system_health.run_health_probe") as run_probe:
            result = run_due_health_probes()
    finally:
        cache.delete(HEALTH_SCHEDULE_LEASE_KEY)

    assert result == {
        "due": 0,
        "executed": 0,
        "runs": [],
        "skipped": "lease_held",
    }
    run_probe.assert_not_called()


def test_scheduled_health_probes_respect_batch_limit_and_release_owned_lease():
    probes = tuple(_probe(index) for index in range(3))

    def completed(probe_key: str):
        return SimpleNamespace(id=uuid4(), probe_key=probe_key, status="healthy")

    cache.delete(HEALTH_SCHEDULE_LEASE_KEY)
    with (
        patch.object(HEALTH_CHECKS, "all", return_value=probes),
        patch("catalog.services.system_health.run_health_probe", side_effect=completed) as run_probe,
    ):
        result = run_due_health_probes(limit=2)

    assert result["due"] == 3
    assert result["executed"] == 2
    assert [row["probe_key"] for row in result["runs"]] == [
        "test.schedule.0",
        "test.schedule.1",
    ]
    assert run_probe.call_count == 2
    assert cache.get(HEALTH_SCHEDULE_LEASE_KEY) is None


def test_health_probe_serializes_datetime_and_uuid_details_for_postgresql_json():
    observed_at = timezone.now()
    source_id = uuid4()
    probe_key = "test.schedule.json-details"
    probe = HealthProbe(
        key=probe_key,
        capability="research",
        label="JSON 详情测试",
        interval_seconds=60,
        runner=lambda: ProbeResult(
            True,
            True,
            True,
            False,
            "候选尚未产出",
            {"observed_at": observed_at, "source_id": source_id},
            "research_not_productive",
        ),
    )
    if not any(row.key == probe_key for row in HEALTH_CHECKS.all()):
        HEALTH_CHECKS.register(probe)

    run = run_health_probe(probe_key)
    incident = HealthIncident.objects.get(probe_key=probe_key)

    assert isinstance(run.details["observed_at"], str)
    assert run.details["source_id"] == str(source_id)


@pytest.mark.parametrize(
    ("research_status", "orphan_count", "functional", "error_code", "expected_actions"),
    [
        ("completed", 0, True, "research_not_productive", ["rerun_probe"]),
        ("degraded", 0, True, "research_not_productive", ["rerun_probe"]),
        (
            "failed",
            0,
            False,
            "research_run_failed",
            ["rerun_probe", "retry_failed_research"],
        ),
        (
            "completed",
            1,
            True,
            "research_orphaned_runs",
            ["rerun_probe", "recover_stale_research"],
        ),
    ],
)
def test_research_productive_incident_exposes_only_currently_executable_actions(
    research_status,
    orphan_count,
    functional,
    error_code,
    expected_actions,
):
    result = ProbeResult(
        True,
        True,
        functional,
        False,
        "Research Pipeline 当前未证明候选产出。",
        {
            "run_id": str(uuid4()),
            "status": research_status,
            "candidate_counts": {"entities": 0},
            "orphan_nonterminal_count": orphan_count,
        },
        error_code,
    )
    probe = HealthProbe(
        key="research_productive",
        capability="research",
        label="Research Pipeline 产出",
        interval_seconds=300,
        runner=lambda: result,
        safe_recovery_actions=(
            "rerun_probe",
            "recover_stale_research",
            "retry_failed_research",
        ),
    )

    with patch.object(HEALTH_CHECKS, "get", return_value=probe):
        run_health_probe("research_productive")

    incident = HealthIncident.objects.get(
        incident_key=f"research_productive:{error_code}"
    )
    assert incident.safe_recovery_actions == expected_actions


def test_research_productive_existing_incident_replaces_stale_recovery_actions():
    run_id = str(uuid4())
    results = iter(
        [
            ProbeResult(
                True,
                True,
                False,
                False,
                "最近 ResearchRun 失败。",
                {
                    "run_id": run_id,
                    "status": "failed",
                    "candidate_counts": {},
                    "orphan_nonterminal_count": 0,
                },
                "research_not_productive",
            ),
            ProbeResult(
                True,
                True,
                True,
                False,
                "ResearchRun 已完成但没有候选。",
                {
                    "run_id": run_id,
                    "status": "completed",
                    "candidate_counts": {"entities": 0},
                    "orphan_nonterminal_count": 0,
                },
                "research_not_productive",
            ),
        ]
    )
    probe = HealthProbe(
        key="research_productive",
        capability="research",
        label="Research Pipeline 产出",
        interval_seconds=300,
        runner=lambda: next(results),
        safe_recovery_actions=(
            "rerun_probe",
            "recover_stale_research",
            "retry_failed_research",
        ),
    )

    with patch.object(HEALTH_CHECKS, "get", return_value=probe):
        run_health_probe("research_productive")
        run_health_probe("research_productive")

    incident = HealthIncident.objects.get(
        incident_key="research_productive:research_not_productive"
    )
    assert incident.occurrence_count == 2
    assert incident.safe_recovery_actions == ["rerun_probe"]


def test_builtin_catalog_and_query_lexicon_probes_use_current_model_fields():
    public_result = _public_catalog_probe()
    state = QueryLexiconState.objects.select_related("active_generation").first()
    if state is None:
        generation = QueryLexiconGeneration.objects.create(
            status=QueryLexiconGeneration.Status.ACTIVE,
            normalization_version="health-test-v1",
            source_registry_version="health-test-v1",
            entry_count=1,
        )
        QueryLexiconState.objects.create(
            active_generation=generation,
            normalization_version="health-test-v1",
            source_registry_version="health-test-v1",
        )
    else:
        generation = state.active_generation
    QueryLexiconEntry.objects.create(
        generation=generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=uuid4(),
        term="George Herbert Mead",
        normalized_term="george herbert mead",
        language="en",
        term_type=QueryLexiconEntry.TermType.CANONICAL,
        source_kind=QueryLexiconEntry.SourceKind.AUTHORITY_FIELD,
        trust_level=QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        source_ref="catalog.Person.preferred_name",
        source_fingerprint="a" * 64,
        admin_resolvable=True,
        public_active=True,
        displayable=True,
    )

    lexicon_result = _query_lexicon_probe()

    assert public_result.error_code == "public_catalog_not_fresh"
    assert lexicon_result.productive is True
    assert lexicon_result.details["admin_resolvable_entries"] == 1
    assert isinstance(django_settings.CROSSREF_MAILTO, str)


def test_health_probe_propagates_soft_timeout_without_false_incident():
    probe_key = "test.schedule.soft-timeout"
    probe = HealthProbe(
        key=probe_key,
        capability="external_research",
        label="超时测试",
        interval_seconds=60,
        runner=lambda: (_ for _ in ()).throw(SoftTimeLimitExceeded()),
    )
    if not any(row.key == probe_key for row in HEALTH_CHECKS.all()):
        HEALTH_CHECKS.register(probe)

    with pytest.raises(SoftTimeLimitExceeded):
        run_health_probe(probe_key)

    assert not HealthIncident.objects.filter(probe_key=probe_key).exists()


def test_scheduled_health_task_converts_soft_timeout_to_bounded_result():
    with patch(
        "catalog.services.system_health.run_due_health_probes",
        side_effect=SoftTimeLimitExceeded(),
    ):
        result = run_scheduled_health_probes.apply(throw=False)

    assert result.successful()
    assert result.result["skipped"] == "time_budget"


def _incident(*, probe_key: str, action: str) -> HealthIncident:
    return HealthIncident.objects.create(
        incident_key=f"{probe_key}:failure",
        capability="research",
        probe_key=probe_key,
        status=HealthIncident.Status.OPEN,
        severity=HealthIncident.Severity.WARNING,
        error_code="test_failure",
        error_category="RuntimeError",
        error_message="测试恢复失败",
        safe_recovery_actions=[action],
    )


def _request(
    incident: HealthIncident,
    admin_user,
    django_capture_on_commit_callbacks,
) -> RecoveryAction:
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as initial_dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        recovery, created = request_recovery(
            incident,
            action=incident.safe_recovery_actions[0],
            actor=admin_user,
            request_key=f"request-{incident.id}",
    )
    assert created is True
    initial_dispatch.assert_called_once_with(
        args=[str(recovery.id)],
        task_id=recovery.details["dispatch_task_id"],
    )
    return recovery


def _make_due(recovery: RecoveryAction) -> None:
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        next_retry_at=timezone.now() - timedelta(seconds=1)
    )


def test_active_recovery_is_reused_after_incident_occurrence_changes(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.concurrent-occurrence",
        action="recover_semantic_queue",
    )
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        first, first_created = request_recovery(
            incident,
            action="recover_semantic_queue",
            actor=admin_user,
        )
    assert first_created is True
    assert dispatch.call_count == 1

    stale_incident = incident
    HealthIncident.objects.filter(pk=incident.pk).update(
        occurrence_count=incident.occurrence_count + 1,
        status=HealthIncident.Status.OPEN,
    )
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as next_dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        second, second_created = request_recovery(
            stale_incident,
            action="recover_semantic_queue",
            actor=admin_user,
        )

    assert second_created is False
    assert second.id == first.id
    next_dispatch.assert_not_called()
    assert RecoveryAction.objects.filter(incident=incident).count() == 1


def test_failed_probe_during_recovery_keeps_incident_recovering_and_prevents_duplicate(
    admin_user,
    django_capture_on_commit_callbacks,
):
    probe_key = "test.recovery.probe-during-recovery"
    probe = HealthProbe(
        key=probe_key,
        capability="research",
        label="恢复期间探测",
        interval_seconds=60,
        runner=lambda: ProbeResult(
            True,
            True,
            False,
            False,
            "恢复尚未完成。",
            {},
            "failure",
        ),
        safe_recovery_actions=("recover_semantic_queue",),
    )
    with patch.object(HEALTH_CHECKS, "get", return_value=probe):
        run_health_probe(probe_key)
    incident = HealthIncident.objects.get(incident_key=f"{probe_key}:failure")
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)

    with patch.object(HEALTH_CHECKS, "get", return_value=probe):
        run_health_probe(probe_key)

    incident.refresh_from_db()
    assert incident.status == HealthIncident.Status.RECOVERING
    assert incident.occurrence_count == 2
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as duplicate_dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        repeated, created = request_recovery(
            incident,
            action="recover_semantic_queue",
            actor=admin_user,
        )
    assert created is False
    assert repeated.id == recovery.id
    duplicate_dispatch.assert_not_called()


def test_running_recovery_can_only_be_reclaimed_by_its_owner_after_stale_timeout(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.stale-owner",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)
    task_id = recovery.details["dispatch_task_id"]
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        status=RecoveryAction.Status.RUNNING,
        attempt=1,
        details={
            "dispatch_task_id": task_id,
            "claimed_at": timezone.now().isoformat(),
        },
    )

    with patch(
        "catalog.services.semantic_indexing.recover_semantic_index_jobs",
        return_value={"requeued": 1},
    ) as recover:
        wrong_owner = execute_recovery(str(recovery.id), task_id="wrong-owner")
        current_owner = execute_recovery(str(recovery.id), task_id=task_id)
        assert wrong_owner.status == RecoveryAction.Status.RUNNING
        assert current_owner.status == RecoveryAction.Status.RUNNING
        recover.assert_not_called()

        RecoveryAction.objects.filter(pk=recovery.pk).update(
            details={
                "dispatch_task_id": task_id,
                "claimed_at": (timezone.now() - timedelta(minutes=16)).isoformat(),
            },
        )
        reclaimed = execute_recovery(str(recovery.id), task_id=task_id)

    assert reclaimed.status == RecoveryAction.Status.SUCCEEDED
    assert reclaimed.attempt == 2
    assert reclaimed.details == {"requeued": 1}
    recover.assert_called_once_with()


def test_health_recovery_task_passes_actual_celery_owner(admin_user):
    incident = _incident(
        probe_key="test.recovery.task-owner",
        action="recover_semantic_queue",
    )
    recovery = RecoveryAction.objects.create(
        incident=incident,
        action="recover_semantic_queue",
        idempotency_key=f"task-owner-{uuid4()}",
        requested_by=admin_user,
        details={"dispatch_task_id": "actual-task-owner", "claimed_at": None},
    )
    with patch(
        "catalog.services.system_health.execute_recovery",
        return_value=recovery,
    ) as execute:
        result = execute_health_recovery.apply(
            args=[str(recovery.id)],
            task_id="actual-task-owner",
            throw=False,
        )

    assert result.successful()
    execute.assert_called_once_with(
        str(recovery.id),
        task_id="actual-task-owner",
    )


def test_stale_running_recovery_is_reowned_and_requeued_after_worker_loss(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.worker-loss",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)
    old_task_id = recovery.details["dispatch_task_id"]
    stale_at = timezone.now() - timedelta(minutes=30)
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        status=RecoveryAction.Status.RUNNING,
        attempt=1,
        started_at=stale_at,
        details={
            "dispatch_task_id": old_task_id,
            "claimed_at": stale_at.isoformat(),
        },
        updated_at=stale_at,
    )

    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = recover_stale_recovery_actions(
            now=timezone.now(),
            stale_after_seconds=300,
            ownership_snapshot=SimpleNamespace(
                available=True,
                task_ids=frozenset(),
                workers=("celery@test",),
                detail="complete empty inventory",
            ),
        )

    recovery.refresh_from_db()
    new_task_id = recovery.details["dispatch_task_id"]
    assert result["requeued"] == 1
    assert recovery.status == RecoveryAction.Status.QUEUED
    assert recovery.attempt == 1
    assert new_task_id and new_task_id != old_task_id
    assert recovery.details["dispatch_lifecycle"][-1]["code"] == "recovery_worker_lost"
    dispatch.assert_called_once_with(args=[str(recovery.id)], task_id=new_task_id)

    with patch(
        "catalog.services.semantic_indexing.recover_semantic_index_jobs",
        return_value={"requeued": 1},
    ) as recover:
        old_owner = execute_recovery(str(recovery.id), task_id=old_task_id)
        completed = execute_recovery(str(recovery.id), task_id=new_task_id)

    assert old_owner.status == RecoveryAction.Status.QUEUED
    assert completed.status == RecoveryAction.Status.SUCCEEDED
    assert completed.attempt == 2
    recover.assert_called_once_with()


def test_stale_queued_recovery_is_redispatched_with_same_task_id_and_executes_once(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.broker-message-not-received",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)
    task_id = recovery.details["dispatch_task_id"]
    stale_at = timezone.now() - timedelta(minutes=30)
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        status=RecoveryAction.Status.QUEUED,
        attempt=0,
        details={
            "dispatch_task_id": task_id,
            "claimed_at": None,
            "preserved": {"source": "before-broker-publish"},
        },
        updated_at=stale_at,
    )

    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = recover_stale_recovery_actions(
            now=timezone.now(),
            stale_after_seconds=300,
            ownership_snapshot=SimpleNamespace(
                available=True,
                task_ids=frozenset(),
                workers=("celery@test",),
                detail="complete empty inventory",
            ),
        )

    recovery.refresh_from_db()
    assert result["candidates"] == 1
    assert result["requeued"] == 1
    assert result["requeued_ids"] == [str(recovery.id)]
    assert recovery.status == RecoveryAction.Status.QUEUED
    assert recovery.attempt == 0
    assert recovery.details["dispatch_task_id"] == task_id
    assert recovery.details["preserved"] == {"source": "before-broker-publish"}
    assert recovery.details["dispatch_lifecycle"][-1]["code"] == "recovery_dispatch_stale"
    dispatch.assert_called_once_with(args=[str(recovery.id)], task_id=task_id)

    with patch(
        "catalog.services.semantic_indexing.recover_semantic_index_jobs",
        return_value={"requeued": 1},
    ) as recover:
        first_delivery = execute_recovery(str(recovery.id), task_id=task_id)
        duplicate_delivery = execute_recovery(str(recovery.id), task_id=task_id)

    assert first_delivery.status == RecoveryAction.Status.SUCCEEDED
    assert first_delivery.attempt == 1
    assert duplicate_delivery.status == RecoveryAction.Status.SUCCEEDED
    assert duplicate_delivery.attempt == 1
    recover.assert_called_once_with()


def test_due_failed_recovery_recovers_lost_or_early_countdown_with_same_task_id(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.lost-countdown",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)
    retry_task_id = "retry-countdown-owner"
    retry_due = timezone.now() + timedelta(minutes=1)
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        status=RecoveryAction.Status.FAILED,
        attempt=1,
        details={"dispatch_task_id": retry_task_id, "claimed_at": None},
        error_code="recovery_failed",
        next_retry_at=retry_due,
        finished_at=timezone.now(),
    )

    with patch(
        "catalog.services.semantic_indexing.recover_semantic_index_jobs"
    ) as recover:
        early_delivery = execute_recovery(
            str(recovery.id),
            task_id=retry_task_id,
        )
    assert early_delivery.status == RecoveryAction.Status.FAILED
    assert early_delivery.attempt == 1
    recover.assert_not_called()

    now = retry_due + timedelta(seconds=1)
    RecoveryAction.objects.filter(pk=recovery.pk).update(
        next_retry_at=now - timedelta(seconds=1)
    )
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        result = recover_stale_recovery_actions(
            now=now,
            stale_after_seconds=300,
        )

    recovery.refresh_from_db()
    assert result["requeued"] == 1
    assert recovery.status == RecoveryAction.Status.QUEUED
    assert recovery.details["dispatch_task_id"] == retry_task_id
    assert recovery.finished_at is None
    assert recovery.details["dispatch_lifecycle"][-1]["code"] == "recovery_dispatch_retry"
    dispatch.assert_called_once_with(
        args=[str(recovery.id)],
        task_id=retry_task_id,
    )


def test_failed_recovery_uses_bounded_exponential_backoff_and_terminal_incident_state(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.exhaustion",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)

    with (
        patch(
            "catalog.services.semantic_indexing.recover_semantic_index_jobs",
            side_effect=RuntimeError("semantic recovery unavailable"),
        ) as recover,
        patch("catalog.tasks.execute_health_recovery.apply_async") as retry_dispatch,
    ):
        with django_capture_on_commit_callbacks(execute=True):
            first = execute_recovery(str(recovery.id))
        first_due = first.next_retry_at
        assert first.status == RecoveryAction.Status.FAILED
        assert first.attempt == 1
        assert first_due is not None
        assert timedelta(seconds=25) <= first_due - first.finished_at <= timedelta(seconds=35)

        with django_capture_on_commit_callbacks(execute=True):
            too_early = execute_recovery(str(recovery.id))
        assert too_early.attempt == 1
        assert too_early.next_retry_at == first_due
        assert recover.call_count == 1

        _make_due(recovery)
        with django_capture_on_commit_callbacks(execute=True):
            second = execute_recovery(str(recovery.id))
        second_due = second.next_retry_at
        assert second.attempt == 2
        assert second_due is not None
        assert timedelta(seconds=55) <= second_due - second.finished_at <= timedelta(seconds=65)

        _make_due(recovery)
        with django_capture_on_commit_callbacks(execute=True):
            terminal = execute_recovery(str(recovery.id))
        assert terminal.status == RecoveryAction.Status.FAILED
        assert terminal.attempt == terminal.max_attempts == 3
        assert terminal.next_retry_at is None
        assert recover.call_count == 3

        with django_capture_on_commit_callbacks(execute=True):
            duplicate_terminal = execute_recovery(str(recovery.id))
        assert duplicate_terminal.attempt == 3
        assert duplicate_terminal.error_code == "recovery_failed"
        assert recover.call_count == 3

    assert [call.kwargs["countdown"] for call in retry_dispatch.call_args_list] == [30, 60]
    assert all(
        call.kwargs["args"] == [str(recovery.id)]
        for call in retry_dispatch.call_args_list
    )
    assert all(call.kwargs["task_id"] for call in retry_dispatch.call_args_list)
    incident.refresh_from_db()
    assert incident.status == HealthIncident.Status.OPEN
    failed_events = list(
        AuditEvent.objects.filter(
            action="health_recovery_failed",
            after__recovery_action_id=str(recovery.id),
        ).order_by("created_at")
    )
    assert len(failed_events) == 3
    assert [row.after["attempt"] for row in failed_events] == [1, 2, 3]
    assert [row.after["next_retry_at"] is not None for row in failed_events] == [
        True,
        True,
        False,
    ]
    assert AuditEvent.objects.filter(
        action="health_recovery_requested",
        after__recovery_action_id=str(recovery.id),
    ).count() == 1
    assert not AuditEvent.objects.filter(
        action="health_recovery_completed",
        after__recovery_action_id=str(recovery.id),
    ).exists()


def test_successful_retry_clears_next_retry_and_does_not_duplicate_completed_audit(
    admin_user,
    django_capture_on_commit_callbacks,
):
    incident = _incident(
        probe_key="test.recovery.eventual-success",
        action="recover_semantic_queue",
    )
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)

    with (
        patch(
            "catalog.services.semantic_indexing.recover_semantic_index_jobs",
            side_effect=[RuntimeError("first attempt failed"), {"requeued": 2}],
        ) as recover,
        patch("catalog.tasks.execute_health_recovery.apply_async"),
    ):
        with django_capture_on_commit_callbacks(execute=True):
            first = execute_recovery(str(recovery.id))
        assert first.next_retry_at is not None

        _make_due(recovery)
        with django_capture_on_commit_callbacks(execute=True):
            succeeded = execute_recovery(str(recovery.id))
        repeated = execute_recovery(str(recovery.id))

    assert succeeded.status == RecoveryAction.Status.SUCCEEDED
    assert succeeded.attempt == 2
    assert succeeded.next_retry_at is None
    assert succeeded.details == {"requeued": 2}
    assert repeated.status == RecoveryAction.Status.SUCCEEDED
    assert repeated.attempt == 2
    assert recover.call_count == 2
    incident.refresh_from_db()
    assert incident.status == HealthIncident.Status.RECOVERING
    assert AuditEvent.objects.filter(
        action="health_recovery_failed",
        after__recovery_action_id=str(recovery.id),
    ).count() == 1
    completed = AuditEvent.objects.get(
        action="health_recovery_completed",
        after__recovery_action_id=str(recovery.id),
    )
    assert completed.after["attempt"] == 2
    assert completed.after["max_attempts"] == 3


def test_successful_probe_recovery_resolves_incident(
    admin_user,
    django_capture_on_commit_callbacks,
):
    probe_key = "test.recovery.healthy-probe"
    probe = HealthProbe(
        key=probe_key,
        capability="research",
        label="健康恢复测试",
        interval_seconds=60,
        runner=lambda: ProbeResult(True, True, True, True, "恢复检查通过"),
        safe_recovery_actions=("rerun_probe",),
    )
    if not any(row.key == probe_key for row in HEALTH_CHECKS.all()):
        HEALTH_CHECKS.register(probe)
    incident = _incident(probe_key=probe_key, action="rerun_probe")
    recovery = _request(incident, admin_user, django_capture_on_commit_callbacks)

    succeeded = execute_recovery(str(recovery.id))

    assert succeeded.status == RecoveryAction.Status.SUCCEEDED
    assert succeeded.attempt == 1
    assert succeeded.next_retry_at is None
    incident.refresh_from_db()
    assert incident.status == HealthIncident.Status.RESOLVED
    assert incident.resolved_at is not None
    assert AuditEvent.objects.filter(
        action="health_recovery_completed",
        after__recovery_action_id=str(recovery.id),
    ).count() == 1


def test_celery_eager_failure_does_not_consume_future_attempts_before_due(
    settings,
    admin_user,
    django_capture_on_commit_callbacks,
):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True
    incident = _incident(
        probe_key="test.recovery.eager",
        action="recover_semantic_queue",
    )

    with (
        patch(
            "catalog.services.semantic_indexing.recover_semantic_index_jobs",
            side_effect=RuntimeError("eager failure"),
        ) as recover,
        django_capture_on_commit_callbacks(execute=True),
    ):
        recovery, created = request_recovery(
            incident,
            action="recover_semantic_queue",
            actor=admin_user,
            request_key="eager-request",
        )

    assert created is True
    recovery.refresh_from_db()
    incident.refresh_from_db()
    assert recovery.status == RecoveryAction.Status.FAILED
    assert recovery.attempt == 1
    assert recovery.next_retry_at is not None
    assert incident.status == HealthIncident.Status.RECOVERING
    assert recover.call_count == 1
    assert AuditEvent.objects.filter(
        action="health_recovery_failed",
        after__recovery_action_id=str(recovery.id),
    ).count() == 1
