"""Deferred website review acceptance; authored only, not executed."""
from uuid import uuid4

import pytest
from catalog.models import EditorialRevision, SiteSetting
from catalog.services import editorial_issues as service
from catalog.site_publication_review import changes
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
BASE = "/api/catalog/admin/site-content/"


def saved_site(actor):
    SiteSetting.objects.create(key="site_config", value={"site_name": "合成原网站"}, public=True)
    payload = service.site_payload()
    payload["config"]["site_name"] = "合成待发布网站"
    return service.save_site(payload, actor)


def test_review_is_read_only_owned_and_versioned(api_client, admin_user, reader_user):
    saved = saved_site(admin_user)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    counts = (EditorialRevision.objects.count(), AuditEvent.objects.count())
    query = {"edit_version": saved["edit_version"]}
    review = api_client.get(BASE + "review/", query)
    assert review.status_code == 200, review.data
    assert "no-store" in review["Cache-Control"]
    assert review.data["can_publish"] is True
    assert any(row["field"] == "config.site_name" for row in review.data["changes"])
    assert api_client.get(BASE + "review/", query).data["fingerprint"] == review.data["fingerprint"]
    assert counts == (EditorialRevision.objects.count(), AuditEvent.objects.count())
    assert service.site_public_payload()["config"]["site_name"] == "合成原网站"
    assert api_client.get(BASE + "review/", {"edit_version": "0"}).status_code == 409
    assert api_client.get(BASE + "review/?edit_version=0&edit_version=0").status_code == 400
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(BASE + "review/", query).status_code == 403
    api_client.force_authenticate(reader_user)
    assert api_client.get(BASE + "review/", query).status_code == 403


def test_fingerprint_publish_replay_and_stale_review(api_client, admin_user):
    saved = saved_site(admin_user)
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    review = api_client.get(BASE + "review/", {"edit_version": saved["edit_version"]}).data
    body = {"edit_version": saved["edit_version"], "confirm": True, "expected_fingerprint": "0" * 64}
    assert api_client.post(BASE + "publish/", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 409
    assert service.site_public_payload()["config"]["site_name"] == "合成原网站"
    body["expected_fingerprint"] = review["fingerprint"]
    request_id = str(uuid4())
    first = api_client.post(BASE + "publish/", body, format="json", HTTP_IDEMPOTENCY_KEY=request_id)
    assert first.status_code == 200, first.data
    replay = api_client.post(BASE + "publish/", body, format="json", HTTP_IDEMPOTENCY_KEY=request_id)
    assert replay.status_code == 200 and replay.data["replayed"] is True
    assert replay.data["receipt"] == first.data["receipt"]
    assert api_client.get(BASE + "review/", {"edit_version": saved["edit_version"]}).status_code == 409
    assert service.site_public_payload()["config"]["site_name"] == "合成待发布网站"


def test_source_disappearance_blocks_legacy_and_review_publication(api_client, admin_user):
    saved = saved_site(admin_user)
    latest = EditorialRevision.objects.get(pk=saved["history"][0]["id"])
    # Represents an originally valid slot whose source is no longer published.
    latest.materialized_preview["home_layout"]["featured"] = [{"id": str(uuid4()),
        "target": {"type": "issue", "id": str(uuid4())}, "title": "", "description": "",
        "cover_rendition_id": None, "visible": True}]
    latest.save(update_fields=["materialized_preview"])
    api_client.force_authenticate(admin_user)
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    review = api_client.get(BASE + "review/", {"edit_version": saved["edit_version"]})
    assert review.status_code == 200 and review.data["can_publish"] is False
    assert any(row["code"] == "source_unavailable" for row in review.data["checks"])
    published = api_client.post(BASE + "publish/", {"edit_version": saved["edit_version"], "confirm": True},
        format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert published.status_code == 400
    assert service.site_public_payload()["config"]["site_name"] == "合成原网站"


def test_same_image_different_delivery_route_is_not_a_content_change():
    identifier = str(uuid4())
    before = {"config": {"home_hero_rendition_id": identifier, "home_hero_image": "/public-image/"}}
    after = {"config": {"home_hero_rendition_id": identifier, "home_hero_image": "/admin-image/"}}
    assert changes(before, after) == []
