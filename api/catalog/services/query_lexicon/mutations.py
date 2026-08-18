from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import logging
from typing import Callable, Iterable, TypeVar
import uuid

from django.db import connection, transaction
from django.utils import timezone


T = TypeVar("T")
QUERY_LEXICON_GENERATION_LOCK_KEY = 0x514C455849434F4E
logger = logging.getLogger(__name__)
_NESTED_QUERYSET_MUTATION_SUPPRESSED = ContextVar(
    "query_lexicon_nested_queryset_mutation_suppressed",
    default=False,
)


@dataclass(frozen=True)
class SourceSnapshot:
    source_model: str
    source_object_id: uuid.UUID
    entity_keys: frozenset


def nested_queryset_mutation_is_suppressed() -> bool:
    """Return whether Django is inside a lexicon-aware outer bulk mutation."""

    return bool(_NESTED_QUERYSET_MUTATION_SUPPRESSED.get())


@contextmanager
def suppress_nested_queryset_mutation():
    """Prevent Django bulk_update internals from emitting a second outbox event."""

    token = _NESTED_QUERYSET_MUTATION_SUPPRESSED.set(True)
    try:
        yield
    finally:
        _NESTED_QUERYSET_MUTATION_SUPPRESSED.reset(token)


def acquire_generation_lock(*, shared: bool) -> None:
    """Serialize authority writers and generation cutover on PostgreSQL."""

    if connection.vendor != "postgresql":
        return
    function = "pg_advisory_xact_lock_shared" if shared else "pg_advisory_xact_lock"
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {function}(%s)", [QUERY_LEXICON_GENERATION_LOCK_KEY])


def acquire_entity_lock(entity_type: str, entity_id) -> None:
    if connection.vendor != "postgresql":
        return
    digest = hashlib.blake2b(
        f"query-lexicon:{entity_type}:{entity_id}".encode("utf-8"),
        digest_size=8,
    ).digest()
    lock_key = int.from_bytes(digest, byteorder="big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [lock_key])


def _snapshot(instance) -> SourceSnapshot:
    from catalog.services.query_lexicon.registry import entity_keys_for_source

    return SourceSnapshot(
        source_model=instance._meta.label,
        source_object_id=uuid.UUID(str(instance.pk)),
        entity_keys=frozenset(entity_keys_for_source(instance)),
    )


def _validate_instance(instance) -> None:
    validator = getattr(instance, "validate_query_lexicon_authority_state", None)
    if validator is not None:
        validator()


def _prepare_bulk_instance(instance) -> None:
    preparer = getattr(instance, "prepare_query_lexicon_bulk_object", None)
    if preparer is not None:
        preparer()
    _validate_instance(instance)


def _record_events(
    before: Iterable[SourceSnapshot],
    after: Iterable[SourceSnapshot],
    *,
    action: str,
) -> list[int]:
    from catalog.models import QueryLexiconChangeEvent

    before_by_source = {
        (item.source_model, item.source_object_id): item for item in before
    }
    after_by_source = {
        (item.source_model, item.source_object_id): item for item in after
    }
    correlation_id = uuid.uuid4()
    event_seqs: list[int] = []
    for source_key in sorted(
        set(before_by_source) | set(after_by_source),
        key=lambda item: (item[0], str(item[1])),
    ):
        old = before_by_source.get(source_key)
        new = after_by_source.get(source_key)
        entity_keys = set(old.entity_keys if old else ()) | set(
            new.entity_keys if new else ()
        )
        for entity_key in sorted(entity_keys):
            event = QueryLexiconChangeEvent.objects.create(
                entity_type=entity_key.entity_type,
                entity_id=entity_key.entity_id,
                action=action,
                source_model=source_key[0],
                source_object_id=source_key[1],
                correlation_id=correlation_id,
            )
            event_seqs.append(event.event_seq)
    return event_seqs


def dispatch_query_lexicon_wakeup(event_seqs: Iterable[int]) -> bool:
    """Wake a stateless consumer; pending events remain durable on broker failure."""

    from catalog.models import QueryLexiconChangeEvent
    from catalog.tasks import process_query_lexicon_events

    event_seqs = list(event_seqs)
    if not event_seqs:
        return False
    try:
        process_query_lexicon_events.apply_async(ignore_result=True)
    except Exception as exc:  # The durable outbox is the recovery boundary.
        try:
            QueryLexiconChangeEvent.objects.filter(
                event_seq__in=event_seqs,
                processed_at__isnull=True,
            ).update(
                last_error_code="queue_unavailable",
                last_error_message=str(exc)[:4000],
                next_attempt_at=timezone.now(),
            )
        except Exception:
            logger.exception(
                "QueryLexicon wakeup and outbox error annotation both failed; "
                "the durable event remains available to scheduled recovery."
            )
        return False
    return True


def _schedule_wakeup(event_seqs: list[int]) -> None:
    if not event_seqs:
        return
    transaction.on_commit(
        lambda seqs=tuple(event_seqs): dispatch_query_lexicon_wakeup(seqs)
    )


def mutate_authority_instance(
    instance,
    *,
    action: str,
    operation: Callable[[], T],
    include_after: bool = True,
) -> T:
    with transaction.atomic():
        acquire_generation_lock(shared=True)
        before = []
        if action != "create" and instance.pk:
            persisted = (
                instance.__class__.objects.select_for_update()
                .filter(pk=instance.pk)
                .first()
            )
            if persisted is not None:
                before = [_snapshot(persisted)]
        result = operation()
        after = [_snapshot(instance)] if include_after else []
        if include_after:
            _validate_instance(instance)
        event_seqs = _record_events(before, after, action=action)
        _schedule_wakeup(event_seqs)
        return result


def mutate_authority_queryset(
    queryset,
    *,
    action: str,
    operation: Callable[[], T],
    include_after: bool = True,
) -> T:
    with transaction.atomic():
        acquire_generation_lock(shared=True)
        instances = list(queryset.select_for_update().order_by("pk"))
        before = [_snapshot(instance) for instance in instances]
        source_ids = [instance.pk for instance in instances]
        result = operation()
        after_instances = (
            list(queryset.model.objects.filter(pk__in=source_ids).order_by("pk"))
            if include_after
            else []
        )
        for instance in after_instances:
            _validate_instance(instance)
        after = [_snapshot(instance) for instance in after_instances]
        event_seqs = _record_events(before, after, action=action)
        _schedule_wakeup(event_seqs)
        return result


def mutate_authority_objects(
    objects: Iterable,
    *,
    action: str,
    operation: Callable[[], T],
    include_before: bool = True,
) -> T:
    objects = list(objects)
    if not objects:
        return operation()
    model = objects[0].__class__
    with transaction.atomic():
        acquire_generation_lock(shared=True)
        for instance in objects:
            if instance.__class__ is not model:
                raise ValueError("一次 QueryLexicon bulk mutation 只能包含同一模型。")
            _prepare_bulk_instance(instance)
        ids = [obj.pk for obj in objects if obj.pk]
        before_instances = (
            list(model.objects.select_for_update().filter(pk__in=ids).order_by("pk"))
            if include_before and ids
            else []
        )
        before = [_snapshot(instance) for instance in before_instances]
        result = operation()
        current_ids = [obj.pk for obj in objects if obj.pk]
        after_instances = list(
            model.objects.filter(pk__in=current_ids).order_by("pk")
        )
        for instance in after_instances:
            _validate_instance(instance)
        after = [_snapshot(instance) for instance in after_instances]
        event_seqs = _record_events(before, after, action=action)
        _schedule_wakeup(event_seqs)
        return result
