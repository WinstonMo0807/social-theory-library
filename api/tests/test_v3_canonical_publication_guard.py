from __future__ import annotations

import pytest

from accounts.models import User
from catalog.models import (
    DomainChangeEvent,
    Edition,
    KnowledgeNode,
    KnowledgeRelation,
    ProjectionState,
    TheorySchool,
    Topic,
    Work,
)
from ingestion.services.publication import withdraw_edition


pytestmark = pytest.mark.django_db(transaction=True)


def _reviewer():
    return User.objects.create_user(
        username="legacy-reviewer@example.org",
        email="legacy-reviewer@example.org",
        display_name="兼容审核者",
        role=User.Role.REVIEWER,
        password="Reviewer-Secure-Password-2026",
    )


def _node(name: str, slug: str) -> KnowledgeNode:
    return KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh=name,
        slug=slug,
        status="published",
    )


def test_topic_publication_records_domain_change_and_projection_state(
    api_client,
    admin_user,
):
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/catalog/admin/topics/",
        {
            "name": "规范发布主题",
            "slug": "canonical-publication-topic",
            "editorial_status": "published",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="topic-publication-test",
    )

    assert response.status_code == 201
    topic = Topic.objects.get(pk=response.data["id"])
    event = DomainChangeEvent.objects.get(object_type="topic", object_id=topic.id)
    assert event.change_kind == "publish"
    assert event.processed_at is not None
    assert ProjectionState.objects.filter(
        object_type="topic",
        object_id=topic.id,
        source_revision=event.canonical_revision,
    ).exists()


def test_legacy_reviewer_is_normalized_to_editor_for_authority_publication(
    api_client,
):
    reviewer = _reviewer()
    source = _node("关系起点", "reviewer-relation-source")
    target = _node("关系终点", "reviewer-relation-target")
    api_client.force_authenticate(reviewer)

    topic_response = api_client.post(
        "/api/catalog/admin/topics/",
        {
            "name": "兼容账号发布主题",
            "slug": "reviewer-must-not-publish-topic",
            "editorial_status": "published",
        },
        format="json",
    )
    relation_response = api_client.post(
        "/api/catalog/admin/theory-system/relations/",
        {
            "source_node": str(source.id),
            "target_node": str(target.id),
            "relation_type": "overlaps_with",
            "direction": "undirected",
            "evidence_source": "人工来源说明",
            "status": "published",
        },
        format="json",
    )

    assert topic_response.status_code == 201
    assert relation_response.status_code == 201
    assert Topic.objects.filter(slug="reviewer-must-not-publish-topic").exists()
    assert KnowledgeRelation.objects.filter(
        source_node=source,
        target_node=target,
    ).exists()


def test_published_knowledge_relation_propagates_and_cannot_be_hard_deleted(
    api_client,
    admin_user,
):
    source = _node("规范关系起点", "canonical-relation-source")
    target = _node("规范关系终点", "canonical-relation-target")
    api_client.force_authenticate(admin_user)

    created = api_client.post(
        "/api/catalog/admin/theory-system/relations/",
        {
            "source_node": str(source.id),
            "target_node": str(target.id),
            "relation_type": "overlaps_with",
            "direction": "undirected",
            "description": "两种理论在行动解释上部分重叠。",
            "evidence_source": "Editor 核对后的来源说明",
            "confidence": 1,
            "status": "published",
        },
        format="json",
        HTTP_IDEMPOTENCY_KEY="knowledge-relation-publication-test",
    )

    assert created.status_code == 201
    relation = KnowledgeRelation.objects.get(pk=created.data["id"])
    event = DomainChangeEvent.objects.get(
        object_type="knowledge_relation",
        object_id=relation.id,
    )
    assert event.change_kind == "publish"

    deleted = api_client.delete(
        f"/api/catalog/admin/theory-system/relations/{relation.id}/"
    )
    assert deleted.status_code == 409
    assert deleted.data["code"] == "published_relation_requires_withdrawal"
    assert KnowledgeRelation.objects.filter(pk=relation.id).exists()


def test_edition_withdrawal_records_shared_dependency_event(admin_user):
    work = Work.objects.create(
        title="下架传播测试",
        document_type="book",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        version_label="测试版",
        state="published",
    )

    withdraw_edition(edition, actor=admin_user, reason="验证下架传播")

    event = DomainChangeEvent.objects.get(
        object_type="edition",
        object_id=edition.id,
    )
    assert event.change_kind == "withdraw"
    assert ProjectionState.objects.filter(
        object_type="edition",
        object_id=edition.id,
        source_revision=event.canonical_revision,
    ).exists()


def test_lifecycle_withdrawal_propagates_and_legacy_theory_school_cannot_restore(
    api_client,
    admin_user,
):
    topic = Topic.objects.create(
        name="生命周期传播主题",
        slug="lifecycle-propagation-topic",
        editorial_status="published",
    )
    legacy = TheorySchool.objects.create(
        name="只读兼容理论",
        slug="read-only-legacy-theory",
        editorial_status="archived",
    )
    api_client.force_authenticate(admin_user)

    withdrawn = api_client.post(
        f"/api/catalog/admin/lifecycle/topic/{topic.id}/",
        {"action": "archive"},
        format="json",
        HTTP_IDEMPOTENCY_KEY="topic-lifecycle-withdrawal-test",
    )
    blocked_restore = api_client.post(
        f"/api/catalog/admin/lifecycle/theory-school/{legacy.id}/",
        {"action": "restore"},
        format="json",
    )
    blocked_delete = api_client.post(
        f"/api/catalog/admin/lifecycle/theory-school/{legacy.id}/",
        {"action": "delete", "confirmed": True},
        format="json",
    )

    assert withdrawn.status_code == 202
    topic.refresh_from_db()
    assert topic.editorial_status == "published"
    published = api_client.post(
        f"/api{withdrawn.data['editorial_revision']['publish_url']}",
        {},
        format="json",
    )
    assert published.status_code == 200
    event = DomainChangeEvent.objects.get(object_type="topic", object_id=topic.id)
    assert event.change_kind == "withdraw"
    assert blocked_restore.status_code == 409
    assert blocked_restore.data["code"] == "legacy_theory_school_read_only"
    assert blocked_delete.status_code == 409
    assert TheorySchool.objects.filter(pk=legacy.id).exists()
