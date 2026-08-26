from __future__ import annotations

from collections import Counter, defaultdict
from difflib import SequenceMatcher
import re
from typing import Any

from catalog.models import (
    Contribution,
    DerivedClaim,
    Edition,
    EvidenceSpan,
    KnowledgeNode,
    KnowledgePublicationStatus,
    RelationReviewStatus,
    ScholarProfile,
    WorkNodeRelation,
    WorkTopicRelation,
)
from catalog.services.claim_benchmark import claim_viewpoint_activation_state
from catalog.services.claims.indexing import search_claim_index, visible_claim_queryset
from catalog.services.claims.stance import ClaimStatement, ClaimStance, classify_stance
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.retrieval import unified_retrieve


STANCE_ORDER = (
    ClaimStance.DIRECT.value,
    ClaimStance.SUPPORT.value,
    ClaimStance.OPPOSE.value,
    ClaimStance.QUALIFY.value,
    ClaimStance.CRITIQUE.value,
    ClaimStance.EXTEND.value,
    ClaimStance.REFRAME.value,
)
STANCE_LABELS = {
    ClaimStance.DIRECT.value: "直接",
    ClaimStance.SUPPORT.value: "支持",
    ClaimStance.OPPOSE.value: "相斥",
    ClaimStance.QUALIFY.value: "限定或修正",
    ClaimStance.CRITIQUE.value: "批评",
    ClaimStance.EXTEND.value: "延展",
    ClaimStance.REFRAME.value: "重新界定",
}
SOURCE_TYPE_LABELS = {
    "book": "图书",
    "journal": "期刊",
    "other": "其他",
}

_CAUSAL_ZH_RE = re.compile(
    r"^\s*(?P<subject>.{1,300}?)\s*(?P<predicate>并不导致|不导致|未导致|无法导致|导致|造成|引发|促成|决定|影响)\s*(?P<object>.{1,600}?)\s*$"
)
_CAUSAL_EN_RE = re.compile(
    r"^\s*(?P<subject>.+?)\s+(?P<predicate>(?:does\s+not|do\s+not|cannot|can\s+not|never)?\s*(?:cause|causes|lead\s+to|leads\s+to|affect|affects))\s+(?P<object>.+?)\s*$",
    re.IGNORECASE,
)
_NEGATION_RE = re.compile(
    r"(?:并不|并非|不导致|未导致|无法|不会|不能|没有|"
    r"\bnot\b|\bnever\b|\bcannot\b)",
    re.IGNORECASE,
)
_QUALIFIER_PATTERNS = (
    re.compile(r"(?:仅在|只有在|当).{1,180}?(?:时|情况下)"),
    re.compile(r"(?:取决于|条件是|在.{1,100}?条件下).{0,180}"),
    re.compile(r"\b(?:only if|under|depends? on|to some extent)\b.{0,180}", re.IGNORECASE),
)
_NORMALIZE_RE = re.compile(r"[\s\W_]+", re.UNICODE)


class ViewpointSearchError(ValueError):
    pass


def query_claim(query: str) -> ClaimStatement:
    """Build a bounded deterministic query claim before any retrieval."""

    proposition = str(query or "").strip()
    if not proposition:
        raise ViewpointSearchError("观点检索命题不能为空。")
    if len(proposition) > 2000:
        raise ViewpointSearchError("观点检索命题不能超过 2000 个字符。")
    match = _CAUSAL_ZH_RE.match(proposition) or _CAUSAL_EN_RE.match(proposition)
    subject = predicate = object_value = ""
    claim_type = DerivedClaim.ClaimType.ASSERTION
    if match:
        subject = match.group("subject").strip(" ，,.;。")
        predicate = match.group("predicate").strip()
        object_value = match.group("object").strip(" ，,.;。")
        claim_type = DerivedClaim.ClaimType.CAUSAL
    qualifiers = []
    for pattern in _QUALIFIER_PATTERNS:
        for qualifier in pattern.findall(proposition):
            value = str(qualifier).strip()[:400]
            if value and value not in qualifiers:
                qualifiers.append(value)
    return ClaimStatement(
        proposition=proposition,
        subject=subject,
        predicate=predicate,
        object=object_value,
        polarity=(
            DerivedClaim.Polarity.NEGATIVE
            if _NEGATION_RE.search(predicate or proposition)
            else DerivedClaim.Polarity.POSITIVE
        ),
        qualifiers=tuple(qualifiers),
        claim_type=claim_type,
    )


def _claim_statement(claim: DerivedClaim) -> ClaimStatement:
    return ClaimStatement(
        proposition=claim.proposition,
        subject=claim.subject,
        predicate=claim.predicate,
        object=claim.object,
        polarity=claim.polarity,
        modality=claim.modality,
        qualifiers=tuple(str(row) for row in (claim.qualifiers or [])),
        temporal_scope=claim.temporal_scope if isinstance(claim.temporal_scope, dict) else {},
        geographic_scope=claim.geographic_scope if isinstance(claim.geographic_scope, dict) else {},
        population_scope=claim.population_scope if isinstance(claim.population_scope, dict) else {},
        attribution=claim.attribution,
        claim_type=claim.claim_type,
    )


def _semantic_statement(row: dict) -> ClaimStatement:
    return ClaimStatement(
        proposition=str(row.get("snippet") or "").strip(),
        polarity=(
            DerivedClaim.Polarity.NEGATIVE
            if _NEGATION_RE.search(str(row.get("snippet") or ""))
            else DerivedClaim.Polarity.UNCERTAIN
        ),
        qualifiers=tuple(
            match.group(0)[:400]
            for pattern in _QUALIFIER_PATTERNS
            for match in pattern.finditer(str(row.get("snippet") or ""))
        ),
    )


def _normalized(value: object) -> str:
    return _NORMALIZE_RE.sub("", str(value or "").casefold())


def _source_type(document_type: object) -> str:
    value = str(document_type or "")
    if value == "book":
        return "book"
    if value == "journal_article":
        return "journal"
    return "other"


def _matching_evidence_span(row: dict) -> EvidenceSpan | None:
    asset_id = str(row.get("asset_id") or "").strip()
    try:
        page_number = int(row.get("page_start") or row.get("page_index") or 0)
    except (TypeError, ValueError):
        page_number = 0
    if not asset_id or page_number <= 0:
        return None
    spans = list(
        EvidenceSpan.objects.filter(
            document_revision__asset_id=asset_id,
            document_revision__is_active=True,
            page_number=page_number,
            is_stale=False,
        )
        .select_related("document_revision__asset__edition__work", "page")
        .order_by("start_offset")[:40]
    )
    if not spans:
        return None
    snippet = _normalized(row.get("snippet"))
    if not snippet:
        return spans[0]
    exact = [
        span
        for span in spans
        if snippet in _normalized(span.original_text)
        or _normalized(span.original_text) in snippet
    ]
    if exact:
        return max(exact, key=lambda span: span.quality)
    scored = [
        (
            SequenceMatcher(
                None,
                snippet[:1600],
                _normalized(span.original_text)[:2400],
            ).ratio(),
            span.quality,
            span,
        )
        for span in spans
    ]
    scored.sort(key=lambda value: (value[0], value[1]), reverse=True)
    return scored[0][2] if scored and scored[0][0] >= 0.22 else None


def _semantic_result(
    row: dict,
    *,
    query_statement: ClaimStatement,
    rank: int,
    total: int,
) -> dict | None:
    span = _matching_evidence_span(row)
    if span is None:
        return None
    statement = _semantic_statement(row)
    if not statement.proposition:
        return None
    stance = classify_stance(query_statement, statement)
    envelope = evidence_span_envelope(span).as_dict()
    pdf_url = f"/api/distribution/assets/{envelope['source']['asset_id']}/file/"
    envelope["pdf_url"] = pdf_url
    base_score = max(0.0, 1.0 - ((rank - 1) / max(1, total)))
    return {
        "id": f"semantic:{row.get('id')}",
        "source_kind": "semantic_chunk",
        "claim_id": None,
        "proposition": statement.proposition,
        "stance": stance.stance.value,
        "stance_label": STANCE_LABELS[stance.stance.value],
        "stance_confidence": stance.confidence,
        "stance_reasons": list(stance.reasons),
        "score": round(base_score, 6),
        "authors": list(row.get("authors") or []),
        "work": {
            "id": str(row.get("work_id") or ""),
            "title": str(row.get("title") or ""),
            "slug": str(row.get("edition_slug") or ""),
        },
        "source_type": _source_type(row.get("document_type")),
        "language": str(row.get("language") or "unknown"),
        "publication_year": row.get("publication_year"),
        "page": envelope["locator"].get("page"),
        "printed_page_label": envelope["locator"].get("printed_page_label"),
        "evidence": envelope,
        "reader_url": envelope["reader_url"],
        "pdf_url": pdf_url,
        "attribution": DerivedClaim.Attribution.UNCERTAIN,
        "claim_type": DerivedClaim.ClaimType.ASSERTION,
        "quality_score": span.quality,
        "ranking_source": "semantic_v2_baseline",
    }


def _claim_result(
    claim: DerivedClaim,
    *,
    index_hit: dict,
    query_statement: ClaimStatement,
    rank: int,
    total: int,
) -> dict:
    stance = classify_stance(query_statement, _claim_statement(claim))
    envelope = evidence_span_envelope(claim.primary_evidence).as_dict()
    pdf_url = f"/api/distribution/assets/{envelope['source']['asset_id']}/file/"
    envelope["pdf_url"] = pdf_url
    try:
        index_score = float(index_hit.get("_rankingScore") or 0)
    except (TypeError, ValueError):
        index_score = max(0.0, 1.0 - ((rank - 1) / max(1, total)))
    authors = list(
        claim.edition.contributions.filter(
            approved=True,
            role=Contribution.Role.AUTHOR,
        )
        .order_by("order")
        .values_list("person__preferred_name", flat=True)
    )
    score = (
        min(max(index_score, 0), 1) * 0.25
        + claim.quality_score * 0.25
        + claim.importance_score * 0.25
        + stance.confidence * 0.25
    )
    return {
        "id": f"claim:{claim.id}",
        "source_kind": "derived_claim",
        "claim_id": str(claim.id),
        "proposition": claim.proposition,
        "stance": stance.stance.value,
        "stance_label": STANCE_LABELS[stance.stance.value],
        "stance_confidence": stance.confidence,
        "stance_reasons": list(stance.reasons),
        "score": round(score, 6),
        "authors": authors,
        "work": {
            "id": str(claim.work_id),
            "title": claim.work.title,
            "slug": claim.edition.public_slug or "",
        },
        "source_type": _source_type(claim.work.document_type),
        "language": claim.primary_evidence.language or claim.work.language,
        "publication_year": claim.edition.publication_year,
        "page": envelope["locator"].get("page"),
        "printed_page_label": envelope["locator"].get("printed_page_label"),
        "evidence": envelope,
        "reader_url": envelope["reader_url"],
        "pdf_url": pdf_url,
        "attribution": claim.attribution,
        "claim_type": claim.claim_type,
        "quality_score": claim.quality_score,
        "importance_score": claim.importance_score,
        "qualifiers": claim.qualifiers,
        "temporal_scope": claim.temporal_scope,
        "geographic_scope": claim.geographic_scope,
        "population_scope": claim.population_scope,
        "ranking_source": "claim_index_shadow",
    }


def _validated_claim_results(
    hits: list[dict],
    *,
    filters: dict,
    query_statement: ClaimStatement,
) -> tuple[list[dict], int]:
    hit_ids = [str(hit.get("claim_id") or hit.get("id") or "") for hit in hits]
    rows = (
        visible_claim_queryset(filters)
        .filter(pk__in=[value for value in hit_ids if value])
        .select_related(
            "work",
            "edition",
            "document_revision__asset__edition__work",
            "primary_evidence__page__asset",
        )
    )
    claim_map = {str(claim.id): claim for claim in rows}
    output = []
    rejected = 0
    for rank, hit in enumerate(hits, start=1):
        claim_id = str(hit.get("claim_id") or hit.get("id") or "")
        claim = claim_map.get(claim_id)
        if (
            claim is None
            or str(hit.get("document_revision_id") or claim.document_revision_id)
            != str(claim.document_revision_id)
            or str(hit.get("evidence_span_id") or claim.primary_evidence_id)
            != str(claim.primary_evidence_id)
        ):
            rejected += 1
            continue
        output.append(
            _claim_result(
                claim,
                index_hit=hit,
                query_statement=query_statement,
                rank=rank,
                total=len(hits),
            )
        )
    return output, rejected


def _deduplicate(rows: list[dict]) -> list[dict]:
    chosen: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for row in rows:
        key = (str(row["work"]["id"]), _normalized(row["proposition"]))
        previous = chosen.get(key)
        if previous is None:
            chosen[key] = row
            order.append(key)
            continue
        if (
            row["source_kind"] == "derived_claim"
            and previous["source_kind"] != "derived_claim"
        ) or (
            row["source_kind"] == previous["source_kind"]
            and row["score"] > previous["score"]
        ):
            chosen[key] = row
    return [chosen[key] for key in order]


def _diversified(rows: list[dict], *, limit: int, max_per_work: int) -> list[dict]:
    stance_priority = {stance: index for index, stance in enumerate(STANCE_ORDER)}
    rows = sorted(
        rows,
        key=lambda row: (
            stance_priority.get(row["stance"], len(STANCE_ORDER)),
            -float(row.get("score") or 0),
            row["id"],
        ),
    )
    if max_per_work <= 0:
        return rows[:limit]
    counts: defaultdict[str, int] = defaultdict(int)
    output = []
    for row in rows:
        work_id = str(row["work"]["id"])
        if counts[work_id] >= max_per_work:
            continue
        counts[work_id] += 1
        output.append(row)
        if len(output) >= limit:
            break
    return output


def _groups(rows: list[dict]) -> dict[str, list[dict]]:
    grouped = {stance: [] for stance in STANCE_ORDER}
    for row in rows:
        grouped[row["stance"]].append(row)
    return grouped


def _facet_options(rows: list[dict], *, labels: dict[str, str] | None = None) -> list[dict]:
    labels = labels or {}
    return [
        {
            "id": value,
            "slug": value,
            "label": labels.get(value, value),
            "count": count,
        }
        for value, count in sorted(
            Counter(str(row) for row in rows if row not in (None, "")).items(),
            key=lambda item: (-item[1], labels.get(item[0], item[0])),
        )
    ]


def _entity_facet_options(
    associations,
    *,
    work_counts: Counter[str],
    id_key: str,
    slug_key: str,
    label_key: str,
    work_key: str,
) -> list[dict]:
    aggregated: dict[str, dict] = {}
    seen: set[tuple[str, str]] = set()
    for association in associations:
        identifier = str(association[id_key])
        work_id = str(association[work_key])
        pair = (identifier, work_id)
        if pair in seen:
            continue
        seen.add(pair)
        row = aggregated.setdefault(
            identifier,
            {
                "id": identifier,
                "slug": str(association[slug_key] or ""),
                "label": str(association[label_key] or ""),
                "count": 0,
            },
        )
        row["count"] += int(work_counts.get(work_id, 0))
    return sorted(
        aggregated.values(),
        key=lambda row: (-int(row["count"]), row["label"], row["id"]),
    )


def _viewpoint_facets(rows: list[dict]) -> dict[str, Any]:
    work_counts = Counter(str(row.get("work", {}).get("id") or "") for row in rows)
    work_counts.pop("", None)
    work_ids = list(work_counts)
    work_options = []
    seen_works: set[str] = set()
    if work_ids:
        editions = Edition.objects.filter(
            work_id__in=work_ids,
            state="published",
            is_primary=True,
        ).select_related("work").order_by("work__title", "-publication_year")
        for edition in editions:
            work_id = str(edition.work_id)
            if work_id in seen_works:
                continue
            seen_works.add(work_id)
            work_options.append(
                {
                    "id": work_id,
                    "slug": edition.public_slug or "",
                    "label": edition.work.title,
                    "count": int(work_counts[work_id]),
                }
            )

    scholar_rows = []
    theory_rows = []
    topic_rows = []
    if work_ids:
        scholar_rows = list(
            ScholarProfile.objects.filter(
                editorial_status="published",
                person__contributions__edition__work_id__in=work_ids,
                person__contributions__edition__state="published",
                person__contributions__edition__is_primary=True,
                person__contributions__approved=True,
                person__contributions__role=Contribution.Role.AUTHOR,
            )
            .values(
                "person_id",
                "slug",
                "person__preferred_name",
                "person__contributions__edition__work_id",
            )
            .distinct()
        )
        theory_rows = list(
            WorkNodeRelation.objects.filter(
                work_id__in=work_ids,
                node__node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
                node__status=KnowledgePublicationStatus.PUBLISHED,
                status=KnowledgePublicationStatus.PUBLISHED,
            )
            .values("node_id", "node__slug", "node__canonical_name_zh", "work_id")
            .distinct()
        )
        topic_rows = list(
            WorkTopicRelation.objects.filter(
                work_id__in=work_ids,
                topic__editorial_status="published",
                review_status=RelationReviewStatus.APPROVED,
            )
            .values("topic_id", "topic__slug", "topic__name", "work_id")
            .distinct()
        )

    years = [
        int(row["publication_year"])
        for row in rows
        if row.get("publication_year") not in (None, "")
    ]
    return {
        "relations": _facet_options(
            [row.get("stance") for row in rows],
            labels=STANCE_LABELS,
        ),
        "source_types": _facet_options(
            [row.get("source_type") for row in rows],
            labels=SOURCE_TYPE_LABELS,
        ),
        "languages": _facet_options([row.get("language") for row in rows]),
        "scholars": _entity_facet_options(
            scholar_rows,
            work_counts=work_counts,
            id_key="person_id",
            slug_key="slug",
            label_key="person__preferred_name",
            work_key="person__contributions__edition__work_id",
        ),
        "theories": _entity_facet_options(
            theory_rows,
            work_counts=work_counts,
            id_key="node_id",
            slug_key="node__slug",
            label_key="node__canonical_name_zh",
            work_key="work_id",
        ),
        "topics": _entity_facet_options(
            topic_rows,
            work_counts=work_counts,
            id_key="topic_id",
            slug_key="topic__slug",
            label_key="topic__name",
            work_key="work_id",
        ),
        "works": sorted(
            work_options,
            key=lambda row: (-int(row["count"]), row["label"], row["id"]),
        ),
        "publication_year": {
            "min": min(years) if years else None,
            "max": max(years) if years else None,
        },
    }


def viewpoint_search(
    query: str,
    *,
    filters: dict | None = None,
    limit: int = 40,
    max_per_work: int = 4,
    sort: str = "relevance",
    debug: bool = False,
    retrieval_backend=None,
    claim_search_backend=None,
) -> dict[str, Any]:
    """Return baseline results and a locator-validated Claim shadow ranking.

    The Claim ranking cannot become the default through this call.  Promotion
    is controlled by the benchmark gate setting and remains false by default.
    """

    statement = query_claim(query)
    normalized_filters = dict(filters or {})
    bounded_limit = max(1, min(int(limit), 100))
    bounded_per_work = max(0, min(int(max_per_work), 20))
    semantic_error = ""
    retrieve = retrieval_backend or unified_retrieve
    try:
        baseline_response = retrieve(
            query,
            profile="viewpoint",
            filters=normalized_filters,
            limit=bounded_limit,
            max_per_work=bounded_per_work,
            sort=sort,
            debug=debug,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        semantic_error = exc.__class__.__name__
        baseline_response = {"results": [], "fallback_used": True, "fallback_reason": semantic_error}
    baseline_rows = []
    unvalidated_baseline = 0
    raw_baseline = baseline_response.get("results") if isinstance(baseline_response, dict) else []
    for rank, row in enumerate(raw_baseline or [], start=1):
        result = _semantic_result(
            row,
            query_statement=statement,
            rank=rank,
            total=len(raw_baseline or []),
        )
        if result is None:
            unvalidated_baseline += 1
        else:
            baseline_rows.append(result)

    search_claims = claim_search_backend or search_claim_index
    claim_response = search_claims(
        query,
        filters=normalized_filters,
        limit=min(200, max(bounded_limit * 3, 40)),
    )
    claim_rows, rejected_claim_hits = _validated_claim_results(
        list(claim_response.get("hits") or []),
        filters=normalized_filters,
        query_statement=statement,
    )
    shadow_rows = _diversified(
        _deduplicate([*claim_rows, *baseline_rows]),
        limit=bounded_limit,
        max_per_work=bounded_per_work,
    )
    baseline_rows = baseline_rows[:bounded_limit]

    activation = claim_viewpoint_activation_state()
    gate_passed = bool(activation.get("active"))
    facet_rows = shadow_rows if gate_passed else baseline_rows
    facets = _viewpoint_facets(facet_rows)
    requested_relations = {
        str(value)
        for value in (normalized_filters.get("relations") or [])
        if str(value) in STANCE_ORDER
    }
    if requested_relations:
        baseline_rows = [
            row for row in baseline_rows if row["stance"] in requested_relations
        ]
        shadow_rows = [
            row for row in shadow_rows if row["stance"] in requested_relations
        ]
    default_rows = shadow_rows if gate_passed else baseline_rows
    default_mode = "claim" if gate_passed else "baseline"
    return {
        "query": str(query).strip(),
        "query_claim": {
            "proposition": statement.proposition,
            "subject": statement.subject,
            "predicate": statement.predicate,
            "object": statement.object,
            "polarity": statement.polarity,
            "qualifiers": list(statement.qualifiers),
            "claim_type": statement.claim_type,
        },
        "default_mode": default_mode,
        "results": default_rows,
        "groups": _groups(default_rows),
        "facets": facets,
        "baseline": {
            "results": baseline_rows,
            "groups": _groups(baseline_rows),
            "engine": baseline_response.get("engine") if isinstance(baseline_response, dict) else "",
            "search_version": baseline_response.get("search_version") if isinstance(baseline_response, dict) else "",
            "fallback_used": bool(baseline_response.get("fallback_used")) if isinstance(baseline_response, dict) else True,
            "fallback_reason": baseline_response.get("fallback_reason") if isinstance(baseline_response, dict) else semantic_error,
        },
        "shadow": {
            "results": shadow_rows,
            "groups": _groups(shadow_rows),
            "claim_index_backend": claim_response.get("backend"),
            "claim_index_uid": claim_response.get("index_uid"),
        },
        "metadata": {
            "benchmark_gate_passed": gate_passed,
            "benchmark_activation": activation,
            "default_ranking": "claim_shadow" if gate_passed else "semantic_v2_baseline",
            "claim_ranking_status": "promoted" if gate_passed else "shadow",
            "semantic_error": semantic_error,
            "unvalidated_baseline_results_excluded": unvalidated_baseline,
            "stale_or_invalid_claim_hits_excluded": rejected_claim_hits,
            "evidence_span_validation_required": True,
            "cosine_similarity_used_for_stance": False,
        },
    }


search_viewpoints_v3 = viewpoint_search
