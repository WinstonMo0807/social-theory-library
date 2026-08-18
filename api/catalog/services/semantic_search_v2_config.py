from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from django.conf import settings

from catalog.services.passage_language import language_detector_config


SEARCH_IMPLEMENTATION_VERSION = "semantic-search-v2-query-lexicon-v2"
BASELINE_PARAMETER_SET_ID = "baseline_v2a"

# These defaults are intentionally conservative. Task 2B may tune them with an
# adjudicated library benchmark, but Task 2A keeps every source and request
# count bounded independently of environment configuration.
MAX_MATCHED_ENTITIES = 4
MAX_TERMS_PER_ENTITY = 4
MAX_EXPANSION_BRANCHES = 4  # Includes the mandatory original-query branch.
MAX_EXPANSION_CHARACTERS = 600
MAX_RECOGNITION_SPANS = 512
MAX_BRANCH_HITS_PER_CANDIDATE = 2

BRANCH_WEIGHTS = {
    "original": 1.0,
    "canonical_equivalent": 0.52,
    "verified_translation": 0.48,
    "verified_alias": 0.34,
    "historical": 0.20,
    "legacy_search_variant": 0.10,
    "generated_search_variant": 0.06,
    "explicit_rewrite": 0.44,
    "intent_rewrite": 0.24,
}

TRUST_MULTIPLIERS = {
    "original": 1.0,
    "deterministic": 0.75,
    "authoritative": 1.0,
    "verified": 0.92,
    "unverified": 0.48,
    "legacy": 0.30,
    "generated": 0.18,
}

# A standalone occurrence of these terms does not contain enough context to
# select a social-science entity. The original query still runs normally and
# the resolver reports the possible entity matches.
AMBIGUOUS_STANDALONE_TERMS = frozenset(
    {
        "capital",
        "field",
        "practice",
        "recognition",
        "structure",
        "资本",
        "场域",
        "实践",
        "承认",
        "结构",
    }
)

QUERY_PROFILE_RULES = {
    "exact_entity": {
        "semantic_ratio_cap": 0.48,
        "literal_coverage_weight": 0.16,
        "entity_coverage_weight": 0.10,
        "cross_language_coverage_weight": 0.08,
    },
    "lexical_phrase": {
        "semantic_ratio_cap": 0.58,
        "literal_coverage_weight": 0.15,
        "entity_coverage_weight": 0.08,
        "cross_language_coverage_weight": 0.06,
    },
    "conceptual": {
        "literal_coverage_weight": 0.10,
        "entity_coverage_weight": 0.10,
        "cross_language_coverage_weight": 0.09,
    },
    "cross_language": {
        "semantic_ratio_floor": 0.68,
        "literal_coverage_weight": 0.08,
        "entity_coverage_weight": 0.12,
        "cross_language_coverage_weight": 0.12,
    },
    "mixed_language": {
        "semantic_ratio_floor": 0.62,
        "literal_coverage_weight": 0.10,
        "entity_coverage_weight": 0.11,
        "cross_language_coverage_weight": 0.10,
    },
}


@dataclass(frozen=True, slots=True)
class SearchV2Limits:
    max_matched_entities: int
    max_terms_per_entity: int
    max_expansion_branches: int
    max_expansion_characters: int
    max_recognition_spans: int

    def as_dict(self) -> dict[str, int]:
        return {
            "max_matched_entities": self.max_matched_entities,
            "max_terms_per_entity": self.max_terms_per_entity,
            "max_expansion_branches": self.max_expansion_branches,
            "max_expansion_characters": self.max_expansion_characters,
            "max_recognition_spans": self.max_recognition_spans,
        }


def current_search_v2_limits(*, expansion_limit: int | None = None) -> SearchV2Limits:
    matched = max(
        1,
        min(
            int(
                getattr(
                    settings,
                    "SEMANTIC_SEARCH_V2_MAX_MATCHED_ENTITIES",
                    MAX_MATCHED_ENTITIES,
                )
            ),
            8,
        ),
    )
    terms = max(
        1,
        min(
            int(
                getattr(
                    settings,
                    "SEMANTIC_SEARCH_V2_MAX_TERMS_PER_ENTITY",
                    MAX_TERMS_PER_ENTITY,
                )
            ),
            8,
        ),
    )
    configured_supplemental = max(
        0,
        min(
            int(getattr(settings, "SEMANTIC_SEARCH_QUERY_EXPANSION_MAX", 3)),
            MAX_EXPANSION_BRANCHES - 1,
        ),
    )
    if expansion_limit is not None:
        configured_supplemental = min(
            configured_supplemental,
            max(0, int(expansion_limit)),
        )
    characters = max(
        80,
        min(
            int(
                getattr(
                    settings,
                    "SEMANTIC_SEARCH_V2_MAX_EXPANSION_CHARACTERS",
                    MAX_EXPANSION_CHARACTERS,
                )
            ),
            1200,
        ),
    )
    spans = max(
        64,
        min(
            int(
                getattr(
                    settings,
                    "SEMANTIC_SEARCH_V2_MAX_RECOGNITION_SPANS",
                    MAX_RECOGNITION_SPANS,
                )
            ),
            1024,
        ),
    )
    return SearchV2Limits(
        max_matched_entities=matched,
        max_terms_per_entity=terms,
        max_expansion_branches=1 + configured_supplemental,
        max_expansion_characters=characters,
        max_recognition_spans=spans,
    )


def branch_weight(branch: dict) -> float:
    base = BRANCH_WEIGHTS.get(str(branch.get("branch_type") or ""), 0.0)
    trust = str(branch.get("effective_trust_level") or branch.get("trust_level") or "")
    multiplier = TRUST_MULTIPLIERS.get(trust, 0.25)
    if branch.get("ambiguous"):
        multiplier *= 0.45
    return round(base * multiplier, 6)


def effective_semantic_ratio(base_ratio: float, query_profile: str) -> float:
    value = min(1.0, max(0.0, float(base_ratio)))
    rules = QUERY_PROFILE_RULES.get(query_profile, QUERY_PROFILE_RULES["conceptual"])
    if "semantic_ratio_cap" in rules:
        value = min(value, float(rules["semantic_ratio_cap"]))
    if "semantic_ratio_floor" in rules:
        value = max(value, float(rules["semantic_ratio_floor"]))
    return round(value, 6)


def search_v2_config_snapshot(*, expansion_limit: int | None = None) -> dict:
    limits = current_search_v2_limits(expansion_limit=expansion_limit)
    snapshot = {
        "parameter_set_id": BASELINE_PARAMETER_SET_ID,
        "parameter_status": "frozen_baseline",
        "search_implementation_version": SEARCH_IMPLEMENTATION_VERSION,
        "expansion_limits": limits.as_dict(),
        "branch_weights": dict(BRANCH_WEIGHTS),
        "trust_multipliers": dict(TRUST_MULTIPLIERS),
        "query_profile_rules": {
            key: dict(value) for key, value in QUERY_PROFILE_RULES.items()
        },
        "ambiguous_standalone_terms": sorted(AMBIGUOUS_STANDALONE_TERMS),
        "max_branch_hits_per_candidate": MAX_BRANCH_HITS_PER_CANDIDATE,
        "retrieval_limits": {
            "dense_top_k": int(
                getattr(settings, "SEMANTIC_SEARCH_DENSE_TOP_K", 50)
            ),
            "sparse_top_k": int(
                getattr(settings, "SEMANTIC_SEARCH_SPARSE_TOP_K", 50)
            ),
            "fusion_top_k": int(
                getattr(settings, "SEMANTIC_SEARCH_FUSION_TOP_K", 24)
            ),
            "rerank_top_k": int(
                getattr(settings, "SEMANTIC_SEARCH_RERANK_TOP_K", 24)
            ),
            "final_top_k": int(
                getattr(settings, "SEMANTIC_SEARCH_FINAL_TOP_K", 10)
            ),
        },
        "branch_controls": {
            "query_lexicon_branches": True,
            "explicit_rewrite_when_supplied": True,
            "deterministic_intent_rewrite": True,
            "uses_llm_rewrite": False,
        },
        "language_detector": language_detector_config(),
    }
    canonical = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    snapshot["config_hash"] = sha256(canonical.encode("utf-8")).hexdigest()
    return snapshot
