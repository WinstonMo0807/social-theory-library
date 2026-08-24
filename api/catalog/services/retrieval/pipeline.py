from __future__ import annotations

from collections.abc import Callable
from typing import Any

from catalog.services.semantic_search import semantic_search

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
    """Thin, permission-neutral adapter over Semantic Search V2.

    Callers remain responsible for deriving visibility filters from the
    authenticated request.  This adapter forwards those filters unchanged and
    never retries with a wider scope.  The returned mapping is the original V2
    response so existing clients keep their current contract.
    """

    def __init__(self, search_backend: SearchBackend | None = None):
        self.search_backend = search_backend or semantic_search

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
            raise UnifiedRetrievalError("Semantic Search V2 返回了无效结果。")
        return response


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
