"""Only newly missing issue captions and genuine upload filenames."""
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.exceptions import ValidationError

from catalog.models import EditorialRevision, RecommendationIssue
from catalog.services import editorial_issues as service
from catalog.services.media import build_rendition, ingest_image, update_media_metadata
from ingestion.models import AuditEvent
from tests.test_v307_editorial_issues import issue_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def cover(admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    buffer = BytesIO()
    Image.new("RGB", (32, 24), (44, 55, 66)).save(buffer, "PNG")
    raw = buffer.getvalue()
    media, created = ingest_image(SimpleUploadedFile("城市配图.png", raw, content_type="image/png"), actor=admin_user,
                                  metadata={"alt_text": "原图保存的替代文字"})
    assert created
    rendition = build_rendition(media.pk, width=320, kind="hero")
    return media, rendition, raw


def test_recorded_original_filename_is_private_and_dedup_keeps_first_name(api_client, admin_user, cover):
    media, rendition, raw = cover
    api_client.force_authenticate(admin_user)
    detail = api_client.get(f"/api/catalog/admin/media/{media.pk}/")
    assert detail.status_code == 200 and detail.data["original_filename"] == "城市配图.png"
    collection = api_client.get("/api/catalog/admin/media/collection/")
    assert collection.status_code == 200 and collection.data["results"][0]["original_filename"] == "城市配图.png"
    same, created = ingest_image(SimpleUploadedFile("另一个文件名.png", raw, content_type="image/png"), actor=admin_user)
    assert not created and same.pk == media.pk
    issue = service.create_issue({**issue_data(), "cover_rendition_id": str(rendition.pk), "cover_original_filename": "伪造原名.png"}, admin_user)
    draft = service.issue_payload(issue)
    assert draft["cover_original_filename"] == "城市配图.png"
    issue = service.publish_issue(issue.pk, draft["edit_version"], admin_user)
    public = service.issue_payload(issue, public=True)
    assert "cover_original_filename" not in public
    assert "original_filename" not in EditorialRevision.objects.get(pk=issue.active_revision_id).materialized_preview
    assert "cover_original_filename" not in EditorialRevision.objects.get(pk=issue.active_revision_id).materialized_preview


def test_cover_caption_follows_issue_snapshot_and_exact_rendition_alt(admin_user, cover):
    media, rendition, _ = cover
    issue = service.create_issue({**issue_data(), "cover_rendition_id": str(rendition.pk), "cover_caption": "编辑核对后的配图说明"}, admin_user)
    first = service.issue_payload(issue)
    assert first["cover_caption"] == "编辑核对后的配图说明"
    assert first["cover_alt_text"] == "原图保存的替代文字"
    issue = service.publish_issue(issue.pk, first["edit_version"], admin_user)
    update_media_metadata(media.pk, actor=admin_user, metadata={"alt_text": "后来修改的媒体文字"})
    service.save_issue(issue.pk, {**service.issue_payload(issue), "cover_caption": "尚未发布的新说明"}, admin_user)
    assert service.issue_payload(issue)["cover_caption"] == "尚未发布的新说明"
    published = service.issue_payload(issue, public=True)
    assert published["cover_caption"] == "编辑核对后的配图说明"
    assert published["cover_alt_text"] == "原图保存的替代文字"
    assert "cover_original_filename" not in published


def test_legacy_filename_and_caption_stay_unknown_without_rewriting_history(admin_user, cover):
    media, rendition, _ = cover
    event = AuditEvent.objects.get(action="media.upload", object_id=str(media.pk))
    legacy_upload = dict(event.after)
    legacy_upload.pop("original_filename", None)
    AuditEvent.objects.filter(pk=event.pk).update(after=legacy_upload)
    issue = service.create_issue({**issue_data(), "items": [], "cover_rendition_id": str(rendition.pk)}, admin_user)
    revision = EditorialRevision.objects.filter(target_id=issue.pk).latest("revision")
    legacy_snapshot = dict(revision.materialized_preview)
    legacy_snapshot.pop("cover_caption", None)
    legacy_snapshot.pop("cover_alt_text", None)
    EditorialRevision.objects.filter(pk=revision.pk).update(materialized_preview=legacy_snapshot)
    payload = service.issue_payload(issue)
    assert payload["cover_caption"] == "" and payload["cover_original_filename"] == ""
    assert payload["cover_alt_text"] == rendition.metadata_snapshot["alt_text"]
    revision.refresh_from_db()
    assert revision.materialized_preview == legacy_snapshot
    event.refresh_from_db()
    assert event.after == legacy_upload


@pytest.mark.parametrize("caption", ["x"*501, 123, None])
def test_cover_caption_rejects_invalid_text_without_committing(admin_user, caption):
    before = RecommendationIssue.objects.count(), EditorialRevision.objects.count()
    with pytest.raises(ValidationError):
        service.create_issue({**issue_data(), "items": [], "cover_caption": caption}, admin_user)
    assert (RecommendationIssue.objects.count(), EditorialRevision.objects.count()) == before
