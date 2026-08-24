from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


class UnifiedRetrievalError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RetrievalProfile:
    """Bounded execution settings for one consumer of shared retrieval.

    Profiles select existing Semantic Search V2 behavior.  They do not own an
    index, permission policy, query lexicon, embedder, or reranker.
    """

    key: str
    semantic_profile: str
    strategy: str
    default_limit: int
    max_limit: int
    default_max_per_work: int
    max_per_work: int
    search_version: str = "v2"
    rerank_top_k_override: int | None = None


@dataclass(frozen=True, slots=True)
class UnifiedRetrievalRequest:
    query: str
    profile: str
    filters: Mapping[str, Any] = field(default_factory=dict)
    limit: int | None = None
    max_per_work: int | None = None
    sort: str = "relevance"
    debug: bool = False

