from __future__ import annotations

from collections.abc import Iterable
from datetime import timedelta
from difflib import SequenceMatcher
import json
import re
import uuid

import httpx
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from catalog.models import (
    Asset,
    DerivedClaim,
    DocumentRevision,
    ProjectionState,
    PublicationState,
)
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.semantic_search import YEAR_FILTERS, viewer_access_statuses
from ingestion.services.indexing import _headers, _wait_task


DEFAULT_CLAIM_INDEX_UID = "derived_claims"
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'_-]{1,}|[\u3400-\u9fff]{2,}", re.IGNORECASE)

SEARCHABLE_ATTRIBUTES = [
    "proposition",
    "subject",
    "predicate",
    "object",
    "qualifiers_text",
    "evidence_text",
    "title",
    "authors",
]
FILTERABLE_ATTRIBUTES = [
    "claim_id",
    "document_revision_id",
    "evidence_span_id",
    "asset_id",
    "edition_id",
    "work_id",
    "document_type",
    "language",
    "publication_year",
    "author_ids",
    "claim_type",
    "attribution",
    "polarity",
    "status",
    "shadow",
    "is_public",
    "access_status",
    "document_revision_active",
    "evidence_stale",
]
DISPLAYED_ATTRIBUTES = [
    "id",
    "claim_id",
    "document_revision_id",
    "evidence_span_id",
    "asset_id",
    "edition_id",
    "work_id",
    "title",
    "authors",
    "author_ids",
    "document_type",
    "language",
    "publication_year",
    "proposition",
    "subject",
    "predicate",
    "object",
    "polarity",
    "modality",
    "qualifiers",
    "temporal_scope",
    "geographic_scope",
    "population_scope",
    "attribution",
    "claim_type",
    "quality_score",
    "importance_score",
    "cluster_key",
    "evidence_text",
    "page_number",
    "printed_page_label",
    "reader_url",
    "status",
    "shadow",
    "is_public",
    "access_status",
    "document_revision_active",
    "evidence_stale",
]


def claim_index_uid() -> str:
    return str(getattr(settings, "CLAIM_INDEX_UID", DEFAULT_CLAIM_INDEX_UID) or DEFAULT_CLAIM_INDEX_UID)


def _base_url() -> str:
    return settings.MEILISEARCH_URL.rstrip("/")


def _post_timeout() -> int:
    return max(15, int(getattr(settings, "SEMANTIC_SEARCH_TIMEOUT_SECONDS", 30)))


def ensure_claim_index() -> None:
    """Create/configure a Claim index on the existing Meilisearch service."""

    uid = claim_index_uid()
    response = httpx.get(f"{_base_url()}/indexes/{uid}", headers=_headers(), timeout=5)
    if response.status_code == 404:
        created = httpx.post(
            f"{_base_url()}/indexes",
            headers=_headers(),
            json={"uid": uid, "primaryKey": "id"},
            timeout=5,
        )
        created.raise_for_status()
        _wait_task(created.json())
    else:
        response.raise_for_status()

    current_response = httpx.get(
        f"{_base_url()}/indexes/{uid}/settings",
        headers=_headers(),
        timeout=5,
    )
    current_response.raise_for_status()
    current = current_response.json()
    if (
        current.get("searchableAttributes") == SEARCHABLE_ATTRIBUTES
        and current.get("filterableAttributes") == FILTERABLE_ATTRIBUTES
        and current.get("displayedAttributes") == DISPLAYED_ATTRIBUTES
    ):
        return
    updated = httpx.patch(
        f"{_base_url()}/indexes/{uid}/settings",
        headers=_headers(),
        json={
            "searchableAttributes": SEARCHABLE_ATTRIBUTES,
            "filterableAttributes": FILTERABLE_ATTRIBUTES,
            "displayedAttributes": DISPLAYED_ATTRIBUTES,
            "searchCutoffMs": 1200,
        },
        timeout=5,
    )
    updated.raise_for_status()
    _wait_task(updated.json())


def _approved_contributors(claim: DerivedClaim) -> tuple[list[str], list[str]]:
    rows = list(
        claim.edition.contributions.filter(approved=True)
        .order_by("order")
        .values_list("person_id", "person__preferred_name")
    )
    return [str(row[0]) for row in rows], [str(row[1]) for row in rows]


def serialize_claim_document(claim: DerivedClaim) -> dict:
    """Serialize a claim only when its PDF locator is still valid."""

    revision = claim.document_revision
    evidence = claim.primary_evidence
    asset = revision.asset
    if evidence.document_revision_id != revision.id:
        raise ValueError("claim primary evidence belongs to another document revision")
    if evidence.page.asset_id != asset.id:
        raise ValueError("claim evidence page belongs to another asset")
    author_ids, authors = _approved_contributors(claim)
    envelope = evidence_span_envelope(evidence)
    is_public = (
        claim.edition.state == PublicationState.PUBLISHED
        and claim.edition.is_primary
        and asset.kind == Asset.Kind.NORMALIZED
        and asset.status == Asset.Status.READY
        and asset.is_current
    )
    return {
        "id": str(claim.id),
        "claim_id": str(claim.id),
        "document_revision_id": str(revision.id),
        "evidence_span_id": str(evidence.id),
        "asset_id": str(asset.id),
        "edition_id": str(claim.edition_id),
        "work_id": str(claim.work_id),
        "title": claim.work.title,
        "authors": authors,
        "author_ids": author_ids,
        "document_type": claim.work.document_type,
        "language": evidence.language or claim.work.language,
        "publication_year": claim.edition.publication_year,
        "proposition": claim.proposition,
        "subject": claim.subject,
        "predicate": claim.predicate,
        "object": claim.object,
        "polarity": claim.polarity,
        "modality": claim.modality,
        "qualifiers": claim.qualifiers,
        "qualifiers_text": " ".join(str(row) for row in (claim.qualifiers or [])),
        "temporal_scope": claim.temporal_scope,
        "geographic_scope": claim.geographic_scope,
        "population_scope": claim.population_scope,
        "attribution": claim.attribution,
        "claim_type": claim.claim_type,
        "quality_score": claim.quality_score,
        "importance_score": claim.importance_score,
        "cluster_key": claim.cluster_key,
        "evidence_text": evidence.original_text,
        "page_number": evidence.page_number,
        "printed_page_label": evidence.printed_page_label,
        "reader_url": envelope.reader_url,
        "status": claim.status,
        "shadow": claim.shadow,
        "is_public": is_public,
        "access_status": asset.access_status,
        "document_revision_active": revision.is_active,
        "evidence_stale": evidence.is_stale,
    }


def _fetch_revision_document_ids(revision_id: str) -> set[str]:
    uid = claim_index_uid()
    offset = 0
    limit = 1000
    output: set[str] = set()
    while True:
        response = httpx.post(
            f"{_base_url()}/indexes/{uid}/documents/fetch",
            headers=_headers(),
            json={
                "filter": f'document_revision_id = {json.dumps(str(revision_id))}',
                "offset": offset,
                "limit": limit,
                "fields": ["id"],
            },
            timeout=_post_timeout(),
        )
        response.raise_for_status()
        payload = response.json()
        rows = payload.get("results") or []
        output.update(str(row["id"]) for row in rows if row.get("id"))
        total = int(payload.get("total") or len(output))
        if offset + len(rows) >= total:
            return output
        if not rows:
            raise RuntimeError("Claim Index 文档分页提前结束。")
        offset += len(rows)


def _sync_claim_documents(revision_id: str, documents: list[dict]) -> dict:
    ensure_claim_index()
    uid = claim_index_uid()
    task = None
    if documents:
        response = httpx.post(
            f"{_base_url()}/indexes/{uid}/documents",
            headers=_headers(),
            json=documents,
            timeout=_post_timeout(),
        )
        response.raise_for_status()
        task = _wait_task(response.json(), timeout=max(45, _post_timeout()))
    revision = DocumentRevision.objects.only("asset_id", "is_active").get(pk=revision_id)
    cleanup_revision_ids = {str(revision.id)}
    if revision.is_active:
        cleanup_revision_ids.update(
            str(value)
            for value in DocumentRevision.objects.filter(asset_id=revision.asset_id)
            .exclude(pk=revision.pk)
            .values_list("pk", flat=True)
        )
    current_ids = {str(document["id"]) for document in documents}
    stale_ids: set[str] = set()
    for cleanup_revision_id in cleanup_revision_ids:
        indexed = _fetch_revision_document_ids(cleanup_revision_id)
        stale_ids.update(
            indexed - current_ids
            if cleanup_revision_id == str(revision.id)
            else indexed
        )
    stale_ids = sorted(stale_ids)
    for offset in range(0, len(stale_ids), 1000):
        response = httpx.post(
            f"{_base_url()}/indexes/{uid}/documents/delete-batch",
            headers=_headers(),
            json=stale_ids[offset : offset + 1000],
            timeout=_post_timeout(),
        )
        response.raise_for_status()
        _wait_task(response.json(), timeout=max(45, _post_timeout()))
    return {
        "backend": "meilisearch",
        "index_uid": uid,
        "documents": len(documents),
        "removed_stale_documents": len(stale_ids),
        "cleaned_revision_count": len(cleanup_revision_ids),
        "task": task,
    }


def _projection_objects(
    revision: DocumentRevision,
    claims: Iterable[DerivedClaim],
) -> list[tuple[str, uuid.UUID, int]]:
    rows = [("document_revision", revision.id, max(1, revision.revision))]
    rows.extend(
        ("derived_claim", claim.id, max(1, revision.revision))
        for claim in claims
    )
    return rows


@transaction.atomic
def _begin_projection(
    revision: DocumentRevision,
    claims: list[DerivedClaim],
) -> list[tuple[uuid.UUID, int]]:
    captured = []
    for object_type, object_id, source_revision in _projection_objects(revision, claims):
        state, _created = ProjectionState.objects.select_for_update().get_or_create(
            object_type=object_type,
            object_id=object_id,
            projection_type=ProjectionState.ProjectionType.CLAIM_INDEX,
            defaults={
                "source_revision": source_revision,
                "projected_revision": 0,
                "status": ProjectionState.Status.STALE,
                "stale_reason": "claim index not projected",
            },
        )
        if source_revision > state.source_revision:
            state.source_revision = source_revision
        state.status = ProjectionState.Status.PROJECTING
        state.lease_token = uuid.uuid4()
        state.lease_expires_at = timezone.now() + timedelta(minutes=5)
        state.task_owner_type = "document_revision"
        state.task_owner_key = str(revision.id)
        state.attempts += 1
        state.last_error_code = ""
        state.last_error_message = ""
        state.save(
            update_fields=[
                "source_revision",
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
        captured.append((state.id, state.source_revision))
    return captured


@transaction.atomic
def _finish_projection(captured: list[tuple[uuid.UUID, int]]) -> None:
    now = timezone.now()
    for state_id, source_revision in captured:
        state = ProjectionState.objects.select_for_update().get(pk=state_id)
        state.projected_revision = max(state.projected_revision, source_revision)
        state.last_projected_at = now
        state.lease_token = None
        state.lease_expires_at = None
        if state.projected_revision >= state.source_revision:
            state.projected_revision = state.source_revision
            state.status = ProjectionState.Status.CURRENT
            state.stale_reason = ""
        else:
            state.status = ProjectionState.Status.STALE
            state.stale_reason = "newer claim source revision remains"
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


@transaction.atomic
def _fail_projection(captured: list[tuple[uuid.UUID, int]], exc: Exception) -> None:
    for state_id, _source_revision in captured:
        state = ProjectionState.objects.select_for_update().get(pk=state_id)
        state.status = ProjectionState.Status.FAILED
        state.lease_token = None
        state.lease_expires_at = None
        state.last_error_code = exc.__class__.__name__[:120]
        state.last_error_message = str(exc)[:4000]
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


def index_document_revision_claims(
    revision: DocumentRevision,
    *,
    writer=None,
    required: bool | None = None,
    track_projection: bool = True,
) -> dict:
    """Synchronize one revision's active claims and their projection state.

    ``track_projection=False`` is reserved for the v3 projection coordinator,
    which already owns a revision-aware lease for the same operation. This
    avoids replacing its token with a second specialist lease while keeping
    direct claim-pipeline calls backward compatible.
    """

    claims = list(
        DerivedClaim.objects.filter(
            document_revision=revision,
            status=DerivedClaim.Status.ACTIVE,
            primary_evidence__is_stale=False,
        )
        .select_related(
            "document_revision__asset__edition__work",
            "primary_evidence__page__asset",
            "edition__work",
        )
        .prefetch_related("edition__contributions__person")
        .order_by("id")
    )
    documents = [serialize_claim_document(claim) for claim in claims]
    captured = _begin_projection(revision, claims) if track_projection else []
    sync = writer or _sync_claim_documents
    try:
        result = sync(str(revision.id), documents)
    except (httpx.HTTPError, RuntimeError, TimeoutError, ValueError) as exc:
        if captured:
            _fail_projection(captured, exc)
        must_raise = bool(
            getattr(settings, "CLAIM_INDEX_REQUIRED", False)
            if required is None
            else required
        )
        if must_raise:
            raise
        return {
            "status": "degraded",
            "backend": "database-fallback",
            "documents": len(documents),
            "error_code": exc.__class__.__name__,
            "warning": str(exc)[:500],
            "publication_blocking": False,
        }
    if captured:
        _finish_projection(captured)
    return {
        "status": "completed",
        **(result if isinstance(result, dict) else {"documents": len(documents)}),
        "publication_blocking": False,
    }


def _json_value(value: object) -> str:
    return json.dumps(str(value), ensure_ascii=False)


def _search_filters(filters: dict) -> list[str]:
    allowed_access = filters.get("_allowed_access_statuses") or viewer_access_statuses()
    output = [
        'status = "active"',
        "document_revision_active = true",
        "evidence_stale = false",
        "is_public = true",
        "access_status IN [" + ", ".join(_json_value(row) for row in allowed_access) + "]",
    ]
    mapping = {
        "work_ids": "work_id",
        "document_types": "document_type",
        "languages": "language",
        "authors": "author_ids",
    }
    for source, target in mapping.items():
        values = filters.get(source) or []
        if source == "document_types":
            values = ["journal_article" if value in {"article", "journal_article"} else value for value in values]
        if values:
            output.append(f"{target} IN [{', '.join(_json_value(row) for row in values)}]")
    year_groups = []
    for value in filters.get("years") or []:
        start, end = YEAR_FILTERS.get(value, (None, None))
        parts = []
        if start is not None:
            parts.append(f"publication_year >= {start}")
        if end is not None:
            parts.append(f"publication_year <= {end}")
        if parts:
            year_groups.append("(" + " AND ".join(parts) + ")")
    if year_groups:
        output.append("(" + " OR ".join(year_groups) + ")")
    return output


def visible_claim_queryset(filters: dict | None = None):
    filters = dict(filters or {})
    allowed_access = filters.get("_allowed_access_statuses") or viewer_access_statuses()
    rows = DerivedClaim.objects.filter(
        status=DerivedClaim.Status.ACTIVE,
        document_revision__is_active=True,
        primary_evidence__is_stale=False,
        edition__state=PublicationState.PUBLISHED,
        edition__is_primary=True,
        document_revision__asset__kind=Asset.Kind.NORMALIZED,
        document_revision__asset__status=Asset.Status.READY,
        document_revision__asset__is_current=True,
        document_revision__asset__access_status__in=allowed_access,
    )
    if filters.get("work_ids"):
        rows = rows.filter(work_id__in=filters["work_ids"])
    if filters.get("document_types"):
        values = [
            "journal_article" if value in {"article", "journal_article"} else value
            for value in filters["document_types"]
        ]
        rows = rows.filter(work__document_type__in=values)
    if filters.get("languages"):
        rows = rows.filter(Q(primary_evidence__language__in=filters["languages"]) | Q(work__language__in=filters["languages"]))
    if filters.get("authors"):
        rows = rows.filter(
            edition__contributions__person_id__in=filters["authors"],
            edition__contributions__approved=True,
        )
    if filters.get("years"):
        condition = Q()
        for value in filters["years"]:
            start, end = YEAR_FILTERS.get(value, (None, None))
            branch = Q()
            if start is not None:
                branch &= Q(edition__publication_year__gte=start)
            if end is not None:
                branch &= Q(edition__publication_year__lte=end)
            if start is not None or end is not None:
                condition |= branch
        if condition:
            rows = rows.filter(condition)
    return rows.distinct()


def _tokens(value: str) -> set[str]:
    return {match.group(0).casefold() for match in _TOKEN_RE.finditer(str(value or ""))}


def _database_claim_search(query: str, filters: dict, limit: int) -> dict:
    query_tokens = _tokens(query)
    candidates = list(
        visible_claim_queryset(filters)
        .select_related(
            "document_revision__asset__edition__work",
            "primary_evidence__page__asset",
            "edition__work",
        )
        .prefetch_related("edition__contributions__person")[:500]
    )
    ranked = []
    for claim in candidates:
        candidate_text = " ".join(
            (
                claim.proposition,
                claim.subject,
                claim.predicate,
                claim.object,
                " ".join(str(row) for row in (claim.qualifiers or [])),
            )
        )
        candidate_tokens = _tokens(candidate_text)
        overlap = len(query_tokens & candidate_tokens) / max(1, len(query_tokens))
        phrase = SequenceMatcher(None, query.casefold()[:600], claim.proposition.casefold()[:1200]).ratio()
        score = overlap * 0.55 + phrase * 0.2 + claim.quality_score * 0.1 + claim.importance_score * 0.15
        if score > 0.01:
            document = serialize_claim_document(claim)
            document["_rankingScore"] = round(score, 6)
            ranked.append((score, document))
    ranked.sort(key=lambda row: (-row[0], row[1]["id"]))
    return {
        "backend": "database-fallback",
        "index_uid": claim_index_uid(),
        "hits": [row[1] for row in ranked[:limit]],
    }


def search_claim_index(
    query: str,
    *,
    filters: dict | None = None,
    limit: int = 60,
) -> dict:
    query = str(query or "").strip()
    if not query:
        return {"backend": "none", "index_uid": claim_index_uid(), "hits": []}
    bounded_limit = max(1, min(int(limit), 200))
    normalized_filters = dict(filters or {})
    try:
        response = httpx.post(
            f"{_base_url()}/indexes/{claim_index_uid()}/search",
            headers=_headers(),
            json={
                "q": query[:2000],
                "limit": bounded_limit,
                "filter": " AND ".join(_search_filters(normalized_filters)),
                "attributesToRetrieve": DISPLAYED_ATTRIBUTES,
                "showRankingScore": True,
            },
            timeout=min(8, _post_timeout()),
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "backend": "meilisearch",
            "index_uid": claim_index_uid(),
            "hits": payload.get("hits") or [],
            "estimated_total_hits": payload.get("estimatedTotalHits"),
            "processing_time_ms": payload.get("processingTimeMs"),
        }
    except (httpx.HTTPError, RuntimeError, TimeoutError, ValueError) as exc:
        fallback = _database_claim_search(query, normalized_filters, bounded_limit)
        fallback["warning"] = str(exc)[:500]
        fallback["error_code"] = exc.__class__.__name__
        return fallback


index_claim_revision = index_document_revision_claims
