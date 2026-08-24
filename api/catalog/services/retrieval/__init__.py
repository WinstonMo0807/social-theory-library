"""Profile-driven adapters over the existing Semantic Search V2 pipeline."""

from .pipeline import UnifiedRetrievalPipeline, unified_retrieve
from .profiles import RETRIEVAL_PROFILES, get_retrieval_profile
from .types import RetrievalProfile, UnifiedRetrievalRequest

__all__ = [
    "RETRIEVAL_PROFILES",
    "RetrievalProfile",
    "UnifiedRetrievalPipeline",
    "UnifiedRetrievalRequest",
    "get_retrieval_profile",
    "unified_retrieve",
]
