"""Deferred command/visibility acceptance; intentionally not executed here."""
from uuid import uuid4
import pytest

from catalog.models import EditorialRevision, Person, ScholarProfile, ScholarRelation
from catalog.services import shared_curation as service

pytestmark = pytest.mark.django_db


def profiles():
    return [ScholarProfile.objects.create(person=Person.objects.create(preferred_name=f"验收人物{i}", authority_status="verified"), slug=f"accept-{uuid4()}", editorial_status="published") for i in range(2)]


def headers(user, key):
    return {"HTTP_X_EDITOR_OWNER": str(user.pk), "HTTP_IDEMPOTENCY_KEY": str(key)}


def test_relation_create_publish_and_replay(api_client, admin_user):
    first, second = profiles()
    api_client.force_authenticate(admin_user)
    key = uuid4()
    payload = {"source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "cooperation", "direction": "undirected", "summary": "验收说明", "source": "验收出处"}
    url = "/api/catalog/admin/scholar-relations/"
    saved = api_client.post(url, payload, format="json", **headers(admin_user, key))
    assert saved.status_code == 201
    replay = api_client.post(url, payload, format="json", **headers(admin_user, key))
    assert replay.status_code == 200 and replay.data["id"] == saved.data["id"]
    assert ScholarRelation.objects.count() == 1
    publish = f'{url}{saved.data["id"]}/publish/'
    publish_key = uuid4()
    body = {"edit_version": saved.data["edit_version"]}
    assert api_client.post(publish, body, format="json", **headers(admin_user, publish_key)).status_code == 200
    assert api_client.post(publish, body, format="json", **headers(admin_user, publish_key)).data["save_replayed"]
    assert EditorialRevision.objects.filter(target_type="scholar_relation").count() == 1


def test_stop_prevents_late_create_and_receipt_is_private(api_client, admin_user, reader_user):
    first, second = profiles()
    api_client.force_authenticate(admin_user)
    key = uuid4()
    receipt = f"/api/catalog/admin/scholar-relations/commands/{key}/"
    assert api_client.post(receipt, {"action": "cancel_pending"}, format="json", **headers(admin_user, key)).data["state"] == "cancelled"
    response = api_client.post("/api/catalog/admin/scholar-relations/", {"source_scholar": str(first.pk), "target_scholar": str(second.pk)}, format="json", **headers(admin_user, key))
    assert response.status_code == 409 and not ScholarRelation.objects.exists()
    api_client.force_authenticate(reader_user)
    assert api_client.get(receipt, HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code in (403, 404)


def test_public_relation_uses_published_person_names(admin_user):
    first, second = profiles()
    EditorialRevision.objects.create(target_type="scholar_profile", target_id=first.pk, revision=1, status="published", materialized_preview={"slug": first.slug, "person": {"preferred_name": "公开姓名"}}, idempotency_key=str(uuid4()))
    Person.objects.filter(pk=first.person_id).update(preferred_name="未发布姓名")
    saved = service.save_relation(None, {"source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "influence", "direction": "directed", "summary": "验收说明", "source": "验收出处"}, admin_user)
    service.publish_relation(saved["id"], saved["edit_version"], admin_user)
    relation = ScholarRelation.objects.get(pk=saved["id"])
    assert service.relation_payload(relation, public=True)["source_name"] == "公开姓名"
    ScholarProfile.objects.filter(pk=second.pk).update(editorial_status="archived")
    assert service.relation_payload(relation, public=True) is None
