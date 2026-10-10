"""Media usage follows the same effective public snapshots as anonymous readers."""
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from catalog.models import SiteSetting
from catalog.services import editorial_issues as editorial
from catalog.services.media import build_rendition, ingest_image, media_reference_inventory
from catalog.services.recycle import recycle_object
from .test_media_v305 import picture
from .test_v307_editorial_issues import issue_data

pytestmark = pytest.mark.django_db


def test_issue_media_inventory_and_anonymous_access_follow_effective_revision(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    old, _ = ingest_image(picture(size=(320, 180)), actor=admin_user)
    new, _ = ingest_image(picture(size=(400, 225)), actor=admin_user)
    old_image = build_rendition(old.pk, kind="hero", width=320)
    new_image = build_rendition(new.pk, kind="hero", width=320)
    issue = editorial.create_issue({**issue_data(), "cover_rendition_id": str(old_image.pk)}, admin_user)
    editorial.publish_issue(issue.pk, editorial.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    url = f"/recommendations/{issue.slug}"
    public = lambda media: [r for r in media_reference_inventory(media.pk)["results"] if r["kind"] == "current_public"]
    assert [r["public_url"] for r in public(old)] == [url]
    future = timezone.now() + timedelta(days=2)
    editorial.save_issue(issue.pk, {**editorial.issue_payload(issue), "title": "预约新稿", "cover_rendition_id": str(new_image.pk), "display_from": future.isoformat()}, admin_user)
    assert any(r["kind"] == "draft" for r in media_reference_inventory(new.pk)["results"])
    assert public(old)[0]["label"] == "推荐第一期"
    editorial.publish_issue(issue.pk, editorial.issue_payload(issue)["edit_version"], admin_user)
    assert len(public(old)) == 1 and not public(new)
    old_url = f"/api/catalog/editorial-media/{old_image.pk}/"
    new_url = f"/api/catalog/editorial-media/{new_image.pk}/"
    response = api_client.get(old_url)
    assert response.status_code == 200
    assert api_client.get(new_url).status_code == 404
    with patch("catalog.services.editorial_issues.timezone.now", return_value=future + timedelta(seconds=1)):
        assert not public(old)
        assert public(new)[0]["label"] == "预约新稿"
        assert api_client.get(old_url).status_code == 404
        response = api_client.get(new_url)
        assert response.status_code == 200
    issue.refresh_from_db()
    recycle_object(issue, actor=admin_user, kind="recommendation_issue", name=issue.title)
    assert not public(old) and not public(new)
    assert media_reference_inventory(old.pk)["results"][0]["kind"] == "history"
    assert api_client.get(old_url).status_code == 404


def test_site_media_inventory_uses_published_setting_without_exposing_draft(api_client, admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    media, _ = ingest_image(picture(), actor=admin_user)
    image = build_rendition(media.pk, kind="hero", width=320)
    setting, _ = SiteSetting.objects.update_or_create(key="site_config", defaults={"public": True, "value": {"site_name": "公开书库", "home_hero_rendition_id": str(image.pk)}})
    # A legacy published setting remains an actual use even without a revision row.
    references = media_reference_inventory(media.pk)["results"]
    assert len(references) == 1 and references[0]["kind"] == "current_public"
    assert references[0]["public_url"] == "/"
    original = editorial.site_payload()
    editorial.save_site(original, admin_user)
    editorial.publish_site(editorial.site_payload()["edit_version"], admin_user)
    references = media_reference_inventory(media.pk)["results"]
    assert len(references) == 1 and references[0]["kind"] == "current_public"
    original = editorial.site_payload()
    editorial.save_site({**original, "config": {**original["config"], "home_hero_rendition_id": None, "home_hero_image": ""}}, admin_user)
    assert any(r["kind"] == "current_public" for r in media_reference_inventory(media.pk)["results"])
    editorial.publish_site(editorial.site_payload()["edit_version"], admin_user)
    assert not any(r["kind"] == "current_public" for r in media_reference_inventory(media.pk)["results"])
    assert api_client.get(f"/api/catalog/editorial-media/{image.pk}/").status_code == 404
    setting.refresh_from_db()
    assert not setting.value["home_hero_rendition_id"]
