"""Deferred coverage for M13; run only during unified acceptance."""
from copy import deepcopy
from uuid import uuid4

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import EditorialRevision, KnowledgeNode, KnowledgeNodeAlias
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_revision import _apply_knowledge_node_relations

pytestmark = pytest.mark.django_db
PATH = "/api/catalog/admin/index-maintenance/knowledge-terms/"


def test_original_draft_retains_other_fields_and_recovers_without_republishing():
    actor = User.objects.create_user(username="knowledge-terms-editor", role="admin")
    node = KnowledgeNode.objects.create(node_type="concept", slug="terms-concept", canonical_name_zh="示例概念", status="published")
    alias = KnowledgeNodeAlias.objects.create(node=node, alias="Original term", is_verified=True)
    save_object_editorial_patch("knowledge_node", node.pk, {"summary": "已有草稿内容"}, actor=actor, request_key="prior-summary")
    client = APIClient(); client.force_authenticate(actor)
    headers = {"HTTP_X_EDITOR_OWNER": str(actor.pk)}
    before = client.get(f"{PATH}{node.pk}/", **headers)
    assert before.status_code == 200
    payload = {"request_id": str(uuid4()), "node_id": str(node.pk), "expected_version": before.data["version"],
        "aliases": [*deepcopy(before.data["aliases"]), {"alias": "Pending term", "language": "en", "alias_type": "translation", "source_kind": "other", "is_verified": False}],
        "reason": "核对馆藏出处后记录", "confirmed": True}
    result = client.post(PATH, payload, format="json", **headers)
    assert result.status_code == 200
    draft = EditorialRevision.objects.get(pk=result.data["revision_id"])
    assert draft.patch["summary"] == "已有草稿内容"
    assert draft.patch["aliases"][-1]["is_verified"] is False
    assert node.aliases.count() == 1  # source untouched until the original publication flow
    assert node.aliases.get().pk == alias.pk
    assert client.post(PATH, payload, format="json", **headers).data == result.data
    assert client.get(f"{PATH}commands/{payload['request_id']}/", **headers).data == result.data
    changed = deepcopy(payload); changed["reason"] = "不同依据"
    assert client.post(PATH, changed, format="json", **headers).status_code == 409
    late = deepcopy(payload); late["request_id"] = str(uuid4())
    stopped = client.post(f"{PATH}commands/{late['request_id']}/", {"action": "cancel_pending"}, format="json", **headers)
    assert stopped.data["state"] == "cancelled"
    assert client.post(PATH, late, format="json", **headers).data["state"] == "cancelled"
    client.force_authenticate(User.objects.create_user(username="different-terms-editor", role="admin"))
    assert client.post(PATH, payload, format="json", **headers).status_code == 403


def test_explicit_unverified_alias_is_not_promoted_and_identity_is_retained():
    actor = User.objects.create_user(username="alias-publisher", role="admin")
    node = KnowledgeNode.objects.create(node_type="concept", slug="unverified-term", canonical_name_zh="示例概念")
    rows = [{"alias": "Pending term", "language": "en", "alias_type": "alias", "source_kind": "other", "is_verified": False}]
    _apply_knowledge_node_relations(node, {"aliases": rows}, actor)
    alias = node.aliases.get()
    assert alias.is_verified is False
    rows[0]["language"] = "en-GB"
    _apply_knowledge_node_relations(node, {"aliases": rows}, actor)
    alias.refresh_from_db()
    assert node.aliases.get().pk == alias.pk
    assert alias.language == "en-GB" and not alias.is_verified
