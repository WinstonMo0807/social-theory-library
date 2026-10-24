"""Deferred website history/restore acceptance. Not executed during development."""
from copy import deepcopy
from uuid import uuid4

import pytest
from catalog.models import EditorialRevision, SiteSetting
from catalog.services import editorial_issues as ledger
from catalog.site_history import revision_fingerprint
from ingestion.models import AuditEvent
from tests.test_stl4_site_publication_review_20261024 import BASE, saved_site

pytestmark = pytest.mark.django_db


def sign_in(client, actor):
    client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))


def test_history_is_paginated_private_and_excludes_other_targets(api_client, admin_user, reader_user):
    saved = saved_site(admin_user)
    for index in range(24):
        saved["config"]["site_name"] = f"分页合成网站 {index}"
        saved = ledger.save_site(saved, admin_user)
    sign_in(api_client, admin_user)
    counts = (EditorialRevision.objects.count(), AuditEvent.objects.count())
    first = api_client.get(BASE + "history/", {"edit_version": saved["edit_version"]})
    assert first.status_code == 200, first.data
    assert first.data["count"] == 25 and len(first.data["results"]) == 20
    second = api_client.get(BASE + "history/", {"edit_version": saved["edit_version"], "page": 2})
    assert second.status_code == 200 and len(second.data["results"]) == 5
    assert not {row["id"] for row in first.data["results"]} & {row["id"] for row in second.data["results"]}
    assert "no-store" in second["Cache-Control"]
    assert counts == (EditorialRevision.objects.count(), AuditEvent.objects.count())
    foreign = ledger._save_revision("recommendation_issue", uuid4(), {"title": "不属于网站的合成修订"}, admin_user)
    assert api_client.get(BASE + "history/", {"edit_version": saved["edit_version"], "revision": str(foreign.pk)}).status_code == 404
    sign_in(api_client, reader_user)
    assert api_client.get(BASE + "history/", {"edit_version": saved["edit_version"]}).status_code == 403


def test_restore_creates_one_draft_preserves_public_and_can_be_recovered(api_client, admin_user):
    original = saved_site(admin_user)
    first_id = original["history"][0]["id"]
    public = ledger.publish_site(original["edit_version"], admin_user)
    public["config"]["site_name"] = "后来保存的合成网站"
    saved = ledger.save_site(public, admin_user)
    source = EditorialRevision.objects.get(pk=first_id)
    before = deepcopy(source.materialized_preview)
    sign_in(api_client, admin_user)
    body = {"revision_id": first_id, "edit_version": saved["edit_version"],
        "expected_fingerprint": revision_fingerprint(source), "reason": "合成验收恢复", "confirm": True}
    request_id = str(uuid4())
    result = api_client.post(BASE + "restore/", body, format="json", HTTP_IDEMPOTENCY_KEY=request_id)
    assert result.status_code == 200, result.data
    assert result.data["has_unpublished_changes"] is True
    assert result.data["history"][0]["revision"] == 3 and result.data["history"][0]["state"] == "draft"
    assert result.data["receipt"]["action"] == "restore"
    replay = api_client.post(BASE + "restore/", body, format="json", HTTP_IDEMPOTENCY_KEY=request_id)
    assert replay.status_code == 200 and replay.data["replayed"] is True
    assert api_client.get(BASE + f"commands/{request_id}/").data == result.data["receipt"]
    source.refresh_from_db()
    assert source.materialized_preview == before and source.status == "published"
    assert ledger.site_public_payload()["config"]["site_name"] == "合成待发布网站"
    assert EditorialRevision.objects.filter(target_type="site_content").count() == 3
    assert AuditEvent.objects.get(pk=request_id).after["restored_revision_id"] == first_id
    assert api_client.post(BASE + "restore/", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code == 409


def test_stop_fences_restore_and_historical_withdrawn_source_stays_unpublished(api_client, admin_user):
    saved = saved_site(admin_user)
    site = SiteSetting.objects.get(key="site_config")
    historical = deepcopy(saved)
    historical["home_layout"]["featured"] = [{"id": str(uuid4()), "target": {"type": "issue", "id": str(uuid4())},
        "title": "失效来源的合成槽位", "description": "", "cover_rendition_id": None, "visible": True}]
    source = ledger._save_revision("site_content", site.pk, {key: historical[key] for key in ("config", "home_layout", "about_blocks")}, admin_user)
    current = ledger.site_payload()
    current["home_layout"]["featured"] = []
    saved = ledger.save_site(current, admin_user)
    sign_in(api_client, admin_user)
    body = {"revision_id": str(source.pk), "edit_version": saved["edit_version"], "expected_fingerprint": revision_fingerprint(source),
        "confirm": True, "reason": "保留历史关系供修正"}
    cancelled = str(uuid4())
    assert api_client.post(BASE + f"commands/{cancelled}/", {"action": "cancel_pending"}, format="json").status_code == 200
    assert api_client.post(BASE + "restore/", body, format="json", HTTP_IDEMPOTENCY_KEY=cancelled).status_code == 409
    result = api_client.post(BASE + "restore/", body, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4()))
    assert result.status_code == 200, result.data
    assert result.data["home_preview"]["featured"][0]["available"] is False
    review = api_client.get(BASE + "review/", {"edit_version": result.data["edit_version"]})
    assert review.status_code == 200 and review.data["can_publish"] is False
    assert ledger.site_public_payload()["config"]["site_name"] == "合成原网站"
