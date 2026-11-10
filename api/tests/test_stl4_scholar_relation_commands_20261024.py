"""Relation commands use reviewed knowledge; old receipts remain recoverable."""
from uuid import uuid4
import pytest

from catalog.models import EditorialRevision, Person, ScholarProfile, ScholarRelation, ChangeSet, Assertion, KnowledgePage
from catalog.services import shared_curation as service
from catalog.services.knowledge_public import page_data, publish_page
from catalog.services.academic_projection import scholar_links, scholar_payload
from .test_manual_knowledge_sources import apply_all

pytestmark = pytest.mark.django_db


def profiles():
    return [ScholarProfile.objects.create(person=Person.objects.create(preferred_name=f"验收人物{i}", authority_status="verified"), slug=f"accept-{uuid4()}", editorial_status="published") for i in range(2)]


def headers(user, key):
    return {"HTTP_X_EDITOR_OWNER": str(user.pk), "HTTP_IDEMPOTENCY_KEY": str(key)}


def publish(draft, actor):
    result = apply_all(draft, actor)
    assert not result["blocked"], result
    page = KnowledgePage.objects.get(entity=draft.subject_entity)
    publish_page(page.pk, page_data(page, actor, draft=True)["revision_id"], actor)
    page.refresh_from_db()
    return page


def test_relation_create_publish_and_replay(api_client, admin_user):
    first, second = profiles()
    api_client.force_authenticate(admin_user)
    key = uuid4()
    payload = {"source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "cooperation", "direction": "undirected", "summary": "验收说明", "source": "验收出处"}
    url = "/api/catalog/admin/scholar-relations/"
    saved = api_client.post(url, payload, format="json", **headers(admin_user, key))
    assert saved.status_code == 202, saved.data
    replay = api_client.post(url, payload, format="json", **headers(admin_user, key))
    assert replay.status_code == 202 and replay.data["id"] == saved.data["id"]
    assert not ScholarRelation.objects.exists() and not Assertion.objects.exists()
    assert not list(scholar_links())
    receipt = f"{url}commands/{key}/"
    stopped = api_client.post(receipt, {"action": "cancel_pending"}, format="json", **headers(admin_user, key))
    assert stopped.data["state"] == "draft" and stopped.data["changeset_id"] == saved.data["id"]
    changed = api_client.post(url, {**payload, "summary": "changed"}, format="json", **headers(admin_user, key))
    assert changed.status_code in {400, 409}
    publish(ChangeSet.objects.get(pk=saved.data["id"]), admin_user)
    assert len(list(scholar_links())) == 1
    assert api_client.post(f'{url}{saved.data["id"]}/publish/', {}, format="json", **headers(admin_user, uuid4())).status_code == 409
    assert not EditorialRevision.objects.filter(target_type="scholar_relation").exists()


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
    first.person.preferred_name = "未发布姓名"
    first.person.save(update_fields=["preferred_name"])
    saved = service.save_relation(None, {"request_id": str(uuid4()), "source_scholar": str(first.pk), "target_scholar": str(second.pk), "relation_type": "influence", "direction": "directed", "summary": "验收说明", "source": "验收出处"}, admin_user)
    publish(saved, admin_user)
    relation = list(scholar_links())[0]
    assert scholar_payload(relation)["source_name"] == "公开姓名"
    ScholarProfile.objects.filter(pk=second.pk).update(editorial_status="archived")
    assert not list(scholar_links())
