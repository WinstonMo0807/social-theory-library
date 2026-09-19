from hashlib import sha256
from uuid import uuid4
from unittest.mock import patch

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from catalog.models import Asset, Work, Edition, CoverCandidate, EditorialRevision, CatalogFieldDecision, Page
from catalog.services.covers import generate_cover_candidates
from ingestion.models import AuditEvent, UploadBatch, UploadItem, ProcessingAttempt
from ingestion.services.pipeline import run_pipeline, prepare_early_cover_candidates
from .test_reader_cover_semantic import build_cover_pdf
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


@pytest.fixture
def cover_source(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.COVER_AUTO_SELECT_THRESHOLD = 0
    work = Work.objects.create(title="The Social Test Book", document_type="book", language="en")
    edition = Edition.objects.create(work=work)
    pdf = build_cover_pdf()
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid", page_count=3, sha256=sha256(pdf).hexdigest(), file=SimpleUploadedFile("cover.pdf", pdf, content_type="application/pdf"))
    Page.objects.create(asset=asset, index=1, text="Preserve this page")
    return work, edition, asset


def call(api_client, edition, action, *, snapshot=None, key=None, **extra):
    url = f"/api/catalog/admin/editions/{edition.pk}/cover/"
    snapshot = snapshot or api_client.get(url).data
    body = {name: snapshot[name] or "" for name in ("fingerprint", "asset_id", "source_checksum")}
    body.update(action=action, request_key=key or str(uuid4()), **extra)
    return api_client.post(url, body, format="multipart" if action == "upload" else "json")


def test_cover_candidates_visible_without_click_and_never_auto_adopt(api_client, admin_user, cover_source):
    work, edition, asset = cover_source
    batch = UploadBatch.objects.create(created_by=admin_user)
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="cover.pdf")
    assert prepare_early_cover_candidates(item, asset)
    api_client.force_authenticate(admin_user)
    state = api_client.get(f"/api/catalog/admin/editions/{edition.pk}/cover/")
    assert state.status_code == 200 and state.data["state"] == "ready"
    assert state.data["results"] and state.data["page_count"] == 3
    work.refresh_from_db()
    assert not work.cover
    assert ProcessingAttempt.objects.get(upload_item=item, stage="cover_detection").output_summary["before_fulltext"]


@pytest.mark.django_db(transaction=True)
def test_cover_manual_page_select_upload_default_and_retry(api_client, admin_user, cover_source):
    work, edition, asset = cover_source
    api_client.force_authenticate(admin_user)
    original_pdf = asset.file.read(); asset.file.close()
    page_ids = list(Page.objects.filter(asset=asset).values_list("id", flat=True))
    preview = call(api_client, edition, "preview_page", page_index=3)
    assert preview.status_code == 200, preview.data
    assert preview.data["preview_candidate"]["page_index"] == 3
    work.refresh_from_db(); assert not work.cover
    key = str(uuid4())
    selected = call(api_client, edition, "select", snapshot=preview.data, key=key, candidate_id=preview.data["preview_candidate"]["id"])
    assert selected.status_code == 200 and not selected.data["is_default"], selected.data
    assert selected.data["image_url"].startswith("http://testserver/api/catalog/")
    image = api_client.get(selected.data["image_url"])
    assert image.status_code == 200 and image["Content-Type"] == "image/jpeg"
    image.close()
    retry = call(api_client, edition, "select", snapshot=preview.data, key=key, candidate_id=preview.data["preview_candidate"]["id"])
    assert retry.status_code == 200 and retry.data["replayed"]
    assert AuditEvent.objects.filter(action="catalog.cover_command", request_id=key).count() == 1
    work.refresh_from_db(); selected_name = work.cover.name
    upload = call(api_client, edition, "upload", image=picture())
    assert upload.status_code == 200 and not upload.data["is_default"], upload.data
    work.refresh_from_db(); assert work.cover_rendition_id
    uploaded_name = work.cover.name
    cleared = call(api_client, edition, "default")
    assert cleared.status_code == 200 and cleared.data["is_default"], cleared.data
    generate_cover_candidates(asset, force=True)
    work.refresh_from_db(); assert not work.cover
    assert work.cover.storage.exists(selected_name) and work.cover.storage.exists(uploaded_name)
    assert list(Page.objects.filter(asset=asset).values_list("id", flat=True)) == page_ids
    with asset.file.open("rb") as source:
        assert source.read() == original_pdf


@pytest.mark.parametrize("problem", ["page", "foreign", "stale", "old_asset"])
def test_cover_rejects_bad_page_stale_context_and_wrong_pdf(api_client, admin_user, cover_source, problem):
    work, edition, asset = cover_source
    api_client.force_authenticate(admin_user)
    snapshot = api_client.get(f"/api/catalog/admin/editions/{edition.pk}/cover/").data
    if problem == "foreign": snapshot["asset_id"] = str(uuid4())
    if problem == "stale": snapshot["fingerprint"] = "old"
    if problem == "old_asset": asset.is_current = False; asset.save()
    result = call(api_client, edition, "preview_page", snapshot=snapshot, page_index=99 if problem == "page" else 1)
    assert result.status_code == 409, result.data
    work.refresh_from_db(); assert not work.cover


def test_article_may_use_default_or_upload_without_pdf(api_client, admin_user, cover_source):
    work, edition, asset = cover_source
    work.document_type = "journal_article"; work.save()
    asset.is_current = False; asset.save()
    api_client.force_authenticate(admin_user)
    response = call(api_client, edition, "default")
    assert response.status_code == 200 and response.data["is_default"]
    assert CatalogFieldDecision.objects.get(edition=edition, field_name="cover").status == "not_applicable"
    response = call(api_client, edition, "upload", image=picture())
    assert response.status_code == 200 and not response.data["is_default"], response.data


def test_published_cover_changes_remain_in_draft(api_client, admin_user, cover_source):
    work, edition, asset = cover_source
    api_client.force_authenticate(admin_user)
    assert call(api_client, edition, "upload", image=picture()).status_code == 200
    work.refresh_from_db(); before = work.cover.name
    edition.state = "published"; edition.save()
    preview = call(api_client, edition, "preview_page", page_index=2)
    result = call(api_client, edition, "select", candidate_id=preview.data["preview_candidate"]["id"])
    assert result.status_code == 200, result.data
    work.refresh_from_db(); assert work.cover.name == before
    draft = EditorialRevision.objects.get(target_type="work", target_id=work.pk, status="draft")
    assert draft.materialized_preview["cover"] != before and draft.materialized_preview["cover_rendition"] is None
    assert result.data["has_unpublished_cover"]


def test_reader_cannot_read_private_cover_or_change_it(api_client, reader_user, cover_source):
    _, edition, _ = cover_source
    api_client.force_authenticate(reader_user)
    url = f"/api/catalog/admin/editions/{edition.pk}/cover/"
    assert api_client.get(url).status_code == 403
    assert api_client.post(url, {"action": "default"}, format="json").status_code == 403


def test_upload_prepares_candidates_before_ai_or_whole_pdf_extraction(admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_NORMALIZED_ROOT = settings.MEDIA_ROOT / "normalized"
    settings.COVER_AUTO_SELECT_THRESHOLD = 0
    batch = UploadBatch.objects.create(created_by=admin_user, ai_suggestions_enabled=True, external_enrichment_enabled=False, ocr_strategy="skip")
    item = UploadItem.objects.create(batch=batch, source_filename="The Social Test Book.pdf", file=SimpleUploadedFile("book.pdf", build_cover_pdf(), content_type="application/pdf"))
    class StopAfterPreview(RuntimeError): pass
    def ai(*args, **kwargs):
        item.refresh_from_db()
        assert CoverCandidate.objects.filter(asset__edition=item.edition).exists()
        return [], {"status": "controlled_test"}
    def extraction(*args, **kwargs):
        item.refresh_from_db()
        assert CoverCandidate.objects.filter(asset__edition=item.edition).exists()
        raise StopAfterPreview()
    with patch("ingestion.services.pipeline.metadata_candidates_from_ai", side_effect=ai), patch("ingestion.services.pipeline.extract_native_pages", side_effect=extraction):
        with pytest.raises(StopAfterPreview): run_pipeline(str(item.pk))
    assert ProcessingAttempt.objects.get(upload_item=item, stage="cover_detection").status == "completed"


def test_optional_cover_failure_is_recorded_not_raised(admin_user, cover_source):
    _, edition, asset = cover_source
    item = UploadItem.objects.create(batch=UploadBatch.objects.create(created_by=admin_user), edition=edition, source_filename="cover.pdf")
    with patch("ingestion.services.pipeline.generate_cover_candidates", side_effect=ValueError("controlled renderer error")):
        assert prepare_early_cover_candidates(item, asset) is False
    attempt = ProcessingAttempt.objects.get(upload_item=item, stage="cover_detection")
    assert attempt.status == "failed" and attempt.error_message == "controlled renderer error"


def test_background_ranking_keeps_a_selection_made_while_rendering(cover_source):
    from catalog.services import covers
    _, _, asset = cover_source
    chosen = generate_cover_candidates(asset, auto_select=False)[0]
    original_metrics = covers._page_metrics
    def metrics(*args, **kwargs):
        # Simulate a human selection arriving after the initial candidate read.
        CoverCandidate.objects.filter(pk=chosen.pk).update(selected=True)
        return original_metrics(*args, **kwargs)
    with patch.object(covers, "_page_metrics", side_effect=metrics):
        generate_cover_candidates(asset, force=True, auto_select=False)
    chosen.refresh_from_db()
    assert chosen.selected
