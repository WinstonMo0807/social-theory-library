from __future__ import annotations

from .types import RetrievalProfile, UnifiedRetrievalError


# These settings choose among already benchmarked V2 components.  They avoid
# declaring a new default ranking winner before the Claim benchmark gate.
RETRIEVAL_PROFILES = {
    "public_fulltext": RetrievalProfile(
        key="public_fulltext",
        semantic_profile="balanced",
        strategy="hybrid_rerank",
        default_limit=40,
        max_limit=100,
        default_max_per_work=3,
        max_per_work=20,
    ),
    "viewpoint": RetrievalProfile(
        key="viewpoint",
        semantic_profile="precision",
        strategy="hybrid_rerank",
        default_limit=40,
        max_limit=100,
        default_max_per_work=4,
        max_per_work=20,
    ),
    "research_evidence": RetrievalProfile(
        key="research_evidence",
        semantic_profile="precision",
        strategy="hybrid_rerank",
        default_limit=60,
        max_limit=100,
        default_max_per_work=6,
        max_per_work=20,
    ),
    "entity_discovery": RetrievalProfile(
        key="entity_discovery",
        semantic_profile="fast",
        strategy="hybrid_rerank",
        default_limit=30,
        max_limit=80,
        default_max_per_work=3,
        max_per_work=12,
    ),
    "curation": RetrievalProfile(
        key="curation",
        semantic_profile="precision",
        strategy="hybrid_rerank",
        default_limit=48,
        max_limit=100,
        default_max_per_work=5,
        max_per_work=20,
    ),
    "reader_qa": RetrievalProfile(
        key="reader_qa",
        semantic_profile="balanced",
        strategy="hybrid_rerank",
        default_limit=24,
        max_limit=60,
        default_max_per_work=3,
        max_per_work=12,
    ),
}


def get_retrieval_profile(key: str) -> RetrievalProfile:
    normalized = str(key or "").strip().casefold()
    try:
        return RETRIEVAL_PROFILES[normalized]
    except KeyError as exc:
        raise UnifiedRetrievalError("不支持的 retrieval profile。") from exc

