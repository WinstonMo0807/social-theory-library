from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .profiles import get_retrieval_profile
from .types import UnifiedRetrievalError, UnifiedRetrievalRequest


SearchBackend = Callable[..., dict[str, Any]]
ALLOWED_SORTS = frozenset({"relevance", "newest", "year"})


def _copied_filters(value) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        rows = dict(value)
    except (TypeError, ValueError) as exc:
        raise UnifiedRetrievalError("retrieval filters 必须是对象。") from exc
    output = {}
    for key, item in rows.items():
        normalized_key = str(key or "").strip()
        if not normalized_key:
            continue
        if isinstance(item, (list, tuple, set, frozenset)):
            output[normalized_key] = list(item)
        else:
            output[normalized_key] = item
    return output


class UnifiedRetrievalPipeline:
    """Compatibility response over the shared permission-scoped recall service."""

    def __init__(self, search_backend: SearchBackend | None = None):
        self.search_backend = search_backend or _shared_search

    def retrieve(self, request: UnifiedRetrievalRequest) -> dict[str, Any]:
        query = str(request.query or "").strip()
        if not query:
            raise UnifiedRetrievalError("检索命题不能为空。")
        if len(query) > 2000:
            raise UnifiedRetrievalError("检索命题不能超过 2000 个字符。")
        profile = get_retrieval_profile(request.profile)
        sort = str(request.sort or "relevance").strip().casefold()
        if sort not in ALLOWED_SORTS:
            raise UnifiedRetrievalError("不支持的 retrieval sort。")
        limit = (
            profile.default_limit
            if request.limit is None
            else max(1, min(int(request.limit), profile.max_limit))
        )
        max_per_work = (
            profile.default_max_per_work
            if request.max_per_work is None
            else max(0, min(int(request.max_per_work), profile.max_per_work))
        )
        response = self.search_backend(
            query,
            filters=_copied_filters(request.filters),
            limit=limit,
            max_per_work=max_per_work,
            debug=bool(request.debug),
            strategy=profile.strategy,
            sort=sort,
            search_version=profile.search_version,
            search_profile=profile.semantic_profile,
            rerank_top_k_override=profile.rerank_top_k_override,
        )
        if not isinstance(response, dict):
            raise UnifiedRetrievalError("统一检索返回了无效结果。")
        return response


def _shared_search(query, *, filters, limit, max_per_work, sort="relevance", **options):
    from .search import retrieve_channel
    from catalog.services.semantic_search import viewer_access_statuses
    scope = dict(filters)
    allowed = scope.pop("_allowed_access_statuses", viewer_access_statuses())
    result = retrieve_channel(query, "passages", scope, allowed, limit=min(300, max(100, limit * 4)))
    rows, counts = [], {}
    for row in result["rows"]:
        work = str(row.get("work_id") or row.get("work", {}).get("id", ""))
        if max_per_work and counts.get(work, 0) >= max_per_work:
            continue
        counts[work] = counts.get(work, 0) + 1
        rows.append({**row, "snippet": row.get("text") or row.get("excerpt", ""),
                     "page_index": row.get("pdf_page"), "printed_label": row.get("printed_page", ""),
                     "_discovery_identity": True})
        if len(rows) >= limit:
            break
    if sort in {"newest", "year"}:
        rows.sort(key=lambda row: str(row.get("work", {}).get("year") or ""), reverse=True)
    return {"results": rows, "engine": "discovery", "search_version": "unified-source-v1",
        "retrieval": result.get("retrieval", {}),
        "index_uid": result.get("index_uid", ""), "warnings": result["warnings"],
        "fallback_used": bool(result["warnings"]), "fallback_reason": ",".join(w.get("code", "") for w in result["warnings"])}


def unified_retrieve(
    query: str,
    *,
    profile: str,
    filters=None,
    limit: int | None = None,
    max_per_work: int | None = None,
    sort: str = "relevance",
    debug: bool = False,
    search_backend: SearchBackend | None = None,
) -> dict[str, Any]:
    return UnifiedRetrievalPipeline(search_backend).retrieve(
        UnifiedRetrievalRequest(
            query=query,
            profile=profile,
            filters=filters or {},
            limit=limit,
            max_per_work=max_per_work,
            sort=sort,
            debug=debug,
        )
    )
