from types import SimpleNamespace

import pytest

from catalog.models import KnowledgeNode, KnowledgeRelation
from catalog.services.relation_registry import relation_policy
from catalog.theory_serializers import AdminKnowledgeRelationSerializer


pytestmark = pytest.mark.django_db


def node(name: str):
    return KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh=name,
        slug=name,
    )


def test_registry_marks_interpretive_relations_as_reviewed_and_evidenced():
    policy = relation_policy(KnowledgeRelation.RelationType.CRITICIZES)

    assert policy.directed is True
    assert policy.requires_review is True
    assert policy.requires_evidence is True


def test_symmetric_relation_rejects_directed_direction():
    source = node("source")
    target = node("target")
    serializer = AdminKnowledgeRelationSerializer(
        context={
            "request": SimpleNamespace(
                user=SimpleNamespace(role="admin", is_authenticated=True, is_superuser=False)
            )
        },
        data={
            "source_node": source.id,
            "target_node": target.id,
            "relation_type": KnowledgeRelation.RelationType.OVERLAPS_WITH,
            "direction": KnowledgeRelation.Direction.DIRECTED,
        }
    )

    assert serializer.is_valid() is False
    assert "direction" in serializer.errors


def test_published_relation_requires_evidence():
    source = node("source")
    target = node("target")
    serializer = AdminKnowledgeRelationSerializer(
        context={
            "request": SimpleNamespace(
                user=SimpleNamespace(role="admin", is_authenticated=True, is_superuser=False)
            )
        },
        data={
            "source_node": source.id,
            "target_node": target.id,
            "relation_type": KnowledgeRelation.RelationType.CRITICIZES,
            "direction": KnowledgeRelation.Direction.DIRECTED,
            "status": "published",
        }
    )

    assert serializer.is_valid() is False
    assert "evidence_source" in serializer.errors


def test_hierarchical_relation_rejects_cycle():
    first = node("first")
    second = node("second")
    third = node("third")
    KnowledgeRelation.objects.create(
        source_node=first,
        target_node=second,
        relation_type=KnowledgeRelation.RelationType.BRANCHES_FROM,
        direction=KnowledgeRelation.Direction.DIRECTED,
    )
    KnowledgeRelation.objects.create(
        source_node=second,
        target_node=third,
        relation_type=KnowledgeRelation.RelationType.BRANCHES_FROM,
        direction=KnowledgeRelation.Direction.DIRECTED,
    )
    serializer = AdminKnowledgeRelationSerializer(
        data={
            "source_node": third.id,
            "target_node": first.id,
            "relation_type": KnowledgeRelation.RelationType.BRANCHES_FROM,
            "direction": KnowledgeRelation.Direction.DIRECTED,
        }
    )

    assert serializer.is_valid() is False
    assert "target_node" in serializer.errors
