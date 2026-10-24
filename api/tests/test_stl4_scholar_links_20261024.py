"""Deferred acceptance definitions. Do not run during the current development phase."""
from uuid import uuid4
import pytest

from catalog.models import KnowledgeNode, Person, PersonNodeRelation, PersonTopicRelation, ScholarProfile, Topic
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


def setup_link(kind):
    person = Person.objects.create(preferred_name="验收人物", authority_status="verified")
    scholar = ScholarProfile.objects.create(person=person, slug=f"link-{uuid4()}", editorial_status="published")
    target = KnowledgeNode.objects.create(node_type="concept", canonical_name_zh="验收概念", slug=f"node-{uuid4()}", status="published") if kind == "node" else Topic.objects.create(name="验收主题", slug=f"topic-{uuid4()}", editorial_status="published")
    return scholar, target, f"/api/catalog/admin/scholars/{scholar.pk}/links/{kind}/"


def body(target):
    return {"action": "save", "target_id": str(target.pk), "relation_label": "验收关系说明", "source": "验收书目第12页", "featured": False, "sort_order": 0}


def send(client, user, url, payload, key=None):
    return client.post(url, payload, format="json", HTTP_X_EDITOR_OWNER=str(user.pk), HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))


@pytest.mark.parametrize("kind", ["node", "topic"])
def test_original_identity_explicit_confirmation_and_audit(api_client, admin_user, kind):
    scholar, target, url = setup_link(kind)
    api_client.force_authenticate(admin_user)
    key, data = uuid4(), body(target)
    created = send(api_client, admin_user, url, data, key)
    assert created.status_code == 200 and not created.data["confirmed"]
    assert send(api_client, admin_user, url, data, key).data["id"] == created.data["id"]
    model = PersonNodeRelation if kind == "node" else PersonTopicRelation
    assert model.objects.filter(person=scholar.person).count() == 1
    saved = created.data
    confirmed = send(api_client, admin_user, url, {**data, "action": "confirm", "id": saved["id"], "edit_version": saved["edit_version"]})
    assert confirmed.status_code == 200 and confirmed.data["confirmed"]
    changed = {**data, "id": saved["id"], "edit_version": confirmed.data["edit_version"], "source": "新的验收出处"}
    assert send(api_client, admin_user, url, changed).status_code == 400
    assert model.objects.get(pk=saved["id"]).source == data["source"]
    stale = send(api_client, admin_user, url, {**changed, "action": "confirm", "edit_version": saved["edit_version"]})
    assert stale.status_code == 409
    withdrawn = send(api_client, admin_user, url, {"action": "withdraw", "id": saved["id"], "edit_version": confirmed.data["edit_version"]})
    assert withdrawn.status_code == 200 and not withdrawn.data["confirmed"]
    assert model.objects.filter(pk=saved["id"]).exists()
    assert send(api_client, admin_user, url, data).status_code == 409
    assert AuditEvent.objects.filter(action="scholar_link_review", object_id=saved["id"]).count() == 3


@pytest.mark.parametrize("kind", ["node", "topic"])
def test_stop_and_reader_boundary(api_client, admin_user, reader_user, kind):
    _, target, url = setup_link(kind)
    api_client.force_authenticate(admin_user)
    key = uuid4()
    receipt = f"/api/catalog/admin/scholar-links/{kind}/commands/{key}/"
    assert send(api_client, admin_user, receipt, {"action": "cancel_pending"}, key).data["state"] == "cancelled"
    assert send(api_client, admin_user, url, body(target), key).status_code == 409
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    assert api_client.get(receipt, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403


@pytest.mark.parametrize("kind", ["node", "topic"])
def test_cross_scholar_identity_and_unpublished_target(api_client, admin_user, kind):
    _, target, url = setup_link(kind)
    _, _, other = setup_link(kind)
    api_client.force_authenticate(admin_user)
    data = body(target)
    saved = send(api_client, admin_user, url, data).data
    assert send(api_client, admin_user, other, {**data, "id": saved["id"], "edit_version": saved["edit_version"]}).status_code == 404
    target.__class__.objects.filter(pk=target.pk).update(**{"status" if kind == "node" else "editorial_status": "draft"})
    assert send(api_client, admin_user, url, {**data, "action": "confirm", "id": saved["id"], "edit_version": saved["edit_version"]}).status_code == 400
    assert api_client.get(other, {"id": saved["id"]}, HTTP_X_EDITOR_OWNER=str(admin_user.pk)).data["results"] == []
