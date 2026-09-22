from unittest.mock import patch
from uuid import uuid4

import pytest

from catalog.models import (
    Asset,
    Contribution,
    Edition,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Person,
    Page,
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
from catalog.discovery_models import DiscoverySearchSession
from .v304_helpers import activate_catalog_revision


def _activate_search_edition(edition):
    asset = Asset.objects.create(
        edition=edition, kind="normalized", status="ready", validation_status="valid",
        sha256=edition.pk.hex * 2, page_count=1,
    )
    Page.objects.create(
        asset=asset, index=1, text="筛选项测试的正式原文", normalized_text="筛选项测试的正式原文", text_source="embedded",
    )
    activate_catalog_revision(edition, reader_asset=asset)


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
    with (
        patch("catalog.services.discovery_sessions._enqueue"),
        patch("catalog.viewpoint_views.search_viewpoints_v3") as retired_search,
    ):
        response = api_client.get(
            "/api/catalog/viewpoint-search/",
            {
                "q": "制度信任促进合作",
                "document_type": ["book"],
                "language": ["zh-CN"],
                "work_id": [work_id],
                "limit": "16",
                "max_per_work": "2",
                "sort": "newest",
            },
        )

    assert response.status_code == 202
    assert response.data["status"] == "queued"
    assert response.data["engine"] == "discovery_v308"
    assert response.data["search_version"] == "3.0.8"
    assert response.data["access_token"]
    assert response.data["compatibility_notice"]
    assert response["Location"] == response.data["status_url"]
    assert response["Cache-Control"] == "private, no-store"
    assert "shadow" not in response.data
    assert "baseline" not in response.data
    assert response.data["stance_counts"] == {}
    assert response.data["groups"] == {}
    assert response.data["results"] == []
    session = DiscoverySearchSession.objects.get(pk=response.data["id"])
    assert session.filters["work_ids"] == [work_id]
    assert session.filters["document_types"] == ["book"]
    assert session.access_statuses == ["inherit", "public"]
    retired_search.assert_not_called()
    denied = api_client.get(response.data["status_url"])
    assert denied.status_code == 404
    status = api_client.get(response.data["status_url"], HTTP_X_DISCOVERY_TOKEN=response.data["access_token"])
    assert status.status_code == 200 and status.data["status"] == "queued"


@pytest.mark.django_db
def test_staff_debug_does_not_restore_retired_claim_shadow_in_public_endpoint(api_client, admin_user):
    admin_user.is_staff = True
    admin_user.save(update_fields=["is_staff"])
    api_client.force_authenticate(admin_user)
    with (
        patch("catalog.services.discovery_sessions._enqueue"),
        patch("catalog.viewpoint_views.search_viewpoints_v3") as retired_search,
    ):
        response = api_client.get(
            "/api/catalog/viewpoint-search/",
            {"q": "制度信任促进合作", "debug": "1"},
        )

    assert response.status_code == 202
    assert "shadow" not in response.data and "baseline" not in response.data
    assert response.data["groups"] == {}
    retired_search.assert_not_called()
    session = DiscoverySearchSession.objects.get(pk=response.data["id"])
    assert session.owner_id == admin_user.pk
    assert session.access_statuses == [
        "inherit",
        "public",
        "registered",
        "restricted",
        "private",
    ]


@pytest.mark.django_db
@pytest.mark.parametrize("query", ["", "单"])
def test_public_viewpoint_api_rejects_queries_shorter_than_a_search(api_client, query):
    response = api_client.get("/api/catalog/viewpoint-search/", {"q": query})

    assert response.status_code == 400
    assert response.data["error"]["status"] == 400
    assert "2 至 1200" in str(response.data["error"]["detail"]["q"])


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
    edition = Edition.objects.create(work=work, state="published", public_slug="formal-filter-work")
    _activate_search_edition(edition)
    scholar_id = str(uuid4())
    with (
        patch("catalog.services.discovery_sessions._enqueue"),
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
                "year_min": "1980",
                "year_max": "2025",
                "language": "zh-CN",
            },
        )

    assert response.status_code == 202
    filters = DiscoverySearchSession.objects.get(pk=response.data["id"]).filters
    assert "relations" not in filters
    assert filters["document_types"] == ["thesis", "report"]
    assert filters["authors"] == [scholar_id]
    assert filters["theory_node_ids"] == [str(theory.id)]
    assert filters["topic_ids"] == [str(topic.id)]
    assert filters["work_ids"] == [str(work.id)]
    assert filters["year_min"] == 1980
    assert filters["year_max"] == 2025
    assert filters["languages"] == ["zh-CN"]


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [{"work_id": "not-a-uuid"}, {"year_min": "2025", "year_max": "1980"},
                                    {"_allowed_access_statuses": "private"}, {"document_type": "invented"}])
def test_legacy_viewpoint_rejects_invalid_or_client_supplied_security_filters(api_client, invalid):
    response = api_client.get("/api/catalog/viewpoint-search/", {"q": "制度与合作", **invalid})
    assert response.status_code == 400
    assert DiscoverySearchSession.objects.count() == 0


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
    person = Person.objects.create(
        preferred_name="测试学者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
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
    _activate_search_edition(edition)
    rows = [
        {
            "work": {"id": str(work.id), "title": work.title, "slug": edition.public_slug},
            "evidence": {"source": {"edition_id": str(edition.pk)}},
            "stance": "support",
            "source_type": "journal",
            "language": "zh-CN",
            "publication_year": 2022,
        },
        {
            "work": {"id": str(work.id), "title": work.title, "slug": edition.public_slug},
            "evidence": {"source": {"edition_id": str(edition.pk)}},
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


@pytest.mark.django_db
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
