from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher
from hashlib import sha256
import logging
import re
import time
import unicodedata

import httpx
from django.conf import settings
from django.db import DatabaseError

from catalog.models import SemanticChunk
from catalog.services.query_lexicon.search import resolve_search_query
from catalog.services.query_lexicon.sync import QueryLexiconInvariantError
from catalog.services.semantic_indexing import active_semantic_index_uid
from catalog.services.semantic_reranker import (
    SemanticRerankerError,
    current_reranker_config,
    rerank_candidates,
)
from catalog.services.semantic_search import (
    _apply_feedback_calibration,
    _base_queryset,
    _keyword_candidates,
    _meili_filters,
    _passage_keyword_candidates,
    _query_terms,
    _rrf,
    _serialize_row,
    current_semantic_runtime,
    semantic_model_health,
)
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.semantic_search_v2_config import (
    MAX_BRANCH_HITS_PER_CANDIDATE,
    QUERY_PROFILE_RULES,
    branch_weight,
    current_search_v2_limits,
    effective_semantic_ratio,
)
from ingestion.services.indexing import _headers


logger = logging.getLogger(__name__)

PROFILE_NAMES = {"fast", "balanced", "precision"}
INTENT_LABELS = {
    "definition": "概念与定义",
    "cause": "原因解释",
    "mechanism": "机制分析",
    "comparison": "比较判断",
    "path_solution": "路径与主张",
    "evaluation": "评价与条件",
    "historical_process": "历史过程",
    "relationship": "关系判断",
    "statement": "观点陈述",
}
INTENT_MARKERS = {
    "definition": ("是指", "所谓", "定义", "意味着", "概念"),
    "cause": ("因为", "由于", "原因", "导致", "源于", "取决于"),
    "mechanism": ("机制", "通过", "使得", "从而", "进而", "作用于"),
    "comparison": ("相比", "区别", "不同", "共同", "一方面", "另一方面"),
    "path_solution": ("关键在于", "应当", "应该", "需要", "可以通过", "路径", "方向", "出路", "制度安排", "组织形式"),
    "evaluation": ("能够", "不能", "作用", "局限", "条件", "取决于", "有效"),
    "historical_process": ("逐渐", "演变", "经历", "阶段", "形成", "发展过程"),
    "relationship": ("关系", "影响", "关联", "作用", "制约", "互动"),
    "statement": (),
}
QUESTION_TRIM_RE = re.compile(
    r"(?:是什么|为什么|有什么|怎么办|如何|怎样|是否|能否|何以|何种|哪些|吗|呢)+[？?。！!]*$"
)
PUNCT_RE = re.compile(r"[，。；：、！？?,.;:!]+")
SUPPLEMENTAL_BRANCH_TYPES = frozenset(
    {
        "canonical_equivalent",
        "verified_translation",
        "verified_alias",
        "historical",
        "legacy_search_variant",
        "generated_search_variant",
        "explicit_rewrite",
        "intent_rewrite",
    }
)


def _profile(
    name: str | None,
    *,
    rerank_top_k_override: int | None,
    final_top_k_override: int | None = None,
) -> dict:
    selected = str(name or getattr(settings, "SEMANTIC_SEARCH_PROFILE", "precision")).strip().casefold()
    if selected not in PROFILE_NAMES:
        selected = "precision"
    expansion_limit = int(getattr(settings, "SEMANTIC_SEARCH_QUERY_EXPANSION_MAX", 3))
    rerank_top_k = int(getattr(settings, "SEMANTIC_SEARCH_RERANK_TOP_K", 24))
    fusion_top_k = int(getattr(settings, "SEMANTIC_SEARCH_FUSION_TOP_K", 24))
    if selected == "fast":
        expansion_limit = 0
        rerank_top_k = 0
        fusion_top_k = min(fusion_top_k, 20)
    elif selected == "balanced":
        # The balanced profile is also the V2-B ablation: passage reranking is
        # measured without query expansion or parent context.
        expansion_limit = 0
        rerank_top_k = min(rerank_top_k, 12)
    if rerank_top_k_override is not None:
        rerank_top_k = max(0, min(int(rerank_top_k_override), 64))
    final_top_k = int(getattr(settings, "SEMANTIC_SEARCH_FINAL_TOP_K", 10))
    if final_top_k_override is not None:
        # Offline evaluation may need a complete top 20 for Recall@20. This
        # only changes how many already-ranked candidates are returned; the
        # public profile default and every ranking parameter remain unchanged.
        final_top_k = max(1, min(int(final_top_k_override), fusion_top_k, 50))
    return {
        "name": selected,
        "dense_top_k": int(getattr(settings, "SEMANTIC_SEARCH_DENSE_TOP_K", 50)),
        "sparse_top_k": int(getattr(settings, "SEMANTIC_SEARCH_SPARSE_TOP_K", 50)),
        "fusion_top_k": fusion_top_k,
        "rerank_top_k": rerank_top_k,
        "final_top_k": final_top_k,
        "expansion_limit": expansion_limit,
    }


def _intent(query: str) -> str:
    value = query.casefold()
    if any(token in value for token in ("有什么区别", "有何区别", "异同", "相比", "比较", "不同于", "versus", " vs ")):
        return "comparison"
    if any(token in value for token in ("为什么", "何以", "原因", "为何")):
        return "cause"
    if any(token in value for token in ("如何导致", "如何造成", "怎样产生", "机制", "通过什么", "何种机制")):
        return "mechanism"
    if any(token in value for token in ("出路", "怎么办", "应当如何", "应该如何", "发展路径", "发展方向", "解决", "对策", "方案")):
        return "path_solution"
    if any(token in value for token in ("如何演变", "怎样演变", "历史过程", "发展过程", "如何形成", "变迁")):
        return "historical_process"
    if any(token in value for token in ("什么是", "是指什么", "如何理解", "怎样理解", "含义", "定义")):
        return "definition"
    if any(token in value for token in ("是否", "能否", "怎样评价", "如何评价", "作用如何", "有效吗")):
        return "evaluation"
    if any(token in value for token in ("什么关系", "有何关系", "如何影响", "相互作用", "关联")):
        return "relationship"
    if any(token in value for token in ("如何", "怎样")):
        return "mechanism"
    return "statement"


def _query_object(query: str) -> str:
    value = QUESTION_TRIM_RE.sub("", query.strip())
    value = re.sub(r"^(请问|请解释|请说明|试论|论述)", "", value).strip()
    value = re.sub(r"(的出路|的发展路径|的发展方向)$", "", value).strip()
    value = PUNCT_RE.sub(" ", value)
    return re.sub(r"\s+", " ", value).strip()[:120]


def analyze_query(
    query: str,
    *,
    expansion_limit: int,
    explicit_rewrite: str = "",
    disabled_branch_types: Iterable[str] | None = None,
) -> dict:
    folded, terms = _query_terms(query)
    intent = _intent(query)
    target = _query_object(query) or query.strip()[:120]
    limits = current_search_v2_limits(expansion_limit=expansion_limit)
    lexicon_fallback_reason = ""
    try:
        resolution = resolve_search_query(
            query,
            expansion_limit=expansion_limit,
        )
    except (
        DatabaseError,
        QueryLexiconInvariantError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        lexicon_fallback_reason = exc.__class__.__name__
        resolution = {
            "normalized_original_query": normalize_term(query),
            "query_language": "unknown",
            "query_lexicon_revision": None,
            "matched_entities": [],
            "ambiguous": False,
            "truncated": False,
            "query_profile": "conceptual",
            "limits": limits.as_dict(),
            "recognition_span_count": 0,
            "cache_hit": False,
            "resolver_db_query_count": 0,
            "resolver_timing_ms": 0.0,
            "expansion_branches": [
                {
                    "branch_id": "original:0",
                    "branch_type": "original",
                    "query": query.strip(),
                    "term": query.strip(),
                    "language": "unknown",
                    "term_type": "original",
                    "source_kind": "original_query",
                    "trust_level": "original",
                    "effective_trust_level": "original",
                    "displayable": True,
                    "ambiguous": False,
                    "retrieval_channels": ["sparse", "dense"],
                    "entities": [],
                }
            ],
        }
    disabled = {
        str(value).strip()
        for value in (disabled_branch_types or ())
        if str(value).strip() in SUPPLEMENTAL_BRANCH_TYPES
    }
    branches = [
        dict(branch)
        for branch in resolution["expansion_branches"]
        if branch.get("branch_type") == "original"
        or branch.get("branch_type") not in disabled
    ]
    seen_queries = {normalize_term(branch["query"]) for branch in branches}
    used_characters = sum(len(str(branch["query"])) for branch in branches[1:])

    def add_branch(candidate: str, *, branch_type: str, trust_level: str) -> None:
        nonlocal used_characters
        value = str(candidate or "").strip()
        normalized = normalize_term(value)
        if (
            branch_type in disabled
            or not value
            or not normalized
            or normalized in seen_queries
            or len(branches) >= limits.max_expansion_branches
            or used_characters + len(value) > limits.max_expansion_characters
        ):
            return
        branches.append(
            {
                "branch_id": f"{branch_type}:{len(branches)}",
                "branch_type": branch_type,
                "query": value,
                "term": value,
                "language": resolution["query_language"],
                "term_type": branch_type,
                "source_kind": (
                    "reader_explicit_rewrite"
                    if branch_type == "explicit_rewrite"
                    else "deterministic_intent_rule"
                ),
                "trust_level": trust_level,
                "effective_trust_level": trust_level,
                "displayable": branch_type
                not in {"legacy_search_variant", "generated_search_variant"},
                "ambiguous": False,
                "retrieval_channels": ["sparse", "dense"],
                "entities": [],
            }
        )
        seen_queries.add(normalized)
        used_characters += len(value)

    if explicit_rewrite:
        add_branch(
            explicit_rewrite.strip()[:600],
            branch_type="explicit_rewrite",
            trust_level="original",
        )
    patterns = {
        "definition": ("概念界定", "含义"),
        "cause": ("原因", "形成条件"),
        "mechanism": ("作用机制", "通过何种过程"),
        "comparison": ("区别", "共同点"),
        "path_solution": ("发展路径", "制度安排", "关键在于"),
        "evaluation": ("作用与条件", "局限"),
        "historical_process": ("历史演变", "形成过程"),
        "relationship": ("相互关系", "影响机制"),
        "statement": (),
    }
    for phrase in patterns[intent]:
        add_branch(
            f"{target} {phrase}".strip(),
            branch_type="intent_rewrite",
            trust_level="deterministic",
        )
    rewrites = [branch["query"] for branch in branches]
    return {
        "type": INTENT_LABELS[intent],
        "intent": intent,
        "intent_label": INTENT_LABELS[intent],
        "object": target,
        "terms": terms[:10],
        "related_concepts": [
            {
                "name": item["canonical_entity"]["canonical_label"],
                "kind": item["canonical_entity"]["entity_type"],
                "entity_id": item["canonical_entity"]["entity_id"],
                # Keep the legacy response shape used by the Explore UI. The
                # stable entity id is used as the key because the resolver does
                # not perform an extra authority lookup just to obtain a slug.
                "slug": item["canonical_entity"]["entity_id"],
                "ambiguous": item["ambiguity"]["is_ambiguous"],
            }
            for item in resolution["matched_entities"]
        ],
        "rewrites": rewrites,
        "rewrite_source": (
            "QueryLexicon 与保守问题结构"
            if resolution["matched_entities"]
            else "原始问题与保守问题结构"
        ),
        "query_profile": resolution["query_profile"],
        "query_lexicon_revision": resolution["query_lexicon_revision"],
        "query_lexicon": resolution,
        "matched_entities": resolution["matched_entities"],
        "expansion_branches": branches,
        "disabled_branch_types": sorted(disabled),
        "lexicon_fallback_reason": lexicon_fallback_reason,
    }


def _meili_sparse_candidates(query: str, filters: dict, *, limit: int, index_uid: str) -> list[tuple[str, float]]:
    payload = {
        "q": query,
        "limit": min(200, max(1, int(limit))),
        "filter": " AND ".join(_meili_filters(filters)),
        "attributesToRetrieve": ["id"],
        "showRankingScore": True,
    }
    response = httpx.post(
        f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/search",
        headers=_headers(),
        json=payload,
        timeout=min(5, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    hits = response.json().get("hits", [])
    return [
        (str(hit["id"]), float(hit.get("_rankingScore") or 0))
        for hit in hits
        if hit.get("id")
    ]


def _meili_dense_candidates(query: str, config: dict, filters: dict, *, limit: int, index_uid: str) -> list[tuple[str, float]]:
    payload = {
        "q": query,
        "limit": min(200, max(1, int(limit))),
        "filter": " AND ".join(_meili_filters(filters)),
        "attributesToRetrieve": ["id"],
        "showRankingScore": True,
        "hybrid": {
            "semanticRatio": 1.0,
            "embedder": config["embedder_name"],
        },
    }
    response = httpx.post(
        f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/search",
        headers=_headers(),
        json=payload,
        timeout=min(5, settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    hits = response.json().get("hits", [])
    return [
        (str(hit["id"]), float(hit.get("_rankingScore") or 0))
        for hit in hits
        if hit.get("id")
    ]


def _hydrate_sources(
    sources: list[tuple[list[tuple[str, float]], float, dict]],
    filters: dict,
) -> list[tuple[list[tuple[object, float]], float, dict]]:
    """Hydrate every sparse branch with one bounded ORM query."""

    identifiers = {
        str(identifier)
        for rows, _weight, _metadata in sources
        for identifier, _raw_score in rows
    }
    if not identifiers:
        return []
    chunks = _base_queryset(filters).filter(pk__in=identifiers)
    mapping = {str(chunk.id): chunk for chunk in chunks}
    return [
        (
            [
                (mapping[identifier], raw_score)
                for identifier, raw_score in rows
                if identifier in mapping
            ],
            weight,
            metadata,
        )
        for rows, weight, metadata in sources
    ]


def _merge_ranked_lists(
    sources: list[tuple[list[tuple[object, float]], float] | tuple[list[tuple[object, float]], float, dict]],
    *,
    key,
    return_provenance: bool = False,
):
    """Fuse bounded branches without multiplying a score by alias count.

    The original branch contributes fully. Expansion branches contribute their
    strongest hit and at most a quarter of one additional hit. Every passage
    remains one candidate, even when it appears in several branch result sets.
    """

    values: dict[str, object] = {}
    strongest: dict[str, float] = defaultdict(float)
    contributions: dict[str, list[dict]] = defaultdict(list)
    for source_index, source in enumerate(sources):
        rows, weight = source[:2]
        metadata = source[2] if len(source) > 2 else {}
        if weight <= 0:
            continue
        for rank, (value, raw_score) in enumerate(rows, start=1):
            item_key = key(value)
            values[item_key] = value
            strongest[item_key] = max(strongest[item_key], float(raw_score or 0))
            contributions[item_key].append(
                {
                    "branch_id": metadata.get("branch_id", f"branch:{source_index}"),
                    "branch_type": metadata.get("branch_type", "original"),
                    "rank": rank,
                    "weight": float(weight),
                    "raw_score": float(raw_score or 0),
                }
            )
    scores: dict[str, float] = {}
    provenance: dict[str, list[dict]] = {}
    for item_key, hits in contributions.items():
        original_hits = [hit for hit in hits if hit["branch_type"] == "original"]
        expansion_hits = [hit for hit in hits if hit["branch_type"] != "original"]
        expansion_hits.sort(
            key=lambda hit: (hit["weight"] / (60 + hit["rank"]), -hit["rank"]),
            reverse=True,
        )
        selected_hits = original_hits + expansion_hits[:MAX_BRANCH_HITS_PER_CANDIDATE]
        score = 0.0
        for index, hit in enumerate(selected_hits):
            contribution = hit["weight"] / (60 + hit["rank"])
            if hit["branch_type"] != "original" and index > len(original_hits):
                contribution *= 0.25
            score += contribution
        scores[item_key] = score
        provenance[item_key] = selected_hits
    ordered = sorted(
        scores,
        key=lambda item: (-scores[item], str(item)),
    )
    result = [(values[item], strongest[item]) for item in ordered]
    if return_provenance:
        return result, provenance
    return result


def _entity_coverage_context(understanding: dict) -> list[dict]:
    context = []
    query_language = understanding.get("query_lexicon", {}).get("query_language", "unknown")
    for matched in understanding.get("matched_entities", []):
        ambiguity = matched.get("ambiguity") or {}
        if ambiguity.get("expansion_suppressed"):
            continue
        terms = []
        for group_name in ("canonical_terms", "verified_translations", "verified_aliases"):
            terms.extend(matched.get(group_name) or [])
        trusted_terms = []
        for term in terms:
            normalized = normalize_term(term.get("term"))
            if not normalized or len(normalized) < 2:
                continue
            language = str(term.get("language") or "").casefold()
            language_family = (
                "zh" if language.startswith("zh") else "en" if language.startswith("en") else "unknown"
            )
            trusted_terms.append(
                {
                    "normalized_term": normalized,
                    "language": language_family,
                    "cross_language": (
                        query_language in {"zh", "en"}
                        and language_family in {"zh", "en"}
                        and language_family != query_language
                    ),
                }
            )
        if trusted_terms:
            context.append(
                {
                    "entity": matched["canonical_entity"],
                    "terms": trusted_terms,
                    "ambiguous": bool(ambiguity.get("is_ambiguous")),
                }
            )
    return context


def _is_latin_word_character(value: str) -> bool:
    if not value:
        return False
    if value.isdigit():
        return True
    return "LATIN" in unicodedata.name(value, "")


def _normalized_term_occurs(normalized_text: str, raw_term: object) -> bool:
    """Match Latin terms at word boundaries while preserving CJK compounds.

    Plain substring checks make ``field`` match ``midfield`` and ``structure``
    match ``infrastructure``. Chinese terms still use substring matching because
    ordinary Chinese prose has no explicit word separators. NFKC and casefold
    are inherited from QueryLexicon normalization.
    """

    normalized_text = normalize_term(normalized_text)
    term = normalize_term(raw_term)
    if not term:
        return False
    position = normalized_text.find(term)
    while position >= 0:
        end = position + len(term)
        before = normalized_text[position - 1] if position else ""
        after = normalized_text[end] if end < len(normalized_text) else ""
        left_ok = not (
            _is_latin_word_character(term[0])
            and _is_latin_word_character(before)
        )
        right_ok = not (
            _is_latin_word_character(term[-1])
            and _is_latin_word_character(after)
        )
        if left_ok and right_ok:
            return True
        position = normalized_text.find(term, position + 1)
    return False


def _coverage_features(chunk, terms: list[str], entity_context: list[dict]) -> dict:
    normalized = normalize_term(getattr(chunk, "original_text", "") or getattr(chunk, "normalized_text", ""))
    literal_hits = [term for term in terms if _normalized_term_occurs(normalized, term)]
    entity_hits = 0
    cross_language_hits = 0
    entity_terms: list[str] = []
    for entity in entity_context:
        hits = [
            term
            for term in entity["terms"]
            if _normalized_term_occurs(normalized, term["normalized_term"])
        ]
        if not hits:
            continue
        entity_hits += 1
        entity_terms.extend(term["normalized_term"] for term in hits[:3])
        if any(term["cross_language"] for term in hits):
            cross_language_hits += 1
    denominator = max(1, len(entity_context))
    return {
        "literal_coverage": len(literal_hits) / max(1, len(terms)),
        "entity_coverage": entity_hits / denominator if entity_context else 0.0,
        "cross_language_alias_coverage": (
            cross_language_hits / denominator if entity_context else 0.0
        ),
        "literal_hits": literal_hits[:6],
        "entity_term_hits": entity_terms[:6],
    }


def _public_understanding(understanding: dict) -> dict:
    """Hide internal-only generated and legacy terms from reader responses."""

    sanitized = deepcopy(understanding)
    resolution = sanitized.get("query_lexicon")
    if not isinstance(resolution, dict):
        return sanitized
    for matched in resolution.get("matched_entities") or []:
        matched_term = matched.get("matched_term")
        if isinstance(matched_term, dict) and not matched_term.get("displayable", True):
            matched_term["term"] = ""
        matched["search_variants"] = []
        for group_name in (
            "canonical_terms",
            "verified_translations",
            "verified_aliases",
            "historical_terms",
        ):
            matched[group_name] = [
                term
                for term in matched.get(group_name) or []
                if term.get("displayable", False)
            ]
    resolution["expansion_branches"] = [
        branch
        for branch in resolution.get("expansion_branches") or []
        if branch.get("displayable", True)
    ]
    sanitized["matched_entities"] = resolution.get("matched_entities", [])
    sanitized["expansion_branches"] = resolution.get("expansion_branches", [])
    return sanitized


def _intent_signal(text: str, intent: str) -> bool:
    return any(marker in text for marker in INTENT_MARKERS.get(intent, ()))


def _rule_rerank_v2(
    rows: list[dict],
    terms: list[str],
    intent: str,
    *,
    entity_context: list[dict] | None = None,
    query_profile: str = "conceptual",
) -> list[dict]:
    profile_rules = QUERY_PROFILE_RULES.get(
        query_profile,
        QUERY_PROFILE_RULES["conceptual"],
    )
    literal_weight = float(profile_rules.get("literal_coverage_weight", 0.10))
    entity_weight = float(profile_rules.get("entity_coverage_weight", 0.10))
    cross_language_weight = float(
        profile_rules.get("cross_language_coverage_weight", 0.09)
    )
    for row in rows:
        chunk = row["chunk"]
        coverage = _coverage_features(chunk, terms, entity_context or [])
        heading = normalize_term(f"{chunk.chapter_title} {chunk.section_title}")
        heading_signal = any(
            _normalized_term_occurs(heading, term)
            for term in terms
        )
        answer_signal = _intent_signal(str(chunk.original_text or ""), intent)
        quality_penalty = any(
            flag in chunk.quality_flags for flag in ("references", "table_of_contents")
        )
        multiplier = (
            1
            + coverage["literal_coverage"] * literal_weight
            + coverage["entity_coverage"] * entity_weight
            + coverage["cross_language_alias_coverage"] * cross_language_weight
            + (0.12 if answer_signal else 0)
            + (0.05 if heading_signal else 0)
            - (0.28 if quality_penalty else 0)
        )
        row["term_coverage"] = coverage["literal_coverage"]
        row["literal_coverage"] = coverage["literal_coverage"]
        row["entity_coverage"] = coverage["entity_coverage"]
        row["cross_language_alias_coverage"] = coverage[
            "cross_language_alias_coverage"
        ]
        row["literal_hits"] = coverage["literal_hits"]
        row["entity_term_hits"] = coverage["entity_term_hits"]
        row["intent_signal"] = answer_signal
        row["reranker_score"] = max(0.0, row["rrf"] * multiplier)
    return sorted(rows, key=lambda row: row["reranker_score"], reverse=True)


def _deduplicate_v2(rows: list[dict], *, limit: int, max_per_work: int) -> list[dict]:
    selected: list[dict] = []
    work_counts: dict[str, int] = defaultdict(int)
    content_hashes: set[str] = set()
    for row in rows:
        chunk = row["chunk"]
        work_id = str(chunk.work_id)
        if max_per_work and work_counts[work_id] >= max_per_work:
            continue
        content_hash = str(getattr(chunk, "content_hash", "") or "")
        if content_hash and content_hash in content_hashes:
            continue
        duplicate = False
        for existing in selected:
            other = existing["chunk"]
            if str(other.work_id) != work_id:
                continue
            if abs(other.page_start - chunk.page_start) > 1:
                continue
            if SequenceMatcher(
                None,
                str(other.normalized_text or "")[:1800],
                str(chunk.normalized_text or "")[:1800],
            ).ratio() >= 0.82:
                duplicate = True
                break
        if duplicate:
            continue
        selected.append(row)
        work_counts[work_id] += 1
        if content_hash:
            content_hashes.add(content_hash)
        if len(selected) >= limit:
            break
    return selected


def _response_type(row: dict, *, intent: str, model_applied: bool) -> tuple[str, str]:
    coverage = float(row.get("term_coverage") or 0)
    entity_coverage = float(row.get("entity_coverage") or 0)
    cross_language_coverage = float(
        row.get("cross_language_alias_coverage") or 0
    )
    intent_signal = bool(row.get("intent_signal"))
    model_rank = int(row.get("model_rerank_rank") or 0)
    evidence_coverage = max(coverage, entity_coverage * 0.75, cross_language_coverage * 0.8)
    if model_applied and model_rank and model_rank <= 3 and intent_signal and evidence_coverage >= 0.15:
        return "possible_response", "可能回应"
    if intent_signal and evidence_coverage >= 0.12:
        return "substantive_evidence", "相关论述"
    if row.get("vector_rank") and not row.get("keyword_rank"):
        return "semantic_related", "语义近似"
    return "background_context", "背景材料"


def _serialize_v2(
    row: dict,
    rank: int,
    total: int,
    terms: list[str],
    *,
    intent: str,
    model_applied: bool,
    debug: bool,
    entity_context: list[dict] | None = None,
    query_profile: str = "conceptual",
) -> dict:
    # Classification is a post-ranking description.  Computing these signals
    # here keeps the fast and balanced ablations free of intent-based ranking
    # bonuses while still giving readers a consistent, non-probabilistic label.
    if "term_coverage" not in row:
        coverage = _coverage_features(row["chunk"], terms, entity_context or [])
        row["term_coverage"] = coverage["literal_coverage"]
        row["literal_coverage"] = coverage["literal_coverage"]
        row["entity_coverage"] = coverage["entity_coverage"]
        row["cross_language_alias_coverage"] = coverage[
            "cross_language_alias_coverage"
        ]
        row["literal_hits"] = coverage["literal_hits"]
        row["entity_term_hits"] = coverage["entity_term_hits"]
    if "intent_signal" not in row:
        row["intent_signal"] = _intent_signal(
            str(row["chunk"].original_text or ""),
            intent,
        )
    payload = _serialize_row(row, rank, total, terms, debug=debug)
    # V1's serializer deliberately keeps its historical Work.language field.
    # V2 exposes the passage-level value without changing the V1 response.
    payload["language"] = getattr(row["chunk"], "language", "") or payload["language"]
    if row.get("cross_language_alias_coverage", 0) > 0:
        payload["reasons"] = [
            *payload.get("reasons", []),
            "原文命中同一术语实体的已确认跨语言名称",
        ]
    response_type, response_label = _response_type(
        row,
        intent=intent,
        model_applied=model_applied,
    )
    payload["candidate_order"] = rank
    payload["response_type"] = response_type
    payload["response_label"] = response_label
    # Keep the compatibility field, but no longer present a rank bucket as a
    # calibrated probability or absolute quality judgment.
    payload["relevance"] = response_label
    if debug:
        payload["debug"].update(
            {
                "keyword_score": row.get("keyword_score"),
                "vector_score": row.get("vector_score"),
                "model_rerank_score": row.get("model_rerank_score"),
                "term_coverage": round(float(row.get("term_coverage") or 0), 6),
                "literal_coverage": round(
                    float(row.get("literal_coverage") or 0),
                    6,
                ),
                "entity_coverage": round(
                    float(row.get("entity_coverage") or 0),
                    6,
                ),
                "cross_language_alias_coverage": round(
                    float(row.get("cross_language_alias_coverage") or 0),
                    6,
                ),
                "literal_hits": row.get("literal_hits", [])[:6],
                "entity_term_hits": row.get("entity_term_hits", [])[:6],
                "sparse_branch_hits": row.get("sparse_branch_hits", [])[:MAX_BRANCH_HITS_PER_CANDIDATE],
                "dense_branch_hits": row.get("dense_branch_hits", [])[:MAX_BRANCH_HITS_PER_CANDIDATE],
                "intent_signal": bool(row.get("intent_signal")),
            }
        )
    return payload


def semantic_search_v2(
    query: str,
    *,
    filters=None,
    limit=40,
    max_per_work=None,
    debug=False,
    strategy="hybrid_rerank",
    sort="relevance",
    query_override="",
    disable_query_rewrite=False,
    index_uid: str | None = None,
    semantic_ratio_override: float | None = None,
    search_profile: str | None = None,
    rerank_top_k_override: int | None = None,
    runtime_config_override: dict | None = None,
    disabled_branch_types: Iterable[str] | None = None,
    final_top_k_override: int | None = None,
) -> dict:
    started = time.monotonic()
    timings: dict[str, float | None] = {"query_embedding_ms": None}
    counts: dict[str, int] = {}
    config = runtime_config_override or current_semantic_runtime()
    filters = filters or {}
    profile = _profile(
        search_profile,
        rerank_top_k_override=rerank_top_k_override,
        final_top_k_override=final_top_k_override,
    )
    index_uid = index_uid or active_semantic_index_uid()
    query_override = str(query_override or "").strip()[:600]
    expansion_enabled = bool(
        getattr(settings, "SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED", True)
        and not disable_query_rewrite
    )

    stage_started = time.monotonic()
    query_rewrite_fallback = False
    try:
        understanding = analyze_query(
            query,
            expansion_limit=profile["expansion_limit"] if expansion_enabled else 0,
            explicit_rewrite=query_override,
            disabled_branch_types=disabled_branch_types,
        )
    except (DatabaseError, RuntimeError, TypeError, ValueError):
        query_rewrite_fallback = True
        folded, terms = _query_terms(query)
        understanding = {
            "type": "观点陈述",
            "intent": "statement",
            "intent_label": "观点陈述",
            "object": query[:120],
            "terms": terms[:10],
            "related_concepts": [],
            "rewrites": [query],
            "rewrite_source": "原始问题",
        }
    timings["query_analysis_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    folded, terms = _query_terms(query)
    expansion_branches = [dict(branch) for branch in understanding.get("expansion_branches", [])]
    if not expansion_branches:
        expansion_branches = [
            {
                "branch_id": "original:0",
                "branch_type": "original",
                "query": query,
                "term": query,
                "trust_level": "original",
                "effective_trust_level": "original",
                "displayable": True,
                "retrieval_channels": ["sparse", "dense"],
                "ambiguous": False,
                "entities": [],
            }
        ]
    for branch in expansion_branches:
        branch["weight"] = branch_weight(branch)
    expansion_queries = expansion_branches[1:]
    entity_context = _entity_coverage_context(understanding)
    query_profile = understanding.get("query_profile") or "conceptual"
    semantic_ratio_base = (
        config["semantic_ratio"]
        if semantic_ratio_override is None
        else min(1.0, max(0.0, float(semantic_ratio_override)))
    )
    semantic_ratio = (
        effective_semantic_ratio(semantic_ratio_base, query_profile)
        if semantic_ratio_override is None
        else semantic_ratio_base
    )
    fallback_reasons: list[str] = []
    page_fallback_used = False
    counts["retrieval_branch_count"] = len(expansion_branches)
    counts["expansion_branch_count"] = len(expansion_queries)
    counts["matched_entity_count"] = len(understanding.get("matched_entities") or [])
    counts["query_lexicon_db_query_count"] = int(
        understanding.get("query_lexicon", {}).get("resolver_db_query_count") or 0
    )
    timings["query_lexicon_ms"] = float(
        understanding.get("query_lexicon", {}).get("resolver_timing_ms") or 0
    )

    sparse_sources: list[tuple[list[tuple[object, float]], float, dict]] = []
    sparse_remote_sources: list[tuple[list[tuple[str, float]], float, dict]] = []
    stage_started = time.monotonic()
    if strategy != "vector":
        for branch in expansion_branches:
            if "sparse" not in branch.get("retrieval_channels", ["sparse"]):
                continue
            try:
                sparse_remote_sources.append(
                    (
                        _meili_sparse_candidates(
                            branch["query"],
                            filters,
                            limit=profile["sparse_top_k"],
                            index_uid=index_uid,
                        ),
                        float(branch.get("weight") or 0),
                        {
                            "branch_id": branch["branch_id"],
                            "branch_type": branch["branch_type"],
                        },
                    )
                )
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                fallback_reasons.append(
                    "sparse_service_unavailable"
                    if branch["branch_type"] == "original"
                    else "sparse_expansion_unavailable"
                )
        sparse_sources.extend(_hydrate_sources(sparse_remote_sources, filters))
        if not sparse_remote_sources or not any(
            metadata.get("branch_type") == "original"
            for _rows, _weight, metadata in sparse_sources
        ):
            sparse_sources.append(
                (
                    _keyword_candidates(
                        folded,
                        terms,
                        filters,
                        limit=profile["sparse_top_k"],
                    ),
                    1.0,
                    {"branch_id": "original:db-fallback", "branch_type": "original"},
                )
            )
        passage_rows = _passage_keyword_candidates(
            folded,
            terms,
            filters,
            limit=profile["sparse_top_k"],
        )
        if passage_rows:
            page_fallback_used = True
            sparse_sources.append(
                (
                    passage_rows,
                    0.82,
                    {"branch_id": "original:passage-fallback", "branch_type": "original"},
                )
            )
    sparse_rows, sparse_provenance = _merge_ranked_lists(
        sparse_sources,
        key=lambda value: str(value.id),
        return_provenance=True,
    )
    timings["sparse_retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["sparse_candidate_count"] = len(sparse_rows)
    counts["sparse_retrieval_request_count"] = len(sparse_remote_sources)

    dense_sources: list[tuple[list[tuple[str, float]], float, dict]] = []
    stage_started = time.monotonic()
    if strategy not in {"keyword", "legacy"} and semantic_ratio > 0:
        local_health = (
            semantic_model_health(config)
            if config.get("provider") == "huggingFace" and config.get("offline_mode")
            else None
        )
        if not config.get("enabled") or config.get("engine") != "meilisearch_hybrid":
            fallback_reasons.append("semantic_disabled")
        elif local_health is not None and not local_health.get("available"):
            fallback_reasons.append("local_model_unavailable")
        else:
            for branch in expansion_branches:
                if "dense" not in branch.get("retrieval_channels", ["dense"]):
                    continue
                try:
                    dense_sources.append(
                        (
                            _meili_dense_candidates(
                                branch["query"],
                                config,
                                filters,
                                limit=profile["dense_top_k"],
                                index_uid=index_uid,
                            ),
                            float(branch.get("weight") or 0),
                            {
                                "branch_id": branch["branch_id"],
                                "branch_type": branch["branch_type"],
                            },
                        )
                    )
                except (httpx.HTTPError, KeyError, TypeError, ValueError):
                    fallback_reasons.append(
                        "semantic_service_unavailable"
                        if branch["branch_type"] == "original"
                        else "dense_expansion_unavailable"
                    )
    dense_rows, dense_provenance = _merge_ranked_lists(
        dense_sources,
        key=str,
        return_provenance=True,
    )
    timings["dense_retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["dense_candidate_count"] = len(dense_rows)
    counts["dense_retrieval_request_count"] = len(dense_sources)

    stage_started = time.monotonic()
    rows = _rrf(
        sparse_rows,
        dense_rows,
        filters=filters,
        semantic_ratio=semantic_ratio,
    )
    for row in rows:
        candidate_id = str(row["chunk"].id)
        row["sparse_branch_hits"] = sparse_provenance.get(candidate_id, [])
        row["dense_branch_hits"] = dense_provenance.get(candidate_id, [])
    rows = sorted(rows, key=lambda row: row["rrf"], reverse=True)[: profile["fusion_top_k"]]
    timings["rrf_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["fusion_candidate_count"] = len(rows)

    stage_started = time.monotonic()
    if profile["name"] == "precision":
        rows = _rule_rerank_v2(
            rows,
            terms,
            understanding["intent"],
            entity_context=entity_context,
            query_profile=query_profile,
        )
    reranker_config = current_reranker_config()
    model_applied = False
    reranker_fallback = False
    reranker_fallback_reason = ""
    if (
        strategy == "hybrid_rerank"
        and profile["rerank_top_k"] > 0
        and reranker_config.provider == "local_http"
    ):
        try:
            reranked = rerank_candidates(
                query,
                rows,
                top_k=profile["rerank_top_k"],
                config=reranker_config,
                include_context=profile["name"] == "precision",
            )
            rows = reranked["rows"]
            model_applied = bool(reranked["applied"])
        except SemanticRerankerError:
            reranker_fallback = True
            reranker_fallback_reason = "reranker_service_unavailable"
    timings["rerank_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["rerank_candidate_count"] = (
        min(profile["rerank_top_k"], len(rows)) if model_applied else 0
    )
    counts["rule_rerank_candidate_count"] = (
        len(rows) if profile["name"] == "precision" else 0
    )

    if sort == "relevance":
        rows = _apply_feedback_calibration(rows, query)
    elif sort == "newest":
        rows.sort(
            key=lambda row: (
                row["chunk"].asset.edition.first_published_at
                or row["chunk"].asset.edition.published_at
                or row["chunk"].asset.edition.created_at
            ).timestamp(),
            reverse=True,
        )
    elif sort == "year":
        rows.sort(
            key=lambda row: row["chunk"].asset.edition.publication_year or 0,
            reverse=True,
        )

    stage_started = time.monotonic()
    effective_max = max_per_work if max_per_work is not None else config["max_results_per_work"]
    final_limit = min(max(1, int(limit)), profile["final_top_k"])
    rows = _deduplicate_v2(
        rows,
        limit=final_limit,
        max_per_work=max(0, int(effective_max)),
    )
    timings["dedup_ms"] = round((time.monotonic() - stage_started) * 1000, 2)

    stage_started = time.monotonic()
    results = [
        _serialize_v2(
            row,
            rank,
            len(rows),
            terms,
            intent=understanding["intent"],
            model_applied=model_applied,
            debug=debug,
            entity_context=entity_context,
            query_profile=query_profile,
        )
        for rank, row in enumerate(rows, start=1)
    ]
    timings["context_fetch_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    timings["total_ms"] = round((time.monotonic() - started) * 1000, 2)
    counts["final_result_count"] = len(results)
    response_understanding = (
        understanding if debug else _public_understanding(understanding)
    )
    response_branches = (
        expansion_branches
        if debug
        else [branch for branch in expansion_branches if branch.get("displayable", True)]
    )
    response_expansions = response_branches[1:]
    response_understanding["rewrites"] = [
        str(branch.get("query") or "") for branch in response_branches
    ]
    response_understanding["expansion_branches"] = response_branches
    fallback_reasons = list(dict.fromkeys(fallback_reasons))
    fallback_used = bool(fallback_reasons)
    engine = (
        "v2_hybrid"
        if sparse_rows and dense_rows
        else "v2_sparse_fallback"
        if sparse_rows
        else "v2_dense_only"
        if dense_rows
        else "v2_empty"
    )
    logger.info(
        "viewpoint_search_v2_completed",
        extra={
            "query_hash": sha256(query.strip().casefold().encode("utf-8")).hexdigest(),
            "search_profile": profile["name"],
            "index_uid": index_uid,
            "engine": engine,
            "fallback_reasons": fallback_reasons,
            "reranker_fallback": reranker_fallback,
            "timing_ms": timings,
            "candidate_counts": counts,
        },
    )
    return {
        "search_version": "v2",
        "search_profile": profile["name"],
        "engine": engine,
        "index_uid": index_uid,
        "semantic_ratio": semantic_ratio,
        "semantic_ratio_base": semantic_ratio_base,
        "strategy": strategy,
        "sort": sort,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reasons[0] if fallback_reasons else "",
        "fallback_reasons": fallback_reasons,
        "page_fallback_used": page_fallback_used,
        "notice": (
            "当前限定下没有找到可核对的馆藏原文。"
            if not results
            else "语义召回当前不可用，已使用馆藏关键词和章节位置继续检索。"
            if not dense_rows and sparse_rows
            else "结果经过关键词与语义候选融合，并保留原文、上下文和页码供核对。"
        ),
        "understanding": response_understanding,
        "query_rewrite_enabled": bool(
            getattr(settings, "SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED", True)
        ),
        "query_rewrite_active": bool(response_expansions),
        "active_rewrite": " | ".join(
            str(branch.get("query") or "") for branch in response_expansions
        ),
        "query_rewrite_fallback": query_rewrite_fallback,
        "query_profile": query_profile,
        "disabled_branch_types": understanding.get("disabled_branch_types", []),
        "query_lexicon_revision": understanding.get("query_lexicon_revision"),
        "query_lexicon_resolution": response_understanding.get("query_lexicon"),
        "expansion_branches": response_branches,
        "reranker": {
            "provider": reranker_config.provider,
            "model": reranker_config.model if reranker_config.provider == "local_http" else "",
            "applied": model_applied,
        },
        "reranker_fallback": reranker_fallback,
        "reranker_fallback_reason": reranker_fallback_reason,
        "results": results,
        "work_count": len({item["work_id"] for item in results}),
        "timing_ms": timings["total_ms"] if debug else None,
        "stage_timings_ms": timings if debug else None,
        "candidate_counts": counts if debug else None,
        "diagnostics": {
            "timing_ms": timings,
            "candidate_counts": counts,
            "query_embedding_ms_note": "查询向量由 Meilisearch 在 dense 请求内生成，当前无法单独测量。",
            "query_lexicon_revision": understanding.get("query_lexicon_revision"),
            "query_profile": query_profile,
            "disabled_branch_types": understanding.get(
                "disabled_branch_types",
                [],
            ),
            "expansion_limits": understanding.get("query_lexicon", {}).get(
                "limits",
                current_search_v2_limits(
                    expansion_limit=profile["expansion_limit"]
                ).as_dict(),
            ),
        }
        if debug
        else None,
    }
