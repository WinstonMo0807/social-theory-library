"""Synthetic contracts for final-atlas 95–98; authored for unified acceptance."""
from hashlib import sha256
from io import BytesIO
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from catalog.models import (Asset, CatalogingSession, CatalogPublicationRevision, DocumentRevision,
                            Edition, EvidenceSnippet, Work)
from catalog.services.edition_file_intake import (convert_tiff, format_capabilities, generate_reader, prepare_reader_input,
                                                submit_file, workspace_file)
from catalog.services.edition_file_workspace import (adopt_file, create_edition, prepare_adoption, prepare_public_file, state, update_rights)
from catalog.services.edition_files import EditionFileError
from ingestion.models import UploadItem
from ingestion.services.pipeline import _copy_asset, _create_or_update_catalog, ProcessingCancelled

pytestmark = pytest.mark.django_db
PDF = b"%PDF-1.4\n% isolated synthetic signature fixture\n%%EOF"


@pytest.fixture(autouse=True)
def isolated_files(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.STORAGES = {**settings.STORAGES, "intake": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": str(tmp_path / "intake")}}}
    settings.DOCX_PREVIEW_ENABLED = False
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    with patch("catalog.services.edition_file_intake.schedule_upload_item") as schedule:
        yield schedule


def edition():
    return Edition.objects.create(work=Work.objects.create(title="合成文件测试", document_type="book"), publication_mode="bibliographic")


def submit(row, user, *, content=PDF, filename="source.pdf", action="supplement", generate_reader=True, key=None, **kwargs):
    return submit_file(edition_id=row.pk, actor=user, uploaded=SimpleUploadedFile(filename, content),
        action=action, request_key=key or uuid4(), expected_updated_at=row.updated_at.isoformat(),
        generate_reader=generate_reader, **kwargs)


def published(user):
    row = edition()
    old = Asset.objects.create(edition=row, kind="normalized", status="ready", validation_status="valid",
        sha256=sha256(PDF + b"old").hexdigest(), mime_type="application/pdf", original_filename="old.pdf", version=1)
    old.file.save("old.pdf", ContentFile(PDF), save=True)
    revision = CatalogPublicationRevision.objects.create(edition=row, revision=1, status="active", metadata_ready=True,
        reader_asset=old, snapshot={"work": {"title": "已正式公开的题名"}, "edition": {"id": str(row.pk)}},
        content_fingerprint="synthetic", activated_at=timezone.now())
    row.state, row.active_catalog_revision = "published", revision
    row.save(update_fields=["state", "active_catalog_revision", "updated_at"])
    return row, old, revision


def reader_candidate(row, content=PDF):
    asset = Asset.objects.create(edition=row, kind="normalized", status="ready", validation_status="valid", is_current=False,
        sha256=sha256(content).hexdigest(), mime_type="application/pdf", original_filename="candidate.pdf", version=2)
    asset.file.save("candidate.pdf", ContentFile(content), save=True)
    DocumentRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256, text_checksum="synthetic", is_active=True)
    return asset


def test_many_supplemental_originals_never_replace_public_reader(admin_user):
    row, old, revision = published(admin_user)
    first, _ = submit(row, admin_user, generate_reader=False)
    second, _ = submit(row, admin_user, content=PDF+b"second", generate_reader=False)
    row.refresh_from_db(); old.refresh_from_db()
    assert row.active_catalog_revision_id == revision.pk and old.is_current
    assert first.replacement_of_asset_id is None and second.replacement_of_asset_id is None
    assert first.asset.version == 2 and second.asset.version == 3
    assert not first.asset.is_current and not second.asset.is_current
    assert first.asset.file.read() == PDF


def test_upload_receipt_replays_before_stale_context_and_scope_checks(admin_user, reader_user, isolated_files):
    row = edition()
    first, created = submit(row, admin_user)
    assert created
    Edition.objects.filter(pk=row.pk).update(updated_at=timezone.now())
    replay, created = submit(row, admin_user, key=first.pk)
    assert not created and replay.pk == first.pk and isolated_files.call_count == 1
    with pytest.raises(EditionFileError):
        submit(row, reader_user, key=first.pk)
    with pytest.raises(EditionFileError):
        submit(row, admin_user, key=first.pk, generate_reader=False)


def test_no_automatic_work_rebinding_or_metadata_overwrite(admin_user):
    row = edition()
    item, _ = submit(row, admin_user)
    _create_or_update_catalog(item, {"title": "不应采纳", "language": "en"}, [], "")
    row.work.refresh_from_db()
    assert row.work.title == "合成文件测试" and Work.objects.count() == 1
    other = Edition.objects.create(work=row.work, is_primary=False)
    with pytest.raises(EditionFileError, match="相同原件"):
        submit(other, admin_user)


def test_stale_reader_and_context_block_upload_without_asset_creation(admin_user):
    row, old, _ = published(admin_user)
    with pytest.raises(EditionFileError, match="阅读文件已变化"):
        submit(row, admin_user, action="replace", expected_reader_asset_id=uuid4())
    Edition.objects.filter(pk=row.pk).update(updated_at=timezone.now())
    with pytest.raises(EditionFileError, match="出版版本已变化"):
        submit(row, admin_user)
    assert Asset.objects.count() == 1 and not UploadItem.objects.exists()


def test_one_active_conversion_per_edition_and_explicit_replace(admin_user):
    row, old, _ = published(admin_user)
    first, _ = submit(row, admin_user, action="replace", expected_reader_asset_id=old.pk)
    assert workspace_file(first)["expected_reader_asset_id"] == str(old.pk)
    assert first.replacement_of_asset_id is None
    with pytest.raises(EditionFileError, match="正在处理"):
        submit(row, admin_user, content=PDF+b"next")


@pytest.mark.parametrize("filename,content", [("wrong.exe", b"MZ"), ("bad.pdf", b"other"), ("bad.docx", b"other"), ("bad.tiff", b"other")])
def test_bad_uploads_do_not_create_objects(admin_user, filename, content):
    with pytest.raises(EditionFileError):
        submit(edition(), admin_user, filename=filename, content=content)
    assert not UploadItem.objects.exists() and not Asset.objects.exists()


def test_size_and_configuration_are_real_capabilities(settings, admin_user):
    settings.MAX_UPLOAD_BYTES = 20
    with pytest.raises(EditionFileError, match="上限"):
        submit(edition(), admin_user)
    assert next(row for row in format_capabilities() if row["extension"] == "docx")["can_generate_reader"] is False


def test_docx_can_be_retained_with_conversion_off(admin_user):
    row = edition()
    blob = b"PK\x03\x04synthetic-retention-only"
    item, _ = submit(row, admin_user, filename="original.docx", content=blob, generate_reader=False)
    assert item.status == "ready" and item.asset.file.read() == blob and item.asset.page_count == 0
    assert workspace_file(item)["generate_reader"] is False


def test_docx_conversion_preserves_original_and_uses_distinct_pdf(settings, admin_user):
    settings.DOCX_PREVIEW_ENABLED = True
    row = edition()
    blob = b"PK\x03\x04synthetic-conversion-transport"
    item, _ = submit(row, admin_user, filename="original.docx", content=blob)
    with patch("reading.document_preview.convert", return_value=(PDF, {"page_count": 1, "output_hash": sha256(PDF).hexdigest()})):
        prepare_reader_input(item)
    original = _copy_asset(item, row, "original", "original.docx")
    normalized = _copy_asset(item, row, "normalized", "reader.pdf")
    assert original.file.read() == blob and normalized.file.read() == PDF
    assert original.sha256 != normalized.sha256 and original.version == normalized.version
    assert original.mime_type.endswith("document") and normalized.mime_type == "application/pdf"
    assert normalized.original_filename == "original.pdf" and not normalized.is_current


def test_late_conversion_cannot_overwrite_retry_generation(settings, admin_user):
    settings.DOCX_PREVIEW_ENABLED = True
    item, _ = submit(edition(), admin_user, filename="original.docx", content=b"PK\x03\x04synthetic")
    def converted(*_args):
        UploadItem.objects.filter(pk=item.pk).update(dispatch_task_id="new-worker")
        return PDF, {}
    with patch("reading.document_preview.convert", side_effect=converted), pytest.raises(ProcessingCancelled):
        prepare_reader_input(item)
    item.refresh_from_db()
    assert not workspace_file(item)["converted"]


def test_tiff_real_multiframe_conversion_is_bounded():
    from PIL import Image
    import fitz
    source = BytesIO()
    with Image.new("RGB", (10, 20), "white") as first, Image.new("RGB", (12, 22), "black") as second:
        first.save(source, format="TIFF", save_all=True, append_images=[second])
    pdf = convert_tiff(source.getvalue())
    with fitz.open(stream=pdf, filetype="pdf") as document:
        assert document.page_count == 2


def test_new_edition_reuses_work_and_manual_identity(admin_user):
    row = edition()
    data = {"request_key": uuid4(), "expected_work_updated_at": row.work.updated_at.isoformat(), "version_label": "修订版", "publication_year": 2026, "publisher": "合成出版者"}
    created = create_edition(row.work_id, admin_user, data)
    repeated = create_edition(row.work_id, admin_user, data)
    assert not repeated["created"] and repeated["edition_id"] == created["edition_id"]
    assert Work.objects.count() == 1 and Edition.objects.count() == 2
    assert CatalogingSession.objects.get(edition_id=created["edition_id"]).source_type == "manual"
    assert not Edition.objects.get(pk=created["edition_id"]).is_primary


def test_adoption_preview_reports_loss_of_fulltext_and_cross_edition_rejected(admin_user):
    row, _old, _revision = published(admin_user)
    candidate = reader_candidate(row)
    preview = prepare_adoption(row.pk, candidate.pk, admin_user)
    assert preview["can_adopt"] and any("全文尚未就绪" in text for text in preview["impact"])
    other = edition()
    with pytest.raises(Asset.DoesNotExist):
        prepare_adoption(other.pk, candidate.pk, admin_user)


def test_adoption_stale_fingerprint_cannot_mutate_public_reader(admin_user):
    row, old, _revision = published(admin_user)
    candidate = reader_candidate(row)
    preview = prepare_adoption(row.pk, candidate.pk, admin_user)
    Asset.objects.filter(pk=candidate.pk).update(updated_at=timezone.now())
    with pytest.raises(EditionFileError, match="预览后变化"):
        adopt_file(row.pk, candidate.pk, admin_user, preview)
    row.refresh_from_db()
    assert row.active_catalog_revision.reader_asset_id == old.pk


def test_file_selection_preserves_published_metadata_and_old_references(admin_user):
    row, old, revision = published(admin_user)
    candidate = reader_candidate(row)
    preview = prepare_adoption(row.pk, candidate.pk, admin_user)
    with patch("catalog.services.knowledge_publication.dispatch_knowledge_event"):
        receipt = adopt_file(row.pk, candidate.pk, admin_user, preview)
        replay = adopt_file(row.pk, candidate.pk, admin_user, preview)
    assert receipt["event_id"] == replay["event_id"]
    latest = row.catalog_revisions.order_by("-revision").first()
    assert latest.snapshot["work"]["title"] == revision.snapshot["work"]["title"]
    assert latest.reader_asset_id == candidate.pk
    row.refresh_from_db(); old.refresh_from_db()
    assert row.active_catalog_revision_id == revision.pk and old.is_current


def test_pending_publication_requires_resolution_before_file_selection(admin_user):
    row, _old, _revision = published(admin_user)
    candidate = reader_candidate(row)
    CatalogPublicationRevision.objects.create(edition=row, revision=2, status="preparing", metadata_ready=True,
        reader_asset=candidate, snapshot={}, content_fingerprint="pending")
    preview = prepare_adoption(row.pk, candidate.pk, admin_user)
    assert not preview["can_adopt"] and any("待完成" in item for item in preview["blocking"])


def test_state_paginates_files_and_keeps_current_reader_separate(admin_user):
    row, old, _ = published(admin_user)
    for index in range(22):
        Asset.objects.create(edition=row, kind="original", version=index+2, sha256=sha256(str(index).encode()).hexdigest(), is_current=False)
    result = state(row.work_id, admin_user, page=1)
    assert result["files"]["count"] == 23 and len(result["files"]["results"]) == 20
    assert result["current_reader_file"]["id"] == str(old.pk)
    assert result["impact"]["summary"]["reader_annotations"] == 0


def test_http_permissions_and_historical_file_download(api_client, admin_user, reader_user):
    row, old, _ = published(admin_user)
    old.is_current = False
    old.save(update_fields=["is_current"])
    url = f"/api/catalog/admin/editions/{row.pk}/files/{old.pk}/content/"
    api_client.force_authenticate(reader_user)
    assert api_client.get(url).status_code == 403
    api_client.force_authenticate(admin_user)
    response = api_client.get(url + "?download=1")
    assert response.status_code == 200 and "no-store" in response["Cache-Control"]
    assert b"".join(response.streaming_content) == PDF


def test_non_pdf_original_is_attachment_only(api_client, admin_user):
    row = edition()
    item, _ = submit(row, admin_user, filename="source.docx", content=b"PK\x03\x04fixture", generate_reader=False)
    url = f"/api/catalog/admin/editions/{row.pk}/files/{item.asset_id}/content/"
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).status_code == 400
    response = api_client.get(url + "?download=1")
    assert response.status_code == 200 and "source.docx" in response["Content-Disposition"]
    assert response["Content-Type"].endswith("document")


def test_impact_exports_actual_locations_without_quote_or_personal_text(api_client, admin_user):
    row, old, _ = published(admin_user)
    EvidenceSnippet.objects.create(work=row.work, file=old, page_number=4, quote="不应导出的证据正文", printed_page_label="iv")
    api_client.force_authenticate(admin_user)
    response = api_client.get(f"/api/catalog/admin/editions/{row.pk}/files/impact.csv")
    assert response.status_code == 200 and "iv" in response.content.decode("utf-8")
    assert "不应导出" not in response.content.decode("utf-8")


def test_original_head_preserves_mime_and_private_headers(api_client, admin_user):
    row = edition()
    item, _ = submit(row, admin_user, filename="source.docx", content=b"PK\x03\x04head", generate_reader=False)
    api_client.force_authenticate(admin_user)
    response = api_client.head(f"/api/catalog/admin/editions/{row.pk}/files/{item.asset_id}/content/?download=1")
    assert response.status_code == 200 and response["Content-Type"].endswith("document")
    assert "no-store" in response["Cache-Control"] and not response.content


def test_existing_original_generation_keeps_identity_and_replays(admin_user, isolated_files):
    row = edition()
    item, _ = submit(row, admin_user, generate_reader=False)
    data = {"request_key": uuid4(), "expected_asset_updated_at": item.asset.updated_at.isoformat()}
    generated = generate_reader(row.pk, item.asset_id, admin_user, data)
    repeated = generate_reader(row.pk, item.asset_id, admin_user, data)
    assert generated.pk == repeated.pk == item.pk and Asset.objects.count() == 1
    assert workspace_file(generated)["generate_reader"] and isolated_files.call_count == 1
    assert generated.workflow_state == UploadItem.WorkflowState.UPLOADED


def test_upload_request_lookup_is_owner_and_edition_bound(api_client, admin_user, superadmin_user):
    row = edition()
    item, _ = submit(row, admin_user, generate_reader=False)
    url = f"/api/catalog/admin/editions/{row.pk}/files/requests/{item.pk}/"
    api_client.force_authenticate(superadmin_user)
    assert api_client.get(url).status_code == 404
    api_client.force_authenticate(admin_user)
    assert api_client.get(url).data["item_id"] == str(item.pk)
    assert api_client.get(url.replace(str(row.pk), str(uuid4()))).status_code == 404


def test_rights_edit_is_revision_bound_and_cannot_change_access(api_client, admin_user):
    row = edition()
    item, _ = submit(row, admin_user, generate_reader=False)
    asset = item.asset
    original_access = asset.access_status
    data = {"request_key": uuid4(), "expected_asset_updated_at": asset.updated_at.isoformat(), "rights_note": "原件来源与使用说明"}
    result = update_rights(row.pk, asset.pk, admin_user, data)
    assert update_rights(row.pk, asset.pk, admin_user, data) == result
    asset.refresh_from_db()
    assert asset.access_status == original_access and asset.rights_note == data["rights_note"]
    with pytest.raises(EditionFileError):
        update_rights(row.pk, asset.pk, admin_user, {**data, "request_key": uuid4(), "rights_note": "旧修订不得覆盖"})
    api_client.force_authenticate(admin_user)
    response = api_client.patch(f"/api/catalog/admin/editions/{row.pk}/files/{asset.pk}/rights/",
        {**data, "request_key": str(uuid4()), "expected_asset_updated_at": asset.updated_at.isoformat(), "access_status": "public"}, format="json")
    assert response.status_code == 400
    payload = state(row.work_id, admin_user)
    assert payload["edition"]["rights"]["source_asset_id"] == str(asset.pk)
    assert payload["edition"]["rights"]["can_edit"] and payload["edition"]["rights"]["updated_at"] == asset.updated_at


def test_draft_selection_does_not_reactivate_normalized_source_or_publish(admin_user):
    row = edition()
    old = reader_candidate(row, PDF+b"ancestor")
    old.is_current = True; old.save(update_fields=["is_current"])
    candidate = reader_candidate(row, PDF+b"new")
    candidate.source_asset = old; candidate.save(update_fields=["source_asset"])
    result = adopt_file(row.pk, candidate.pk, admin_user, prepare_adoption(row.pk, candidate.pk, admin_user))
    old.refresh_from_db(); candidate.refresh_from_db(); row.refresh_from_db()
    assert result["effective"] and not result["public_effective"] and result["publication_required"]
    assert candidate.is_current and not old.is_current and row.state == "draft"
    assert not row.catalog_revisions.exists()


def test_staged_pipeline_skips_catalog_and_all_automatic_services(admin_user, settings):
    import fitz
    from contextlib import ExitStack
    from ingestion.services.pipeline import run_pipeline
    with fitz.open() as doc:
        doc.new_page().insert_text((30, 30), "Isolated synthetic reader copy")
        blob = doc.tobytes()
    row = edition()
    work_stamp, edition_stamp = row.work.updated_at, row.updated_at
    item, _ = submit(row, admin_user, content=blob)
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    prohibited = ["_create_or_update_catalog", "extract_local_candidates", "run_front_matter_intelligence",
                  "prepare_early_cover_candidates", "generate_theory_review_tasks", "queue_ocr_job",
                  "queue_semantic_job", "queue_page_label_job", "_ensure_cloud_copy"]
    with ExitStack() as stack:
        for name in prohibited:
            stack.enter_context(patch(f"ingestion.services.pipeline.{name}", side_effect=AssertionError(name)))
        intelligence = stack.enter_context(patch("ingestion.services.pipeline.best_effort_native_extraction", return_value={"status": "ready"}))
        result = run_pipeline(str(item.pk))
    row.refresh_from_db(); row.work.refresh_from_db()
    assert result.status == "ready" and row.work.updated_at == work_stamp and row.updated_at == edition_stamp
    assert row.assets.filter(kind="normalized", is_current=False, page_count=1).exists()
    assert intelligence.call_args.kwargs["schedule_claims"] is False and intelligence.call_args.kwargs["schedule_outline"] is False
    assert not row.assets.filter(cloud_objects__isnull=False).exists()


def test_staged_retry_after_adoption_never_rewrites_historical_pages(admin_user):
    from ingestion.services.pipeline import _run_staged_file_pipeline
    from pathlib import Path
    row = edition()
    item, _ = submit(row, admin_user)
    normalized = _copy_asset(item, row, "normalized", "reader.pdf")
    UploadItem.objects.filter(pk=item.pk).update(workflow_state="preflight")
    with patch("catalog.services.document_intelligence.document_asset_is_published", return_value=True), \
            patch("ingestion.services.pipeline.extract_native_pages", side_effect=AssertionError("published parse")):
        assert _run_staged_file_pipeline(item, Path("unused.pdf")).status == "ready"
    normalized.refresh_from_db()
    assert not normalized.pages.exists()


def test_cloud_preparation_requires_publish_permission_confirm_and_cas(api_client, admin_user, reader_user, settings):
    from distribution.models import CloudProvider
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    row = edition(); asset = reader_candidate(row)
    CloudProvider.objects.create(name="Synthetic destination", bucket="isolated", enabled=True, is_default=True)
    url = f"/api/catalog/admin/editions/{row.pk}/files/{asset.pk}/prepare-public/"
    data = {"request_key": str(uuid4()), "expected_asset_updated_at": asset.updated_at.isoformat(), "confirm": True}
    api_client.force_authenticate(reader_user)
    assert api_client.post(url, data, format="json").status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post(url, {**data, "confirm": False}, format="json").status_code == 400
    Asset.objects.filter(pk=asset.pk).update(updated_at=timezone.now())
    assert api_client.post(url, data, format="json").status_code == 409
    assert not asset.cloud_objects.exists()


def test_cloud_preparation_is_durable_idempotent_and_never_selects_file(admin_user, settings, django_capture_on_commit_callbacks):
    from distribution.models import CloudProvider
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    row = edition(); asset = reader_candidate(row)
    CloudProvider.objects.create(name="Synthetic destination", bucket="isolated", enabled=True, is_default=True)
    data = {"request_key": uuid4(), "expected_asset_updated_at": asset.updated_at.isoformat(), "confirm": True}
    with patch("catalog.services.edition_file_workspace.dispatch_public_preparation") as dispatch, django_capture_on_commit_callbacks(execute=True):
        first = prepare_public_file(row.pk, asset.pk, admin_user, data)
        second = prepare_public_file(row.pk, asset.pk, admin_user, data)
    assert first == second and dispatch.call_count == 1 and asset.cloud_objects.count() == 1
    asset.refresh_from_db(); row.refresh_from_db()
    assert not asset.is_current and row.state == "draft" and not row.catalog_revisions.exists()


def test_failed_cloud_dispatch_remains_visible_and_retryable(admin_user, settings):
    from distribution.models import CloudProvider
    from catalog.services.edition_file_workspace import dispatch_public_preparation, public_preparation
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    row = edition(); asset = reader_candidate(row)
    provider = CloudProvider.objects.create(name="Synthetic destination", bucket="isolated", enabled=True, is_default=True)
    cloud = asset.cloud_objects.create(provider=provider, object_key="synthetic.pdf", sha256=asset.sha256, byte_size=asset.byte_size)
    with patch("distribution.tasks.sync_cloud_object.apply_async", side_effect=ConnectionError("synthetic broker failure")):
        dispatch_public_preparation(cloud.pk)
    cloud.refresh_from_db()
    assert cloud.status == "failed" and public_preparation(asset, True)["can_prepare"]


def test_public_adoption_waits_for_explicit_cloud_preparation(admin_user, settings):
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    row, old, revision = published(admin_user)
    candidate = reader_candidate(row)
    preview = prepare_adoption(row.pk, candidate.pk, admin_user)
    assert not preview["can_adopt"] and any("公开分发" in reason for reason in preview["blocking"])
    with pytest.raises(EditionFileError):
        adopt_file(row.pk, candidate.pk, admin_user, preview)
    row.refresh_from_db()
    assert row.active_catalog_revision_id == revision.pk and row.active_catalog_revision.reader_asset_id == old.pk


def test_failed_intake_second_write_removes_only_new_unowned_storage(admin_user, settings):
    from pathlib import Path
    from unittest.mock import patch
    from django.db.models.fields.files import FieldFile
    row = edition()
    first, _ = submit(row, admin_user, generate_reader=False)
    original_save = FieldFile.save
    def fail_second(field, *args, **kwargs):
        if isinstance(field.instance, UploadItem):
            raise OSError("synthetic second storage failure")
        return original_save(field, *args, **kwargs)
    before = {str(path) for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}
    with patch.object(FieldFile, "save", fail_second), pytest.raises(OSError):
        submit(row, admin_user, content=PDF+b"uncommitted", generate_reader=False)
    after = {str(path) for path in Path(settings.MEDIA_ROOT).rglob("*") if path.is_file()}
    assert before == after and Asset.objects.count() == 1 and UploadItem.objects.count() == 1
    assert first.asset.file.read() == PDF


def test_ready_cloud_receipt_does_not_depend_on_later_provider_budget(admin_user, settings):
    from distribution.models import CloudProvider
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = True
    row = edition(); asset = reader_candidate(row)
    provider = CloudProvider.objects.create(name="Synthetic destination", bucket="isolated", enabled=True, is_default=True)
    data = {"request_key": uuid4(), "expected_asset_updated_at": asset.updated_at.isoformat(), "confirm": True}
    prepare_public_file(row.pk, asset.pk, admin_user, data)
    asset.cloud_objects.update(status="ready")
    provider.enabled = False; provider.is_default = False; provider.save()
    with patch("distribution.services.cloud_budget_allows_new_publication", side_effect=AssertionError("ready receipt budget")):
        assert prepare_public_file(row.pk, asset.pk, admin_user, data)["status"] == "ready"


def test_explicit_cloud_preparation_cannot_resume_legacy_publication(admin_user):
    from distribution.models import CloudProvider
    from distribution.tasks import sync_cloud_object
    row = edition(); asset = reader_candidate(row)
    provider = CloudProvider.objects.create(name="Synthetic destination", bucket="isolated", enabled=True, is_default=True)
    cloud = asset.cloud_objects.create(provider=provider, object_key="synthetic.pdf", sha256=asset.sha256, byte_size=asset.byte_size)
    with patch("distribution.tasks.sync_asset_to_cloud"), patch("ingestion.services.pipeline.resume_publication_for_asset") as resume:
        sync_cloud_object.run(str(cloud.pk), resume_publication=False)
    resume.assert_not_called()
