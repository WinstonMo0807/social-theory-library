from __future__ import annotations

import pytest
from django.test import override_settings

from catalog.services.claims.stance import ClaimStance, classify_stance
from catalog.services.retrieval import (
    RETRIEVAL_PROFILES,
    UnifiedRetrievalPipeline,
    UnifiedRetrievalRequest,
)
from common.ai_runtime import (
    AICapability,
    CAPABILITY_POLICIES,
    LEGACY_REQUIRED_CAPABILITIES,
    _environment_profiles,
    validate_profile_document,
)


def test_ai_runtime_registers_v3_capabilities_as_disabled_defaults():
    with override_settings(
        AI_PROVIDER="openai_compatible",
        AI_CLASSIFIER_MODEL="reasoning-model",
        AI_LIBRARY_MODEL="library-model",
    ):
        document = _environment_profiles()

    assert set(document["active"]) == set(AICapability.VALUES)
    rows = {row["capability"]: row for row in document["profiles"]}
    assert rows[AICapability.CLAIM_EXTRACTION]["enabled"] is False
    assert rows[AICapability.CLAIM_EXTRACTION]["model"] == "reasoning-model"
    assert rows[AICapability.CLAIM_STANCE]["answer_behavior"] == "evidence_bound_classification"
    assert rows[AICapability.READING_PATH_GENERATION]["answer_behavior"] == "candidate_only"


def test_legacy_ai_runtime_document_gains_only_disabled_v3_profiles():
    environment = _environment_profiles()
    legacy = {
        "active": {
            capability: environment["active"][capability]
            for capability in LEGACY_REQUIRED_CAPABILITIES
        },
        "profiles": [
            row
            for row in environment["profiles"]
            if row["capability"] in LEGACY_REQUIRED_CAPABILITIES
        ],
    }

    validated = validate_profile_document(legacy)

    rows = {row["capability"]: row for row in validated["profiles"]}
    assert set(validated["active"]) == set(AICapability.VALUES)
    assert rows[AICapability.CLAIM_EXTRACTION]["provider"] == "none"
    assert rows[AICapability.CLAIM_EXTRACTION]["enabled"] is False
    assert rows[AICapability.RERANK]["answer_behavior"] == CAPABILITY_POLICIES[
        AICapability.RERANK
    ].default_answer_behavior


def test_unified_retrieval_profiles_cover_all_consumers():
    assert set(RETRIEVAL_PROFILES) == {
        "public_fulltext",
        "viewpoint",
        "research_evidence",
        "entity_discovery",
        "curation",
        "reader_qa",
    }


def test_unified_retrieval_forwards_visibility_and_returns_v2_response_unchanged():
    calls = []
    expected = {"search_version": "v2", "engine": "v2_hybrid", "results": []}

    def fake_search(query, **kwargs):
        calls.append((query, kwargs))
        return expected

    filters = {
        "work_ids": ("work-1",),
        "_allowed_access_statuses": ("public", "authenticated"),
    }
    response = UnifiedRetrievalPipeline(fake_search).retrieve(
        UnifiedRetrievalRequest(
            query="X 导致 Y",
            profile="viewpoint",
            filters=filters,
            limit=500,
            max_per_work=500,
            debug=True,
        )
    )

    assert response is expected
    assert calls[0][0] == "X 导致 Y"
    assert calls[0][1]["filters"] == {
        "work_ids": ["work-1"],
        "_allowed_access_statuses": ["public", "authenticated"],
    }
    assert calls[0][1]["search_version"] == "v2"
    assert calls[0][1]["search_profile"] == "precision"
    assert calls[0][1]["strategy"] == "hybrid_rerank"
    assert calls[0][1]["limit"] == RETRIEVAL_PROFILES["viewpoint"].max_limit
    assert calls[0][1]["max_per_work"] == RETRIEVAL_PROFILES["viewpoint"].max_per_work
    assert calls[0][1]["debug"] is True


@pytest.mark.parametrize(
    ("query", "candidate", "expected"),
    [
        ("贫困导致犯罪", "贫困导致犯罪", ClaimStance.DIRECT),
        ("贫困导致犯罪", "贫困不导致犯罪", ClaimStance.OPPOSE),
        ("贫困导致犯罪", "新证据支持贫困导致犯罪", ClaimStance.SUPPORT),
        ("贫困导致犯罪", "贫困可能导致犯罪，但仅在失业率高时如此", ClaimStance.QUALIFY),
        ("贫困导致犯罪", "新的田野证据进一步拓展了这一命题", ClaimStance.EXTEND),
        ("贫困导致犯罪", "问题不是贫困，而是制度排斥", ClaimStance.REFRAME),
    ],
)
def test_stance_rules_do_not_use_similarity_as_polarity(query, candidate, expected):
    result = classify_stance(query, candidate)

    assert result.stance == expected
    assert result.deterministic is True


def test_structured_claim_polarity_overrides_high_text_similarity():
    query = {
        "proposition": "X 导致 Y",
        "subject": "X",
        "predicate": "导致",
        "object": "Y",
        "polarity": "positive",
    }
    candidate = {
        "proposition": "X 导致 Y",
        "subject": "X",
        "predicate": "导致",
        "object": "Y",
        "polarity": "negative",
    }

    result = classify_stance(query, candidate)

    assert result.stance == ClaimStance.OPPOSE
    assert result.confidence == 0.99
    assert "opposite_explicit_polarity" in result.reasons


def test_criticized_attribution_is_reported_as_critique():
    result = classify_stance(
        "X 导致 Y",
        {
            "proposition": "X 导致 Y",
            "attribution": "criticized_claim",
            "claim_type": "criticism",
        },
    )

    assert result.stance == ClaimStance.CRITIQUE
