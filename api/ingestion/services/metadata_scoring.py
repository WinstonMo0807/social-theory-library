from __future__ import annotations

from dataclasses import dataclass
import json
import re
import unicodedata


AI_SOURCE_RE = re.compile(r"(?:^|[_-])(ai|llm|ollama|vllm|openai)(?:$|[_-])", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CandidateScore:
    score: float
    factors: dict


def normalized_candidate_value(value) -> str:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    text = unicodedata.normalize("NFKC", text).casefold().strip()
    return "".join(character for character in text if character.isalnum())


def _source_reliability(source: str) -> float:
    value = source.casefold()
    if AI_SOURCE_RE.search(value):
        return 0.45
    if value in {"manual_review", "manual", "human_review"}:
        return 1.0
    if value.startswith("crossref"):
        return 0.96
    if value in {"openlibrary", "openlibrary_search"}:
        return 0.9
    if value.startswith("google_books"):
        return 0.88
    if value in {"grobid", "pdf_copyright_page", "pdf_title_page"}:
        return 0.9
    if value == "pdf_metadata":
        return 0.72
    if value in {"first_pages", "ocr", "filename", "ai_metadata_candidate"}:
        return 0.66
    return 0.6


def calibrate_candidate(candidate, candidates: list) -> CandidateScore:
    same_field = [row for row in candidates if row.field_name == candidate.field_name]
    value_key = normalized_candidate_value(candidate.value)
    agreeing_sources = {
        row.source
        for row in same_field
        if normalized_candidate_value(row.value) == value_key
    }
    distinct_values = {
        normalized_candidate_value(row.value)
        for row in same_field
        if normalized_candidate_value(row.value)
    }
    source_reliability = _source_reliability(candidate.source)
    declared_confidence = max(0.0, min(float(candidate.confidence), 1.0))
    declared_component = 0.5 if AI_SOURCE_RE.search(candidate.source) else declared_confidence
    exact_identifier = bool(
        candidate.field_name in {"doi", "isbn"}
        and (
            "exact" in str(candidate.evidence.get("match_type", "")).casefold()
            or candidate.source in {"crossref", "openlibrary"}
        )
    )
    evidence_present = bool(
        candidate.evidence.get("page")
        or candidate.evidence.get("page_range")
        or candidate.evidence.get("record_url")
        or candidate.evidence.get("doi")
        or candidate.evidence.get("isbn")
        or candidate.evidence.get("source_record_id")
    )
    agreement = min(max(len(agreeing_sources) - 1, 0), 3) / 3
    conflict_count = max(len(distinct_values) - 1, 0)
    conflict_penalty = min(conflict_count * 0.025, 0.1)
    score = (
        declared_component * 0.55
        + source_reliability * 0.27
        + agreement * 0.1
        + (0.08 if evidence_present else 0)
        + (0.08 if exact_identifier else 0)
        - conflict_penalty
    )
    score = round(max(0.0, min(score, 0.99)), 4)
    return CandidateScore(
        score=score,
        factors={
            "declared_confidence": declared_confidence,
            "declared_confidence_used": not bool(AI_SOURCE_RE.search(candidate.source)),
            "source_reliability": source_reliability,
            "independent_sources": len(agreeing_sources),
            "exact_identifier": exact_identifier,
            "evidence_present": evidence_present,
            "conflicting_values": conflict_count,
            "conflict_penalty": round(conflict_penalty, 4),
            "calibration_version": "metadata-candidate-v1",
        },
    )


def ranked_candidates(candidates: list) -> list[tuple[object, CandidateScore]]:
    ranked = [(candidate, calibrate_candidate(candidate, candidates)) for candidate in candidates]
    return sorted(
        ranked,
        key=lambda row: (row[1].score, row[0].source, normalized_candidate_value(row[0].value)),
        reverse=True,
    )
