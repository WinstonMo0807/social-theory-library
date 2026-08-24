from __future__ import annotations

import pytest

from catalog.models import (
    Asset,
    EvidenceSnippet,
    Edition,
    Contribution,
    KnowledgeNode,
    KnowledgeNodeTopic,
    Person,
    PersonNodeRelation,
    Page,
    Passage,
    PublicationState,
    ReadingPath,
    ReadingPathItem,
    ReadingPathStage,
    ScholarProfile,
    Topic,
    Work,
    WorkNodeRelation,
    WorkTopicRelation,
)


pytestmark = pytest.mark.django_db


def _published_node(*, name: str, slug: str, node_type: str):
    return KnowledgeNode.objects.create(
        canonical_name_zh=name,
        slug=slug,
        node_type=node_type,
        summary=f"{name}的公开说明",
        status="published",
    )


def test_topic_and_scholar_public_pages_consume_normalized_knowledge_relations(api_client):
    theory = _published_node(
        name="规范制度理论",
        slug="normalized-institutional-theory-public",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
    )
    concept = _published_node(
        name="组织场域",
        slug="organizational-field-public",
        node_type=KnowledgeNode.NodeType.CONCEPT,
    )
    debate = _published_node(
        name="结构是否决定行动",
        slug="structure-agency-public",
        node_type=KnowledgeNode.NodeType.DEBATE,
    )
    unpublished = KnowledgeNode.objects.create(
        canonical_name_zh="未发布理论",
        slug="unpublished-node-public",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        status="draft",
    )
    topic = Topic.objects.create(
        name="制度变迁",
        slug="institutional-change-public-v301",
        editorial_status="published",
    )
    KnowledgeNodeTopic.objects.create(
        node=theory,
        topic=topic,
        relation_label="用于解释制度变迁",
        status="published",
    )
    KnowledgeNodeTopic.objects.create(node=concept, topic=topic, status="published")
    KnowledgeNodeTopic.objects.create(node=unpublished, topic=topic, status="published")

    person = Person.objects.create(
        preferred_name="规范关系学者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    scholar = ScholarProfile.objects.create(
        person=person,
        slug="normalized-relation-scholar-public",
        editorial_status="published",
    )
    PersonNodeRelation.objects.create(
        person=person,
        node=theory,
        relation_label="代表学者",
        is_representative=True,
        status="published",
    )
    PersonNodeRelation.objects.create(
        person=person,
        node=debate,
        relation_label="主要参与者",
        status="published",
    )
    PersonNodeRelation.objects.create(
        person=person,
        node=concept,
        relation_label="提出者",
        status="pending",
    )

    topic_response = api_client.get(f"/api/catalog/topics/{topic.slug}/")
    assert topic_response.status_code == 200
    assert {row["id"] for row in topic_response.data["knowledge_nodes"]} == {
        str(theory.id),
        str(concept.id),
    }
    theory_row = next(
        row for row in topic_response.data["knowledge_nodes"] if row["id"] == str(theory.id)
    )
    assert theory_row["relation_label"] == "用于解释制度变迁"

    filtered = api_client.get("/api/catalog/topics/", {"theory": theory.slug})
    assert filtered.status_code == 200
    assert [row["id"] for row in filtered.data["results"]] == [str(topic.id)]

    scholar_response = api_client.get(f"/api/catalog/scholars/{scholar.slug}/")
    assert scholar_response.status_code == 200
    assert {row["id"] for row in scholar_response.data["knowledge_nodes"]} == {
        str(theory.id),
        str(debate.id),
    }
    theory_row = next(
        row for row in scholar_response.data["knowledge_nodes"] if row["id"] == str(theory.id)
    )
    assert theory_row["is_representative"] is True


def test_public_work_theory_tags_are_normalized_first_with_legacy_optional(api_client):
    theory = _published_node(
        name="只写规范关系的理论",
        slug="normalized-only-work-theory-public",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
    )
    work = Work.objects.create(title="规范知识关系作品", language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug="normalized-knowledge-work-public-v301",
    )
    WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        role=WorkNodeRelation.Role.FOUNDATIONAL,
        status="published",
    )
    topic = Topic.objects.create(
        name="规范主题关系",
        slug="normalized-only-work-topic-public",
        editorial_status="published",
    )
    WorkTopicRelation.objects.create(
        work=work,
        topic=topic,
        review_status="approved",
    )
    author = Person.objects.create(
        preferred_name="作品关系作者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    scholar = ScholarProfile.objects.create(
        person=author,
        slug="work-relation-scholar-public",
        editorial_status="published",
    )
    Contribution.objects.create(
        edition=edition,
        person=author,
        role=Contribution.Role.AUTHOR,
        approved=True,
    )

    response = api_client.get("/api/catalog/works/")

    assert response.status_code == 200
    row = next(item for item in response.data["results"] if item["id"] == str(work.id))
    assert row["theories"] == [
        {"id": str(theory.id), "name": theory.canonical_name_zh, "slug": theory.slug}
    ]
    assert row["topics"] == [
        {"id": str(topic.id), "name": topic.name, "slug": topic.slug}
    ]

    scholar_response = api_client.get(f"/api/catalog/scholars/{scholar.slug}/")
    assert scholar_response.status_code == 200
    assert scholar_response.data["knowledge_nodes"] == [
        {
            "id": str(theory.id),
            "node_type": "theory_tradition",
            "name": theory.canonical_name_zh,
            "foreign_name": "",
            "slug": theory.slug,
            "summary": theory.summary,
            "relation_label": "奠基性原著",
            "is_representative": False,
            "relation_source": "published_work_relation",
        }
    ]


def test_public_knowledge_evidence_never_serializes_restricted_asset_text(api_client):
    theory = _published_node(
        name="证据访问边界理论",
        slug="knowledge-evidence-access-public",
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
    )
    topic = Topic.objects.create(
        name="证据访问边界主题",
        slug="knowledge-evidence-access-topic",
        editorial_status="published",
    )
    work = Work.objects.create(title="证据访问边界作品", language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug="knowledge-evidence-access-work",
    )
    relation = WorkNodeRelation.objects.create(
        work=work,
        node=theory,
        role=WorkNodeRelation.Role.SYSTEMATIC_EXPOSITION,
        status="published",
    )
    WorkTopicRelation.objects.create(
        work=work,
        topic=topic,
        review_status="approved",
    )

    def source(*, label: str, access_status: str, seed: str):
        asset = Asset.objects.create(
            edition=edition,
            kind=Asset.Kind.NORMALIZED,
            file=f"public/{label}.pdf",
            sha256=seed * 64,
            status=Asset.Status.READY,
            is_current=True,
            access_status=access_status,
        )
        page = Page.objects.create(
            asset=asset,
            index=1,
            printed_label="1",
            text=f"{label}原文",
            normalized_text=f"{label}原文",
            text_source=Page.TextSource.EMBEDDED,
        )
        Passage.objects.create(
            page=page,
            order=1,
            text=f"{label}原文",
            normalized_text=f"{label}原文",
        )
        evidence = EvidenceSnippet.objects.create(
            work=work,
            file=asset,
            node=theory,
            work_node_relation=relation,
            page_number=1,
            printed_page_label="1",
            quote=f"{label}原文",
            review_status="approved",
        )
        return asset, evidence

    public_asset, public_evidence = source(
        label="公开",
        access_status=Asset.AccessStatus.PUBLIC,
        seed="a",
    )
    _restricted_asset, restricted_evidence = source(
        label="受限",
        access_status=Asset.AccessStatus.RESTRICTED,
        seed="b",
    )

    work_response = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert work_response.status_code == 200
    assert work_response.data["edition"]["readable_asset"]["id"] == str(public_asset.id)
    association_evidence = work_response.data["theory_associations"][0]["evidence"]
    assert [row["id"] for row in association_evidence] == [str(public_evidence.id)]
    assert "受限原文" not in str(work_response.data)

    node_response = api_client.get(f"/api/catalog/theory-system/nodes/{theory.slug}/")
    assert node_response.status_code == 200
    assert [row["id"] for row in node_response.data["evidence"]] == [str(public_evidence.id)]
    assert node_response.data["work_groups"][relation.role][0]["evidence"][0]["id"] == str(
        public_evidence.id
    )
    assert "受限原文" not in str(node_response.data)

    topic_response = api_client.get(f"/api/catalog/topics/{topic.slug}/")
    assert topic_response.status_code == 200
    assert [row["asset_id"] for row in topic_response.data["passages"]] == [
        str(public_asset.id)
    ]
    assert "受限原文" not in str(topic_response.data)

    assert (
        api_client.get(
            f"/api/catalog/theory-system/evidence/{restricted_evidence.id}/focus/"
        ).status_code
        == 404
    )
    assert (
        api_client.get(
            f"/api/catalog/theory-system/evidence/{public_evidence.id}/focus/"
        ).status_code
        == 200
    )


def test_public_reading_path_preserves_learning_goal_and_prerequisite(api_client):
    path = ReadingPath.objects.create(
        title="规范阅读路径",
        slug="canonical-learning-goal-public",
        introduction="这是一条从问题到争论的阅读说明。",
        learning_goal="理解制度解释之间的主要分歧。",
        audience="社会科学初学者",
        status="published",
    )
    stage = ReadingPathStage.objects.create(
        reading_path=path,
        name="第一阶段",
        description="先理解核心概念。",
        position=1,
    )
    node = _published_node(
        name="制度概念",
        slug="reading-path-prerequisite-concept",
        node_type=KnowledgeNode.NodeType.CONCEPT,
    )
    ReadingPathItem.objects.create(
        reading_path=path,
        stage=stage,
        stage_name=stage.name,
        stage_description=stage.description,
        node=node,
        recommendation_reason="为后续争论建立共同词汇。",
        prerequisite="无需预备知识。",
        reading_order=1,
        is_required=True,
    )

    response = api_client.get(f"/api/catalog/theory-system/reading-paths/{path.slug}/")

    assert response.status_code == 200
    assert response.data["learning_goal"] == path.learning_goal
    assert response.data["items"][0]["prerequisite"] == "无需预备知识。"
    assert response.data["items"][0]["recommendation_reason"] == "为后续争论建立共同词汇。"
