from copy import deepcopy
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from catalog.models import EditorialRevision
from catalog.services.publication_commands import prepare_revision, rollback_revision
from ingestion.services.publication import publish_edition
from .publication_fixtures import acknowledge_catalog_projections
from .test_catalog_contracts_v305 import _manual_ready


pytestmark = pytest.mark.django_db


def image_upload(name="image.png", color="navy"):
    output = BytesIO()
    Image.new("RGB", (800, 600), color).save(output, format="PNG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/png")


def published_with_legacy_image(actor, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    edition = _manual_ready(actor)
    work = edition.work
    original = image_upload("original.png")
    original_bytes = original.read()
    original.seek(0)
    work.recommendation_image.save("original.png", original)
    publish_edition(edition, actor=actor, confirm_warnings=True)
    acknowledge_catalog_projections(edition)
    return work, edition, original_bytes


@pytest.mark.parametrize("action", ["replace", "remove"])
def test_legacy_image_endpoint_stages_changes_and_preserves_published_file(api_client, admin_user, settings, tmp_path, action):
    work, edition, original_bytes = published_with_legacy_image(admin_user, settings, tmp_path)
    original_name = work.recommendation_image.name
    public_snapshot = deepcopy(edition.active_catalog_revision.snapshot)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/works/{work.pk}/recommendation-image/"
    response = (
        api_client.post(url, {"image": image_upload("replacement.png", "red")}, format="multipart")
        if action == "replace" else api_client.delete(url)
    )
    assert response.status_code == 200, response.data
    assert work.recommendation_image.storage.exists(original_name)
    work.refresh_from_db()
    assert work.recommendation_image.name == original_name
    assert response.data["canonical_write_deferred"] is True
    draft = EditorialRevision.objects.get(target_type="work", target_id=work.pk, status="draft")
    assert draft.patch["recommendation_image"] != original_name
    if action == "remove":
        assert draft.patch["recommendation_image"] == ""
    edition.active_catalog_revision.refresh_from_db()
    assert edition.active_catalog_revision.snapshot == public_snapshot
    api_client.force_authenticate(None)
    public = api_client.get(f"/api/catalog/works/{work.pk}/recommendation-image/")
    assert public.status_code == 200
    assert b"".join(public.streaming_content) == original_bytes
    public.close()


def publish_reviewed_image(api_client, edition):
    prepared = prepare_revision(edition)
    response = api_client.post(
        f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
        {"confirm_warnings": True, "prepared_fingerprint": prepared["fingerprint"]}, format="json",
    )
    assert response.status_code == 200, response.data
    return acknowledge_catalog_projections(edition)


def test_recommendation_media_publish_clear_and_rollback_keep_exact_files(api_client, admin_user, settings, tmp_path):
    from django.db.models.deletion import ProtectedError
    from catalog.models import CatalogPublicationMedia, MediaAsset, MediaRendition

    work, edition, _original_bytes = published_with_legacy_image(admin_user, settings, tmp_path)
    original_name = work.recommendation_image.name
    api_client.force_authenticate(admin_user)
    endpoint = f"/api/catalog/admin/works/{work.pk}/recommendation-image/"
    selected = api_client.post(endpoint, {"image": image_upload("selected.png", "red")}, format="multipart")
    assert selected.status_code == 200
    draft = EditorialRevision.objects.get(pk=selected.data["editorial_revision_id"])
    primary = MediaRendition.objects.get(pk=draft.patch["recommendation_rendition"])
    assert primary.kind == "hero"
    assert primary.width == 640 and primary.height == 360
    assert primary.media.file.name != primary.file.name
    preview = api_client.get(f"/api/catalog/admin/page-preview/editions/{edition.pk}/")
    assert preview.status_code == 200
    assert preview.data["work"]["recommendation_media"]["primary_rendition_id"] == str(primary.pk)
    metadata = api_client.get(endpoint + "metadata/")
    assert metadata.status_code == 200 and metadata.data["canonical_write_deferred"]
    assert metadata["Cache-Control"] == "private, no-store"
    diff = next(row for row in prepare_revision(edition)["changes"] if row["field"] == "recommendation_image")
    assert diff["change"] == "changed" and "推荐图例" in diff["after_display"]
    event = publish_reviewed_image(api_client, edition)
    assert not event.deliveries.filter(consumer__in=["semantic", "fulltext", "viewpoint"]).exists()
    published_id = event.catalog_revision_id
    work.refresh_from_db()
    assert work.recommendation_rendition_id == primary.pk
    assert not work.cover_rendition_id and not work.cover
    assert CatalogPublicationMedia.objects.filter(catalog_revision_id=published_id).count() == 3
    api_client.force_authenticate(None)
    public = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    media = public.data["recommendation_media"]
    assert len(media["renditions"]) == 3
    public_file = api_client.get(public.data["recommendation_image"])
    assert public_file.status_code == 200 and public_file["Content-Type"] == "image/webp"
    published_bytes = b"".join(public_file.streaming_content)
    public_file.close()
    assert api_client.get(f"/api/catalog/works/{work.pk}/recommendation-image/?rendition={primary.media_id}").status_code == 404
    api_client.force_authenticate(admin_user)
    removed = api_client.delete(endpoint)
    assert removed.status_code == 200 and removed.data["canonical_write_deferred"]
    assert work.recommendation_image.storage.exists(original_name)
    publish_reviewed_image(api_client, edition)
    work.refresh_from_db()
    assert not work.recommendation_image and work.recommendation_rendition_id is None
    with pytest.raises(ProtectedError):
        primary.delete()
    assert MediaAsset.objects.filter(pk=primary.media_id).exists()
    restored = rollback_revision(edition, published_id, actor=admin_user, idempotency_key="rec-image-rollback", reason="恢复先前图例")
    acknowledge_catalog_projections(edition)
    assert restored.catalog_revision_id == edition.active_catalog_revision_id
    work.refresh_from_db()
    assert work.recommendation_rendition_id is None  # Recovery does not rewrite later canonical edits.
    api_client.force_authenticate(None)
    restored_file = api_client.get(f"/api/catalog/works/{work.pk}/recommendation-image/")
    assert restored_file.status_code == 200
    assert b"".join(restored_file.streaming_content) == published_bytes
    restored_file.close()


def test_recommendation_and_cover_selection_are_independent(api_client, admin_user, settings, tmp_path):
    from catalog.services.media import ingest_image, select_work_cover, select_work_image

    settings.MEDIA_ROOT = tmp_path
    edition = _manual_ready(admin_user)
    cover, _ = ingest_image(image_upload("cover.png", "navy"), actor=admin_user)
    recommendation, _ = ingest_image(image_upload("recommendation.png", "red"), actor=admin_user)
    select_work_cover(edition.pk, cover.pk, actor=admin_user)
    select_work_image(edition.pk, recommendation.pk, slot="recommendation", actor=admin_user)
    edition.work.refresh_from_db()
    cover_id = edition.work.cover_rendition_id
    assert edition.work.recommendation_rendition_id != cover_id
    select_work_image(edition.pk, None, slot="recommendation", actor=admin_user)
    edition.work.refresh_from_db()
    assert edition.work.cover_rendition_id == cover_id and edition.work.recommendation_rendition_id is None


def test_private_image_metadata_and_mutations_reject_readers(api_client, admin_user, reader_user, settings, tmp_path):
    work, _edition, _ = published_with_legacy_image(admin_user, settings, tmp_path)
    endpoint = f"/api/catalog/admin/works/{work.pk}/recommendation-image/"
    for user in (None, reader_user):
        api_client.force_authenticate(user)
        assert api_client.get(endpoint + "metadata/").status_code in {401, 403}
        assert api_client.get(endpoint).status_code in {401, 403}
        assert api_client.post(endpoint, {"image": image_upload()}, format="multipart").status_code in {401, 403}
        assert api_client.delete(endpoint).status_code in {401, 403}


def test_pdf_generated_recommendation_is_media_and_cannot_override_manual_choice(admin_user, settings, tmp_path):
    from catalog.models import Asset, CatalogFieldDecision, Edition, Work
    from catalog.services.covers import generate_recommendation_image
    from catalog.services.media import ingest_image, select_work_image
    from .test_reader_cover_semantic import build_cover_pdf

    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="报告的图例", document_type="report", language="en")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256="e" * 64, file=SimpleUploadedFile("report.pdf", build_cover_pdf()), page_count=3)
    generate_recommendation_image(asset)
    work.refresh_from_db()
    assert work.recommendation_rendition.media.source_type == "pdf"
    assert work.recommendation_rendition.media.source_label.startswith("PDF 第 ")
    assert CatalogFieldDecision.objects.get(edition=edition, field_name="recommendation_image").status == "suggested"
    manual, _ = ingest_image(image_upload("manual.png", "green"), actor=admin_user)
    select_work_image(edition.pk, manual.pk, slot="recommendation", actor=admin_user)
    work.refresh_from_db()
    selected_id = work.recommendation_rendition_id
    generate_recommendation_image(asset, force=True)
    work.refresh_from_db()
    assert work.recommendation_rendition_id == selected_id


@pytest.mark.parametrize("target", ["work", "edition"])
def test_image_selection_changes_only_request_public_projection(target):
    from catalog.services.dependency_engine import ProjectionType, projection_types_for

    assert set(projection_types_for(target, ["recommendation_image", "recommendation_rendition"])) == {ProjectionType.PUBLIC}


def test_legacy_recommendation_actions_keep_the_requested_edition(api_client, admin_user, settings, tmp_path):
    from unittest.mock import patch
    from catalog.models import Asset, Edition, Work

    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(title="多版本图例", document_type="report")
    first = Edition.objects.create(work=work, is_primary=True)
    selected = Edition.objects.create(work=work, is_primary=False)
    Asset.objects.create(edition=first, kind="normalized", status="ready", sha256="3" * 64)
    selected_asset = Asset.objects.create(edition=selected, kind="normalized", status="ready", sha256="4" * 64)
    api_client.force_authenticate(admin_user)
    endpoint = f"/api/catalog/admin/works/{work.pk}/recommendation-image/"
    metadata = api_client.get(endpoint + "metadata/", {"edition_id": str(selected.pk)})
    assert metadata.status_code == 200
    assert f"edition={selected.pk}" in metadata.data["media_library_url"]
    with patch("catalog.views.generate_recommendation_image") as render:
        response = api_client.post(endpoint + f"?edition_id={selected.pk}", {"action": "regenerate"}, format="json")
    assert response.status_code == 200
    assert render.call_args.args[0].pk == selected_asset.pk
    assert render.call_args.kwargs["expected_work_id"] == work.pk
    other = Work.objects.create(title="无关作品")
    unrelated = Edition.objects.create(work=other)
    assert api_client.delete(endpoint + f"?edition_id={unrelated.pk}").status_code == 404
    assert api_client.get(endpoint + "metadata/?edition_id=not-a-uuid").status_code == 400


def test_manual_pdf_image_can_follow_the_saved_draft_document_type(api_client, admin_user, settings, tmp_path):
    from hashlib import sha256
    from catalog.models import Asset
    from catalog.services.editorial_revision import save_workflow_editorial_revision
    from .test_reader_cover_semantic import build_cover_pdf

    work, edition, _ = published_with_legacy_image(admin_user, settings, tmp_path)
    previous_file = work.recommendation_image.name
    content = build_cover_pdf()
    Asset.objects.create(edition=edition, kind="normalized", status="ready", sha256=sha256(content).hexdigest(), file=SimpleUploadedFile("draft-report.pdf", content), page_count=3)
    save_workflow_editorial_revision(work_id=work.pk, section_patch={"document_type": "report"}, actor=admin_user)
    api_client.force_authenticate(admin_user)
    result = api_client.post(f"/api/catalog/admin/works/{work.pk}/recommendation-image/?edition_id={edition.pk}", {"action": "regenerate"}, format="json")
    assert result.status_code == 200, result.data
    assert result.data["document_type"] == "report" and result.data["canonical_write_deferred"]
    work.refresh_from_db()
    assert work.document_type == "book" and work.recommendation_image.name == previous_file
    draft = EditorialRevision.objects.get(pk=result.data["editorial_revision_id"])
    assert draft.patch["recommendation_rendition"]
