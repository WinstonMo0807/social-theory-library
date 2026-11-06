from uuid import uuid4

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts import avatars
from catalog.services import editorial_issues as issues
from catalog.services.public_editorial import directory_card
from catalog.site_layout import source_card
from .test_stl4_account_avatar_20261024 import photo

pytestmark = pytest.mark.django_db


def change_avatar(user, action="set"):
    return avatars.command(user, {"action": action, "confirmed": True,
        "request_id": uuid4(), "expected_version": avatars.state(user)["expected_version"]},
        SimpleUploadedFile("portrait.png", photo(), content_type="image/png") if action == "set" else None)


def draft(user, **values):
    return issues.create_issue({"title": "隔离测试策展", "public_byline": "策展署名",
        "body_blocks": [{"type": "paragraph", "text": "隔离测试内容"}], "items": [], **values}, user)


def publish(row, user):
    issues.publish_issue(row.pk, issues.edit_version("recommendation_issue", row.pk), user)
    row.refresh_from_db()


def test_curator_uses_live_avatar_across_home_directory_detail_without_republication(admin_user):
    change_avatar(admin_user)
    row = draft(admin_user)
    url = f"/api/catalog/recommendation-issues/{row.slug}/curator-avatar/"
    client = APIClient()
    assert client.get(url).status_code == 404
    publish(row, admin_user)
    detail = issues.issue_payload(row, public=True)
    card = directory_card(issues.published_issues().get(pk=row.pk))
    home = source_card({"type": "issue", "id": str(row.pk)})
    assert detail["curator"] == card["curator"] == home["curator"]
    assert "curator_account_id" not in detail["article_metadata"]
    old_url = detail["curator"]["portrait_url"]
    result = client.get(old_url)
    assert result.status_code == 200 and result["Content-Type"] == "image/png"
    assert "no-store" in result["Cache-Control"]
    revision = row.active_revision_id
    change_avatar(admin_user)
    assert issues.issue_payload(row, public=True)["curator"]["portrait_url"] != old_url
    assert client.get(old_url).content == avatars.image_data(admin_user)
    row.refresh_from_db()
    assert row.active_revision_id == revision
    change_avatar(admin_user, "remove")
    assert client.get(old_url).status_code == 404
    assert issues.issue_payload(row, public=True)["curator"]["portrait_url"] == ""


def test_reader_avatar_cannot_be_linked_by_another_account_or_read_as_draft(admin_user, reader_user):
    change_avatar(reader_user)
    with pytest.raises(ValidationError):
        draft(admin_user, article_metadata={"curator_account_id": reader_user.pk})
    row = draft(admin_user)
    url = f"/api/catalog/admin/recommendation-issues/{row.pk}/curator-avatar/"
    client = APIClient()
    assert client.get(url).status_code in (401, 403)
    client.force_authenticate(reader_user)
    assert client.get(url).status_code == 403
    assert client.get(f"/api/auth/users/{admin_user.pk}/avatar/", HTTP_X_READER_OWNER=str(reader_user.pk)).status_code == 403


def test_draft_unlink_does_not_change_published_byline_until_published(admin_user):
    change_avatar(admin_user)
    row = draft(admin_user)
    publish(row, admin_user)
    url = issues.issue_payload(row, public=True)["curator"]["portrait_url"]
    issues.save_issue(row.pk, {"edit_version": issues.edit_version("recommendation_issue", row.pk),
        "article_metadata": {"curator_account_id": None}}, admin_user)
    assert APIClient().get(url).status_code == 200
    publish(row, admin_user)
    assert APIClient().get(url).status_code == 404


def test_no_byline_never_exposes_avatar_and_private_preview_is_available(admin_user):
    change_avatar(admin_user)
    row = draft(admin_user)
    client = APIClient(); client.force_authenticate(admin_user)
    assert client.get(f"/api/catalog/admin/recommendation-issues/{row.pk}/curator-avatar/").status_code == 200
    anonymous = draft(admin_user, public_byline="")
    publish(anonymous, admin_user)
    assert issues.issue_payload(anonymous, public=True)["curator"]["portrait_url"] == ""
    assert APIClient().get(f"/api/catalog/recommendation-issues/{anonymous.slug}/curator-avatar/").status_code == 404
