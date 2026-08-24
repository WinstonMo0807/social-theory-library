from contextlib import nullcontext
from unittest.mock import patch
from uuid import uuid4

import pytest


def _search_payload():
    work_id = str(uuid4())
    row = {
        "id": f"semantic:{uuid4()}",
        "source_kind": "semantic_chunk",
        "claim_id": None,
        "proposition": "制度信任能够降低合作中的不确定性。",
        "stance": "support",
        "stance_label": "支持",
        "stance_confidence": 0.83,
        "stance_reasons": ["命题方向一致"],
        "score": 0.91,
        "authors": ["测试作者"],
        "work": {"id": work_id, "title": "制度与合作"},
        "page": 12,
        "printed_page_label": "8",
        "evidence": {
            "id": str(uuid4()),
            "kind": "collection_text",
            "source": {
                "work_id": work_id,
                "work_title": "制度与合作",
                "authors": ["测试作者"],
            },
            "text": "制度信任能够降低合作中的不确定性。",
            "locator": {"page": 12, "printed_page_label": "8"},
            "quality": {"score": 0.96, "stale": False},
            "provenance": {"parser": "pymupdf"},
            "reader_url": f"/reader/{uuid4()}?page=12",
            "pdf_url": f"/api/catalog/assets/{uuid4()}/manifest/",
        },
        "reader_url": f"/reader/{uuid4()}?page=12",
        "pdf_url": f"/api/catalog/assets/{uuid4()}/manifest/",
        "attribution": "author_claim",
        "claim_type": "assertion",
        "quality_score": 0.96,
        "ranking_source": "semantic_v2_baseline",
    }
    groups = {
        "direct": [],
        "support": [row],
        "oppose": [],
        "qualify": [],
        "critique": [],
        "extend": [],
        "reframe": [],
    }
    return {
        "query": "制度信任促进合作",
        "query_claim": {
            "proposition": "制度信任促进合作",
            "subject": "制度信任",
            "predicate": "促进",
            "object": "合作",
            "polarity": "positive",
            "qualifiers": [],
            "claim_type": "causal",
        },
        "default_mode": "baseline",
        "results": [row],
        "groups": groups,
        "baseline": {
            "results": [row],
            "groups": groups,
            "engine": "v2_hybrid",
            "search_version": "v2",
            "fallback_used": False,
            "fallback_reason": "",
        },
        "shadow": {"results": [], "groups": groups},
        "metadata": {
            "benchmark_gate_passed": False,
            "default_ranking": "semantic_v2_baseline",
            "claim_ranking_status": "shadow",
            "evidence_span_validation_required": True,
            "cosine_similarity_used_for_stance": False,
        },
    }


@pytest.mark.django_db
def test_public_viewpoint_api_reuses_visibility_throttle_and_hides_shadow(api_client):
    work_id = str(uuid4())
    payload = _search_payload()
    with (
        patch("catalog.viewpoint_views.capacity_slot", return_value=nullcontext(True)),
        patch("catalog.viewpoint_views.search_viewpoints_v3", return_value=payload) as search,
    ):
        response = api_client.get(
            "/api/catalog/viewpoint-search/",
            {
                "q": "制度信任促进合作",
                "document_type": ["book"],
                "language": ["zh-CN"],
                "work_id": [work_id, "not-a-uuid"],
                "limit": "16",
                "max_per_work": "2",
                "sort": "newest",
            },
        )

    assert response.status_code == 200
    assert response.data["default_mode"] == "baseline"
    assert response.data["metadata"]["default_ranking"] == "semantic_v2_baseline"
    assert "shadow" not in response.data
    assert "baseline" not in response.data
    assert response.data["stance_counts"]["support"] == 1
    assert response.data["results"][0]["evidence"]["text"].startswith("制度信任")
    assert response.data["results"][0]["reader_url"].endswith("?page=12")
    kwargs = search.call_args.kwargs
    assert kwargs["limit"] == 16
    assert kwargs["max_per_work"] == 2
    assert kwargs["sort"] == "newest"
    assert kwargs["filters"]["work_ids"] == [work_id]
    assert kwargs["filters"]["_allowed_access_statuses"] == ["inherit", "public"]


@pytest.mark.django_db
def test_staff_debug_can_inspect_claim_shadow_without_promoting_it(api_client, admin_user):
    admin_user.is_staff = True
    admin_user.save(update_fields=["is_staff"])
    api_client.force_authenticate(admin_user)
    payload = _search_payload()

    with (
        patch("catalog.viewpoint_views.capacity_slot", return_value=nullcontext(True)),
        patch("catalog.viewpoint_views.search_viewpoints_v3", return_value=payload) as search,
    ):
        response = api_client.get(
            "/api/catalog/viewpoint-search/",
            {"q": "制度信任促进合作", "debug": "1"},
        )

    assert response.status_code == 200
    assert "shadow" in response.data
    assert response.data["metadata"]["benchmark_gate_passed"] is False
    assert search.call_args.kwargs["debug"] is True
    assert search.call_args.kwargs["filters"]["_allowed_access_statuses"] == [
        "inherit",
        "public",
        "registered",
        "restricted",
        "private",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("query", ["", "单"])
def test_public_viewpoint_api_rejects_queries_shorter_than_a_proposition(api_client, query):
    response = api_client.get("/api/catalog/viewpoint-search/", {"q": query})

    assert response.status_code == 400
    assert response.data["q"] == ["观点检索至少需要两个字符。"]
