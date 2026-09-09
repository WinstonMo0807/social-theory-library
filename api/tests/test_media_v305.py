from hashlib import sha256
from io import BytesIO

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import MediaAsset
from catalog.services.media import MediaValidationError, build_rendition, ingest_image, select_work_cover, update_media_metadata


pytestmark = pytest.mark.django_db


def picture(name="image.png", content_type="image/png", size=(800, 1200)):
    output = BytesIO()
    Image.new("RGB", size, "#334455").save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type=content_type)


def test_upload_deduplicates_without_overwriting_source_or_rights(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, created = ingest_image(picture(), actor=admin_user, metadata={"rights": "人工确认来源", "alt_text": "测试封面"})
    assert created
    first_file = row.file.name
    repeated, created = ingest_image(picture(), actor=admin_user, metadata={"rights": "其他来源"})
    assert not created and repeated.pk == row.pk
    assert repeated.file.name == first_file
    assert repeated.rights == "人工确认来源"
    with row.file.open("rb") as handle:
        assert sha256(handle.read()).hexdigest() == row.checksum


@pytest.mark.parametrize("name,mime", [("fake.jpg", "image/jpeg"), ("image.png", "image/svg+xml"), ("unsafe.svg", "image/png")])
def test_file_extension_mime_and_signature_must_agree(settings, tmp_path, admin_user, name, mime):
    settings.MEDIA_ROOT = tmp_path
    with pytest.raises(MediaValidationError):
        ingest_image(picture(name, mime), actor=admin_user)
    assert not MediaAsset.objects.exists()


def test_cover_preserves_ratio_and_renditions_are_idempotent(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(), actor=admin_user)
    rendition = build_rendition(row.pk, width=320, kind="cover")
    assert rendition.width == 320 and rendition.height == 480
    assert build_rendition(row.pk, width=320, kind="cover").pk == rendition.pk
    with rendition.file.open("rb") as handle, Image.open(handle) as image:
        assert image.format == "WEBP"
    assert row.file.name != rendition.file.name


def test_focal_change_preserves_old_rendition_and_original(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(size=(1200, 800)), actor=admin_user)
    original = row.checksum
    old = build_rendition(row.pk, width=320, kind="portrait")
    update_media_metadata(row.pk, actor=admin_user, metadata={"focal_x": 0.1})
    new = build_rendition(row.pk, width=320, kind="portrait")
    assert new.pk != old.pk
    assert new.width == 320 and new.height == 400
    assert row.renditions.filter(pk=old.pk).exists()
    row.refresh_from_db()
    assert row.checksum == original
    with pytest.raises(ValidationError):
        update_media_metadata(row.pk, actor=admin_user, metadata={"focal_x": 2})


def test_metadata_only_change_creates_an_immutable_selection_version(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(), actor=admin_user, metadata={"alt_text": "原说明", "license": "原许可"})
    old = build_rendition(row.pk)
    update_media_metadata(row.pk, actor=admin_user, metadata={"alt_text": "新说明", "license": "新许可"})
    new = build_rendition(row.pk)
    assert new.pk != old.pk and new.group_key != old.group_key
    assert new.checksum == old.checksum  # Same pixels, different editorial statements.
    old.refresh_from_db()
    assert old.metadata_snapshot["license"] == "原许可"
    assert new.metadata_snapshot["license"] == "新许可"
    with pytest.raises(ValidationError, match="不可覆盖"):
        type(old).objects.filter(pk=old.pk).update(metadata_snapshot={"license": "被覆盖"})


def test_original_image_cannot_be_overwritten(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(), actor=admin_user)
    row.checksum = "f" * 64
    with pytest.raises(ValidationError, match="不可覆盖"):
        row.save()


def test_media_and_rendition_bulk_updates_cannot_replace_file_identity(settings, tmp_path, admin_user):
    from catalog.models import MediaRendition

    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(), actor=admin_user)
    rendition = build_rendition(row.pk)
    with pytest.raises(ValidationError, match="不可覆盖"):
        MediaAsset.objects.filter(pk=row.pk).update(media_type="image/jpeg")
    with pytest.raises(ValidationError, match="不可覆盖"):
        MediaRendition.objects.filter(pk=rendition.pk).update(file="another.webp")
    rendition.checksum = "f" * 64
    with pytest.raises(ValidationError, match="不可覆盖"):
        rendition.save()
    rendition.refresh_from_db()
    with rendition.file.open("rb") as handle:
        assert sha256(handle.read()).hexdigest() == rendition.checksum


def test_metadata_rejects_stale_editor_snapshot(settings, tmp_path, admin_user):
    settings.MEDIA_ROOT = tmp_path
    row, _ = ingest_image(picture(), actor=admin_user)
    previous = row.updated_at
    update_media_metadata(row.pk, actor=admin_user, metadata={"credit": "先保存的署名"})
    with pytest.raises(MediaValidationError, match="其他操作"):
        update_media_metadata(row.pk, actor=admin_user, metadata={"credit": "旧页面署名"}, expected_updated_at=previous)
    row.refresh_from_db()
    assert row.credit == "先保存的署名"


def test_private_media_endpoints_do_not_expose_unpublished_uploads(api_client, admin_user, reader_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    assert api_client.get("/api/catalog/admin/media/").status_code in {401, 403}
    api_client.force_authenticate(admin_user)
    uploaded = api_client.post("/api/catalog/admin/media/", {"image": picture(), "alt_text": "可访问名称"}, format="multipart")
    assert uploaded.status_code == 201
    payload = uploaded.data
    assert "file" not in payload
    assert payload["renditions"][0]["width"] <= 320
    preview_url = payload["renditions"][0]["url"]
    preview = api_client.get(preview_url)
    assert preview.status_code == 200
    assert preview["Cache-Control"] == "private, no-store"
    preview.close()
    api_client.force_authenticate(reader_user)
    assert api_client.get(preview_url).status_code == 403


def test_cover_enters_public_snapshot_only_after_human_publication(api_client, admin_user, settings, tmp_path):
    from catalog.models import KnowledgePublicationEvent, ProjectionState
    from catalog.services.knowledge_publication import process_knowledge_event
    from ingestion.services.publication import publish_edition
    from .test_catalog_contracts_v305 import _manual_ready

    settings.MEDIA_ROOT = tmp_path
    edition = _manual_ready(admin_user)
    image, _ = ingest_image(picture(), actor=admin_user, metadata={"alt_text": "已确认的封面说明", "credit": "测试图片"})
    selection = select_work_cover(edition.pk, image.pk, actor=admin_user)
    assert selection["editorial_revision_id"] is None
    assert api_client.get(f"/api/catalog/works/{edition.work_id}/cover/").status_code == 404
    api_client.force_authenticate(admin_user)
    draft_preview = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/")
    assert draft_preview.status_code == 200
    assert draft_preview.data["work"]["cover"].startswith("/api/catalog/admin/media/renditions/")
    assert all(row["url"].startswith("/api/catalog/admin/media/") for row in draft_preview.data["work"]["cover_media"]["renditions"])
    api_client.force_authenticate(None)
    publish_edition(edition, actor=admin_user, confirm_warnings=True)
    event = KnowledgePublicationEvent.objects.get(catalog_revision__edition=edition)
    ProjectionState.objects.filter(object_type="edition", object_id=edition.pk).update(status="current", projected_revision=event.domain_event.canonical_revision)
    process_knowledge_event(event.pk)
    edition.refresh_from_db()
    public = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert public.status_code == 200
    media = public.data["cover_media"]
    assert media["alt_text"] == "已确认的封面说明"
    assert len(media["renditions"]) == 3
    for rendition in media["renditions"]:
        response = api_client.get(rendition["url"])
        assert response.status_code == 200
        assert response["Content-Type"] == "image/webp"
        response.close()
    from catalog.models import MediaRendition
    from django.db.models.deletion import ProtectedError
    with pytest.raises(ProtectedError):
        MediaRendition.objects.get(pk=media["renditions"][0]["id"]).delete()
    frozen = edition.active_catalog_revision.snapshot["work"]["cover_media"]
    update_media_metadata(image.pk, actor=admin_user, metadata={"alt_text": "未发布的新说明"})
    select_work_cover(edition.pk, image.pk, actor=admin_user)
    edition.refresh_from_db()
    assert edition.active_catalog_revision.snapshot["work"]["cover_media"] == frozen
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").data["cover_media"]["alt_text"] == "已确认的封面说明"
    api_client.force_authenticate(admin_user)
    preview = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/")
    assert preview.status_code == 200
    preview_media = preview.data["work"]["cover_media"]
    assert preview_media["alt_text"] == "未发布的新说明"
    assert preview_media["primary_rendition_id"] != frozen["primary_rendition_id"]
    expected_url = f"/api/catalog/admin/media/renditions/{preview_media['primary_rendition_id']}/file/"
    assert preview.data["work"]["cover"] == expected_url
    private_image = api_client.get(expected_url)
    assert private_image.status_code == 200
    private_image.close()
    from catalog.services.publication_commands import prepare_revision

    prepared = prepare_revision(edition)
    cover_diff = next(row for row in prepared["changes"] if row["field"] == "cover")
    assert cover_diff["change"] == "changed"
    assert "未发布的新说明" in cover_diff["after_display"]
    assert "已确认的封面说明" in cover_diff["before_display"]
    # Editing the source after selection cannot silently alter the reviewed
    # publication. Reselecting the media is an explicit new editorial action.
    update_media_metadata(image.pk, actor=admin_user, metadata={"alt_text": "选择之后另一个管理员编辑的说明"})
    assert prepare_revision(edition)["fingerprint"] == prepared["fingerprint"]
    edition.work.refresh_from_db()
    assert str(edition.work.cover_rendition_id) == frozen["primary_rendition_id"]
    api_client.force_authenticate(None)
    assert api_client.get(expected_url).status_code in {401, 403}
    assert api_client.get(f"/api/catalog/works/{edition.work_id}/cover/?rendition={preview_media['primary_rendition_id']}").status_code == 404
    api_client.force_authenticate(admin_user)
    published = api_client.post(
        f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
        {"confirm_warnings": True, "prepared_fingerprint": prepared["fingerprint"]}, format="json",
    )
    assert published.status_code == 200, published.data
    replacement = KnowledgePublicationEvent.objects.filter(catalog_revision__edition=edition).exclude(pk=event.pk).get()
    assert replacement.catalog_revision.snapshot["work"]["cover_media"]["alt_text"] == "未发布的新说明"
    ProjectionState.objects.filter(object_type=replacement.object_type, object_id=replacement.object_id).update(status="current", projected_revision=replacement.domain_event.canonical_revision)
    completed = process_knowledge_event(replacement.pk)
    assert completed.status == KnowledgePublicationEvent.Status.COMPLETED, completed.last_error_message
    api_client.force_authenticate(None)
    after_publication = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert after_publication.data["cover_media"]["alt_text"] == "未发布的新说明"


def test_small_cover_has_unique_srcset_widths_and_keeps_primary(settings, tmp_path, admin_user):
    from catalog.services.media import cover_media_snapshot
    from .test_catalog_contracts_v305 import _manual_ready

    settings.MEDIA_ROOT = tmp_path
    edition = _manual_ready(admin_user)
    image, _ = ingest_image(picture(size=(100, 150)), actor=admin_user)
    select_work_cover(edition.pk, image.pk, actor=admin_user)
    edition.work.refresh_from_db()
    snapshot = cover_media_snapshot(edition.work)
    assert len(snapshot["renditions"]) == 1
    assert snapshot["renditions"][0]["id"] == snapshot["primary_rendition_id"]
