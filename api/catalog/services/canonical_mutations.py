from __future__ import annotations

from collections.abc import Iterable

from catalog.services.dependency_engine import record_canonical_change


def record_admin_canonical_change(
    *,
    object_type: str,
    target,
    change_kind: str,
    changed_fields: Iterable[str] | None,
    actor,
    request_idempotency_key: str = "",
):
    """Record one explicit admin mutation in the shared dependency runtime.

    Callers invoke this inside the same database transaction as the canonical
    save. The generated key is stable for that saved object revision while an
    optional request key makes client retries deterministic.
    """

    request_key = str(request_idempotency_key or "").strip()
    if request_key:
        suffix = request_key[:120]
    else:
        marker = getattr(target, "updated_at", None)
        suffix = marker.isoformat() if marker is not None else str(target.pk)
    return record_canonical_change(
        object_type=object_type,
        object_id=target.pk,
        change_kind=change_kind,
        changed_fields=changed_fields,
        actor=actor,
        idempotency_key=(
            f"admin-mutation:{object_type}:{target.pk}:{change_kind}:{suffix}"
        )[:200],
    )
