"""Deferred original relation command and draft-membership acceptance."""
from uuid import uuid4
from unittest.mock import patch
import pytest

from catalog.models import EditorialRevision, KnowledgeNode, KnowledgeRelation
from catalog.relation_editorial_views import relations_for_node
from common.capabilities import Capability

pytestmark = pytest.mark.django_db
BASE = "/api/catalog/admin/theory-system/relations/"


def node():
    return KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="验收节点", slug=f"inline-{uuid4()}", status="published")


def headers(user, key=None):
    return {"HTTP_X_EDITOR_OWNER": str(user.pk), "HTTP_IDEMPOTENCY_KEY": str(key or uuid4())}


def test_node_relationship_saved_once_and_stopped_request_cannot_create(api_client, admin_user, reader_user):
    first, second = node(), node()
    payload = {"source_node": str(first.pk), "target_node": str(second.pk), "relation_type": "criticizes", "direction": "directed", "status": "pending", "description": "验收关系", "evidence_source": "验收出处"}
    api_client.force_authenticate(admin_user)
    key = uuid4()
    saved = api_client.post(BASE, payload, format="json", **headers(admin_user, key))
    assert saved.status_code == 201
    replay = api_client.post(BASE, payload, format="json", **headers(admin_user, key))
    assert replay.status_code == 200 and replay.data["id"] == saved.data["id"]
    assert KnowledgeRelation.objects.filter(source_node=first, target_node=second).count() == 1
    stopped = uuid4()
    receipt = f"{BASE}commands/{stopped}/"
    assert api_client.post(receipt, {"action": "cancel_pending"}, format="json", **headers(admin_user)).data["state"] == "cancelled"
    assert api_client.post(BASE, payload, format="json", **headers(admin_user, stopped)).status_code == 409
    api_client.force_authenticate(reader_user)
    assert api_client.get(receipt, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403


def test_formal_and_draft_endpoints_share_node_scope(api_client, admin_user):
    first, second, third, unrelated = node(), node(), node(), node()
    relation = KnowledgeRelation.objects.create(source_node=first, target_node=second, relation_type="criticizes", status="published")
    EditorialRevision.objects.create(target_type="knowledge_relation", target_id=relation.pk, revision=1, status="draft",
        materialized_preview={"source_node": str(third.pk), "target_node": str(second.pk)}, idempotency_key=str(uuid4()))
    for member in [first, second, third]:
        assert list(relations_for_node(KnowledgeRelation.objects.all(), str(member.pk)).values_list("pk", flat=True)) == [relation.pk]
    assert not relations_for_node(KnowledgeRelation.objects.all(), str(unrelated.pk)).exists()
    api_client.force_authenticate(admin_user)
    assert api_client.get(f"{BASE}{relation.pk}/", {"node": str(unrelated.pk)}).status_code == 404
    assert api_client.get(BASE, {"node": "invalid-uuid"}).status_code == 400


def test_editing_public_relation_does_not_require_republishing_during_save(api_client, admin_user):
    first, second = node(), node()
    relation = KnowledgeRelation.objects.create(source_node=first, target_node=second, relation_type="criticizes", description="原说明", evidence_source="验收出处", status="published")
    api_client.force_authenticate(admin_user)
    url = f"{BASE}{relation.pk}/"
    version = api_client.get(url).data["edit_version"]
    with patch("catalog.theory_serializers.has_capability", side_effect=lambda actor, capability: capability != Capability.PUBLISH_AUTHORITY):
        result = api_client.patch(url, {"status": "published", "description": "新草稿说明"}, format="json", HTTP_IF_MATCH=version, **headers(admin_user))
    assert result.status_code == 202
    relation.refresh_from_db()
    assert relation.description == "原说明"
    assert result.data["description"] == "新草稿说明" and result.data["editorial_revision"]["status"] == "draft"
