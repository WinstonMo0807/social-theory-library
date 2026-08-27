import pytest

from catalog.models import (
    Discipline,
    EditorialRevision,
    Edition,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
    Person,
    ReadingPath,
    ReadingPathItem,
    ReadingPathStage,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    TopicDisciplineRelation,
    TopicSubdisciplineRelation,
    TopicTheoryRelation,
    Work,
)
from catalog.services.dependency_engine import projection_types_for


pytestmark = pytest.mark.django_db


def _objects():
    discipline = Discipline.objects.create(
        code="studio-v302",
        name="Studio 学科",
        slug="studio-discipline-v302",
        description="学科说明",
        introduction="学科导论",
        editorial_status="published",
    )
    subdiscipline = Subdiscipline.objects.create(
        discipline=discipline,
        name="Studio 子学科",
        slug="studio-subdiscipline-v302",
        research_object="研究对象",
        core_questions=["核心问题"],
        editorial_status="published",
    )
    theory = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="Studio 理论",
        slug="studio-theory-v302",
        definition="正式定义",
        core_questions=["如何解释？"],
        status="published",
    )
    concept = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="Studio 概念",
        slug="studio-concept-v302",
        definition="概念定义",
        status="published",
    )
    debate = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="Studio 争论",
        slug="studio-debate-v302",
        definition="争论问题",
        status="published",
    )
    person = Person.objects.create(
        preferred_name="Studio 学者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    scholar = ScholarProfile.objects.create(
        person=person,
        slug="studio-scholar-v302",
        short_description="学术位置",
        editorial_status="published",
    )
    topic = Topic.objects.create(
        name="Studio 主题",
        slug="studio-topic-v302",
        problem_statement="主题问题",
        editorial_status="published",
    )
    path = ReadingPath.objects.create(
        title="Studio 路径",
        slug="studio-path-v302",
        audience="初学者",
        learning_goal="掌握基本问题",
        status="published",
    )
    work = Work.objects.create(
        document_type="book",
        title="Studio 重要作品",
        is_featured=True,
    )
    Edition.objects.create(
        work=work,
        state="published",
        public_slug="studio-important-work-v302",
        is_primary=True,
    )
    return {
        "theory": theory,
        "concept": concept,
        "scholar": scholar,
        "discipline": discipline,
        "subdiscipline": subdiscipline,
        "topic": topic,
        "debate": debate,
        "reading_path": path,
        "work": work,
    }


def test_studio_objects_share_public_serializer_editor_and_dependency_contract(
    api_client,
    admin_user,
):
    objects = _objects()
    api_client.force_authenticate(admin_user)

    directory = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"object_type": "all", "limit": 50},
    )
    assert directory.status_code == 200
    assert "discipline" in {
        row["value"] for row in directory.data["studio"]["object_types"]
    }
    assert ("discipline", str(objects["discipline"].id)) in {
        (row["object_type"], row["id"])
        for row in directory.data["studio"]["objects"]
    }

    for object_type, target in objects.items():
        response = api_client.get(
            "/api/catalog/admin/knowledge-workspace/",
            {"selected_type": object_type, "selected_id": str(target.id)},
        )
        assert response.status_code == 200
        selected = response.data["studio"]["selection"]
        adapter = selected["editor_adapter"]
        assert adapter["name"] == "KnowledgeObjectEditorAdapter"
        assert adapter["available"] is True
        assert adapter["mutation_mode"] == "editorial_revision"
        assert adapter["create_revision"] == {
            "method": "POST",
            "url": "/catalog/admin/editorial-revisions/",
        }
        assert selected["preview_perspectives"]["published"]["available"] is True
        assert selected["preview_perspectives"]["published"]["data"]["id"] == str(target.id)
        assert selected["preview_perspectives"]["published"]["route"]
        assert selected["preview_perspectives"]["draft"]["route"].startswith(
            "/admin/preview/"
        )
        assert selected["preview_routes"]["draft_is_protected"] is True
        assert selected["preview_routes"]["uses_public_serializer"] is True
        completeness = selected["content_completeness"]
        assert completeness["source"] == "public_serializer"
        assert completeness["module_count"] == len(completeness["modules"])
        assert all(row["serializer_fields"] for row in completeness["modules"])
        public_data = selected["preview_perspectives"]["published"]["data"]
        missing_serializer_fields = [
            field
            for row in completeness["modules"]
            for field in row["serializer_fields"]
            if field not in public_data
        ]
        assert missing_serializer_fields == [], (object_type, missing_serializer_fields)
        impact = selected["frontend_impact"]
        assert impact["source"] == "dependency_engine_and_public_serializer"
        assert impact["projection_types"] == list(
            projection_types_for(adapter["target_type"])
        )
        assert impact["modules"] == [
            row["label"] for row in completeness["modules"]
        ]


def test_draft_perspective_uses_public_serializer_without_mutating_canonical(
    api_client,
    admin_user,
):
    theory = _objects()["theory"]
    revision = EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
        target_id=theory.id,
        base_revision=0,
        revision=1,
        patch={"definition": "草稿定义"},
        materialized_preview={"definition": "草稿定义"},
        changed_fields=["definition"],
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="studio-v302-draft-preview",
        created_by=admin_user,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "theory", "selected_id": str(theory.id)},
    )

    assert response.status_code == 200
    perspectives = response.data["studio"]["selection"]["preview_perspectives"]
    assert perspectives["published"]["serializer"] == "KnowledgeNodeDetailSerializer"
    assert perspectives["published"]["data"]["definition"] == "正式定义"
    assert perspectives["draft"]["available"] is True
    assert perspectives["draft"]["complete"] is True
    assert perspectives["draft"]["serializer"] == "KnowledgeNodeDetailSerializer"
    assert perspectives["draft"]["revision_id"] == str(revision.id)
    assert perspectives["draft"]["data"]["definition"] == "草稿定义"
    assert perspectives["draft"]["unsupported_preview_fields"] == []
    theory.refresh_from_db()
    assert theory.definition == "正式定义"

    preview = api_client.get(
        f"/api/catalog/admin/knowledge-preview/theory/{theory.id}/"
    )
    assert preview.status_code == 200
    assert preview.data["protected"] is True
    assert preview.data["active_perspective"] == "draft"
    assert preview.data["source"] == "editorial_revision"
    assert preview.data["perspective"]["serializer"] == "KnowledgeNodeDetailSerializer"
    assert preview.data["perspective"]["data"]["definition"] == "草稿定义"
    assert preview.data["preview_routes"]["draft"] == (
        f"/admin/preview/knowledge/theory/{theory.id}"
    )


def test_unpublished_object_without_revision_uses_canonical_draft_perspective(
    api_client,
    admin_user,
):
    theory = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="未发布理论",
        slug="studio-unpublished-theory-v302",
        definition="当前规范草稿",
        status="draft",
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/theory/{theory.id}/"
    )

    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
    assert response.data["active_perspective"] == "draft"
    assert response.data["source"] == "canonical_draft"
    published = response.data["perspectives"]["published"]
    assert published["source"] == "published"
    assert published["available"] is False
    assert published["data"] is None
    draft = response.data["perspectives"]["draft"]
    assert draft["source"] == "canonical_draft"
    assert draft["available"] is True
    assert draft["complete"] is True
    assert draft["revision_id"] is None
    assert draft["data"]["definition"] == "当前规范草稿"
    assert draft["unsupported_preview_fields"] == []


def test_special_fields_overlay_matches_public_serializer_without_database_writes(
    api_client,
    admin_user,
):
    objects = _objects()
    theory = objects["theory"]
    scholar = objects["scholar"]
    topic = objects["topic"]
    path = objects["reading_path"]
    discipline = objects["discipline"]
    subdiscipline = objects["subdiscipline"]
    linked_topic = Topic.objects.create(
        name="草稿关联主题",
        slug="studio-linked-topic-v302",
        editorial_status="published",
    )
    legacy_theory = TheorySchool.objects.create(
        name="草稿关联理论",
        slug="studio-linked-theory-v302",
        editorial_status="published",
    )

    node_special = {
        "aliases": [
            {
                "alias": "Studio Theory",
                "language": "en",
                "alias_type": "translation",
                "source_kind": "editorial",
                "is_verified": True,
            }
        ],
        "discipline_links": [
            {
                "discipline_id": str(discipline.id),
                "relation_type": "related",
                "discipline_specific_summary": "草稿学科说明",
                "sort_order": 1,
                "status": "published",
            }
        ],
        "subdiscipline_links": [
            {
                "subdiscipline_id": str(subdiscipline.id),
                "is_primary": True,
                "relation_role": "core",
                "source": "editorial",
                "confidence": 1,
                "sort_order": 0,
                "status": "published",
            }
        ],
        "topic_links": [
            {
                "topic_id": str(linked_topic.id),
                "relation_label": "解释",
                "source": "editorial",
                "confidence": 1,
                "sort_order": 0,
                "status": "published",
            }
        ],
    }
    EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
        target_id=theory.id,
        base_revision=0,
        revision=1,
        patch=node_special,
        materialized_preview=node_special,
        changed_fields=sorted(node_special),
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="studio-v302-node-special-preview",
        created_by=admin_user,
    )
    EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.SCHOLAR_PROFILE,
        target_id=scholar.id,
        base_revision=0,
        revision=1,
        patch={"person": {"preferred_name": "草稿学者", "aliases": ["草稿别名"]}},
        materialized_preview={
            "person": {"preferred_name": "草稿学者", "aliases": ["草稿别名"]}
        },
        changed_fields=["person"],
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="studio-v302-scholar-special-preview",
        created_by=admin_user,
    )
    topic_special = {
        "discipline_relations": [
            {
                "discipline_id": str(discipline.id),
                "is_primary": True,
                "review_status": RelationReviewStatus.APPROVED,
            }
        ],
        "theory_relations": [
            {
                "theory_school_id": str(legacy_theory.id),
                "relation_label": "解释框架",
                "review_status": RelationReviewStatus.APPROVED,
            }
        ],
        "subdiscipline_relations": [
            {
                "subdiscipline_id": str(subdiscipline.id),
                "relation_label": "研究领域",
                "review_status": RelationReviewStatus.APPROVED,
            }
        ],
    }
    EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.TOPIC,
        target_id=topic.id,
        base_revision=0,
        revision=1,
        patch=topic_special,
        materialized_preview=topic_special,
        changed_fields=sorted(topic_special),
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="studio-v302-topic-special-preview",
        created_by=admin_user,
    )
    stage_groups = [
        {
            "id": "",
            "name": "草稿阶段",
            "description": "阶段说明",
            "position": 0,
            "items": [
                {
                    "id": "",
                    "node": None,
                    "work": str(objects["work"].id),
                    "recommendation_reason": "先读这本书",
                    "prerequisite": "",
                    "position": 0,
                    "is_required": True,
                    "editorial_note": "",
                }
            ],
        }
    ]
    EditorialRevision.objects.create(
        target_type=EditorialRevision.TargetType.READING_PATH,
        target_id=path.id,
        base_revision=0,
        revision=1,
        patch={"stage_groups": stage_groups},
        materialized_preview={"stage_groups": stage_groups},
        changed_fields=["stage_groups"],
        status=EditorialRevision.Status.DRAFT,
        idempotency_key="studio-v302-reading-path-special-preview",
        created_by=admin_user,
    )
    api_client.force_authenticate(admin_user)

    node_response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/theory/{theory.id}/"
    )
    assert node_response.status_code == 200
    node_perspectives = node_response.data["perspectives"]
    assert node_perspectives["published"]["data"]["aliases"] == []
    node_draft = node_perspectives["draft"]
    assert node_draft["source"] == "editorial_revision"
    assert node_draft["complete"] is True
    assert node_draft["unsupported_preview_fields"] == []
    node_data = node_draft["data"]
    assert node_data["aliases"][0]["alias"] == "Studio Theory"
    assert node_data["aliases"][0]["normalized_alias"] == "studio theory"
    assert node_data["aliases_count"] == 1
    assert node_data["discipline_links"][0]["discipline"]["id"] == str(
        discipline.id
    )
    assert node_data["related_disciplines"][0]["id"] == str(discipline.id)
    assert node_data["subdiscipline_links"][0]["subdiscipline"]["id"] == str(
        subdiscipline.id
    )
    assert node_data["topic_links"][0]["topic"]["id"] == str(linked_topic.id)

    scholar_response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/scholar/{scholar.id}/"
    )
    assert scholar_response.status_code == 200
    scholar_perspectives = scholar_response.data["perspectives"]
    assert (
        scholar_perspectives["published"]["data"]["person"]["preferred_name"]
        == "Studio 学者"
    )
    draft_person = scholar_perspectives["draft"]["data"]["person"]
    assert draft_person["id"] == str(scholar.person_id)
    assert draft_person["preferred_name"] == "草稿学者"
    assert "草稿别名" in draft_person["aliases"]
    assert scholar_perspectives["draft"]["unsupported_preview_fields"] == []

    topic_response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/topic/{topic.id}/"
    )
    assert topic_response.status_code == 200
    topic_data = topic_response.data["perspectives"]["draft"]["data"]
    assert topic_data["disciplines"] == [
        {
            "id": str(discipline.id),
            "name": discipline.name,
            "slug": discipline.slug,
            "is_primary": True,
        }
    ]
    assert topic_data["linked_theories"][0]["id"] == str(legacy_theory.id)
    assert topic_data["linked_theories"][0]["relation_label"] == "解释框架"
    assert topic_data["subdisciplines"][0]["id"] == str(subdiscipline.id)
    assert topic_response.data["perspectives"]["draft"][
        "unsupported_preview_fields"
    ] == []

    path_response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/reading_path/{path.id}/"
    )
    assert path_response.status_code == 200
    path_draft = path_response.data["perspectives"]["draft"]
    assert path_draft["complete"] is True
    assert path_draft["unsupported_preview_fields"] == []
    path_data = path_draft["data"]
    assert "stage_groups" not in path_data
    assert path_data["stages"][0]["name"] == "草稿阶段"
    assert path_data["items"][0]["stage_data"]["name"] == "草稿阶段"
    assert str(path_data["items"][0]["work"]) == str(objects["work"].id)
    assert path_data["items"][0]["reading_order"] == 0

    theory.refresh_from_db()
    scholar.person.refresh_from_db()
    assert theory.aliases.count() == 0
    assert KnowledgeNodeAlias.objects.filter(node=theory).count() == 0
    assert KnowledgeNodeDiscipline.objects.filter(node=theory).count() == 0
    assert KnowledgeNodeSubdiscipline.objects.filter(node=theory).count() == 0
    assert KnowledgeNodeTopic.objects.filter(node=theory).count() == 0
    assert scholar.person.preferred_name == "Studio 学者"
    assert TopicDisciplineRelation.objects.filter(topic=topic).count() == 0
    assert TopicTheoryRelation.objects.filter(topic=topic).count() == 0
    assert TopicSubdisciplineRelation.objects.filter(topic=topic).count() == 0
    assert ReadingPathStage.objects.filter(reading_path=path).count() == 0
    assert ReadingPathItem.objects.filter(reading_path=path).count() == 0


def test_reader_cannot_access_protected_knowledge_preview(
    api_client,
    reader_user,
):
    theory = _objects()["theory"]
    api_client.force_authenticate(reader_user)

    response = api_client.get(
        f"/api/catalog/admin/knowledge-preview/theory/{theory.id}/"
    )

    assert response.status_code == 403
    assert response["Cache-Control"] == "private, no-store"
