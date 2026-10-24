"""Deferred public-only login card acceptance; no runtime execution in this phase."""
from uuid import uuid4
import pytest

from accounts.return_context import summary
from catalog.models import Edition
from tests.test_publication_invariants_v305 import published_edition

pytestmark = pytest.mark.django_db


def test_private_paths_never_read_or_reveal_private_content(django_assert_num_queries):
    with django_assert_num_queries(0):
        for path in (f"/account/research/{uuid4()}?question=private", "/admin/users", "//external.invalid", "/reader/../account/notes"):
            result = summary(path)
            assert result["state"] == "unavailable" and not result["title"] and not result["path"]


def test_card_projects_current_public_revision_and_hides_withdrawn_source():
    edition, revision = published_edition("仅正式公开题名")
    Edition.objects.filter(pk=edition.pk).update(is_primary=True)
    edition.work.title = "尚未发布的新题名"
    edition.work.save(update_fields=["title"])
    result = summary(f"/works/{edition.public_slug}?question=not-sent&token=not-sent")
    assert result["title"] == "仅正式公开题名"
    assert "token" not in result["path"] and "question" not in result["path"]
    edition.active_catalog_revision = None
    edition.save(update_fields=["active_catalog_revision"])
    assert summary(f"/works/{edition.public_slug}")["state"] == "unavailable"


def test_expired_cookie_cannot_block_anonymous_card_or_disclose_user(api_client, settings):
    api_client.cookies[settings.JWT_ACCESS_COOKIE_NAME] = "expired-synthetic-token"
    response = api_client.get("/api/auth/return-context/", {"path": "/help/account"})
    assert response.status_code == 200 and response.data["state"] == "page"
    assert "user" not in response.data and "email" not in response.data
    assert "no-store" in response["Cache-Control"]
