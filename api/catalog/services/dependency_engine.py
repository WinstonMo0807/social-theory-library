"""Revision-aware dependency and projection coordination.

PostgreSQL remains the fact source.  This module records a durable domain
change next to the canonical revision and derives bounded, rebuildable
projection state from it.  It deliberately does not replace specialist
outboxes such as ``QueryLexiconChangeEvent`` and does not execute projection
work itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable
import uuid

from django.db import connection, transaction
from django.db.models import F, Q
from django.utils import timezone

from catalog.models import (
    CanonicalObjectRevision,
    DomainChangeEvent,
    ProjectionState,
)


ProjectionType = ProjectionState.ProjectionType

ALL_PROJECTIONS: tuple[str, ...] = tuple(value for value, _label in ProjectionType.choices)

# The map is intentionally explicit.  It keeps one canonical mutation from
# turning into an indiscriminate full-library rebuild while documenting every
# supported projection family in one place.
PROJECTION_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "work": ALL_PROJECTIONS,
    "edition": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.FULLTEXT,
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "asset": (
        ProjectionType.FULLTEXT,
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
        ProjectionType.PUBLIC,
    ),
    "document_revision": (
        ProjectionType.FULLTEXT,
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
        ProjectionType.PUBLIC,
    ),
    "page": (
        ProjectionType.FULLTEXT,
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
    ),
    "text_block": (
        ProjectionType.FULLTEXT,
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
    ),
    "evidence_span": (
        ProjectionType.SEMANTIC,
        ProjectionType.CLAIM_INDEX,
        ProjectionType.PUBLIC,
    ),
    "derived_claim": (
        ProjectionType.CLAIM_INDEX,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
    ),
    "curated_claim": (
        ProjectionType.CLAIM_INDEX,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "person": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "scholar_profile": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "knowledge_node": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.CLAIM_INDEX,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "knowledge_relation": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "work_node_relation": (
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "person_node_relation": (
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "discipline": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "subdiscipline": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "topic": (
        ProjectionType.QUERY_LEXICON,
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    "reading_path": (
        ProjectionType.RECOMMENDATION,
        ProjectionType.READING_PATH_SUPPORT,
        ProjectionType.PUBLIC,
    ),
    # TheorySchool remains readable only during canonical migration.  Its sole
    # supported mutation is withdrawal, which still has to invalidate public
    # compatibility output until the legacy adapter is retired.
    "theory_school": (ProjectionType.PUBLIC,),
    "timeline_event": (
        ProjectionType.KNOWLEDGE_GRAPH,
        ProjectionType.TIMELINE,
        ProjectionType.PUBLIC,
    ),
}


# Exact field impacts used by 3.0.4 publication events.  Calls without field
# information deliberately retain the historical object-level mapping.
FIELD_PROJECTION_DEPENDENCIES: dict[str, dict[str, tuple[str, ...]]] = {
    "work": {
        "cover": (ProjectionType.PUBLIC,),
        "title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
        "subtitle": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "original_title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "uniform_title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "document_type": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "language": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "abstract": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "contributors": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "classification": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "knowledge": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "curation": (
            ProjectionType.CLAIM_INDEX,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
    },
    "edition": {
        # Catalog publication is coordinated from Edition so one publication
        # revision cannot enqueue duplicate whole-book jobs for Work and
        # Edition.  Work-owned fields therefore have explicit Edition aliases.
        "catalog_publish": ALL_PROJECTIONS,
        "catalog_withdraw": ALL_PROJECTIONS,
        "cover": (ProjectionType.PUBLIC,),
        "title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
        "subtitle": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "original_title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "uniform_title": (
            ProjectionType.QUERY_LEXICON,
            ProjectionType.FULLTEXT,
            ProjectionType.PUBLIC,
        ),
        "document_type": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "language": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "abstract": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "authors": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "translators": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.PUBLIC,
        ),
        "disciplines": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "subdisciplines": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "topics": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "theories": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.READING_PATH_SUPPORT,
            ProjectionType.PUBLIC,
        ),
        "curation": (
            ProjectionType.CLAIM_INDEX,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
        "version_label": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "publication_date": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "publication_year": (
            ProjectionType.FULLTEXT,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
        "publisher": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "journal_contents": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "publisher_authority": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "publication_place": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "isbn": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "isbn10": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "isbn13": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "doi": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "contributors": (
            ProjectionType.FULLTEXT,
            ProjectionType.KNOWLEDGE_GRAPH,
            ProjectionType.RECOMMENDATION,
            ProjectionType.PUBLIC,
        ),
        "metadata_ready": (ProjectionType.FULLTEXT, ProjectionType.PUBLIC),
        "fulltext_ready": (
            ProjectionType.FULLTEXT,
            ProjectionType.SEMANTIC,
            ProjectionType.CLAIM_INDEX,
            ProjectionType.PUBLIC,
        ),
        "asset": (
            ProjectionType.FULLTEXT,
            ProjectionType.SEMANTIC,
            ProjectionType.CLAIM_INDEX,
            ProjectionType.PUBLIC,
        ),
        "document_revision": (
            ProjectionType.FULLTEXT,
            ProjectionType.SEMANTIC,
            ProjectionType.CLAIM_INDEX,
            ProjectionType.PUBLIC,
        ),
    },
}


@dataclass(frozen=True)
class ProjectionLease:
    state_id: uuid.UUID
    object_type: str
    object_id: uuid.UUID
    projection_type: str
    source_revision: int
    lease_token: uuid.UUID
    lease_expires_at: object


@dataclass(frozen=True)
class DomainChangeLease:
    event_id: uuid.UUID
    canonical_revision: int
    lease_token: uuid.UUID
    lease_expires_at: object


def normalize_object_type(value: str) -> str:
    normalized = str(value or "").strip().casefold().replace("-", "_")
    if "." in normalized:
        normalized = normalized.rsplit(".", 1)[-1]
    if not normalized:
        raise ValueError("object_type is required")
    if len(normalized) > 80:
        raise ValueError("object_type is too long")
    return normalized


def projection_types_for(
    object_type: str,
    changed_fields: Iterable[str] | None = None,
) -> tuple[str, ...]:
    """Return the bounded projections affected by a canonical object type."""

    normalized = normalize_object_type(object_type)
    normalized_fields = _changed_fields(changed_fields)
    field_map = FIELD_PROJECTION_DEPENDENCIES.get(normalized, {})
    if normalized_fields and field_map:
        selected: set[str] = set()
        unknown = False
        for raw_field in normalized_fields:
            field_name = raw_field.split(".", 1)[0]
            projections = field_map.get(field_name)
            if projections is None and normalized == "work":
                projections = FIELD_PROJECTION_DEPENDENCIES["edition"].get(field_name)
            if projections is None and normalized in {"edition", "work"} and field_name in {
                "original_language", "first_publication_date", "translation_of", "series", "extent",
                "journal_title", "volume", "issue", "page_range", "degree_institution",
                "degree_type", "report_institution", "recommendation_image",
            }:
                projections = (ProjectionType.FULLTEXT, ProjectionType.PUBLIC)
            if projections is None:
                unknown = True
                continue
            selected.update(projections)
            if normalized in {"edition", "work"} and field_name in {
                "title", "subtitle", "original_title", "uniform_title", "document_type", "language",
                "authors", "translators", "contributors", "publication_year", "topics", "theories",
                "disciplines", "subdisciplines", "classification", "knowledge",
            }:
                # Reuse existing vectors when only the searchable metadata
                # changes. The semantic consumer chooses metadata_only mode.
                selected.add(ProjectionType.SEMANTIC)
                selected.add(ProjectionType.CLAIM_INDEX)
        if selected and not unknown:
            return tuple(
                projection
                for projection in ALL_PROJECTIONS
                if projection in selected
            )
    # Unknown canonical types still receive a public-consistency marker.  A
    # missing registry entry therefore remains visible without scheduling all
    # expensive projections.
    return PROJECTION_DEPENDENCIES.get(normalized, (ProjectionType.PUBLIC,))


def _uuid(value) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("object_id must be a UUID") from exc


def _changed_fields(values: Iterable[str] | None) -> list[str]:
    return sorted({str(value).strip() for value in (values or ()) if str(value).strip()})


def _schedule_resolved_event(event_id) -> None:
    """Best-effort wakeup for the durable projection coordinator.

    Projection freshness is already durable in ``ProjectionState``.  A broker
    or worker outage therefore must not make the canonical transaction fail
    after it has committed.  The periodic reconciler can recover any wakeup
    that fails here.
    """

    try:
        from catalog.services.projection_refresh import schedule_domain_change_projections

        schedule_domain_change_projections(event_id)
    except Exception as exc:
        event = DomainChangeEvent.objects.filter(pk=event_id).first()
        DomainChangeEvent.objects.filter(pk=event_id).update(
            last_error_code="projection_schedule_failed",
            last_error_message=str(exc)[:4000],
            updated_at=timezone.now(),
        )
        if event is not None:
            ProjectionState.objects.filter(
                object_type=event.object_type,
                object_id=event.object_id,
                source_revision__gt=F("projected_revision"),
            ).update(
                status=ProjectionState.Status.FAILED,
                last_error_code="projection_schedule_failed",
                last_error_message=str(exc)[:4000],
                updated_at=timezone.now(),
            )


def _resolve_locked(event: DomainChangeEvent) -> list[ProjectionState]:
    now = timezone.now()
    states: list[ProjectionState] = []
    reason = f"{event.change_kind}@{event.canonical_revision}"
    for projection_type in projection_types_for(
        event.object_type,
        event.changed_fields,
    ):
        state, _created = ProjectionState.objects.select_for_update().get_or_create(
            object_type=event.object_type,
            object_id=event.object_id,
            projection_type=projection_type,
            defaults={
                "source_revision": event.canonical_revision,
                "projected_revision": 0,
                "status": ProjectionState.Status.STALE,
                "stale_reason": reason,
            },
        )
        fields: list[str] = []
        if event.canonical_revision > state.source_revision:
            state.source_revision = event.canonical_revision
            fields.append("source_revision")
        if state.projected_revision < state.source_revision:
            state.status = ProjectionState.Status.STALE
            state.stale_reason = reason
            # A lease for an earlier source revision must not be allowed to
            # mark this newer revision current.
            state.lease_token = None
            state.lease_expires_at = None
            fields.extend(["status", "stale_reason", "lease_token", "lease_expires_at"])
        if fields:
            state.save(update_fields=[*dict.fromkeys(fields), "updated_at"])
        states.append(state)
    event.processed_at = now
    event.lease_token = None
    event.lease_expires_at = None
    event.last_error_code = ""
    event.last_error_message = ""
    event.save(
        update_fields=[
            "processed_at",
            "lease_token",
            "lease_expires_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    transaction.on_commit(
        lambda event_id=event.id: _schedule_resolved_event(event_id)
    )
    return states


@transaction.atomic
def record_canonical_change(
    *,
    object_type: str,
    object_id,
    change_kind: str,
    idempotency_key: str,
    changed_fields: Iterable[str] | None = None,
    catalog_revision=None,
    actor=None,
    correlation_id=None,
    resolve: bool = True,
) -> DomainChangeEvent:
    """Advance one canonical revision and record exactly one durable event.

    Callers must supply a mutation-scoped idempotency key.  Retrying with the
    same key returns the original event and never advances the revision twice.
    """

    object_type = normalize_object_type(object_type)
    object_id = _uuid(object_id)
    idempotency_key = str(idempotency_key or "").strip()
    if not idempotency_key:
        raise ValueError("idempotency_key is required")
    if len(idempotency_key) > 200:
        raise ValueError("idempotency_key is too long")
    if change_kind not in DomainChangeEvent.ChangeKind.values:
        raise ValueError("unsupported change_kind")

    existing = DomainChangeEvent.objects.select_for_update().filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        if (
            existing.object_type != object_type
            or existing.object_id != object_id
            or existing.change_kind != change_kind
        ):
            raise ValueError("idempotency_key already belongs to another mutation")
        if resolve and existing.processed_at is None:
            _resolve_locked(existing)
        return existing

    CanonicalObjectRevision.objects.get_or_create(
        object_type=object_type,
        object_id=object_id,
        defaults={"current_revision": 0},
    )
    revision = CanonicalObjectRevision.objects.select_for_update().get(
        object_type=object_type,
        object_id=object_id,
    )
    # Recheck after the per-object lock.  This closes the race between two
    # concurrent retries that both observed the idempotency key as absent.
    existing = DomainChangeEvent.objects.select_for_update().filter(
        idempotency_key=idempotency_key
    ).first()
    if existing is not None:
        if (
            existing.object_type != object_type
            or existing.object_id != object_id
            or existing.change_kind != change_kind
        ):
            raise ValueError("idempotency_key already belongs to another mutation")
        if resolve and existing.processed_at is None:
            _resolve_locked(existing)
        return existing
    revision.current_revision += 1
    revision.save(update_fields=["current_revision", "updated_at"])
    event = DomainChangeEvent.objects.create(
        object_type=object_type,
        object_id=object_id,
        canonical_revision=revision.current_revision,
        change_kind=change_kind,
        changed_fields=_changed_fields(changed_fields),
        catalog_revision=catalog_revision,
        actor=actor,
        correlation_id=_uuid(correlation_id) if correlation_id else uuid.uuid4(),
        idempotency_key=idempotency_key,
    )
    if resolve:
        _resolve_locked(event)
    return event


@transaction.atomic
def resolve_domain_change(event_id, *, lease_token=None) -> list[ProjectionState]:
    event = DomainChangeEvent.objects.select_for_update().get(pk=event_id)
    if event.processed_at is not None:
        return list(
            ProjectionState.objects.filter(
                object_type=event.object_type,
                object_id=event.object_id,
                projection_type__in=projection_types_for(
                    event.object_type,
                    event.changed_fields,
                ),
            ).order_by("projection_type")
        )
    if lease_token is not None and event.lease_token != _uuid(lease_token):
        raise ValueError("domain change lease token does not match")
    return _resolve_locked(event)


@transaction.atomic
def claim_domain_change(*, lease_seconds: int = 120) -> DomainChangeLease | None:
    now = timezone.now()
    eligible = DomainChangeEvent.objects.filter(processed_at__isnull=True).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=now),
        Q(lease_expires_at__isnull=True) | Q(lease_expires_at__lte=now),
    ).order_by("created_at")
    if connection.features.has_select_for_update_skip_locked:
        eligible = eligible.select_for_update(skip_locked=True)
    else:
        eligible = eligible.select_for_update()
    event = eligible.first()
    if event is None:
        return None
    token = uuid.uuid4()
    expires_at = now + timedelta(seconds=max(15, int(lease_seconds)))
    event.lease_token = token
    event.lease_expires_at = expires_at
    event.attempts += 1
    event.save(update_fields=["lease_token", "lease_expires_at", "attempts", "updated_at"])
    return DomainChangeLease(
        event_id=event.id,
        canonical_revision=event.canonical_revision,
        lease_token=token,
        lease_expires_at=expires_at,
    )


@transaction.atomic
def renew_domain_change_lease(event_id, lease_token, *, lease_seconds: int = 120) -> DomainChangeLease:
    now = timezone.now()
    event = DomainChangeEvent.objects.select_for_update().get(pk=event_id)
    token = _uuid(lease_token)
    if event.processed_at is not None or event.lease_token != token:
        raise ValueError("domain change lease is no longer active")
    if event.lease_expires_at is not None and event.lease_expires_at <= now:
        raise ValueError("domain change lease has expired")
    event.lease_expires_at = now + timedelta(seconds=max(15, int(lease_seconds)))
    event.save(update_fields=["lease_expires_at", "updated_at"])
    return DomainChangeLease(
        event_id=event.id,
        canonical_revision=event.canonical_revision,
        lease_token=token,
        lease_expires_at=event.lease_expires_at,
    )


@transaction.atomic
def release_domain_change(
    event_id,
    lease_token,
    *,
    error_code: str,
    error_message: str,
    retry_after_seconds: int = 30,
) -> DomainChangeEvent:
    """Release a failed resolver attempt while preserving the durable event."""

    event = DomainChangeEvent.objects.select_for_update().get(pk=event_id)
    if event.processed_at is not None or event.lease_token != _uuid(lease_token):
        raise ValueError("domain change lease is no longer active")
    event.lease_token = None
    event.lease_expires_at = None
    event.last_error_code = str(error_code or "dependency_resolution_failed")[:120]
    event.last_error_message = str(error_message or "")[:4000]
    event.next_attempt_at = timezone.now() + timedelta(
        seconds=max(0, int(retry_after_seconds))
    )
    event.save(
        update_fields=[
            "lease_token",
            "lease_expires_at",
            "last_error_code",
            "last_error_message",
            "next_attempt_at",
            "updated_at",
        ]
    )
    return event


@transaction.atomic
def claim_projection(
    *,
    object_type: str,
    object_id,
    projection_type: str,
    owner_type: str = "",
    owner_key: str = "",
    lease_seconds: int = 300,
) -> ProjectionLease | None:
    now = timezone.now()
    state = ProjectionState.objects.select_for_update().get(
        object_type=normalize_object_type(object_type),
        object_id=_uuid(object_id),
        projection_type=projection_type,
    )
    if state.projected_revision >= state.source_revision:
        if state.status != ProjectionState.Status.CURRENT:
            state.status = ProjectionState.Status.CURRENT
            state.stale_reason = ""
            state.save(update_fields=["status", "stale_reason", "updated_at"])
        return None
    if (
        state.status == ProjectionState.Status.PROJECTING
        and state.lease_expires_at is not None
        and state.lease_expires_at > now
    ):
        return None
    token = uuid.uuid4()
    expires_at = now + timedelta(seconds=max(15, int(lease_seconds)))
    state.status = ProjectionState.Status.PROJECTING
    state.lease_token = token
    state.lease_expires_at = expires_at
    state.task_owner_type = str(owner_type or "")[:80]
    state.task_owner_key = str(owner_key or "")[:255]
    state.attempts += 1
    state.last_error_code = ""
    state.last_error_message = ""
    state.save(
        update_fields=[
            "status",
            "lease_token",
            "lease_expires_at",
            "task_owner_type",
            "task_owner_key",
            "attempts",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    return ProjectionLease(
        state_id=state.id,
        object_type=state.object_type,
        object_id=state.object_id,
        projection_type=state.projection_type,
        source_revision=state.source_revision,
        lease_token=token,
        lease_expires_at=expires_at,
    )


@transaction.atomic
def renew_projection_lease(state_id, lease_token, *, lease_seconds: int = 300) -> ProjectionLease:
    now = timezone.now()
    state = ProjectionState.objects.select_for_update().get(pk=state_id)
    token = _uuid(lease_token)
    if state.status != ProjectionState.Status.PROJECTING or state.lease_token != token:
        raise ValueError("projection lease is no longer active")
    if state.lease_expires_at is not None and state.lease_expires_at <= now:
        raise ValueError("projection lease has expired")
    state.lease_expires_at = now + timedelta(seconds=max(15, int(lease_seconds)))
    state.save(update_fields=["lease_expires_at", "updated_at"])
    return ProjectionLease(
        state_id=state.id,
        object_type=state.object_type,
        object_id=state.object_id,
        projection_type=state.projection_type,
        source_revision=state.source_revision,
        lease_token=token,
        lease_expires_at=state.lease_expires_at,
    )


@transaction.atomic
def complete_projection(state_id, lease_token, *, projected_revision: int) -> ProjectionState:
    state = ProjectionState.objects.select_for_update().get(pk=state_id)
    token = _uuid(lease_token)
    if state.status != ProjectionState.Status.PROJECTING or state.lease_token != token:
        raise ValueError("projection lease is no longer active")
    if state.lease_expires_at is None or state.lease_expires_at <= timezone.now():
        raise ValueError("projection lease has expired")
    revision = int(projected_revision)
    if revision > state.source_revision:
        raise ValueError("projected revision cannot be ahead of canonical source")
    state.projected_revision = max(state.projected_revision, revision)
    state.lease_token = None
    state.lease_expires_at = None
    state.last_projected_at = timezone.now()
    if state.projected_revision == state.source_revision:
        state.status = ProjectionState.Status.CURRENT
        state.stale_reason = ""
    else:
        state.status = ProjectionState.Status.STALE
        state.stale_reason = "newer canonical revision remains"
    state.save(
        update_fields=[
            "projected_revision",
            "lease_token",
            "lease_expires_at",
            "last_projected_at",
            "status",
            "stale_reason",
            "updated_at",
        ]
    )
    return state


@transaction.atomic
def mark_projection_failed(state_id, lease_token, *, error_code: str, error_message: str) -> ProjectionState:
    state = ProjectionState.objects.select_for_update().get(pk=state_id)
    if state.lease_token != _uuid(lease_token):
        raise ValueError("projection lease is no longer active")
    if state.lease_expires_at is None or state.lease_expires_at <= timezone.now():
        raise ValueError("projection lease has expired")
    state.status = ProjectionState.Status.FAILED
    state.lease_token = None
    state.lease_expires_at = None
    state.last_error_code = str(error_code or "projection_failed")[:120]
    state.last_error_message = str(error_message or "")[:4000]
    state.save(
        update_fields=[
            "status",
            "lease_token",
            "lease_expires_at",
            "last_error_code",
            "last_error_message",
            "updated_at",
        ]
    )
    return state


@transaction.atomic
def mark_projection_waiting(
    state_id,
    lease_token=None,
    *,
    reason: str,
    owner_type: str = "",
    owner_key: str = "",
) -> ProjectionState:
    """Release projection work that cannot currently be executed.

    A missing or paused executor is operational state rather than projection
    success.  Keeping the captured source revision unchanged lets the periodic
    capability reconciler resume exactly this object later.
    """

    state = ProjectionState.objects.select_for_update().get(pk=state_id)
    if lease_token is not None and state.lease_token != _uuid(lease_token):
        raise ValueError("projection lease is no longer active")
    if (
        lease_token is not None
        and (state.lease_expires_at is None or state.lease_expires_at <= timezone.now())
    ):
        raise ValueError("projection lease has expired")
    state.status = ProjectionState.Status.WAITING_FOR_CAPABILITY
    state.stale_reason = str(reason or "projection executor unavailable")[:300]
    state.lease_token = None
    state.lease_expires_at = None
    if owner_type:
        state.task_owner_type = str(owner_type)[:80]
    if owner_key:
        state.task_owner_key = str(owner_key)[:255]
    state.save(
        update_fields=[
            "status",
            "stale_reason",
            "lease_token",
            "lease_expires_at",
            "task_owner_type",
            "task_owner_key",
            "updated_at",
        ]
    )
    return state


@transaction.atomic
def reclaim_expired_projection_leases(*, at=None, limit: int = 100) -> int:
    """Make abandoned projection work retryable without accepting its token."""

    at = at or timezone.now()
    candidates = ProjectionState.objects.select_for_update().filter(
        status=ProjectionState.Status.PROJECTING,
        lease_expires_at__lte=at,
        source_revision__gt=F("projected_revision"),
    ).order_by("lease_expires_at")[: max(1, min(int(limit), 500))]
    state_ids = [state.id for state in candidates]
    if not state_ids:
        return 0
    ProjectionState.objects.filter(pk__in=state_ids).update(
        status=ProjectionState.Status.STALE,
        stale_reason="projection lease expired before verified completion",
        lease_token=None,
        lease_expires_at=None,
        last_error_code="projection_lease_expired",
        last_error_message=(
            "The previous projection owner did not complete before its lease expired."
        ),
        updated_at=at,
    )
    return len(state_ids)


@transaction.atomic
def bind_projection_task(
    *,
    object_type: str,
    object_id,
    projection_types: Iterable[str],
    owner_type: str,
    owner_key: str,
) -> int:
    """Attach an existing specialist job to known projection states.

    This is intentionally a no-op before the canonical revision inventory has
    created states.  A manual refresh must not fabricate a canonical revision.
    """

    states = ProjectionState.objects.select_for_update().filter(
        object_type=normalize_object_type(object_type),
        object_id=_uuid(object_id),
        projection_type__in=tuple(projection_types),
    )
    return states.update(
        task_owner_type=str(owner_type or "")[:80],
        task_owner_key=str(owner_key or "")[:255],
        updated_at=timezone.now(),
    )


@transaction.atomic
def mark_projection_revision_current(
    *,
    object_type: str,
    object_id,
    projection_type: str,
    projected_revision: int,
) -> ProjectionState | None:
    """Record synchronous projection work against its captured source revision."""

    state = ProjectionState.objects.select_for_update().filter(
        object_type=normalize_object_type(object_type),
        object_id=_uuid(object_id),
        projection_type=projection_type,
    ).first()
    if state is None:
        return None
    revision = int(projected_revision)
    if revision > state.source_revision:
        raise ValueError("projected revision cannot be ahead of canonical source")
    state.projected_revision = max(state.projected_revision, revision)
    state.last_projected_at = timezone.now()
    state.lease_token = None
    state.lease_expires_at = None
    if state.projected_revision == state.source_revision:
        state.status = ProjectionState.Status.CURRENT
        state.stale_reason = ""
    else:
        state.status = ProjectionState.Status.STALE
        state.stale_reason = "newer canonical revision remains"
    state.save(
        update_fields=[
            "projected_revision",
            "last_projected_at",
            "lease_token",
            "lease_expires_at",
            "status",
            "stale_reason",
            "updated_at",
        ]
    )
    return state


def stale_projection_summary() -> dict[str, int]:
    """Small Processing Center view of knowledge freshness, not process health."""

    rows = (
        ProjectionState.objects.exclude(status=ProjectionState.Status.CURRENT)
        .values("projection_type", "status")
        .order_by()
    )
    summary: dict[str, int] = {}
    for row in rows:
        key = f"{row['projection_type']}:{row['status']}"
        summary[key] = summary.get(key, 0) + 1
    return summary
