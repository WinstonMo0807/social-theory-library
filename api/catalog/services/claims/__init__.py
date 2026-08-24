"""Claim analysis helpers that do not mutate canonical knowledge."""

from .attribution import AttributionDecision, infer_attribution, normalize_attribution
from .curation import (
    decide_claim_curation_candidate,
    high_value_claim_candidates,
    publish_work_curated_claims,
)
from .pipeline import (
    extract_claims_shadow,
    persist_claim_candidates,
    schedule_document_claim_extraction,
)
from .stance import ClaimStatement, ClaimStance, StanceResult, classify_stance

__all__ = [
    "AttributionDecision",
    "ClaimStatement",
    "ClaimStance",
    "StanceResult",
    "classify_stance",
    "decide_claim_curation_candidate",
    "extract_claims_shadow",
    "high_value_claim_candidates",
    "infer_attribution",
    "normalize_attribution",
    "persist_claim_candidates",
    "publish_work_curated_claims",
    "schedule_document_claim_extraction",
]
