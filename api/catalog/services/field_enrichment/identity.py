from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db.models import Q

from catalog.models import EnrichmentCandidate, KnowledgeNode
from catalog.services.query_lexicon.normalization import normalize_term

from .targets import canonical_terms
from .types import FieldObservation


@dataclass(frozen=True)
class IdentityAssessment:
    status: str
    evidence: dict[str, Any]


def _normalized_set(values) -> set[str]:
    output = set()
    for value in values or []:
        if isinstance(value, dict):
            value = value.get("name") or value.get("label") or value.get("value")
        normalized = normalize_term(value)
        if normalized:
            output.add(normalized)
    return output


def _external_ids(value) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key).casefold(): str(item).strip()
        for key, item in value.items()
        if str(item).strip()
    }


def _affiliation_names(values) -> set[str]:
    return _normalized_set(
        [
            value.get("name") if isinstance(value, dict) else value
            for value in (values or [])
        ]
    )


def _person_identity(target, observation: FieldObservation, context: dict) -> IdentityAssessment:
    claims = observation.identity_claims or {}
    known_names = _normalized_set(canonical_terms("person", target))
    candidate_names = _normalized_set(
        [
            claims.get("name"),
            claims.get("original_name"),
            *(claims.get("names") or []),
            *(claims.get("aliases") or []),
        ]
    )
    name_matches = sorted(known_names & candidate_names)
    known_ids = _external_ids(target.external_ids)
    claimed_ids = _external_ids(claims.get("external_ids"))
    identifier_matches = sorted(
        key
        for key in set(known_ids) & set(claimed_ids)
        if known_ids[key].casefold() == claimed_ids[key].casefold()
    )
    identifier_conflicts = sorted(
        key
        for key in set(known_ids) & set(claimed_ids)
        if known_ids[key].casefold() != claimed_ids[key].casefold()
    )
    date_matches = []
    date_conflicts = []
    for field_name in ("birth_year", "death_year"):
        known = getattr(target, field_name, None)
        claimed = claims.get(field_name)
        if known is None or claimed in (None, ""):
            continue
        try:
            claimed = int(claimed)
        except (TypeError, ValueError):
            continue
        if known == claimed:
            date_matches.append(field_name)
        else:
            date_conflicts.append(field_name)
    known_affiliations = _affiliation_names(context.get("affiliations"))
    claimed_affiliations = _affiliation_names(claims.get("affiliations"))
    affiliation_matches = sorted(known_affiliations & claimed_affiliations)
    known_works = _normalized_set(context.get("works"))
    claimed_works = _normalized_set(claims.get("works"))
    work_matches = sorted(known_works & claimed_works)
    evidence = {
        "name_matches": name_matches,
        "identifier_matches": identifier_matches,
        "identifier_conflicts": identifier_conflicts,
        "date_matches": date_matches,
        "date_conflicts": date_conflicts,
        "affiliation_matches": affiliation_matches,
        "work_matches": work_matches,
    }
    if identifier_conflicts or date_conflicts:
        return IdentityAssessment(EnrichmentCandidate.IdentityStatus.CONFLICT, evidence)
    confirmed = bool(identifier_matches) or bool(
        name_matches and (date_matches or affiliation_matches or work_matches)
    )
    return IdentityAssessment(
        EnrichmentCandidate.IdentityStatus.CONFIRMED
        if confirmed
        else EnrichmentCandidate.IdentityStatus.AMBIGUOUS,
        evidence,
    )


def _edition_identity(target, observation: FieldObservation, context: dict) -> IdentityAssessment:
    claims = observation.identity_claims or {}
    known_ids = {
        "doi": str(target.doi or "").strip().casefold(),
        "isbn": str(target.isbn or "").replace("-", "").strip().casefold(),
    }
    claimed_ids = _external_ids(claims.get("external_ids"))
    identifier_matches = [
        key
        for key, value in known_ids.items()
        if value and claimed_ids.get(key, "").replace("-", "").casefold() == value
    ]
    identifier_conflicts = [
        key
        for key, value in known_ids.items()
        if value and claimed_ids.get(key) and claimed_ids[key].replace("-", "").casefold() != value
    ]
    title_matches = bool(
        _normalized_set(canonical_terms("edition", target))
        & _normalized_set([claims.get("title"), claims.get("original_title")])
    )
    corroborators = []
    if target.publication_year and claims.get("publication_year"):
        if int(claims["publication_year"]) == target.publication_year:
            corroborators.append("publication_year")
    if target.publisher and normalize_term(target.publisher) == normalize_term(claims.get("publisher")):
        corroborators.append("publisher")
    if _normalized_set(context.get("authors")) & _normalized_set(claims.get("authors")):
        corroborators.append("author")
    evidence = {
        "identifier_matches": identifier_matches,
        "identifier_conflicts": identifier_conflicts,
        "title_match": title_matches,
        "corroborators": corroborators,
    }
    if identifier_conflicts:
        return IdentityAssessment(EnrichmentCandidate.IdentityStatus.CONFLICT, evidence)
    return IdentityAssessment(
        EnrichmentCandidate.IdentityStatus.CONFIRMED
        if identifier_matches or (title_matches and corroborators)
        else EnrichmentCandidate.IdentityStatus.AMBIGUOUS,
        evidence,
    )


def _work_identity(target_type: str, target, observation: FieldObservation) -> IdentityAssessment:
    claims = observation.identity_claims or {}
    matches = sorted(
        _normalized_set(canonical_terms(target_type, target))
        & _normalized_set(
            [
                claims.get("name"),
                claims.get("title"),
                claims.get("original_name"),
                *(claims.get("names") or []),
                *(claims.get("matched_target_terms") or []),
            ]
        )
    )
    evidence = {"canonical_matches": matches}
    if not matches:
        return IdentityAssessment(EnrichmentCandidate.IdentityStatus.AMBIGUOUS, evidence)
    if target_type == "knowledge_node":
        ambiguous = KnowledgeNode.objects.filter(
            Q(canonical_name_zh__iexact=matches[0])
            | Q(canonical_name_en__iexact=matches[0])
            | Q(aliases__normalized_alias=matches[0])
        ).distinct().exclude(pk=target.pk).exists()
        evidence["same_term_other_target"] = ambiguous
        if ambiguous:
            return IdentityAssessment(EnrichmentCandidate.IdentityStatus.AMBIGUOUS, evidence)
    return IdentityAssessment(EnrichmentCandidate.IdentityStatus.CONFIRMED, evidence)


def assess_identity(
    *,
    target_type: str,
    target,
    observation: FieldObservation,
    context: dict,
    required: bool,
) -> IdentityAssessment:
    if not required:
        return IdentityAssessment(
            EnrichmentCandidate.IdentityStatus.NOT_REQUIRED,
            {"reason": "field_policy_does_not_require_identity"},
        )
    if target_type == "person":
        return _person_identity(target, observation, context)
    if target_type == "edition":
        return _edition_identity(target, observation, context)
    return _work_identity(target_type, target, observation)
