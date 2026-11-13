"""Bound active-library reconciliation; explicit builds keep their full audit."""
import logging

from django.db import transaction
from django.utils import timezone

from catalog.discovery_index_models import DiscoverySourceState
from catalog.services.discovery_sources import SOURCE_TYPES, source_queryset

logger = logging.getLogger(__name__)
SCAN_THRESHOLD = 400
SCAN_BATCH = 200


def scan_window(generation):
    if generation.status != "active":
        return None
    states = DiscoverySourceState.objects.filter(generation=generation)
    if states.count() <= SCAN_THRESHOLD and sum(source_queryset(kind).count() for kind in SOURCE_TYPES) <= SCAN_THRESHOLD:
        return None
    order = (*SOURCE_TYPES[1:], "edition")
    cursor = (generation.validation_details or {}).get("source_scan", {})
    kind = cursor.get("kind") if cursor.get("kind") in order else order[0]
    after = cursor.get("after")
    selected, remaining = {}, SCAN_BATCH
    # Explicit publication notifications create a state even when admission is
    # full. Give unqueued work a bounded share before the recovery cursor.
    for state in states.filter(job__isnull=True, indexed_at__isnull=True).order_by("updated_at", "pk")[:max(1, SCAN_BATCH//4)]:
        if state.source_type in order:
            selected.setdefault(state.source_type, []).append(state.source_id)
            remaining -= 1
    if remaining == 0:
        return selected, {**cursor, "visited": SCAN_BATCH, "checked_at": timezone.now().isoformat()}
    checkpoint = {"kind": order[0], "after": None, "completed_at": cursor.get("completed_at")}
    for position in range(order.index(kind), len(order)):
        source_kind = order[position]
        sources = source_queryset(source_kind)
        previous = states.filter(source_type=source_kind)
        if source_kind == kind and after:
            sources, previous = sources.filter(pk__gt=after), previous.filter(source_id__gt=after)
        # Union includes withdrawn/deleted identities, so cleanup also advances
        # without retaining every source-state row in process memory.
        ids = list(sources.order_by().values_list("pk", flat=True).union(
            previous.order_by().values_list("source_id", flat=True)).order_by("pk")[:remaining+1])
        window_ids = ids[:remaining]
        selected[source_kind] = list(set(selected.get(source_kind, [])) | set(window_ids))
        remaining -= len(window_ids)
        if len(ids) > len(window_ids):
            checkpoint.update(kind=source_kind, after=str(window_ids[-1]))
            break
        if not remaining and position < len(order)-1:
            checkpoint.update(kind=order[position+1], after=None)
            break
    else:
        checkpoint["completed_at"] = timezone.now().isoformat()
    checkpoint.update(visited=sum(map(len, selected.values())), checked_at=timezone.now().isoformat())
    return selected, checkpoint


def publication_changed(edition_id):
    """Target the existing producer after commit; never parse/OCR on the API."""
    def dispatch():
        from catalog.services.discovery_indexing import enabled, schedule_sources
        from catalog.services.discovery_projection import active_generation
        if not enabled():
            return
        generation = active_generation()
        if generation:
            try:
                schedule_sources(generation, source_keys={"edition": [edition_id]}, cleanup=False)
            except Exception:
                # The published revision and periodic scan retain recovery.
                logger.exception("Publication index notification failed for edition %s", edition_id)
    transaction.on_commit(dispatch)
