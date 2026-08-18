import hashlib

import pytest

from catalog.models import (
    Discipline,
    Edition,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Person,
    QueryLexiconEntry,
    QueryLexiconState,
    ReadingPath,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    Work,
)
from catalog.services.query_lexicon.normalization import normalize_term


pytestmark = pytest.mark.django_db


def create_public_work(title="共同研究"):
    work = Work.objects.create(title=title, document_type="book", language="zh-CN")
    Edition.objects.create(
        work=work,
        state="published",
        is_primary=True,
        public_slug=f"work-{work.id}",
    )
    return work


def create_scholar(name, *, status=Person.AuthorityStatus.VERIFIED, profile_status="published"):
    person = Person.objects.create(
        preferred_name=name,
        original_name=f"{name} Original",
        sort_name=name,
        authority_status=status,
    )
    profile = ScholarProfile.objects.create(
        person=person,
        slug=f"scholar-{person.id}",
        editorial_status=profile_status,
        short_description=f"{name} 的公开简介",
    )
    return person, profile


def create_public_alias(person, alias):
    state = QueryLexiconState.objects.get(key="default")
    normalized = normalize_term(alias)
    QueryLexiconEntry.objects.create(
        generation=state.active_generation,
        entity_type=QueryLexiconEntry.EntityType.PERSON,
        entity_id=person.id,
        term=alias,
        normalized_term=normalized,
        language="zh-CN",
        term_type=QueryLexiconEntry.TermType.TRANSLATION,
        source_kind=QueryLexiconEntry.SourceKind.PERSON_NAME_VARIANT,
        trust_level=QueryLexiconEntry.TrustLevel.VERIFIED,
        source_ref=f"test:{person.id}:{normalized}",
        source_fingerprint=hashlib.sha256(
            f"{person.id}:{normalized}".encode()
        ).hexdigest(),
        provenance={"test": True},
        displayable=True,
        public_active=True,
        admin_resolvable=True,
    )


def seeded_entities():
    work = create_public_work()
    person, profile = create_scholar("共同学者")
    create_public_alias(person, "共同别名")
    draft_person, draft_profile = create_scholar(
        "共同草稿学者",
        status=Person.AuthorityStatus.DRAFT,
    )
    discipline = Discipline.objects.create(
        code="SOC",
        name="共同学科",
        slug="shared-discipline",
        editorial_status="published",
    )
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="共同子学科",
        slug="shared-subdiscipline",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="共同主题",
        slug="shared-topic",
        editorial_status="published",
    )
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="共同理论",
        canonical_name_en="Shared Theory",
        slug="shared-theory",
        status="published",
    )
    draft_node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="共同草稿理论",
        slug="shared-draft-theory",
        status="draft",
    )
    legacy = TheorySchool.objects.create(
        name="共同理论旧展示",
        slug="shared-legacy-theory",
        editorial_status="published",
    )
    LegacyKnowledgeMapping.objects.create(
        legacy_model="TheorySchool",
        legacy_id=legacy.id,
        node=node,
        migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
    )
    reading_path = ReadingPath.objects.create(
        title="共同阅读路径",
        slug="shared-reading-path",
        status="published",
    )
    return {
        "work": work,
        "person": person,
        "profile": profile,
        "draft_person": draft_person,
        "draft_profile": draft_profile,
        "discipline": discipline,
        "subdiscipline": subdiscipline,
        "topic": topic,
        "node": node,
        "draft_node": draft_node,
        "legacy": legacy,
        "reading_path": reading_path,
    }


@pytest.mark.parametrize(
    ("context", "expected_type"),
    [
        ("works", "work"),
        ("scholars", "person"),
        ("disciplines", "discipline"),
        ("subdisciplines", "subdiscipline"),
        ("topics", "topic"),
        ("reading_paths", "reading_path"),
    ],
)
def test_scoped_context_never_leaks_other_entities(api_client, context, expected_type):
    seeded_entities()

    response = api_client.get(
        "/api/catalog/search/",
        {"context": context, "envelope": "1", "q": "共同"},
    )

    assert response.status_code == 200
    assert response.data["context"] == context
    assert len(response.data["groups"]) == 1
    assert response.data["groups"][0]["context"] == context
    assert response.data["groups"][0]["results"]
    assert {row["entity_type"] for row in response.data["groups"][0]["results"]} == {
        expected_type
    }


def test_theory_scope_uses_knowledge_node_identity_and_suppresses_mapped_legacy(api_client):
    rows = seeded_entities()

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "theories", "envelope": "1", "q": "共同理论"},
    )

    assert response.status_code == 200
    results = response.data["groups"][0]["results"]
    assert [row["id"] for row in results] == [str(rows["node"].id)]
    assert results[0]["entity_type"] == "knowledge_node"
    assert str(rows["legacy"].id) not in {row["id"] for row in results}
    assert str(rows["draft_node"].id) not in {row["id"] for row in results}


def test_topic_scope_does_not_merge_same_named_theory(api_client):
    seeded_entities()
    Topic.objects.create(
        name="共同理论",
        slug="same-name-topic",
        editorial_status="published",
    )

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "topics", "envelope": "1", "q": "共同理论"},
    )

    results = response.data["groups"][0]["results"]
    assert len(results) == 1
    assert results[0]["entity_type"] == "topic"


def test_global_context_is_explicit_grouped_and_empty_query_does_not_search(api_client):
    seeded_entities()

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "global", "envelope": "1", "q": "共同"},
    )

    assert response.status_code == 200
    assert response.data["context"] == "global"
    groups = {group["context"]: group for group in response.data["groups"]}
    assert {"works", "scholars", "disciplines", "subdisciplines", "theories", "topics", "reading_paths"} <= set(groups)
    assert groups["works"]["results"]
    assert groups["scholars"]["results"]
    assert groups["topics"]["results"]
    assert all(
        row["context"] == context
        for context, group in groups.items()
        for row in group["results"]
    )

    empty = api_client.get(
        "/api/catalog/search/",
        {"context": "global", "envelope": "1", "q": ""},
    )
    assert empty.status_code == 200
    assert empty.data["total"] == 0
    assert all(group["count"] == 0 and group["results"] == [] for group in empty.data["groups"])


def test_public_scholar_search_excludes_draft_and_accepts_public_lexicon_alias(api_client):
    rows = seeded_entities()

    alias = api_client.get(
        "/api/catalog/search/",
        {"context": "scholars", "envelope": "1", "q": "共同别名"},
    )
    assert [row["id"] for row in alias.data["groups"][0]["results"]] == [
        str(rows["person"].id)
    ]

    draft = api_client.get(
        "/api/catalog/search/",
        {"context": "scholars", "envelope": "1", "q": "共同草稿学者"},
    )
    assert draft.data["groups"][0]["results"] == []
    legacy_list = api_client.get("/api/catalog/scholars/", {"q": "共同草稿学者"})
    assert legacy_list.status_code == 200
    assert legacy_list.data["results"] == []


def test_admin_visibility_is_explicit_and_anonymous_cannot_request_it(api_client, admin_user):
    rows = seeded_entities()

    anonymous = api_client.get(
        "/api/catalog/search/",
        {
            "context": "scholars",
            "envelope": "1",
            "visibility": "admin",
            "q": "共同草稿学者",
        },
    )
    assert anonymous.status_code == 200
    assert anonymous.data["visibility"] == "public"
    assert anonymous.data["groups"][0]["results"] == []

    api_client.force_authenticate(admin_user)
    admin = api_client.get(
        "/api/catalog/search/",
        {
            "context": "scholars",
            "envelope": "1",
            "visibility": "admin",
            "q": "共同草稿学者",
        },
    )
    assert admin.status_code == 200
    assert admin.data["visibility"] == "admin"
    assert [row["id"] for row in admin.data["groups"][0]["results"]] == [
        str(rows["draft_person"].id)
    ]


def test_exact_canonical_match_precedes_prefix_match(api_client):
    Topic.objects.create(name="资本", slug="capital-exact", editorial_status="published")
    Topic.objects.create(name="资本主义", slug="capital-prefix", editorial_status="published")

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "topics", "envelope": "1", "q": "资本"},
    )

    results = response.data["groups"][0]["results"]
    assert [row["title"] for row in results[:2]] == ["资本", "资本主义"]
    assert results[0]["match"]["type"] == "exact"
    assert results[1]["match"]["type"] == "prefix"


def test_work_context_returns_one_work_when_multiple_editions_exist(api_client):
    work = create_public_work("多版本馆藏")
    Edition.objects.create(
        work=work,
        state="published",
        is_primary=False,
        public_slug=f"secondary-{work.id}",
    )

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "works", "envelope": "1", "q": "多版本馆藏"},
    )

    results = response.data["groups"][0]["results"]
    assert len(results) == 1
    assert results[0]["id"] == str(work.id)
    assert results[0]["metadata"]["public_slug"].startswith("work-")


def test_scoped_pagination_uses_context_total_not_frontend_slice(api_client):
    for index in range(26):
        Topic.objects.create(
            name=f"分页主题{index:02d}",
            slug=f"paged-topic-{index:02d}",
            editorial_status="published",
        )

    response = api_client.get(
        "/api/catalog/search/",
        {"context": "topics", "envelope": "1", "page": 2, "limit": 10},
    )

    assert response.status_code == 200
    assert response.data["pagination"] == {
        "page": 2,
        "limit": 10,
        "total": 26,
        "total_pages": 3,
    }
    assert len(response.data["groups"][0]["results"]) == 10


def test_legacy_global_payload_is_preserved_but_marked_deprecated(api_client):
    create_public_work("兼容搜索馆藏")

    response = api_client.get("/api/catalog/search/", {"q": "兼容搜索馆藏"})

    assert response.status_code == 200
    assert response.data["context"] == "global"
    assert "works" in response.data and "groups" not in response.data
    assert response.headers["Deprecation"] == "true"


def test_subdiscipline_list_uses_backend_query_not_frontend_slice(api_client):
    discipline = Discipline.objects.create(
        code="T4ANT",
        name="Task4人类学",
        slug="task4-anthropology",
        editorial_status="published",
    )
    match = Subdiscipline.objects.create(
        discipline=discipline,
        name="医学人类学",
        slug="medical-anthropology",
        editorial_status="published",
    )
    Subdiscipline.objects.create(
        discipline=discipline,
        name="经济人类学",
        slug="economic-anthropology",
        editorial_status="published",
    )

    response = api_client.get("/api/catalog/subdisciplines/", {"q": "医学"})

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(match.id)]
