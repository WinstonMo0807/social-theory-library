from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from hashlib import sha256
import logging
import re
import time

import httpx
from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError

from catalog.models import SemanticChunk
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
    _taxonomy_matches,
    current_semantic_runtime,
    semantic_model_health,
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


def _profile(name: str | None, *, rerank_top_k_override: int | None) -> dict:
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
    return {
        "name": selected,
        "dense_top_k": int(getattr(settings, "SEMANTIC_SEARCH_DENSE_TOP_K", 50)),
        "sparse_top_k": int(getattr(settings, "SEMANTIC_SEARCH_SPARSE_TOP_K", 50)),
        "fusion_top_k": fusion_top_k,
        "rerank_top_k": rerank_top_k,
        "final_top_k": int(getattr(settings, "SEMANTIC_SEARCH_FINAL_TOP_K", 10)),
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


def _safe_taxonomy(query: str, terms: list[str]) -> list[dict]:
    cache_key = "semantic:v2:taxonomy:" + sha256(query.encode("utf-8")).hexdigest()
    cached = cache.get(cache_key)
    if isinstance(cached, list):
        return cached
    try:
        rows = _taxonomy_matches(query, terms)
    except DatabaseError:
        return []
    cache.set(cache_key, rows, timeout=300)
    return rows


def analyze_query(query: str, *, expansion_limit: int, explicit_rewrite: str = "") -> dict:
    folded, terms = _query_terms(query)
    intent = _intent(query)
    target = _query_object(query) or query.strip()[:120]
    taxonomy = _safe_taxonomy(folded, terms)
    rewrites = [query.strip()]
    if explicit_rewrite:
        rewrites.append(f"{query.strip()} {explicit_rewrite.strip()[:600]}".strip())
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
        candidate = f"{target} {phrase}".strip()
        if candidate and candidate not in rewrites:
            rewrites.append(candidate)
    # A controlled concept is only added when it already appears in the query
    # or the local matcher is unusually strong.  This avoids treating adjacent
    # social-science concepts as interchangeable synonyms.
    for item in taxonomy:
        name = str(item.get("name") or "").strip()
        if not name or not (name in query or float(item.get("score") or 0) >= 0.38):
            continue
        candidate = f"{query.strip()} {name}".strip()
        if candidate not in rewrites:
            rewrites.append(candidate)
    bounded = [rewrites[0], *rewrites[1 : 1 + max(0, expansion_limit)]]
    return {
        "type": INTENT_LABELS[intent],
        "intent": intent,
        "intent_label": INTENT_LABELS[intent],
        "object": target,
        "terms": terms[:10],
        "related_concepts": [
            {"name": item["name"], "kind": item["label"], "slug": item["slug"]}
            for item in taxonomy[:8]
        ],
        "rewrites": bounded,
        "rewrite_source": "原始问题与保守问题结构",
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


def _hydrate(rows: list[tuple[str, float]], filters: dict) -> list[tuple[object, float]]:
    ids = [item[0] for item in rows]
    chunks = _base_queryset(filters).filter(pk__in=ids)
    mapping = {str(chunk.id): chunk for chunk in chunks}
    return [(mapping[item_id], score) for item_id, score in rows if item_id in mapping]


def _merge_ranked_lists(sources: list[tuple[list[tuple[object, float]], float]], *, key) -> list[tuple[object, float]]:
    scores: dict[str, float] = defaultdict(float)
    values: dict[str, object] = {}
    strongest: dict[str, float] = defaultdict(float)
    for rows, weight in sources:
        if weight <= 0:
            continue
        for rank, (value, raw_score) in enumerate(rows, start=1):
            item_key = key(value)
            values[item_key] = value
            scores[item_key] += float(weight) / (60 + rank)
            strongest[item_key] = max(strongest[item_key], float(raw_score or 0))
    ordered = sorted(scores, key=lambda item: scores[item], reverse=True)
    return [(values[item], strongest[item]) for item in ordered]


def _intent_signal(text: str, intent: str) -> bool:
    return any(marker in text for marker in INTENT_MARKERS.get(intent, ()))


def _rule_rerank_v2(rows: list[dict], terms: list[str], intent: str) -> list[dict]:
    for row in rows:
        chunk = row["chunk"]
        normalized = str(chunk.normalized_text or "")
        coverage = sum(1 for term in terms if term in normalized) / max(1, len(terms))
        heading = f"{chunk.chapter_title} {chunk.section_title}"
        heading_signal = any(term in heading for term in terms)
        answer_signal = _intent_signal(str(chunk.original_text or ""), intent)
        quality_penalty = any(
            flag in chunk.quality_flags for flag in ("references", "table_of_contents")
        )
        multiplier = (
            1
            + coverage * 0.20
            + (0.12 if answer_signal else 0)
            + (0.05 if heading_signal else 0)
            - (0.28 if quality_penalty else 0)
        )
        row["term_coverage"] = coverage
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
    intent_signal = bool(row.get("intent_signal"))
    model_rank = int(row.get("model_rerank_rank") or 0)
    if model_applied and model_rank and model_rank <= 3 and intent_signal and coverage >= 0.15:
        return "possible_response", "可能回应"
    if intent_signal and coverage >= 0.12:
        return "substantive_evidence", "相关论述"
    if row.get("vector_rank") and not row.get("keyword_rank"):
        return "semantic_related", "语义近似"
    return "background_context", "背景材料"


def _serialize_v2(row: dict, rank: int, total: int, terms: list[str], *, intent: str, model_applied: bool, debug: bool) -> dict:
    # Classification is a post-ranking description.  Computing these signals
    # here keeps the fast and balanced ablations free of intent-based ranking
    # bonuses while still giving readers a consistent, non-probabilistic label.
    if "term_coverage" not in row:
        normalized = str(row["chunk"].normalized_text or "")
        row["term_coverage"] = sum(
            1 for term in terms if term in normalized
        ) / max(1, len(terms))
    if "intent_signal" not in row:
        row["intent_signal"] = _intent_signal(
            str(row["chunk"].original_text or ""),
            intent,
        )
    payload = _serialize_row(row, rank, total, terms, debug=debug)
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
) -> dict:
    started = time.monotonic()
    timings: dict[str, float | None] = {"query_embedding_ms": None}
    counts: dict[str, int] = {}
    config = runtime_config_override or current_semantic_runtime()
    filters = filters or {}
    profile = _profile(search_profile, rerank_top_k_override=rerank_top_k_override)
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
    rewrites = understanding["rewrites"]
    expansion_queries = rewrites[1:]

    semantic_ratio = (
        config["semantic_ratio"]
        if semantic_ratio_override is None
        else min(1.0, max(0.0, float(semantic_ratio_override)))
    )
    fallback_reasons: list[str] = []
    page_fallback_used = False

    sparse_sources: list[tuple[list[tuple[object, float]], float]] = []
    stage_started = time.monotonic()
    if strategy != "vector":
        try:
            sparse_original = _hydrate(
                _meili_sparse_candidates(
                    query,
                    filters,
                    limit=profile["sparse_top_k"],
                    index_uid=index_uid,
                ),
                filters,
            )
            sparse_sources.append((sparse_original, 1.0))
            for rewrite in expansion_queries:
                sparse_sources.append(
                    (
                        _hydrate(
                            _meili_sparse_candidates(
                                rewrite,
                                filters,
                                limit=profile["sparse_top_k"],
                                index_uid=index_uid,
                            ),
                            filters,
                        ),
                        0.32,
                    )
                )
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            fallback_reasons.append("sparse_service_unavailable")
            sparse_sources.append(
                (_keyword_candidates(folded, terms, filters, limit=profile["sparse_top_k"]), 1.0)
            )
        passage_rows = _passage_keyword_candidates(
            folded,
            terms,
            filters,
            limit=profile["sparse_top_k"],
        )
        if passage_rows:
            page_fallback_used = True
            sparse_sources.append((passage_rows, 0.82))
    sparse_rows = _merge_ranked_lists(
        sparse_sources,
        key=lambda value: str(value.id),
    )
    timings["sparse_retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["sparse_candidate_count"] = len(sparse_rows)

    dense_sources: list[tuple[list[tuple[object, float]], float]] = []
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
            try:
                dense_sources.append(
                    (
                        _meili_dense_candidates(
                            query,
                            config,
                            filters,
                            limit=profile["dense_top_k"],
                            index_uid=index_uid,
                        ),
                        1.0,
                    )
                )
                for rewrite in expansion_queries:
                    dense_sources.append(
                        (
                            _meili_dense_candidates(
                                rewrite,
                                config,
                                filters,
                                limit=profile["dense_top_k"],
                                index_uid=index_uid,
                            ),
                            0.32,
                        )
                    )
            except (httpx.HTTPError, KeyError, TypeError, ValueError):
                fallback_reasons.append("semantic_service_unavailable")
    dense_rows = _merge_ranked_lists(dense_sources, key=str)
    timings["dense_retrieval_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["dense_candidate_count"] = len(dense_rows)

    stage_started = time.monotonic()
    rows = _rrf(
        sparse_rows,
        dense_rows,
        filters=filters,
        semantic_ratio=semantic_ratio,
    )
    rows = sorted(rows, key=lambda row: row["rrf"], reverse=True)[: profile["fusion_top_k"]]
    timings["rrf_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    counts["fusion_candidate_count"] = len(rows)

    stage_started = time.monotonic()
    if profile["name"] == "precision":
        rows = _rule_rerank_v2(rows, terms, understanding["intent"])
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
        )
        for rank, row in enumerate(rows, start=1)
    ]
    timings["context_fetch_ms"] = round((time.monotonic() - stage_started) * 1000, 2)
    timings["total_ms"] = round((time.monotonic() - started) * 1000, 2)
    counts["final_result_count"] = len(results)
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
        "understanding": understanding,
        "query_rewrite_enabled": bool(
            getattr(settings, "SEMANTIC_SEARCH_V2_QUERY_EXPANSION_ENABLED", True)
        ),
        "query_rewrite_active": bool(expansion_queries),
        "active_rewrite": " | ".join(expansion_queries),
        "query_rewrite_fallback": query_rewrite_fallback,
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
        }
        if debug
        else None,
    }
