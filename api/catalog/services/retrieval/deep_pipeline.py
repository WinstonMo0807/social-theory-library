"""STL 4.0's recommended deep retrieval supplement.

The ordinary Discovery task already provides the first screen: QueryLexicon
normalisation, sparse/dense fusion, source validation and the frozen mMARCO
order.  This module only adds the bounded, asynchronous deep stages required
by the final reader/research views.  Every optional network call is explicitly
enabled, host allowlisted and safe to skip; the baseline remains usable when a
candidate index or deep model is unavailable.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
import json
import logging
from urllib.parse import urlsplit

import httpx
from django.conf import settings

from catalog.services.discovery_inference import DiscoveryInferenceError, embed_texts
from catalog.services.discovery_projection import (
    DiscoveryIndexError,
    current_scopes,
    meili,
    validate_discovery_results,
)
from catalog.services.query_lexicon.search import resolve_search_query

logger = logging.getLogger(__name__)

PIPELINE_VERSION = "stl4-recommended-deep-v1"
MAX_DEEP_CANDIDATES = 40
MAX_BGE_CANDIDATES = 20
MAX_CONTEXT_CANDIDATES = 10
MAX_QUERY_VARIANTS = 3
DEEP_RESULT_KEY = "passages_deep"


def _context_limit() -> int:
    return max(
        5,
        min(
            int(getattr(settings, "STL_DEEP_RETRIEVAL_CONTEXT_TOP_K", MAX_CONTEXT_CANDIDATES)),
            MAX_CONTEXT_CANDIDATES,
        ),
    )


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "channel": "deep"}


def _enabled() -> bool:
    return bool(getattr(settings, "STL_DEEP_RETRIEVAL_ENABLED", False))


def _identity(row: dict) -> str:
    return str(row.get("id") or row.get("document_id") or "")


def _excerpt(row: dict) -> str:
    return str(row.get("excerpt") or row.get("text") or "").strip()


def _rrf(branches: Iterable[tuple[list[dict], float]]) -> list[dict]:
    scores: dict[str, float] = {}
    rows: dict[str, dict] = {}
    for candidates, weight in branches:
        seen: set[str] = set()
        for rank, row in enumerate(candidates, 1):
            key = _identity(row)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.setdefault(key, row)
            scores[key] = scores.get(key, 0.0) + float(weight) / (60 + rank)
    return [rows[key] for key in sorted(rows, key=lambda key: (-scores[key], key))]


def _query_variants(query: str) -> tuple[list[dict], dict]:
    """Resolve bounded public lexicon branches without forcing a rewrite."""

    try:
        result = resolve_search_query(
            query,
            scope="public_active",
            expansion_limit=MAX_QUERY_VARIANTS - 1,
        )
        branches = list(result.get("expansion_branches") or [])
        return branches[:MAX_QUERY_VARIANTS], {
            "status": "completed",
            "revision": result.get("query_lexicon_revision"),
            "branch_count": len(branches),
            "resolver_version": result.get("search_resolver_version", ""),
        }
    except Exception as exc:  # lexicon failure must not hide baseline results
        logger.warning("Deep QueryLexicon unavailable: %s", type(exc).__name__)
        return [{"query": query, "branch_type": "original"}], {
            "status": "degraded",
            "revision": None,
            "branch_count": 1,
            "resolver_version": "",
            "warning": "query_lexicon_unavailable",
        }


def _deep_meili_filter(filters: dict, access_statuses: list[str]) -> dict:
    scopes = current_scopes("passages", access_statuses, filters)
    payload = {
        "limit": MAX_DEEP_CANDIDATES,
        "filter": [
            'channel = "passages"',
            f"scope_token IN {json.dumps(scopes)}",
            f"access_status IN {json.dumps(list(access_statuses))}",
        ],
        "attributesToRetrieve": ["id", "source_revision"],
    }
    if filters.get("languages"):
        from catalog.services.semantic_search import _language_filter_values

        payload["filter"].append(
            f"language IN {json.dumps(_language_filter_values(filters['languages']))}"
        )
    return payload


def _eg2_candidates(
    query: str,
    filters: dict,
    access_statuses: list[str],
    *,
    index_uid: str,
    embedding_artifact: str,
    dimensions: int,
) -> tuple[list[dict], dict, list[dict]]:
    """Read an explicitly configured EG2 index; never touch the active index."""

    warnings: list[dict] = []
    if not index_uid or not embedding_artifact:
        return [], {"status": "disabled", "index_uid": "", "artifact": ""}, warnings
    try:
        base = _deep_meili_filter(filters, access_statuses)
        sparse_response = meili(
            "POST", f"/indexes/{index_uid}/search", {**base, "q": query}
        )
        vector = embed_texts(
            [query],
            kind="query",
            expected_artifact=embedding_artifact,
            expected_dimensions=dimensions,
        )["vectors"][0]
        dense_response = meili(
            "POST",
            f"/indexes/{index_uid}/search",
            {
                **base,
                "q": "",
                "vector": vector,
                "hybrid": {"embedder": "discovery", "semanticRatio": 1.0},
            },
        )
        sparse = sparse_response.get("hits") or []
        dense = dense_response.get("hits") or []
        validated = validate_discovery_results(
            "passages", _rrf([(sparse, 1.0), (dense, 1.0)])[:MAX_DEEP_CANDIDATES], access_statuses
        )
        return validated, {
            "status": "completed",
            "index_uid": index_uid,
            "artifact": embedding_artifact,
            "dimensions": dimensions,
            "sparse_count": len(sparse),
            "dense_count": len(dense),
        }, warnings
    except (DiscoveryIndexError, DiscoveryInferenceError, TypeError, ValueError, KeyError) as exc:
        logger.warning("Deep EmbeddingGemma recall unavailable: %s", type(exc).__name__)
        warnings.append(_warning("deep_embedding_unavailable", "深度向量召回暂不可用，已保留首屏检索结果。"))
        return [], {
            "status": "degraded",
            "index_uid": index_uid,
            "artifact": embedding_artifact,
            "dimensions": dimensions,
        }, warnings


def _validate_service_endpoint(url: str, allowed_hosts: tuple[str, ...]) -> str:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").casefold()
    if (
        parsed.scheme not in {"http", "https"}
        or not hostname
        or hostname not in {value.casefold().strip() for value in allowed_hosts if value.strip()}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("deep service endpoint is not allowlisted")
    return hostname


def _post_deep_service(
    url: str,
    payload: dict,
    *,
    allowed_hosts: tuple[str, ...],
    timeout_seconds: int,
    api_key: str = "",
) -> dict:
    _validate_service_endpoint(url, allowed_hosts)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        response = httpx.post(
            url,
            headers=headers,
            json=payload,
            timeout=timeout_seconds,
            trust_env=False,
            follow_redirects=False,
        )
        if 300 <= response.status_code < 400 or len(response.content) > 1_000_000:
            raise ValueError("unsafe deep service response")
        response.raise_for_status()
        value = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise ValueError("deep service unavailable") from exc
    if not isinstance(value, dict):
        raise ValueError("deep service response is not an object")
    return value


def _parse_order(payload: dict, rows: list[dict]) -> tuple[list[dict], dict[int, float]]:
    values = payload.get("results")
    if not isinstance(values, list):
        raise ValueError("deep service results are invalid")
    ordered: list[dict] = []
    scores: dict[int, float] = {}
    used: set[int] = set()
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
            score = float(item.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(rows) or index in used:
            continue
        ordered.append(rows[index])
        scores[index] = score
        used.add(index)
    if not ordered:
        raise ValueError("deep service returned no usable order")
    ordered.extend(rows[index] for index in range(len(rows)) if index not in used)
    return ordered, scores


def _bge_rerank(query: str, rows: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    config = {
        "enabled": bool(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_ENABLED", False)),
        "url": str(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_URL", "")),
        "model": str(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_MODEL", "")),
    }
    warnings: list[dict] = []
    if not config["enabled"] or not config["url"]:
        return rows, {"status": "disabled", "provider": "local_http", "model": config["model"]}, warnings
    if config["model"].casefold() != "baai/bge-reranker-v2-m3":
        warnings.append(_warning("deep_bge_model_not_allowlisted", "深排模型未通过 BGE-reranker-v2-m3 白名单校验。"))
        return rows, {"status": "degraded", "provider": "local_http", "model": config["model"]}, warnings
    candidates = list(rows[:MAX_BGE_CANDIDATES])
    try:
        payload = _post_deep_service(
            config["url"],
            {
                "model": config["model"],
                "query": str(query)[:1200],
                "documents": [_excerpt(row)[:4000] for row in candidates],
                "top_n": len(candidates),
                "return_documents": False,
            },
            allowed_hosts=tuple(str(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_ALLOWED_HOSTS", "")).split(",")),
            timeout_seconds=int(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_TIMEOUT_SECONDS", 30)),
            api_key=str(getattr(settings, "STL_DEEP_RETRIEVAL_BGE_API_KEY", "")),
        )
        ordered, scores = _parse_order(payload, candidates)
        for rank, row in enumerate(ordered, 1):
            row = row
            row["deep_rank"] = rank
            row["deep_score"] = scores.get(candidates.index(row))
        ordered.extend(rows[len(candidates):])
        return ordered, {
            "status": "completed",
            "provider": "local_http",
            "model": config["model"],
            "top_k": len(candidates),
        }, warnings
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("Deep BGE reranker unavailable: %s", type(exc).__name__)
        warnings.append(_warning("deep_bge_unavailable", "BGE 深度重排暂不可用，已保留 mMARCO 顺序。"))
        return rows, {
            "status": "degraded",
            "provider": "local_http",
            "model": config["model"],
            "top_k": len(candidates),
        }, warnings


def _attach_adjacent_context(rows: list[dict], access_statuses: list[str]) -> tuple[list[dict], dict, list[dict]]:
    warnings: list[dict] = []
    selected = rows[:_context_limit()]
    if not selected:
        return rows, {"status": "skipped", "provider": "adjacent-evidence-v1", "count": 0}, warnings
    try:
        from catalog.services.discovery_context import rerank_contexts

        contexts = rerank_contexts(selected, access_statuses)
        for row, context in zip(selected, contexts):
            row["deep_context"] = {
                "policy": "adjacent-evidence-v1",
                "provider": "library-evidence",
                "available": bool(context.get("context_available")),
                "before": context.get("before", ""),
                "after": context.get("after", ""),
                "blocks": context.get("blocks", []),
            }
        status = "completed"
    except Exception as exc:  # context is supplementary; evidence remains valid
        logger.warning("Adjacent context unavailable: %s", type(exc).__name__)
        warnings.append(_warning("deep_context_unavailable", "邻近原文上下文暂不可用，已保留证据定位。"))
        status = "degraded"
    return rows, {"status": status, "provider": "adjacent-evidence-v1", "count": len(selected)}, warnings


def _convmemory_organize(query: str, rows: list[dict]) -> tuple[list[dict], dict, list[dict]]:
    enabled = bool(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_ENABLED", False))
    url = str(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_URL", ""))
    model = str(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_MODEL", ""))
    warnings: list[dict] = []
    selected = rows[:_context_limit()]
    if not enabled or not url or not selected:
        return rows, {"status": "disabled", "provider": "convmemory-v2", "model": model, "count": len(selected)}, warnings
    try:
        payload = _post_deep_service(
            url,
            {
                "model": model,
                "query": str(query)[:1200],
                "items": [
                    {
                        "id": _identity(row),
                        "text": _excerpt(row)[:4000],
                        "context": row.get("deep_context") or {},
                    }
                    for row in selected
                ],
                "top_n": len(selected),
            },
            allowed_hosts=tuple(str(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_ALLOWED_HOSTS", "")).split(",")),
            timeout_seconds=int(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_TIMEOUT_SECONDS", 30)),
            api_key=str(getattr(settings, "STL_DEEP_RETRIEVAL_CONVMEMORY_API_KEY", "")),
        )
        ordered, _scores = _parse_order(payload, selected)
        for rank, row in enumerate(ordered, 1):
            row["deep_rank"] = rank
        ordered.extend(rows[len(selected):])
        return ordered, {"status": "completed", "provider": "convmemory-v2", "model": model, "count": len(selected)}, warnings
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("ConvMemory context organization unavailable: %s", type(exc).__name__)
        warnings.append(_warning("deep_convmemory_unavailable", "连续上下文组织暂不可用，已保留 BGE 结果和邻近证据。"))
        return rows, {"status": "degraded", "provider": "convmemory-v2", "model": model, "count": len(selected)}, warnings


def run_deep_pipeline(
    query: str,
    baseline_rows: list[dict],
    access_statuses: list[str],
    *,
    filters: dict | None = None,
    is_current: Callable[[], bool] | None = None,
) -> dict:
    """Run the bounded deep supplement and return validated row candidates."""

    if not _enabled():
        return {
            "rows": [],
            "status": "disabled",
            "pipeline_version": PIPELINE_VERSION,
            "query_lexicon": {"status": "disabled"},
            "embedding": {"status": "disabled"},
            "bge": {"status": "disabled"},
            "context": {"status": "disabled"},
            "convmemory": {"status": "disabled"},
            "warnings": [],
        }
    warnings: list[dict] = []
    rows = [dict(row) for row in baseline_rows[:MAX_DEEP_CANDIDATES] if _identity(row)]
    if not rows:
        return {
            "rows": [],
            "status": "skipped",
            "pipeline_version": PIPELINE_VERSION,
            "query_lexicon": {"status": "skipped"},
            "embedding": {"status": "skipped"},
            "bge": {"status": "skipped"},
            "context": {"status": "skipped"},
            "convmemory": {"status": "skipped"},
            "warnings": [],
        }
    branches, lexicon_state = _query_variants(query)
    if lexicon_state.get("warning"):
        warnings.append(_warning("query_lexicon_unavailable", "术语扩展暂不可用，已保留原问题检索。"))
    embedding_rows, embedding_state, embedding_warnings = _eg2_candidates(
        query,
        filters or {},
        access_statuses,
        index_uid=str(getattr(settings, "STL_DEEP_RETRIEVAL_INDEX_UID", "")),
        embedding_artifact=str(getattr(settings, "STL_DEEP_RETRIEVAL_EMBEDDING_ARTIFACT", "")),
        dimensions=int(getattr(settings, "STL_DEEP_RETRIEVAL_EMBEDDING_DIMENSIONS", 768)),
    )
    warnings.extend(embedding_warnings)
    if is_current and not is_current():
        return {"rows": [], "status": "canceled", "pipeline_version": PIPELINE_VERSION, "warnings": warnings}
    retrieval_branches: list[tuple[list[dict], float]] = [(rows, 1.0)]
    if embedding_rows:
        retrieval_branches.append((embedding_rows, 1.0))
    # QueryLexicon branches are bounded and only supplement the existing pool.
    # Their source identity is validated below before any row is persisted.
    if (
        bool(getattr(settings, "STL_DEEP_RETRIEVAL_QUERY_EXPANSION_ENABLED", True))
        and branches
        and len(branches) > 1
    ):
        from catalog.services.discovery_projection import discovery_candidates

        for branch in branches[1:MAX_QUERY_VARIANTS]:
            branch_query = str(branch.get("query") or "").strip()
            if not branch_query:
                continue
            try:
                branch_result = discovery_candidates(
                    branch_query,
                    "passages",
                    filters or {},
                    access_statuses,
                    limit=MAX_DEEP_CANDIDATES,
                )
                branch_rows = validate_discovery_results(
                    "passages",
                    [*(branch_result.get("sparse") or []), *(branch_result.get("dense") or [])],
                    access_statuses,
                )
                if branch_rows:
                    retrieval_branches.append((branch_rows, 0.35))
            except Exception as exc:
                logger.warning("Deep QueryLexicon branch unavailable: %s", type(exc).__name__)
    rows = _rrf(retrieval_branches)[:MAX_DEEP_CANDIDATES]
    if is_current and not is_current():
        return {"rows": [], "status": "canceled", "pipeline_version": PIPELINE_VERSION, "warnings": warnings}
    rows, bge_state, bge_warnings = _bge_rerank(query, rows)
    warnings.extend(bge_warnings)
    rows, context_state, context_warnings = _attach_adjacent_context(rows, access_statuses)
    warnings.extend(context_warnings)
    rows, conv_state, conv_warnings = _convmemory_organize(query, rows)
    warnings.extend(conv_warnings)
    annotations = {
        _identity(row): {
            key: row[key]
            for key in ("deep_rank", "deep_score", "deep_context")
            if key in row
        }
        for row in rows
    }
    rows = validate_discovery_results("passages", rows, access_statuses)
    for row in rows:
        row.update(annotations.get(_identity(row), {}))
    for rank, row in enumerate(rows[:MAX_DEEP_CANDIDATES], 1):
        row.setdefault("deep_rank", rank)
    states = [lexicon_state, embedding_state, bge_state, context_state, conv_state]
    status = "completed" if all(item.get("status") in {"completed", "disabled", "skipped"} for item in states) else "degraded"
    return {
        "rows": rows[:MAX_DEEP_CANDIDATES],
        "status": status,
        "pipeline_version": PIPELINE_VERSION,
        "query_lexicon": lexicon_state,
        "embedding": embedding_state,
        "bge": bge_state,
        "context": context_state,
        "convmemory": conv_state,
        "warnings": warnings[:20],
    }

