"""Capability-aware scheduling above specialist durable job tables.

``CapabilityDemand`` is a sidecar that answers whether an executor exists and
coordinates worker leases.  It is not a replacement for ``ProcessingJob``,
``ResearchRun``, semantic jobs, or the QueryLexicon outbox.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import timedelta
import uuid

from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import CapabilityDemand, CapabilityExecutor


CAPABILITIES = frozenset(
    {
        "cpu_light",
        "document_parse",
        "ocr",
        "embedding",
        "rerank",
        "llm_small",
        "llm_large",
        "web_research",
        "projection",
    }
)


@dataclass(frozen=True)
class DemandScheduleResult:
    demand: CapabilityDemand
    executor_available: bool
    dispatched: bool


@dataclass(frozen=True)
class DemandLease:
    demand_id: uuid.UUID
    owner_type: str
    owner_key: str
    capability: str
    payload: dict
    executor_id: str
    lease_token: uuid.UUID
    lease_expires_at: object


def normalize_capability(value: str) -> str:
    capability = str(value or "").strip().casefold().replace("-", "_")
    if capability not in CAPABILITIES:
        raise ValueError(f"unsupported capability: {capability or '<empty>'}")
    return capability


def _normalized_capabilities(values: Iterable[str]) -> list[str]:
    return sorted({normalize_capability(value) for value in values})


def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("lease token must be a UUID") from exc


def _demand_task_kind(demand_or_payload) -> str:
    payload = (
        demand_or_payload.payload
        if isinstance(demand_or_payload, CapabilityDemand)
        else demand_or_payload
    )
    return str((payload or {}).get("task_kind") or "").strip()


def _demand_task_profile(demand_or_payload) -> str:
    payload = (
        demand_or_payload.payload
        if isinstance(demand_or_payload, CapabilityDemand)
        else demand_or_payload
    )
    payload = payload or {}
    return str(
        payload.get("task_profile_key")
        or payload.get("profile_key")
        or ""
    ).strip()


def _executor_task_kinds(executor: CapabilityExecutor) -> set[str]:
    metadata = executor.metadata if isinstance(executor.metadata, dict) else {}
    declared = {
        str(value or "").strip()
        for value in metadata.get("task_kinds") or []
        if str(value or "").strip()
    }
    if declared:
        return declared
    # Migration compatibility for existing heartbeats. These are narrow
    # protocol facts, not capability-wide wildcards.
    capabilities = set(executor.capabilities or ())
    inferred = set()
    if "llm_small" in capabilities:
        inferred.add("claim_extraction")
    if executor.kind == CapabilityExecutor.Kind.NAS and "projection" in capabilities:
        inferred.add("projection_refresh")
    return inferred


def _executor_task_profiles(
    executor: CapabilityExecutor,
    task_kind: str,
) -> set[str] | None:
    metadata = executor.metadata if isinstance(executor.metadata, dict) else {}
    configured = metadata.get("task_profiles")
    if not isinstance(configured, dict) or task_kind not in configured:
        return None
    values = configured.get(task_kind)
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {
        str(value or "").strip()
        for value in values
        if str(value or "").strip()
    }


def executor_matches_demand(
    executor: CapabilityExecutor,
    demand_or_payload,
    *,
    capability: str | None = None,
) -> bool:
    """Match capability, task implementation and optional runtime profile."""

    required_capability = (
        normalize_capability(capability)
        if capability
        else (
            normalize_capability(demand_or_payload.capability)
            if isinstance(demand_or_payload, CapabilityDemand)
            else None
        )
    )
    if required_capability and required_capability not in set(executor.capabilities or ()):
        return False
    task_kind = _demand_task_kind(demand_or_payload)
    if task_kind and task_kind not in _executor_task_kinds(executor):
        return False
    profile = _demand_task_profile(demand_or_payload)
    supported_profiles = _executor_task_profiles(executor, task_kind)
    if profile and supported_profiles is not None:
        if "*" not in supported_profiles and profile not in supported_profiles:
            return False
    return True


def live_executors(
    capability: str | None = None,
    *,
    at=None,
    require_capacity: bool = False,
    task_kind: str = "",
    task_profile: str = "",
) -> list[CapabilityExecutor]:
    """Return executors with a fresh heartbeat and the requested capability."""

    at = at or timezone.now()
    required = normalize_capability(capability) if capability else None
    candidates = CapabilityExecutor.objects.filter(
        status=CapabilityExecutor.Status.ONLINE,
        heartbeat_expires_at__gt=at,
    ).order_by("current_load", "executor_id")
    return [
        executor
        for executor in candidates
        if (not require_capacity or executor.current_load < executor.concurrency)
        and executor_matches_demand(
            executor,
            {
                "task_kind": task_kind,
                "task_profile_key": task_profile,
            },
            capability=required,
        )
    ]


def has_live_executor(
    capability: str,
    *,
    at=None,
    task_kind: str = "",
    task_profile: str = "",
) -> bool:
    return bool(
        live_executors(
            capability,
            at=at,
            task_kind=task_kind,
            task_profile=task_profile,
        )
    )


def has_matching_executor(demand: CapabilityDemand, *, at=None) -> bool:
    return any(
        executor_matches_demand(executor, demand)
        for executor in live_executors(demand.capability, at=at)
    )


@transaction.atomic
def register_executor_heartbeat(
    *,
    executor_id: str,
    capabilities: Iterable[str],
    kind: str,
    display_name: str = "",
    model_revisions: dict | None = None,
    concurrency: int = 1,
    current_load: int | None = None,
    metadata: dict | None = None,
    ttl_seconds: int = 90,
) -> CapabilityExecutor:
    """Register or refresh an executor and make compatible demands claimable."""

    executor_id = str(executor_id or "").strip()
    if not executor_id:
        raise ValueError("executor_id is required")
    if kind not in CapabilityExecutor.Kind.values:
        raise ValueError("unsupported executor kind")
    declared = _normalized_capabilities(capabilities)
    if not declared:
        raise ValueError("at least one capability is required")
    concurrency = max(1, int(concurrency))
    now = timezone.now()
    expires_at = now + timedelta(seconds=max(30, int(ttl_seconds)))

    executor, _created = CapabilityExecutor.objects.select_for_update().get_or_create(
        executor_id=executor_id,
        defaults={"kind": kind},
    )
    executor.kind = kind
    executor.display_name = str(display_name or "")[:240]
    executor.capabilities = declared
    executor.model_revisions = dict(model_revisions or {})
    executor.concurrency = concurrency
    leased_load = CapabilityDemand.objects.filter(
        claimed_by=executor,
        state=CapabilityDemand.State.CLAIMED,
        lease_expires_at__gt=now,
    ).count()
    if current_load is not None:
        executor.current_load = min(
            max(leased_load, max(0, int(current_load))),
            concurrency,
        )
    else:
        executor.current_load = leased_load
    executor.status = CapabilityExecutor.Status.ONLINE
    executor.last_heartbeat_at = now
    executor.heartbeat_expires_at = expires_at
    executor.metadata = dict(metadata or {})
    executor.save(
        update_fields=[
            "kind",
            "display_name",
            "capabilities",
            "model_revisions",
            "concurrency",
            "current_load",
            "status",
            "last_heartbeat_at",
            "heartbeat_expires_at",
            "metadata",
            "updated_at",
        ]
    )
    waiting = CapabilityDemand.objects.select_for_update().filter(
        state=CapabilityDemand.State.WAITING_FOR_CAPABILITY,
        capability__in=declared,
    )
    ready_ids = [
        demand.id
        for demand in waiting
        if executor_matches_demand(executor, demand)
    ]
    if ready_ids:
        CapabilityDemand.objects.filter(pk__in=ready_ids).update(
            state=CapabilityDemand.State.READY,
            last_error_code="",
            last_error_message="",
            updated_at=now,
        )
    return executor


def _dispatch_ready_demand(
    demand: CapabilityDemand,
    dispatch: Callable[[CapabilityDemand], object],
) -> bool:
    try:
        dispatch(demand)
    except Exception as exc:
        CapabilityDemand.objects.filter(
            pk=demand.pk,
            state=CapabilityDemand.State.READY,
        ).update(
            last_error_code="queue_unavailable",
            last_error_message=str(exc)[:4000],
            updated_at=timezone.now(),
        )
        return False
    return True


def _dispatch_ready_demand_by_id(
    demand_id,
    dispatch: Callable[[CapabilityDemand], object],
) -> bool:
    demand = CapabilityDemand.objects.filter(
        pk=demand_id,
        state=CapabilityDemand.State.READY,
    ).first()
    if demand is None:
        return False
    return _dispatch_ready_demand(demand, dispatch)


def queue_or_wait(
    *,
    owner_type: str,
    owner_key: str,
    capability: str,
    idempotency_key: str,
    payload: dict | None = None,
    priority: int = 0,
    publication_blocking: bool = False,
    preferred_queue: str = "",
    not_before=None,
    dispatch: Callable[[CapabilityDemand], object] | None = None,
) -> DemandScheduleResult:
    """Create one idempotent demand, dispatching only if an executor is live."""

    owner_type = str(owner_type or "").strip()
    owner_key = str(owner_key or "").strip()
    idempotency_key = str(idempotency_key or "").strip()
    if not owner_type or not owner_key or not idempotency_key:
        raise ValueError("owner_type, owner_key and idempotency_key are required")
    if len(idempotency_key) > 200:
        raise ValueError("idempotency_key is too long")
    capability = normalize_capability(capability)
    now = timezone.now()
    normalized_payload = dict(payload or {})

    with transaction.atomic():
        demand, created = CapabilityDemand.objects.select_for_update().get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "owner_type": owner_type[:80],
                "owner_key": owner_key[:255],
                "capability": capability,
                "priority": int(priority),
                "publication_blocking": bool(publication_blocking),
                "preferred_queue": str(preferred_queue or "")[:120],
                "not_before": not_before,
                "payload": normalized_payload,
            },
        )
        if not created and (
            demand.owner_type != owner_type[:80]
            or demand.owner_key != owner_key[:255]
            or demand.capability != capability
        ):
            raise ValueError("idempotency_key already belongs to another demand")
        if demand.state in {
            CapabilityDemand.State.COMPLETED,
            CapabilityDemand.State.CANCELED,
        }:
            return DemandScheduleResult(demand=demand, executor_available=False, dispatched=False)
        if demand.state == CapabilityDemand.State.CLAIMED and (
            demand.lease_expires_at is None or demand.lease_expires_at > now
        ):
            return DemandScheduleResult(demand=demand, executor_available=True, dispatched=False)

        if demand.state == CapabilityDemand.State.CLAIMED:
            _release_executor_load(demand)
        effective_not_before = not_before if not_before is not None else demand.not_before
        effective_payload = normalized_payload if payload is not None or created else dict(demand.payload or {})
        available = has_live_executor(
            capability,
            at=now,
            task_kind=_demand_task_kind(effective_payload),
            task_profile=_demand_task_profile(effective_payload),
        )
        demand.state = (
            CapabilityDemand.State.READY
            if available
            else CapabilityDemand.State.WAITING_FOR_CAPABILITY
        )
        if created is False:
            demand.priority = int(priority)
            demand.publication_blocking = bool(publication_blocking)
            demand.preferred_queue = str(preferred_queue or demand.preferred_queue)[:120]
            if payload is not None:
                demand.payload = normalized_payload
            demand.not_before = effective_not_before
        demand.claimed_by = None
        demand.lease_token = None
        demand.lease_expires_at = None
        demand.save(
            update_fields=[
                "state",
                "priority",
                "publication_blocking",
                "preferred_queue",
                "payload",
                "not_before",
                "claimed_by",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )
        dispatch_scheduled = bool(available and dispatch)
        if dispatch_scheduled:
            transaction.on_commit(
                lambda demand_id=demand.id, callback=dispatch: _dispatch_ready_demand_by_id(
                    demand_id,
                    callback,
                )
            )

    demand.refresh_from_db()
    return DemandScheduleResult(
        demand=demand,
        executor_available=available,
        dispatched=dispatch_scheduled,
    )


def _lock_first(queryset):
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    return queryset.first()


def _lock_first_matching(queryset, executor: CapabilityExecutor):
    if connection.features.has_select_for_update_skip_locked:
        queryset = queryset.select_for_update(skip_locked=True)
    else:
        queryset = queryset.select_for_update()
    for demand in queryset[:100]:
        if executor_matches_demand(executor, demand):
            return demand
    return None


@transaction.atomic
def claim_demand(
    *,
    executor_id: str,
    lease_seconds: int = 300,
    allowed_task_kinds: Iterable[str] | None = None,
) -> DemandLease | None:
    """Atomically claim the highest-priority demand supported by an executor."""

    now = timezone.now()
    executor = CapabilityExecutor.objects.select_for_update().get(executor_id=executor_id)
    active_load = CapabilityDemand.objects.filter(
        claimed_by=executor,
        state=CapabilityDemand.State.CLAIMED,
        lease_expires_at__gt=now,
    ).count()
    if executor.current_load != active_load:
        executor.current_load = active_load
        executor.save(update_fields=["current_load", "updated_at"])
    if (
        executor.status != CapabilityExecutor.Status.ONLINE
        or executor.heartbeat_expires_at is None
        or executor.heartbeat_expires_at <= now
        or executor.current_load >= executor.concurrency
    ):
        return None
    capabilities = _normalized_capabilities(executor.capabilities or ())
    if not capabilities:
        return None
    eligible = (
        CapabilityDemand.objects.filter(capability__in=capabilities)
        .filter(Q(not_before__isnull=True) | Q(not_before__lte=now))
        .filter(
            Q(state=CapabilityDemand.State.READY)
            | Q(
                state=CapabilityDemand.State.CLAIMED,
                lease_expires_at__lte=now,
            )
        )
        .order_by("-priority", "created_at")
    )
    if allowed_task_kinds is not None:
        task_kinds = sorted(
            {
                str(value or "").strip()
                for value in allowed_task_kinds
                if str(value or "").strip()
            }
        )
        if not task_kinds:
            return None
        eligible = eligible.filter(payload__task_kind__in=task_kinds)
    demand = _lock_first_matching(eligible, executor)
    if demand is None:
        return None

    if demand.claimed_by_id:
        previous = CapabilityExecutor.objects.select_for_update().filter(pk=demand.claimed_by_id).first()
        if previous is not None and previous.current_load > 0:
            previous.current_load -= 1
            previous.save(update_fields=["current_load", "updated_at"])
        if previous is not None and previous.pk == executor.pk:
            executor.current_load = previous.current_load

    token = uuid.uuid4()
    expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    demand.state = CapabilityDemand.State.CLAIMED
    demand.claimed_by = executor
    demand.lease_token = token
    demand.lease_expires_at = expires_at
    demand.attempts += 1
    demand.last_error_code = ""
    demand.last_error_message = ""
    demand.save(
        update_fields=[
            "state",
            "claimed_by",
            "lease_token",
            "lease_expires_at",
            "attempts",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    executor.current_load += 1
    executor.save(update_fields=["current_load", "updated_at"])
    return DemandLease(
        demand_id=demand.id,
        owner_type=demand.owner_type,
        owner_key=demand.owner_key,
        capability=demand.capability,
        payload=dict(demand.payload or {}),
        executor_id=executor.executor_id,
        lease_token=token,
        lease_expires_at=expires_at,
    )


@transaction.atomic
def claim_specific_demand(
    demand_id,
    *,
    executor_id: str,
    lease_seconds: int = 300,
) -> DemandLease | None:
    """Reserve one known demand before an external dispatcher enqueues it.

    Pull workers use :func:`claim_demand`.  A Celery dispatcher already knows
    the demand id, so selecting the globally highest-priority row could bind
    the Celery message to a different task.  This variant locks the executor
    and exact demand in the same order as the pull path.  Once it returns a
    lease, neither another Celery dispatcher nor a remote worker can claim that
    demand until the lease is completed, released, or expires.
    """

    now = timezone.now()
    executor = CapabilityExecutor.objects.select_for_update().get(executor_id=executor_id)
    active_load = CapabilityDemand.objects.filter(
        claimed_by=executor,
        state=CapabilityDemand.State.CLAIMED,
        lease_expires_at__gt=now,
    ).count()
    if executor.current_load != active_load:
        executor.current_load = active_load
        executor.save(update_fields=["current_load", "updated_at"])
    if (
        executor.status != CapabilityExecutor.Status.ONLINE
        or executor.heartbeat_expires_at is None
        or executor.heartbeat_expires_at <= now
        or executor.current_load >= executor.concurrency
    ):
        return None

    demand = CapabilityDemand.objects.select_for_update().filter(pk=demand_id).first()
    if demand is None:
        return None
    if not executor_matches_demand(executor, demand):
        return None
    if demand.not_before is not None and demand.not_before > now:
        return None
    if demand.state == CapabilityDemand.State.CLAIMED:
        if demand.lease_expires_at is None or demand.lease_expires_at > now:
            return None
        _release_executor_load(demand)
    elif demand.state != CapabilityDemand.State.READY:
        return None

    token = uuid.uuid4()
    expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    demand.state = CapabilityDemand.State.CLAIMED
    demand.claimed_by = executor
    demand.lease_token = token
    demand.lease_expires_at = expires_at
    demand.attempts += 1
    demand.last_error_code = ""
    demand.last_error_message = ""
    demand.save(
        update_fields=[
            "state",
            "claimed_by",
            "lease_token",
            "lease_expires_at",
            "attempts",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    executor.current_load += 1
    executor.save(update_fields=["current_load", "updated_at"])
    return DemandLease(
        demand_id=demand.id,
        owner_type=demand.owner_type,
        owner_key=demand.owner_key,
        capability=demand.capability,
        payload=dict(demand.payload or {}),
        executor_id=executor.executor_id,
        lease_token=token,
        lease_expires_at=expires_at,
    )


@transaction.atomic
def renew_demand_lease(
    demand_id,
    lease_token,
    *,
    executor_id: str,
    lease_seconds: int = 300,
) -> DemandLease:
    now = timezone.now()
    demand = (
        CapabilityDemand.objects.select_related("claimed_by")
        .select_for_update(of=("self",))
        .get(pk=demand_id)
    )
    token = _uuid(lease_token)
    if (
        demand.state != CapabilityDemand.State.CLAIMED
        or demand.lease_token != token
        or demand.claimed_by is None
        or demand.claimed_by.executor_id != executor_id
    ):
        raise ValueError("demand lease is no longer active")
    if demand.lease_expires_at is not None and demand.lease_expires_at <= now:
        raise ValueError("demand lease has expired")
    demand.lease_expires_at = now + timedelta(seconds=max(30, int(lease_seconds)))
    demand.save(update_fields=["lease_expires_at", "updated_at"])
    return DemandLease(
        demand_id=demand.id,
        owner_type=demand.owner_type,
        owner_key=demand.owner_key,
        capability=demand.capability,
        payload=dict(demand.payload or {}),
        executor_id=executor_id,
        lease_token=token,
        lease_expires_at=demand.lease_expires_at,
    )


def _release_executor_load(demand: CapabilityDemand) -> None:
    if demand.claimed_by_id is None:
        return
    executor = CapabilityExecutor.objects.select_for_update().filter(pk=demand.claimed_by_id).first()
    if executor is not None and executor.current_load > 0:
        executor.current_load -= 1
        executor.save(update_fields=["current_load", "updated_at"])


@transaction.atomic
def complete_demand(
    demand_id,
    lease_token,
    *,
    executor_id: str,
) -> CapabilityDemand:
    demand = (
        CapabilityDemand.objects.select_related("claimed_by")
        .select_for_update(of=("self",))
        .get(pk=demand_id)
    )
    if (
        demand.state != CapabilityDemand.State.CLAIMED
        or demand.lease_token != _uuid(lease_token)
        or demand.claimed_by is None
        or demand.claimed_by.executor_id != executor_id
    ):
        raise ValueError("demand lease is no longer active")
    if demand.lease_expires_at is None or demand.lease_expires_at <= timezone.now():
        raise ValueError("demand lease has expired")
    _release_executor_load(demand)
    demand.state = CapabilityDemand.State.COMPLETED
    demand.claimed_by = None
    demand.lease_token = None
    demand.lease_expires_at = None
    demand.last_error_code = ""
    demand.last_error_message = ""
    demand.save(
        update_fields=[
            "state",
            "claimed_by",
            "lease_token",
            "lease_expires_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    return demand


@transaction.atomic
def release_demand(
    demand_id,
    lease_token,
    *,
    executor_id: str,
    error_code: str,
    error_message: str,
    retry: bool = True,
    retry_after_seconds: int = 0,
) -> CapabilityDemand:
    demand = (
        CapabilityDemand.objects.select_related("claimed_by")
        .select_for_update(of=("self",))
        .get(pk=demand_id)
    )
    if (
        demand.state != CapabilityDemand.State.CLAIMED
        or demand.lease_token != _uuid(lease_token)
        or demand.claimed_by is None
        or demand.claimed_by.executor_id != executor_id
    ):
        raise ValueError("demand lease is no longer active")
    if demand.lease_expires_at is None or demand.lease_expires_at <= timezone.now():
        raise ValueError("demand lease has expired")
    _release_executor_load(demand)
    demand.claimed_by = None
    demand.lease_token = None
    demand.lease_expires_at = None
    demand.last_error_code = str(error_code or "task_failed")[:120]
    demand.last_error_message = str(error_message or "")[:4000]
    if retry:
        demand.not_before = timezone.now() + timedelta(seconds=max(0, int(retry_after_seconds)))
        demand.state = (
            CapabilityDemand.State.READY
            if has_matching_executor(demand)
            else CapabilityDemand.State.WAITING_FOR_CAPABILITY
        )
    else:
        demand.state = CapabilityDemand.State.FAILED
    demand.save(
        update_fields=[
            "state",
            "claimed_by",
            "lease_token",
            "lease_expires_at",
            "last_error_code",
            "last_error_message",
            "not_before",
            "updated_at",
        ]
    )
    return demand


@transaction.atomic
def reconcile_capability_runtime(*, at=None) -> dict[str, int]:
    """Expire silent workers and make their unfinished work visible again."""

    at = at or timezone.now()
    expired = list(
        CapabilityExecutor.objects.select_for_update().filter(
            status=CapabilityExecutor.Status.ONLINE,
            heartbeat_expires_at__lte=at,
        )
    )
    if expired:
        CapabilityExecutor.objects.filter(pk__in=[row.pk for row in expired]).update(
            status=CapabilityExecutor.Status.OFFLINE,
            current_load=0,
            updated_at=at,
        )

    reclaimed = list(
        CapabilityDemand.objects.select_for_update(of=("self",)).filter(
            state=CapabilityDemand.State.CLAIMED,
        ).filter(
            Q(lease_expires_at__lte=at)
            | Q(claimed_by__status=CapabilityExecutor.Status.OFFLINE)
        )
    )
    ready = 0
    waiting = 0
    for demand in reclaimed:
        _release_executor_load(demand)
        demand.claimed_by = None
        demand.lease_token = None
        demand.lease_expires_at = None
        if has_matching_executor(demand, at=at):
            demand.state = CapabilityDemand.State.READY
            ready += 1
        else:
            demand.state = CapabilityDemand.State.WAITING_FOR_CAPABILITY
            waiting += 1
        demand.save(
            update_fields=[
                "state",
                "claimed_by",
                "lease_token",
                "lease_expires_at",
                "updated_at",
            ]
        )

    # Repair historical or race-created READY rows that no live executor can
    # actually implement. Matching includes task kind and optional profile,
    # so a coarse capability heartbeat cannot leave an orphan claim queue.
    reclaimed_ids = {demand.id for demand in reclaimed}
    live = list(
        CapabilityExecutor.objects.filter(
            status=CapabilityExecutor.Status.ONLINE,
            heartbeat_expires_at__gt=at,
        )
    )
    unresolved = (
        CapabilityDemand.objects.select_for_update()
        .filter(
            state__in=[
                CapabilityDemand.State.READY,
                CapabilityDemand.State.WAITING_FOR_CAPABILITY,
            ]
        )
        .exclude(pk__in=reclaimed_ids)
        .order_by("created_at")
    )
    for demand in unresolved.iterator(chunk_size=200):
        matching = any(
            executor_matches_demand(executor, demand)
            for executor in live
        )
        desired = (
            CapabilityDemand.State.READY
            if matching
            else CapabilityDemand.State.WAITING_FOR_CAPABILITY
        )
        if demand.state == desired:
            continue
        demand.state = desired
        demand.save(update_fields=["state", "updated_at"])
        if desired == CapabilityDemand.State.READY:
            ready += 1
        else:
            waiting += 1
    return {"executors_offline": len(expired), "demands_ready": ready, "demands_waiting": waiting}


def missing_capability_summary() -> dict[str, int]:
    rows = CapabilityDemand.objects.filter(
        state=CapabilityDemand.State.WAITING_FOR_CAPABILITY
    ).values_list("capability", flat=True)
    summary: dict[str, int] = {}
    for capability in rows:
        summary[capability] = summary.get(capability, 0) + 1
    return summary
