from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateScore:
    identity_score: float
    context_score: float
    field_fit_score: float
    source_quality: float
    evidence_strength: float

    @property
    def total(self) -> float:
        return round(
            self.identity_score * 0.30
            + self.context_score * 0.20
            + self.field_fit_score * 0.20
            + self.source_quality * 0.15
            + self.evidence_strength * 0.15,
            4,
        )

    def payload(self) -> dict[str, float]:
        return {**asdict(self), "total": self.total}


SOURCE_QUALITY = {
    "local": 1.0,
    "library": 1.0,
    "query_lexicon": 0.92,
    "wikidata": 0.90,
    "viaf": 0.95,
    "loc": 0.95,
    "openalex": 0.88,
    "structured": 0.90,
    "pdf": 0.82,
    "academic": 0.82,
    "syllabus": 0.76,
    "general_web": 0.35,
    "unresolved": 0.10,
}


def score_candidate(candidate: dict[str, Any], *, query: str, expected_entity_types: tuple[str, ...]) -> CandidateScore:
    label = str(candidate.get("label") or candidate.get("name") or "").strip()
    folded_query = str(query or "").strip().casefold()
    folded_label = label.casefold()
    exact = bool(folded_query and folded_query == folded_label)
    contains = bool(folded_query and (folded_query in folded_label or folded_label in folded_query))
    entity_type = str(candidate.get("entity_type") or "")
    source = str(candidate.get("provider") or candidate.get("source_key") or candidate.get("source") or "").casefold()
    reasons = list(candidate.get("match_reasons") or candidate.get("reasons") or [])
    conflicts = list(candidate.get("conflicts") or [])
    evidence = list(candidate.get("evidence") or candidate.get("evidence_records") or [])
    identity = 1.0 if exact else 0.82 if contains else float(candidate.get("confidence") or 0.55)
    context = min(1.0, 0.45 + 0.10 * len(reasons) - 0.15 * len(conflicts))
    field_fit = 1.0 if not expected_entity_types or entity_type in expected_entity_types else 0.0
    source_quality = next((value for key, value in SOURCE_QUALITY.items() if key in source), 0.5)
    evidence_strength = min(1.0, 0.25 + 0.20 * len(evidence)) if evidence else (0.55 if source_quality >= 0.88 else 0.2)
    return CandidateScore(
        identity_score=max(0.0, min(identity, 1.0)),
        context_score=max(0.0, min(context, 1.0)),
        field_fit_score=field_fit,
        source_quality=source_quality,
        evidence_strength=evidence_strength,
    )
