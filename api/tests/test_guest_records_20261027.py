from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import Asset, Edition, EditorialRevision, Page, RecommendationIssue, Work
from ingestion.models import AuditEvent
from reading import privacy
from reading.models import ReadingHistory, ReadingProgress
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db
URL = "/api/reading/guest-records/import/"


@pytest.fixture
def guest_reading():
    work = Work.objects.create(title="访客记录合成样例", document_type="book")
    edition = Edition.objects.create(work=work, state="published", public_slug=f"guest-{work.pk}")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
                                access_status="public", file="test/guest.pdf", sha256="a" * 64, page_count=10)
    Page.objects.create(asset=asset, index=2, text="合成第二页")
    revision = activate_catalog_revision(edition, reader_asset=asset)
    return asset, {"id": str(uuid4()), "kind": "reading", "at": timezone.now().isoformat(),
                   "asset_id": str(asset.pk), "revision_id": str(revision.document_revision_id), "pdf_page": 2}


def send(client, user, records):
    client.force_authenticate(user)
    return client.post(URL, {"owner_id": str(user.pk), "records": records}, format="json")


def test_guest_import_does_not_replace_progress_or_repeat_erased_history(api_client, reader_user, guest_reading):
    asset, record = guest_reading
    progress = ReadingProgress.objects.create(user=reader_user, asset=asset, current_page=8, progress_ratio=.8)
    response = send(api_client, reader_user, [record])
    assert response.status_code == 200 and response.data["results"][0]["state"] == "imported"
    progress.refresh_from_db()
    assert progress.current_page == 8
    assert ReadingHistory.objects.get(user=reader_user).page_index == 2
    ReadingHistory.objects.filter(user=reader_user).delete()
    response = send(api_client, reader_user, [record])
    assert response.data["results"][0]["state"] == "already_imported"
    assert not ReadingHistory.objects.filter(user=reader_user).exists()


def test_guest_import_rejects_changed_owner_and_changed_revision(api_client, reader_user, guest_reading):
    _, record = guest_reading
    api_client.force_authenticate(reader_user)
    response = api_client.post(URL, {"owner_id": str(reader_user.pk + 1), "records": [record]}, format="json")
    assert response.status_code == 403
    record["revision_id"] = str(uuid4())
    response = send(api_client, reader_user, [record])
    assert response.status_code == 200 and response.data["results"][0]["state"] == "unavailable"
    assert not ReadingHistory.objects.exists() and not AuditEvent.objects.filter(action="reader_guest_import").exists()


def test_guest_import_honors_account_retention(api_client, reader_user, guest_reading):
    _, record = guest_reading
    privacy.update_preferences(reader_user, {"expected_revision": privacy.preferences(reader_user)["revision"],
                                             "retention": {"reading_history": False}})
    response = send(api_client, reader_user, [record])
    assert response.status_code == 200 and response.data["results"][0]["state"] == "disabled"
    assert not ReadingHistory.objects.exists()


def test_guest_receipt_cannot_be_reused_for_different_content(api_client, reader_user, guest_reading):
    _, record = guest_reading
    assert send(api_client, reader_user, [record]).status_code == 200
    response = send(api_client, reader_user, [{**record, "pdf_page": 3}])
    assert response.status_code == 409
    assert ReadingHistory.objects.count() == 1


def test_imported_article_uses_public_revision_and_disappears_when_unpublished(api_client, reader_user):
    issue = RecommendationIssue.objects.create(title="未发布草稿标题", slug="guest-article")
    revision = EditorialRevision.objects.create(target_type="recommendation_issue", target_id=issue.pk,
        revision=1, status="published", idempotency_key=str(uuid4()), materialized_preview={"title": "正式文章标题"})
    issue.active_revision, issue.display_from = revision, timezone.now()
    issue.save()
    row = {"id": str(uuid4()), "kind": "article", "at": timezone.now().isoformat(),
           "issue_id": str(issue.pk), "revision_id": str(revision.pk)}
    assert send(api_client, reader_user, [row]).data["results"][0]["state"] == "imported"
    response = api_client.get("/api/reading/history/")
    assert response.status_code == 200
    entry = response.data["results"][0]
    assert entry["title"] == "正式文章标题" and entry["asset"] is None
    assert entry["article"]["href"] == "/recommendations/guest-article"
    revision.status = "superseded"
    revision.save(update_fields=["status"])
    entry = api_client.get("/api/reading/history/").data["results"][0]
    assert entry["article"] is None and entry["title"] == "来源当前不可用"
    row["id"] = str(uuid4())
    assert send(api_client, reader_user, [row]).data["results"][0]["state"] == "unavailable"
