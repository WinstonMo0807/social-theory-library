"""Deferred website announcement/public-copy acceptance; not run in this phase."""
from uuid import uuid4

import pytest
from rest_framework.exceptions import ValidationError
from catalog.services import editorial_issues as ledger
from catalog.site_publication_review import review
from tests.test_stl4_site_publication_review_20261024 import saved_site

pytestmark = pytest.mark.django_db


def announcement(*, visible=True):
    return {"key": f"announcement-{uuid4()}", "block_type": "notice", "title": "合成公告标题",
        "body": "仅在隔离验收环境使用的公告正文", "icon": "", "action_label": "使用帮助", "action_href": "/help",
        "sort_order": 100, "visible": visible, "configuration": {"published_date": "2026-10-24"}}


def test_announcement_stays_draft_until_publish_and_can_be_hidden(api_client, admin_user):
    saved = saved_site(admin_user)
    item = announcement()
    saved["about_blocks"].append(item)
    saved = ledger.save_site(saved, admin_user)
    public = api_client.get("/api/catalog/about-blocks/")
    assert public.status_code == 200 and public.data["results"] == []
    published = ledger.publish_site(saved["edit_version"], admin_user)
    public = api_client.get("/api/catalog/about-blocks/")
    assert public.data["configured"] is False  # An announcement must not hide the default about page.
    assert public.data["results"][0]["key"] == item["key"]
    assert public.data["results"][0]["configuration"]["published_date"] == "2026-10-24"
    published["about_blocks"][0]["visible"] = False
    hidden = ledger.save_site(published, admin_user)
    assert len(api_client.get("/api/catalog/about-blocks/").data["results"]) == 1
    ledger.publish_site(hidden["edit_version"], admin_user)
    assert api_client.get("/api/catalog/about-blocks/").data["results"] == []
    assert ledger.site_payload()["about_blocks"][0]["body"] == item["body"]


def test_incomplete_visible_announcement_blocks_publication_without_blocking_draft(admin_user):
    saved = saved_site(admin_user)
    item = announcement()
    item["body"] = ""
    item["configuration"] = {}
    saved["about_blocks"].append(item)
    saved = ledger.save_site(saved, admin_user)
    result = review(saved["edit_version"])
    assert result["can_publish"] is False
    assert any(row["code"] == "announcement_incomplete" and row["section"] == item["key"] for row in result["checks"])
    with pytest.raises(ValidationError):
        ledger.publish_site(saved["edit_version"], admin_user)
    saved["about_blocks"][0]["visible"] = False
    hidden = ledger.save_site(saved, admin_user)
    assert review(hidden["edit_version"])["can_publish"] is True


@pytest.mark.parametrize("configuration", [{"published_date": "not-a-date"}, {"private_notes": "must-not-be-published"}, []])
def test_invalid_announcement_metadata_is_rejected(admin_user, configuration):
    saved = saved_site(admin_user)
    item = announcement()
    item["configuration"] = configuration
    saved["about_blocks"].append(item)
    with pytest.raises(ValidationError):
        ledger.save_site(saved, admin_user)


def test_all_allowed_public_blocks_fit_public_response(api_client, admin_user):
    saved = saved_site(admin_user)
    saved["about_blocks"] = [dict(announcement(), sort_order=index) for index in range(100)]
    saved = ledger.save_site(saved, admin_user)
    ledger.publish_site(saved["edit_version"], admin_user)
    public = api_client.get("/api/catalog/about-blocks/")
    assert public.status_code == 200 and public.data["count"] == 100
    assert len(public.data["results"]) == 100 and public.data["next"] is None
