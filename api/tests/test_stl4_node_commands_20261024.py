"""Deferred acceptance for original KnowledgeNode command recovery; not executed."""
from uuid import uuid4
import pytest

from catalog.models import KnowledgeNode

pytestmark = pytest.mark.django_db
BASE = "/api/catalog/admin/theory-system/nodes/"


def headers(user, key=None):
    return {"HTTP_X_EDITOR_OWNER": str(user.pk), "HTTP_IDEMPOTENCY_KEY": str(key or uuid4())}


def body():
    return {"node_type": "concept", "canonical_name_zh": "恢复验收概念", "slug": f"receipt-{uuid4()}", "status": "draft"}


def test_create_and_lost_response_replay(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    data, key = body(), uuid4()
    response = api_client.post(BASE, data, format="json", **headers(admin_user, key))
    assert response.status_code == 201
    replay = api_client.post(BASE, data, format="json", **headers(admin_user, key))
    assert replay.status_code == 200 and replay.data["id"] == response.data["id"]
    assert replay.data["save_replayed"] and KnowledgeNode.objects.filter(slug=data["slug"]).count() == 1
    receipt = api_client.get(f"{BASE}commands/{key}/", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert receipt.data["node_id"] == response.data["id"] and receipt.data["exists"]


def test_stop_preserves_completed_and_blocks_late_create(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    key, data = uuid4(), body()
    receipt = f"{BASE}commands/{key}/"
    assert api_client.post(receipt, {"action": "cancel_pending"}, format="json", **headers(admin_user, key)).data["state"] == "cancelled"
    assert api_client.post(BASE, data, format="json", **headers(admin_user, key)).status_code == 409
    key = uuid4()
    saved = api_client.post(BASE, data, format="json", **headers(admin_user, key)).data
    stopped = api_client.post(f"{BASE}commands/{key}/", {"action": "cancel_pending"}, format="json", **headers(admin_user, key))
    assert stopped.data["state"] == "applied" and stopped.data["node_id"] == saved["id"]


def test_update_original_version_and_owner(api_client, admin_user, reader_user):
    api_client.force_authenticate(admin_user)
    saved = api_client.post(BASE, body(), format="json", **headers(admin_user)).data
    url = f"{BASE}{saved['id']}/"
    key = uuid4()
    changed = api_client.patch(url, {"summary": "新摘要"}, format="json", HTTP_IF_MATCH=saved["edit_version"], **headers(admin_user, key))
    assert changed.status_code == 200
    replay = api_client.patch(url, {"summary": "新摘要"}, format="json", HTTP_IF_MATCH=saved["edit_version"], **headers(admin_user, key))
    assert replay.status_code == 200 and replay.data["save_replayed"]
    stale = api_client.patch(url, {"summary": "旧页面覆盖"}, format="json", HTTP_IF_MATCH=saved["edit_version"], **headers(admin_user))
    assert stale.status_code == 409
    assert KnowledgeNode.objects.get(pk=saved["id"]).summary == "新摘要"
    api_client.force_authenticate(reader_user)
    assert api_client.get(f"{BASE}commands/{key}/", HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
