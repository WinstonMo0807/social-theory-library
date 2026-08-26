from contextlib import nullcontext
from unittest.mock import patch
from uuid import uuid4

import pytest

from catalog.models import (
    Contribution,
    Edition,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Person,
    PublicationState,
    RelationReviewStatus,
    ScholarProfile,
    Topic,
    Work,
    WorkNodeRelation,
    WorkTopicRelation,
)
from catalog.services.viewpoint_search import _viewpoint_facets
from catalog.services.claims.indexing import _search_filters as claim_index_filters
from catalog.services.semantic_search import _meili_filters as semantic_index_filters


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
        "source_type": "book",
        "language": "zh-CN",
        "publication_year": 2024,
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
        "facets": {
            "relations": [{"id": "support", "slug": "support", "label": "支持", "count": 1}],
            "source_types": [{"id": "book", "slug": "book", "label": "图书", "count": 1}],
            "languages": [{"id": "zh-CN", "slug": "zh-CN", "label": "zh-CN", "count": 1}],
            "scholars": [],
            "theories": [],
            "topics": [],
            "works": [],
            "publication_year": {"min": 2024, "max": 2024},
        },
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


@pytest.mark.django_db
def test_public_viewpoint_filters_resolve_canonical_ids_and_real_ranges(api_client):
    work = Work.objects.create(document_type="book", title="规范化关系作品")
    theory = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="制度理论",
        slug="institutional-theory-filter",
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    topic = Topic.objects.create(
        name="合作研究",
        slug="cooperation-topic-filter",
        editorial_status="published",
    )
    WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    WorkTopicRelation.objects.create(
        work=work,
        topic=topic,
        review_status=RelationReviewStatus.APPROVED,
    )
    scholar_id = str(uuid4())
    payload = _search_payload()

    with (
        patch("catalog.viewpoint_views.capacity_slot", return_value=nullcontext(True)),
        patch("catalog.viewpoint_views.search_viewpoints_v3", return_value=payload) as search,
    ):
        response = api_client.get(
            "/api/catalog/viewpoint-search/",
            {
                "q": "制度安排促进合作",
                "relation": "oppose",
                "source_type": "other",
                "scholar": scholar_id,
                "theory": str(theory.id),
                "topic": str(topic.id),
                "work": str(work.id),
                "year_min": "2025",
                "year_max": "1980",
                "language": "zh-CN",
            },
        )

    assert response.status_code == 200
    filters = search.call_args.kwargs["filters"]
    assert filters["relations"] == ["oppose"]
    assert filters["document_types"] == ["thesis", "report"]
    assert filters["authors"] == [scholar_id]
    assert filters["theory_node_ids"] == [str(theory.id)]
    assert filters["topic_ids"] == [str(topic.id)]
    assert filters["work_ids"] == [str(work.id)]
    assert filters["year_min"] == 1980
    assert filters["year_max"] == 2025
    assert filters["languages"] == ["zh-CN"]


@pytest.mark.django_db
def test_viewpoint_facets_use_canonical_ids_slugs_labels_and_result_counts():
    work = Work.objects.create(document_type="journal_article", title="关系与证据")
    Edition.objects.create(
        work=work,
        public_slug="relations-and-evidence",
        publication_year=2022,
        state=PublicationState.PUBLISHED,
        is_primary=True,
    )
    person = Person.objects.create(preferred_name="测试学者")
    ScholarProfile.objects.create(
        person=person,
        slug="test-scholar-viewpoint",
        editorial_status="published",
    )
    edition = work.editions.get()
    Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )
    theory = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="证据理论",
        slug="evidence-theory-viewpoint",
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        status=KnowledgePublicationStatus.PUBLISHED,
    )
    topic = Topic.objects.create(
        name="证据主题",
        slug="evidence-topic-viewpoint",
        editorial_status="published",
    )
    WorkTopicRelation.objects.create(
        work=work,
        topic=topic,
        review_status=RelationReviewStatus.APPROVED,
    )
    rows = [
        {
            "work": {"id": str(work.id)},
            "stance": "support",
            "source_type": "journal",
            "language": "zh-CN",
            "publication_year": 2022,
        },
        {
            "work": {"id": str(work.id)},
            "stance": "qualify",
            "source_type": "journal",
            "language": "zh-CN",
            "publication_year": 2022,
        },
    ]

    facets = _viewpoint_facets(rows)

    assert facets["scholars"] == [
        {
            "id": str(person.id),
            "slug": "test-scholar-viewpoint",
            "label": "测试学者",
            "count": 2,
        }
    ]
    assert facets["theories"][0]["id"] == str(theory.id)
    assert facets["theories"][0]["slug"] == theory.slug
    assert facets["theories"][0]["label"] == theory.canonical_name_zh
    assert facets["topics"][0]["id"] == str(topic.id)
    assert facets["topics"][0]["count"] == 2
    assert facets["source_types"][0]["id"] == "journal"
    assert facets["publication_year"] == {"min": 2022, "max": 2022}


def test_viewpoint_year_range_reaches_semantic_and_claim_projection_filters():
    filters = {
        "year_min": 1980,
        "year_max": 2025,
        "_allowed_access_statuses": ["inherit", "public"],
    }

    semantic = semantic_index_filters(filters)
    claims = claim_index_filters(filters)

    assert "publication_year >= 1980" in semantic
    assert "publication_year <= 2025" in semantic
    assert "publication_year >= 1980" in claims
    assert "publication_year <= 2025" in claims
