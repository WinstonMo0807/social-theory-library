from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import ResearchRun
from ingestion.models import AuditEvent


RESEARCH_RUN_NONTERMINAL_STATUSES = frozenset(
    {
        ResearchRun.Status.QUEUED,
        ResearchRun.Status.RUNNING,
    }
)
RESEARCH_RUN_TERMINAL_STATUSES = frozenset(
    {
        ResearchRun.Status.COMPLETED,
        ResearchRun.Status.DEGRADED,
        ResearchRun.Status.FAILED,
        ResearchRun.Status.CANCELED,
        ResearchRun.Status.SUPERSEDED,
    }
)


@dataclass(frozen=True)
class ResearchRunTransition:
    run: ResearchRun
    changed: bool
    reason: str


@dataclass(frozen=True)
class CeleryOwnershipSnapshot:
    available: bool
    task_ids: frozenset[str]
    workers: tuple[str, ...] = ()
    detail: str = ""


def research_run_stale_seconds(value: int | None = None) -> int:
    configured = (
        value
        if value is not None
        else getattr(settings, "RESEARCH_RUN_STALE_SECONDS", 15 * 60)
    )
    return max(60, min(int(configured), 24 * 60 * 60))


def celery_research_ownership_snapshot(
    *,
    timeout_seconds: float | None = None,
) -> CeleryOwnershipSnapshot:
    """Read active, reserved and scheduled Celery ownership.

    A snapshot is authoritative only when at least one worker responds to all
    three control queries. Missing or partial control replies fail closed.
    """

    if settings.CELERY_TASK_ALWAYS_EAGER:
        return CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset(),
            workers=("eager-test-runtime",),
            detail="Celery eager mode",
        )
    timeout = timeout_seconds
    if timeout is None:
        timeout = getattr(
            settings,
            "RESEARCH_RUN_OWNERSHIP_INSPECT_TIMEOUT_SECONDS",
            1.0,
        )
    timeout = max(0.2, min(float(timeout), 5.0))
    from config.celery import app as celery_app

    try:
        inspector = celery_app.control.inspect(timeout=timeout)
        ping = inspector.ping() or {}
        workers = set(ping)
        if not workers:
            return CeleryOwnershipSnapshot(
                available=False,
                task_ids=frozenset(),
                detail="没有 worker 响应 Celery control ping。",
            )
        active = inspector.active() or {}
        reserved = inspector.reserved() or {}
        scheduled = inspector.scheduled() or {}
        if any(set(payload) != workers for payload in (active, reserved, scheduled)):
            return CeleryOwnershipSnapshot(
                available=False,
                task_ids=frozenset(),
                workers=tuple(sorted(str(value)[:160] for value in workers)),
                detail="Celery ownership inventory 回复不完整。",
            )
        task_ids: set[str] = set()
        for payload in (active, reserved):
            for worker in workers:
                for row in payload.get(worker) or []:
                    task_id = str((row or {}).get("id") or "").strip()
                    if task_id:
                        task_ids.add(task_id)
        for worker in workers:
            for row in scheduled.get(worker) or []:
                request = (row or {}).get("request") or {}
                task_id = str(request.get("id") or (row or {}).get("id") or "").strip()
                if task_id:
                    task_ids.add(task_id)
        return CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset(task_ids),
            workers=tuple(sorted(str(value)[:160] for value in workers)),
            detail="Celery ownership inventory 可用。",
        )
    except Exception as exc:
        return CeleryOwnershipSnapshot(
            available=False,
            task_ids=frozenset(),
            detail=f"{exc.__class__.__name__}: Celery ownership inventory 不可用。",
        )


def _celery_ownership_reason(
    run: ResearchRun,
    snapshot: CeleryOwnershipSnapshot | None,
) -> str:
    """Classify ownership without guessing when Celery control is unavailable.

    A blank token is definitively unowned. A non-empty token is unowned only
    when a complete worker inventory confirms that it is absent.
    """

    task_id = str(run.task_id or "").strip()
    if not task_id:
        return "unowned"
    if run.status == ResearchRun.Status.QUEUED:
        # Queued broker messages are not visible in Celery control. Once the
        # durable row itself is stale, safely publish the same task id again.
        # Competing deliveries remain idempotent because the Worker must claim
        # this exact owner under a row lock before execution.
        return "redispatchable"
    if snapshot is None or not snapshot.available:
        return "ownership_unverified"
    return "celery_owned" if task_id in snapshot.task_ids else "unowned"


def stale_research_run_inventory(
    *,
    stale_after_seconds: int | None = None,
    now=None,
    ownership_snapshot: CeleryOwnershipSnapshot | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Return a bounded, read-only classification for health reporting."""

    now = now or timezone.now()
    stale_seconds = research_run_stale_seconds(stale_after_seconds)
    cutoff = now - timedelta(seconds=stale_seconds)
    bounded_limit = max(1, min(int(limit), 500))
    queryset = ResearchRun.objects.filter(
        status__in=RESEARCH_RUN_NONTERMINAL_STATUSES,
        updated_at__lt=cutoff,
    ).order_by("updated_at", "created_at")
    snapshot = ownership_snapshot
    if snapshot is None and queryset.exclude(task_id="").exists():
        snapshot = celery_research_ownership_snapshot()
    # Re-evaluate after the control query. A Celery task may have claimed a
    # previously stale row while the inventory was being collected.
    total = queryset.count()
    runs = list(queryset.only("id", "status", "task_id", "updated_at")[:bounded_limit])
    snapshot = snapshot or CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        detail="所有 stale ResearchRun 均无 task_id。",
    )
    groups: dict[str, list[ResearchRun]] = {
        "unowned": [],
        "redispatchable": [],
        "celery_owned": [],
        "ownership_unverified": [],
    }
    for run in runs:
        groups[_celery_ownership_reason(run, snapshot)].append(run)
    unclassified_count = max(0, total - len(runs))
    orphan_queued = [
        str(run.id)
        for run in [*groups["unowned"], *groups["redispatchable"]]
        if run.status == ResearchRun.Status.QUEUED
    ]
    orphan_running = [
        str(run.id)
        for run in groups["unowned"]
        if run.status == ResearchRun.Status.RUNNING
    ]
    orphan_ids = [
        str(run.id)
        for run in [*groups["unowned"], *groups["redispatchable"]]
    ]
    return {
        "stale_candidate_count": total,
        "orphan_nonterminal_count": len(orphan_ids),
        "orphan_nonterminal_ids": orphan_ids[:20],
        "orphan_queued_count": len(orphan_queued),
        "orphan_queued_ids": orphan_queued[:20],
        "orphan_running_count": len(orphan_running),
        "orphan_running_ids": orphan_running[:20],
        "redispatchable_queued_count": len(groups["redispatchable"]),
        "redispatchable_queued_ids": [
            str(run.id) for run in groups["redispatchable"][:20]
        ],
        "celery_owned_stale_count": len(groups["celery_owned"]),
        "ownership_unverified_count": len(groups["ownership_unverified"])
        + unclassified_count,
        "ownership_inventory_available": snapshot.available,
        "ownership_inventory_workers": list(snapshot.workers),
        "ownership_inventory_detail": snapshot.detail,
        "stale_after_seconds": stale_seconds,
        "inventory_truncated": total > len(runs),
    }


def _append_lifecycle_diagnostic(
    run: ResearchRun,
    *,
    code: str,
    source: str,
    occurred_at,
    previous_status: str,
    stale_after_seconds: int | None = None,
) -> dict[str, Any]:
    diagnostics = dict(run.diagnostics or {})
    history = list(diagnostics.get("lifecycle_events") or [])
    event = {
        "code": code,
        "source": source,
        "occurred_at": occurred_at.isoformat(),
        "previous_status": previous_status,
        "previous_task_id": str(run.task_id or ""),
    }
    if stale_after_seconds is not None:
        event["stale_after_seconds"] = stale_after_seconds
    history.append(event)
    diagnostics["lifecycle_events"] = history[-20:]
    return diagnostics


def _cancel_locked_run(
    run: ResearchRun,
    *,
    actor,
    source: str,
    audit_action: str,
    diagnostic_code: str,
    error_code: str,
    error_message: str,
    now,
    request_id: str = "",
    stale_after_seconds: int | None = None,
) -> ResearchRun:
    previous_status = run.status
    previous_error_code = run.error_code
    diagnostics = _append_lifecycle_diagnostic(
        run,
        code=diagnostic_code,
        source=source,
        occurred_at=now,
        previous_status=previous_status,
        stale_after_seconds=stale_after_seconds,
    )
    run.status = ResearchRun.Status.CANCELED
    run.finished_at = now
    run.diagnostics = diagnostics
    run.error_code = error_code
    run.error_message = error_message
    run.save(
        update_fields=[
            "status",
            "finished_at",
            "diagnostics",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )
    AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=audit_action,
        object_type="catalog.ResearchRun",
        object_id=str(run.id),
        before={
            "status": previous_status,
            "task_id": str(run.task_id or ""),
            "error_code": previous_error_code,
        },
        after={
            "status": run.status,
            "task_id": str(run.task_id or ""),
            "error_code": run.error_code,
            "source": source,
            "finished_at": run.finished_at.isoformat(),
        },
        request_id=str(request_id or "")[:120],
    )
    return run


def cancel_research_run(
    run_id: str,
    *,
    actor=None,
    request_id: str = "",
    now=None,
) -> ResearchRunTransition:
    """Cancel one nonterminal run under a row lock.

    Terminal runs are returned unchanged, making duplicate API requests safe.
    """

    now = now or timezone.now()
    with transaction.atomic():
        run = ResearchRun.objects.select_for_update(of=("self",)).get(pk=run_id)
        if run.status in RESEARCH_RUN_TERMINAL_STATUSES:
            return ResearchRunTransition(run=run, changed=False, reason="terminal")
        if run.status not in RESEARCH_RUN_NONTERMINAL_STATUSES:
            return ResearchRunTransition(run=run, changed=False, reason="unsupported_status")
        run = _cancel_locked_run(
            run,
            actor=actor,
            source="manual",
            audit_action="research_run_canceled",
            diagnostic_code="research_run_canceled",
            error_code="research_run_canceled",
            error_message="ResearchRun 已由管理员取消。",
            now=now,
            request_id=request_id,
        )
        return ResearchRunTransition(run=run, changed=True, reason="canceled")


def recover_orphaned_research_run(
    run_id: str,
    *,
    actor=None,
    request_id: str = "",
    stale_after_seconds: int | None = None,
    now=None,
    ownership_snapshot: CeleryOwnershipSnapshot | None = None,
) -> ResearchRunTransition:
    """Close one stale, unowned queued/running run without retrying research."""

    now = now or timezone.now()
    stale_seconds = research_run_stale_seconds(stale_after_seconds)
    cutoff = now - timedelta(seconds=stale_seconds)
    snapshot = ownership_snapshot
    if snapshot is None:
        candidate = ResearchRun.objects.filter(pk=run_id).only("task_id").first()
        if candidate is not None and str(candidate.task_id or "").strip():
            snapshot = celery_research_ownership_snapshot()
    with transaction.atomic():
        run = ResearchRun.objects.select_for_update(of=("self",)).get(pk=run_id)
        if run.status in RESEARCH_RUN_TERMINAL_STATUSES:
            return ResearchRunTransition(run=run, changed=False, reason="terminal")
        if run.status not in RESEARCH_RUN_NONTERMINAL_STATUSES:
            return ResearchRunTransition(run=run, changed=False, reason="unsupported_status")
        if run.updated_at >= cutoff:
            return ResearchRunTransition(run=run, changed=False, reason="recent")
        ownership_reason = _celery_ownership_reason(run, snapshot)
        if ownership_reason != "unowned":
            return ResearchRunTransition(
                run=run,
                changed=False,
                reason=ownership_reason,
            )
        previous_status = run.status
        run = _cancel_locked_run(
            run,
            actor=actor,
            source="stale_recovery",
            audit_action="research_run_orphan_recovered",
            diagnostic_code="research_run_orphaned",
            error_code="research_run_orphaned",
            error_message="ResearchRun 超过执行时限且没有有效 Celery ownership，已安全收口。",
            now=now,
            request_id=request_id,
            stale_after_seconds=stale_seconds,
        )
        return ResearchRunTransition(
            run=run,
            changed=True,
            reason=f"recovered_{previous_status}",
        )


def recover_stale_research_runs(
    *,
    actor=None,
    request_id: str = "",
    stale_after_seconds: int | None = None,
    limit: int = 100,
    now=None,
    ownership_snapshot: CeleryOwnershipSnapshot | None = None,
) -> dict[str, Any]:
    """Safely close a bounded batch of stale runs without active ownership."""

    now = now or timezone.now()
    stale_seconds = research_run_stale_seconds(stale_after_seconds)
    cutoff = now - timedelta(seconds=stale_seconds)
    bounded_limit = max(1, min(int(limit), 500))
    recovered_ids: list[str] = []
    redispatched: list[tuple[str, str]] = []
    recovered_by_status: dict[str, int] = {}
    skipped_owned = 0
    skipped_unverified = 0
    snapshot = ownership_snapshot
    if snapshot is None:
        has_claim_tokens = ResearchRun.objects.filter(
            status__in=RESEARCH_RUN_NONTERMINAL_STATUSES,
            updated_at__lt=cutoff,
        ).exclude(task_id="").exists()
        if has_claim_tokens:
            snapshot = celery_research_ownership_snapshot()
    with transaction.atomic():
        runs = list(
            ResearchRun.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(
                status__in=RESEARCH_RUN_NONTERMINAL_STATUSES,
                updated_at__lt=cutoff,
            )
            .order_by("updated_at", "created_at")[:bounded_limit]
        )
        for run in runs:
            ownership_reason = _celery_ownership_reason(run, snapshot)
            if ownership_reason == "redispatchable":
                diagnostics = _append_lifecycle_diagnostic(
                    run,
                    code="research_run_redispatched",
                    source="stale_recovery",
                    occurred_at=now,
                    previous_status=run.status,
                    stale_after_seconds=stale_seconds,
                )
                diagnostics["redispatch_count"] = int(
                    diagnostics.get("redispatch_count") or 0
                ) + 1
                run.diagnostics = diagnostics
                # Saving updated_at starts a fresh bounded wait window. The
                # same task id is deliberately retained for duplicate safety.
                run.save(update_fields=["diagnostics", "updated_at"])
                redispatched.append((str(run.id), str(run.task_id)))
                continue
            if ownership_reason == "celery_owned":
                skipped_owned += 1
                continue
            if ownership_reason == "ownership_unverified":
                skipped_unverified += 1
                continue
            previous_status = run.status
            _cancel_locked_run(
                run,
                actor=actor,
                source="stale_recovery",
                audit_action="research_run_orphan_recovered",
                diagnostic_code="research_run_orphaned",
                error_code="research_run_orphaned",
                error_message="ResearchRun 超过执行时限且没有有效 Celery ownership，已安全收口。",
                now=now,
                request_id=request_id,
                stale_after_seconds=stale_seconds,
            )
            recovered_ids.append(str(run.id))
            recovered_by_status[previous_status] = recovered_by_status.get(previous_status, 0) + 1
        for run_id, task_id in redispatched:
            transaction.on_commit(
                lambda run_id=run_id, task_id=task_id: _redispatch_research_run(
                    run_id,
                    task_id,
                )
            )
    effective_snapshot = snapshot or CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        detail="所有 recovery candidate 均无 task_id。",
    )
    return {
        "candidates": len(runs),
        "recovered": len(recovered_ids),
        "redispatched": len(redispatched),
        "redispatched_ids": [row[0] for row in redispatched],
        "skipped_celery_owned": skipped_owned,
        "skipped_ownership_unverified": skipped_unverified,
        "ownership_inventory_available": effective_snapshot.available,
        "ownership_inventory_workers": list(effective_snapshot.workers),
        "ownership_inventory_detail": effective_snapshot.detail,
        "recovered_by_status": recovered_by_status,
        "run_ids": recovered_ids,
        "stale_after_seconds": stale_seconds,
    }


def _redispatch_research_run(run_id: str, task_id: str) -> None:
    # Local import keeps recovery usable without loading the orchestrator's
    # provider graph during module import.
    from .orchestrator import ResearchOrchestrator

    ResearchOrchestrator._dispatch_research_run(str(run_id), str(task_id))
