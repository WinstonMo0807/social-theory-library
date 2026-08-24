from __future__ import annotations

from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from hashlib import sha256
import logging
import re
import time
from typing import Any

from django.db.models import Q

from catalog.models import DerivedClaim, EvidenceSpan, Page, SemanticChunk
from catalog.services.claims.indexing import search_claim_index, visible_claim_queryset
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.passage_language import detect_passage_language
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.retrieval import unified_retrieve
from catalog.services.semantic_indexing import active_semantic_index_uid
from catalog.services.semantic_search import semantic_search  # legacy monkeypatch seam

from .library_query import (
    LibraryQuery,
    LibraryQueryType,
    LibraryScopeError,
    ResolvedLibraryScope,
    normalize_library_scope,
    resolve_library_scope,
)


LIBRARY_RETRIEVAL_VERSION = "library-retrieval-v3"
UNIFIED_RETRIEVAL_PROFILE = "reader_qa"
_CLAIM_FILTER_KEYS = frozenset(
    {
        "work_ids",
        "document_types",
        "languages",
        "authors",
        "years",
        "_allowed_access_statuses",
    }
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LibraryEvidence:
    evidence_id: str
    work_id: str
    work_title: str
    edition_id: str
    asset_id: str
    page_id: str
    page_index: int | None
    printed_label: str
    semantic_chunk_id: str
    document_id: str
    original_passage: str
    language: str
    authors: tuple[str, ...] = ()
    chapter_title: str = ""
    section_title: str = ""
    reader_url: str = ""
    retrieval_provenance: dict[str, Any] = field(default_factory=dict)

    def source_row(self) -> dict:
        return {
            "id": self.semantic_chunk_id or self.document_id or self.evidence_id,
            "document_id": self.document_id,
            "asset_id": self.asset_id,
            "edition_id": self.edition_id,
            "work_id": self.work_id,
            "page_id": self.page_id,
            "title": self.work_title,
            "authors": list(self.authors),
            "page_index": self.page_index,
            "printed_label": self.printed_label,
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
            "snippet": self.original_passage,
            "language": self.language,
            "reader_url": self.reader_url,
            "retrieval_provenance": self.retrieval_provenance,
        }

    def debug_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class LibraryRetrievalResult:
    evidence: tuple[LibraryEvidence, ...]
    sufficient: bool
    insufficiency_reason: str
    metadata: dict[str, Any]


def _strip_quotes(value: str) -> str:
    return value.strip().strip('"“”‘’《》〈〉「」『』').strip()


def _semantic_call(
    query: str,
    *,
    resolved_scope: ResolvedLibraryScope,
    retrieval_profile: str,
    limit: int,
    max_per_work: int,
    strategy: str = "hybrid_rerank",
) -> dict:
    if resolved_scope.empty:
        return {
            "results": [],
            "engine": "scope_empty",
            "fallback_used": False,
            "search_version": "v2",
            "library_requested_profile": retrieval_profile,
            "unified_retrieval_profile": UNIFIED_RETRIEVAL_PROFILE,
        }
    # ``stable`` and ``experimental_v2`` remain accepted API values during the
    # migration.  Execution is owned by the shared reader_qa profile so Ask no
    # longer maintains a second semantic retrieval configuration.
    response = unified_retrieve(
        query,
        profile=UNIFIED_RETRIEVAL_PROFILE,
        filters=resolved_scope.semantic_filters,
        limit=limit,
        max_per_work=max_per_work,
        debug=True,
    )
    return {
        **response,
        "library_requested_profile": retrieval_profile,
        "unified_retrieval_profile": UNIFIED_RETRIEVAL_PROFILE,
        "library_requested_strategy": strategy,
    }


def _merge_resolved_scopes(
    base: ResolvedLibraryScope,
    anchor: ResolvedLibraryScope,
) -> ResolvedLibraryScope:
    filters: dict[str, list[str]] = {}
    empty = bool(base.empty or anchor.empty)
    for key in set(base.semantic_filters) | set(anchor.semantic_filters):
        base_values = base.semantic_filters.get(key)
        anchor_values = anchor.semantic_filters.get(key)
        if base_values is not None and anchor_values is not None:
            values = sorted(set(base_values) & set(anchor_values))
            if not values:
                empty = True
        else:
            values = list(base_values if base_values is not None else anchor_values or [])
        filters[key] = values
    return ResolvedLibraryScope(
        scope=base.scope,
        semantic_filters=filters,
        asset_id=base.asset_id,
        labels=tuple(dict.fromkeys((*base.labels, *anchor.labels))),
        empty=empty,
    )


def _anchor_resolved_scope(
    row: dict,
    *,
    base_scope: ResolvedLibraryScope,
) -> ResolvedLibraryScope | None:
    ambiguity = row.get("ambiguity") or {}
    if ambiguity.get("is_ambiguous") or ambiguity.get("expansion_suppressed"):
        return None
    entity = row.get("canonical_entity") or {}
    entity_type = str(entity.get("entity_type") or "")
    entity_id = str(entity.get("entity_id") or "")
    context = {
        "person": "scholars",
        "knowledge_node": "theories",
        "discipline": "disciplines",
        "subdiscipline": "subdisciplines",
        "topic": "topics",
    }.get(entity_type)
    if not context or not entity_id:
        return None
    try:
        anchor_scope = resolve_library_scope(
            normalize_library_scope({"context": context, "ids": [entity_id]})
        )
    except (LibraryScopeError, ValueError):
        return None
    return _merge_resolved_scopes(base_scope, anchor_scope)


def _retrieval_anchors(
    library_query: LibraryQuery,
    resolved_scope: ResolvedLibraryScope,
) -> list[dict]:
    limit = max(
        1,
        min(int(library_query.retrieval_limits.get("max_entity_branches", 3)), 4),
    )
    output = []
    seen = set()
    for row in library_query.entity_anchors:
        entity = row.get("canonical_entity") or {}
        entity_id = str(entity.get("entity_id") or "")
        label = str(entity.get("canonical_label") or "").strip()
        if not entity_id or not label or entity_id in seen:
            continue
        anchor_scope = _anchor_resolved_scope(row, base_scope=resolved_scope)
        if anchor_scope is None:
            continue
        seen.add(entity_id)
        output.append({"id": entity_id, "label": label, "scope": anchor_scope})
        if len(output) >= limit:
            break
    return output


def _result_rows(
    library_query: LibraryQuery,
    resolved_scope: ResolvedLibraryScope,
) -> tuple[list[dict], list[dict]]:
    max_passages = library_query.retrieval_limits["max_passages"]
    per_work = library_query.retrieval_limits["per_work_cap"]
    diagnostics = []
    rows: list[dict] = []
    if library_query.query_type == LibraryQueryType.QUOTED_PHRASE:
        exact = _strip_quotes(library_query.original_query)
        response = _semantic_call(
            exact,
            resolved_scope=resolved_scope,
            retrieval_profile="stable",
            limit=max(20, max_passages * 2),
            max_per_work=max(per_work, 3),
            strategy="keyword",
        )
        normalized_exact = normalize_term(exact)
        for row in response.get("results", []):
            if normalized_exact and normalized_exact in normalize_term(row.get("snippet")):
                rows.append({**row, "_retrieval_branch": "quoted_exact"})
        diagnostics.append({"branch": "quoted_exact", "response": response})
        return rows, diagnostics

    if library_query.query_type == LibraryQueryType.COMPARISON:
        anchors = _retrieval_anchors(library_query, resolved_scope)
        per_anchor = library_query.retrieval_limits["comparison_per_anchor"]
        for anchor in anchors:
            response = _semantic_call(
                f"{library_query.resolved_query} {anchor['label']}",
                resolved_scope=anchor["scope"],
                retrieval_profile=library_query.retrieval_profile,
                limit=max(4, per_anchor * 3),
                max_per_work=per_work,
            )
            rows.extend(
                {
                    **row,
                    "_retrieval_branch": "comparison_anchor",
                    "_coverage_entity_id": anchor["id"],
                    "_coverage_entity_label": anchor["label"],
                }
                for row in response.get("results", [])
            )
            diagnostics.append({
                "branch": "comparison_anchor",
                "anchor": {"id": anchor["id"], "label": anchor["label"]},
                "response": response,
            })
        response = _semantic_call(
            library_query.resolved_query,
            resolved_scope=resolved_scope,
            retrieval_profile=library_query.retrieval_profile,
            limit=max(6, max_passages),
            max_per_work=per_work,
        )
        rows.extend({**row, "_retrieval_branch": "comparison_shared"} for row in response.get("results", []))
        diagnostics.append({"branch": "comparison_shared", "response": response})
        return rows, diagnostics

    for anchor in _retrieval_anchors(library_query, resolved_scope):
        response = _semantic_call(
            library_query.resolved_query,
            resolved_scope=anchor["scope"],
            retrieval_profile=library_query.retrieval_profile,
            limit=max(4, max_passages),
            max_per_work=per_work,
        )
        rows.extend(
            {
                **row,
                "_retrieval_branch": "entity_anchor",
                "_coverage_entity_id": anchor["id"],
                "_coverage_entity_label": anchor["label"],
            }
            for row in response.get("results", [])
        )
        diagnostics.append({"branch": "entity_anchor", "anchor": {"id": anchor["id"], "label": anchor["label"]}, "response": response})

    response = _semantic_call(
        library_query.resolved_query,
        resolved_scope=resolved_scope,
        retrieval_profile=library_query.retrieval_profile,
        limit=max(12, max_passages * 2),
        max_per_work=per_work,
    )
    rows.extend({**row, "_retrieval_branch": "primary"} for row in response.get("results", []))
    diagnostics.append({"branch": "primary", "response": response})
    return rows, diagnostics


def _row_page_number(row: dict) -> int | None:
    try:
        return int(row.get("page_index") or row.get("page_start") or 0) or None
    except (TypeError, ValueError):
        return None


def _matching_span(
    row: dict,
    candidates: list[EvidenceSpan],
) -> EvidenceSpan | None:
    if not candidates:
        return None
    row_hash = str(row.get("content_hash") or "").strip()
    if row_hash:
        hashed = [span for span in candidates if span.content_hash == row_hash]
        if hashed:
            return max(hashed, key=lambda span: span.quality)
    snippet = normalize_term(row.get("snippet"))
    if not snippet:
        return None
    exact = [
        span
        for span in candidates
        if snippet in normalize_term(span.original_text)
        or normalize_term(span.original_text) in snippet
    ]
    if exact:
        return max(exact, key=lambda span: (span.quality, -abs(len(span.original_text) - len(snippet))))
    ranked = sorted(
        (
            SequenceMatcher(
                None,
                snippet[:1600],
                normalize_term(span.original_text)[:2400],
            ).ratio(),
            span.quality,
            str(span.id),
            span,
        )
        for span in candidates
    )
    if ranked and ranked[-1][0] >= 0.55:
        return ranked[-1][3]
    return None


def _evidence_spans_by_page(rows: list[dict]) -> dict[tuple[str, int], list[EvidenceSpan]]:
    lookups = {
        (str(row.get("asset_id") or ""), page_number)
        for row in rows
        if row.get("asset_id") and (page_number := _row_page_number(row))
    }
    if not lookups:
        return {}
    asset_ids = {asset_id for asset_id, _page_number in lookups}
    page_numbers = {page_number for _asset_id, page_number in lookups}
    spans = (
        EvidenceSpan.objects.filter(
            document_revision__asset_id__in=asset_ids,
            document_revision__is_active=True,
            page_number__in=page_numbers,
            is_stale=False,
        )
        .select_related(
            "document_revision__asset__edition__work",
            "page",
        )
        .prefetch_related("document_revision__asset__edition__contributions__person")
        .order_by("page_number", "start_offset")
    )
    output: dict[tuple[str, int], list[EvidenceSpan]] = {}
    for span in spans:
        key = (str(span.document_revision.asset_id), span.page_number)
        if key in lookups:
            output.setdefault(key, []).append(span)
    return output


def _hydrate_evidence(rows: list[dict], *, retrieval_profile: str) -> list[LibraryEvidence]:
    chunk_ids = []
    for row in rows:
        value = str(row.get("id") or "")
        if value and not value.startswith("passage:"):
            chunk_ids.append(value)
    chunks = {
        str(chunk.id): chunk
        for chunk in SemanticChunk.objects.filter(id__in=chunk_ids).select_related("asset")
    }
    page_lookups = {
        (str(row.get("asset_id") or ""), _row_page_number(row))
        for row in rows
        if row.get("asset_id") and _row_page_number(row)
    }
    page_query = Q()
    for asset_id, page_index in page_lookups:
        page_query |= Q(asset_id=asset_id, index=page_index)
    pages = {}
    if page_query:
        pages = {
            (str(page.asset_id), page.index): page
            for page in Page.objects.filter(page_query)
        }
    spans_by_page = _evidence_spans_by_page(rows)
    output = []
    for index, row in enumerate(rows, start=1):
        asset_id = str(row.get("asset_id") or "")
        page_index = _row_page_number(row)
        chunk = chunks.get(str(row.get("id") or ""))
        page = pages.get((asset_id, page_index or 0))
        passage = str(row.get("snippet") or "").strip()
        if not passage:
            continue
        span = _matching_span(row, spans_by_page.get((asset_id, page_index or 0), []))
        if span is not None:
            envelope = evidence_span_envelope(span)
            revision = span.document_revision
            asset = revision.asset
            edition = asset.edition
            work = edition.work
            passage = span.original_text
            asset_id = str(asset.id)
            page = span.page
            page_index = span.page_number or span.page.index
            row_authors = envelope.source.get("authors") or row.get("authors") or []
        else:
            envelope = None
            work = edition = None
            row_authors = row.get("authors") or []
        language = (
            str(span.language if span else "").strip()
            or
            str(getattr(chunk, "language", "") or "").strip()
            or str(row.get("language") or "").strip()
            or detect_passage_language(passage)
        )
        document_id = str(getattr(chunk, "document_id", "") or row.get("document_id") or "")
        semantic_chunk_id = str(chunk.id) if chunk else ""
        evidence_id = document_id or semantic_chunk_id or str(row.get("id") or f"evidence-{index}")
        provenance = {
            "retrieval_profile": retrieval_profile,
            "branch": row.get("_retrieval_branch", "primary"),
            "coverage_entity_id": row.get("_coverage_entity_id", ""),
            "coverage_entity_label": row.get("_coverage_entity_label", ""),
            "relevance": row.get("relevance", ""),
            "debug": row.get("debug") if isinstance(row.get("debug"), dict) else {},
            "source_kind": "semantic_chunk",
            "locator_validation": "evidence_span" if span else "page_compatibility",
            **(
                {
                    "evidence_span_id": str(span.id),
                    "document_revision_id": str(span.document_revision_id),
                    "evidence_quality": span.quality,
                }
                if span
                else {}
            ),
        }
        reader_url = envelope.reader_url if envelope else str(row.get("reader_url") or "")
        if not reader_url and asset_id:
            passage_value = semantic_chunk_id or document_id
            passage_query = f"&passage={passage_value}" if passage_value else ""
            reader_url = f"/reader/{asset_id}?page={page_index or 1}{passage_query}"
        output.append(
            LibraryEvidence(
                evidence_id=str(span.id) if span else evidence_id,
                work_id=str(work.id) if work else str(row.get("work_id") or ""),
                work_title=(work.title if work else str(row.get("title") or "未题名"))[:500],
                edition_id=str(edition.id) if edition else str(row.get("edition_id") or ""),
                asset_id=asset_id,
                page_id=str(page.id) if page else "",
                page_index=page_index,
                printed_label=str(
                    (span.printed_page_label if span else "")
                    or row.get("printed_label")
                    or ""
                )[:80],
                semantic_chunk_id=semantic_chunk_id,
                document_id=document_id,
                original_passage=passage,
                language=language,
                authors=tuple(str(value)[:240] for value in row_authors[:20] if value),
                chapter_title=str(row.get("chapter_title") or "")[:500],
                section_title=str((span.section if span else "") or row.get("section_title") or "")[:500],
                reader_url=reader_url[:1000],
                retrieval_provenance=provenance,
            )
        )
    return output


def _claim_filters_supported(filters: dict) -> bool:
    return not any(
        key not in _CLAIM_FILTER_KEYS and value not in (None, "", [], (), {})
        for key, value in filters.items()
    )


def _claim_evidence_from_hit(
    hit: dict,
    *,
    filters: dict,
    branch: str,
    coverage_entity_id: str = "",
    coverage_entity_label: str = "",
) -> LibraryEvidence | None:
    claim_id = str(hit.get("claim_id") or hit.get("id") or "").strip()
    if not claim_id:
        return None
    claim = (
        visible_claim_queryset(filters)
        .filter(pk=claim_id)
        .select_related(
            "work",
            "edition",
            "document_revision__asset__edition__work",
            "primary_evidence__page",
        )
        .prefetch_related("edition__contributions__person")
        .first()
    )
    if claim is None:
        return None
    if (
        hit.get("document_revision_id")
        and str(hit["document_revision_id"]) != str(claim.document_revision_id)
    ) or (
        hit.get("evidence_span_id")
        and str(hit["evidence_span_id"]) != str(claim.primary_evidence_id)
    ):
        return None
    span = claim.primary_evidence
    asset = claim.document_revision.asset
    if (
        not span.original_text.strip()
        or asset.edition_id != claim.edition_id
        or claim.edition.work_id != claim.work_id
        or span.page.asset_id != asset.id
    ):
        return None
    envelope = evidence_span_envelope(span)
    authors = [
        contribution.person.preferred_name
        for contribution in claim.edition.contributions.all()
        if contribution.approved and contribution.person_id
    ]
    return LibraryEvidence(
        evidence_id=str(span.id),
        work_id=str(claim.work_id),
        work_title=claim.work.title[:500],
        edition_id=str(claim.edition_id),
        asset_id=str(asset.id),
        page_id=str(span.page_id),
        page_index=span.page_number or span.page.index,
        printed_label=span.printed_page_label[:80],
        semantic_chunk_id="",
        document_id=f"evidence:{span.id}",
        original_passage=span.original_text,
        language=span.language or claim.work.language or detect_passage_language(span.original_text),
        authors=tuple(str(value)[:240] for value in authors[:20] if value),
        section_title=span.section[:500],
        reader_url=envelope.reader_url[:1000],
        retrieval_provenance={
            "retrieval_profile": UNIFIED_RETRIEVAL_PROFILE,
            "branch": branch,
            "source_kind": "derived_claim_evidence",
            "derived_claim_id": str(claim.id),
            "evidence_span_id": str(span.id),
            "document_revision_id": str(claim.document_revision_id),
            "evidence_quality": span.quality,
            "claim_quality": claim.quality_score,
            "claim_importance": claim.importance_score,
            "claim_type": claim.claim_type,
            "claim_attribution": claim.attribution,
            "coverage_entity_id": coverage_entity_id,
            "coverage_entity_label": coverage_entity_label,
            "locator_validation": "evidence_span",
        },
    )


def _claim_recall(
    library_query: LibraryQuery,
    resolved_scope: ResolvedLibraryScope,
) -> tuple[list[LibraryEvidence], dict[str, Any]]:
    if resolved_scope.empty or library_query.query_type in {
        LibraryQueryType.QUOTED_PHRASE,
        LibraryQueryType.COMPARISON,
    }:
        return [], {"status": "skipped", "reason": "scope_empty_or_specialized_query"}
    branches = [("claim_primary", resolved_scope.semantic_filters, "", "")]
    output: list[LibraryEvidence] = []
    diagnostics = []
    rejected = 0
    degraded = False
    for branch, filters, entity_id, entity_label in branches:
        if not _claim_filters_supported(filters):
            diagnostics.append({"branch": branch, "status": "skipped_unsupported_filter"})
            continue
        try:
            result = search_claim_index(
                f"{library_query.resolved_query} {entity_label}".strip(),
                filters=filters,
                limit=max(4, min(library_query.retrieval_limits["max_passages"], 12)),
            )
        except Exception as exc:  # Derived Claim recall is optional to a grounded answer.
            degraded = True
            logger.exception(
                "Library Claim recall degraded branch=%s error=%s",
                branch,
                exc.__class__.__name__,
            )
            diagnostics.append(
                {
                    "branch": branch,
                    "status": "degraded",
                    "error_category": exc.__class__.__name__,
                }
            )
            continue
        hits = result.get("hits") if isinstance(result, dict) else []
        validated = 0
        for hit in hits or []:
            evidence = _claim_evidence_from_hit(
                hit,
                filters=filters,
                branch=branch,
                coverage_entity_id=entity_id,
                coverage_entity_label=entity_label,
            )
            if evidence is None:
                rejected += 1
                continue
            output.append(evidence)
            validated += 1
        diagnostics.append(
            {
                "branch": branch,
                "status": "completed",
                "backend": result.get("backend") if isinstance(result, dict) else "invalid",
                "hit_count": len(hits or []),
                "validated_count": validated,
            }
        )
    return output, {
        "status": "degraded" if degraded else "completed",
        "validated_count": len(output),
        "rejected_count": rejected,
        "branches": diagnostics,
    }


def _deduplicate_and_budget(
    evidence: list[LibraryEvidence],
    *,
    library_query: LibraryQuery,
) -> list[LibraryEvidence]:
    max_passages = library_query.retrieval_limits["max_passages"]
    max_chars = library_query.retrieval_limits["max_evidence_chars"]
    per_work = library_query.retrieval_limits["per_work_cap"]
    selected: list[LibraryEvidence] = []
    seen = set()
    work_counts: dict[str, int] = {}
    used_chars = 0

    def add(row: LibraryEvidence) -> bool:
        nonlocal used_chars
        normalized_passage = normalize_term(row.original_passage)
        evidence_span_id = str(row.retrieval_provenance.get("evidence_span_id") or "")
        key = (
            ("evidence_span", evidence_span_id)
            if evidence_span_id
            else row.document_id
            or (
                row.work_id,
                row.page_id or row.page_index,
                sha256(normalized_passage.encode("utf-8")).hexdigest(),
            )
        )
        page_key = (row.work_id, row.page_id or row.page_index, normalized_passage[:180])
        if key in seen or page_key in seen:
            return False
        if work_counts.get(row.work_id, 0) >= per_work:
            return False
        remaining = max_chars - used_chars
        if remaining <= 80:
            return False
        if len(row.original_passage) > remaining:
            row = LibraryEvidence(
                **{
                    **row.debug_dict(),
                    "original_passage": row.original_passage[:remaining],
                }
            )
        selected.append(row)
        seen.add(key)
        seen.add(page_key)
        work_counts[row.work_id] = work_counts.get(row.work_id, 0) + 1
        used_chars += len(row.original_passage)
        return True

    if library_query.query_type == LibraryQueryType.COMPARISON:
        per_anchor = library_query.retrieval_limits["comparison_per_anchor"]
        anchor_ids = [
            str(row.get("canonical_entity", {}).get("entity_id") or "")
            for row in library_query.entity_anchors[:3]
        ]
        for anchor_id in anchor_ids:
            count = 0
            for row in evidence:
                if row.retrieval_provenance.get("coverage_entity_id") != anchor_id:
                    continue
                if add(row):
                    count += 1
                if count >= per_anchor or len(selected) >= max_passages:
                    break
        for row in evidence:
            if len(selected) >= max_passages:
                break
            add(row)
    else:
        for row in evidence:
            if len(selected) >= max_passages:
                break
            add(row)
    return selected


class LibraryRetrievalService:
    def retrieve(
        self,
        *,
        library_query: LibraryQuery,
        resolved_scope: ResolvedLibraryScope,
    ) -> LibraryRetrievalResult:
        started = time.monotonic()
        rows, diagnostics = _result_rows(library_query, resolved_scope)
        hydrated = _hydrate_evidence(rows, retrieval_profile=library_query.retrieval_profile)
        claim_evidence, claim_diagnostics = _claim_recall(library_query, resolved_scope)
        if resolved_scope.asset_id:
            hydrated = [row for row in hydrated if row.asset_id == resolved_scope.asset_id]
            claim_evidence = [
                row for row in claim_evidence if row.asset_id == resolved_scope.asset_id
            ]
        # Claim recall remains a bounded helper for locating original text.  It
        # never supplies a proposition to the answer composer as evidence.
        claim_cap = min(3, max(1, library_query.retrieval_limits["max_passages"] // 3))
        combined = []
        for index in range(max(len(hydrated), min(len(claim_evidence), claim_cap))):
            if index < len(hydrated):
                combined.append(hydrated[index])
            if index < claim_cap and index < len(claim_evidence):
                combined.append(claim_evidence[index])
        selected = _deduplicate_and_budget(combined, library_query=library_query)
        reason = ""
        sufficient = bool(selected)
        if library_query.query_type == LibraryQueryType.QUOTED_PHRASE and not selected:
            reason = "quoted_phrase_not_found"
        elif library_query.query_type == LibraryQueryType.COMPARISON:
            required_ids = {
                str(row.get("canonical_entity", {}).get("entity_id") or "")
                for row in library_query.entity_anchors[:2]
                if row.get("canonical_entity", {}).get("entity_id")
            }
            covered = {
                str(row.retrieval_provenance.get("coverage_entity_id") or "")
                for row in selected
            }
            if len(required_ids) < 2:
                sufficient = False
                reason = "comparison_entities_unresolved"
            elif not required_ids.issubset(covered):
                sufficient = False
                reason = "comparison_entity_coverage_incomplete"
        if not selected and not reason:
            reason = "no_library_evidence"
        engines = [
            str(item["response"].get("engine") or "")
            for item in diagnostics
        ]
        fallbacks = [
            str(item["response"].get("fallback_reason") or "")
            for item in diagnostics
            if item["response"].get("fallback_used")
        ]
        metadata = {
            "implementation_version": LIBRARY_RETRIEVAL_VERSION,
            "retrieval_profile": library_query.retrieval_profile,
            "unified_retrieval_profile": UNIFIED_RETRIEVAL_PROFILE,
            "semantic_search_version": "v2",
            "semantic_index_uid": next(
                (
                    item["response"].get("index_uid")
                    for item in diagnostics
                    if item["response"].get("index_uid")
                ),
                active_semantic_index_uid(),
            ),
            "query_lexicon_revision": library_query.query_lexicon_revision,
            "engines": engines,
            "fallback_used": bool(fallbacks),
            "fallback_reasons": fallbacks,
            "raw_candidate_count": len(rows),
            "hydrated_candidate_count": len(hydrated),
            "evidence_span_validated_count": sum(
                1
                for row in hydrated
                if row.retrieval_provenance.get("locator_validation") == "evidence_span"
            ),
            "derived_claim_recall": claim_diagnostics,
            "knowledge_anchor_count": len(library_query.entity_anchors),
            "knowledge_use": "query_normalization_and_scope_only",
            "answer_evidence_kind": "collection_original_text",
            "evidence_count": len(selected),
            "latency_ms": round((time.monotonic() - started) * 1000, 3),
            "branches": [
                {
                    "branch": item.get("branch"),
                    "anchor": item.get("anchor"),
                    "result_count": len(item["response"].get("results", [])),
                }
                for item in diagnostics
            ],
        }
        return LibraryRetrievalResult(
            evidence=tuple(selected),
            sufficient=sufficient,
            insufficiency_reason=reason,
            metadata=metadata,
        )
