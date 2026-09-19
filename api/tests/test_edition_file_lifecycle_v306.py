"""Real isolated catalog HTTP + PDF/pipeline lifecycles for 3.0.6.

The PDF parser, originals, Pages, DocumentRevisions, metadata decisions and
publication activation are real. Queue dispatch, optional enrichment/image
production and index adapters are controlled fixtures; explicit projection
acknowledgement is not evidence of a real Worker/OCR/Meilisearch deployment.
"""
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import fitz
import pytest
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError

from catalog.models import Asset, CatalogPublicationRevision, CatalogingSession, DocumentRevision, Edition, KnowledgePublicationEvent, Page, Person, Work
from ingestion.models import AuditEvent, FieldLock, UploadBatch, UploadItem
from ingestion.services.pipeline import run_pipeline
from reading.models import Annotation, Bookmark, ReadingProgress, SavedItem
from .publication_fixtures import acknowledge_catalog_projections


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def lifecycle_adapters(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    settings.PUBLIC_DEPLOYMENT_MODE = False
    settings.X_ACCEL_REDIRECT_ENABLED = False
    settings.REQUIRE_EXTERNAL_SEARCH = False
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.PROCESS_INGESTION_INLINE = False
    # FileField retains its callable-created storage. Set the actual isolated
    # field storage, not merely a later settings.STORAGES dictionary.
    monkeypatch.setattr(UploadItem._meta.get_field("file"), "storage", FileSystemStorage(location=tmp_path / "incoming"))
    with ExitStack() as stack:
        stack.enter_context(patch("catalog.services.edition_files.schedule_upload_item"))
        stack.enter_context(patch("catalog.services.knowledge_publication.dispatch_knowledge_event", return_value=True))
        stack.enter_context(patch("catalog.services.document_intelligence._schedule_claim_shadow"))
        stack.enter_context(patch("catalog.services.front_matter_intelligence.schedule_library_synthesis", return_value={"status": "waiting_for_capability"}))
        for name in ("queue_semantic_job", "queue_page_label_job", "queue_ocr_job", "queue_external_enrichment_job"):
            stack.enter_context(patch(f"ingestion.services.pipeline.{name}"))
        stack.enter_context(patch("ingestion.services.pipeline.index_asset", return_value={"status": "staging_only", "documents": 0, "test_adapter": True}))
        stack.enter_context(patch("ingestion.services.pipeline.detect_publication_places", return_value=[]))
        stack.enter_context(patch("ingestion.services.pipeline.generate_cover_candidates", return_value=[]))
        stack.enter_context(patch("ingestion.services.pipeline.generate_recommendation_image", return_value=None))
        stack.enter_context(patch("ingestion.services.pipeline.generate_theory_review_tasks", return_value={"created": 0, "reused": 0}))
        yield


def pdf_bytes(marker):
    document = fitz.open()
    for index in range(1, 4):
        page = document.new_page(width=595, height=842)
        content = ("A digital sociology report\n" + "Power, institutions and social relations are documented in this report. " * 18 + f"\n{marker} page {index}")
        assert page.insert_textbox(fitz.Rect(50, 50, 545, 790), content, fontsize=10, fontname="helv") > 0
    document.set_metadata({"title": f"Machine title must remain a candidate {marker}", "author": "Machine Author", "subject": "social report"})
    result = document.tobytes()
    document.close()
    return result


def manual_report(client, actor, *, complete=True):
    client.force_authenticate(actor)
    response = client.post("/api/catalog/admin/cataloging-sessions/", {
        "source_type": "manual", "document_type": "report", "title": "人工确认的社会调查报告", "language": "zh-CN", "request_key": str(uuid4()),
    }, format="json")
    assert response.status_code == 201, response.data
    session = CatalogingSession.objects.get(pk=response.data["id"])
    edition = session.edition
    if complete:
        person = Person.objects.create(preferred_name="人工确认责任者", sort_name="人工确认责任者", authority_status="verified")
        for section, data in (
            ("bibliography", {"report_institution": "隔离测试研究机构", "publication_year": 2026}),
            ("contributors", {"contributors": [{"person_id": str(person.pk), "role": "author", "order": 0}]}),
        ):
            saved = client.patch(f"/api/catalog/admin/library/works/{edition.work_id}/sections/{section}/?edition={edition.pk}",
                                 {"data": data, "confirm_section": True}, format="json")
            assert saved.status_code == 200, saved.data
    edition.refresh_from_db()
    return session, edition


def submit_file(client, edition, content, *, action="supplement", key=None):
    edition.refresh_from_db()
    values = {"action": action, "file": SimpleUploadedFile(f"{action}.pdf", content, content_type="application/pdf"),
              "request_key": str(key or uuid4()), "expected_updated_at": edition.updated_at.isoformat(), "confirm": True}
    if action == "replace":
        values["expected_reader_asset_id"] = str(edition.active_catalog_revision.reader_asset_id)
    result = client.post(f"/api/catalog/admin/editions/{edition.pk}/files/", values, format="multipart")
    assert result.status_code in {200, 202}, result.data
    return result, UploadItem.objects.get(pk=result.data["item_id"])


def publish(client, edition):
    prepared = client.get(f"/api/catalog/admin/editions/{edition.pk}/publication/prepare/")
    assert prepared.status_code == 200
    assert prepared.data["blocking"] == [], prepared.data
    result = client.post(f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
                         {"confirm_warnings": True, "prepared_fingerprint": prepared.data["fingerprint"]}, format="json")
    assert result.status_code == 200, result.data
    return result, prepared.data


def range_header(client, asset):
    response = client.get(f"/api/distribution/assets/{asset.pk}/file/", HTTP_RANGE="bytes=0-4")
    assert response.status_code == 206
    assert response["Content-Range"].startswith("bytes 0-4/")
    assert b"".join(response.streaming_content) == b"%PDF-"
    response.close()


def test_A05_manual_report_without_pdf_publishes_via_real_http_and_activation(api_client, admin_user):
    session, edition = manual_report(api_client, admin_user)
    assert not UploadItem.objects.exists() and not Asset.objects.exists()
    queue = api_client.get("/api/catalog/admin/workflows/queue/?source=manual")
    assert any(row["session_id"] == str(session.pk) for row in queue.data["results"])
    publish(api_client, edition)
    event = acknowledge_catalog_projections(edition)
    assert event.catalog_revision.reader_asset_id is None
    detail = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert detail.status_code == 200
    assert detail.data["title"] == "人工确认的社会调查报告"
    assert detail.data["edition"]["readable_asset"] is None
    assert Work.objects.count() == Edition.objects.count() == CatalogingSession.objects.count() == 1
    assert not UploadItem.objects.exists() and not DocumentRevision.objects.exists() and not Page.objects.exists()
    session.refresh_from_db()
    assert session.source_type == "manual" and session.status == "published" and session.upload_item_id is None


def test_A09_early_manual_pdf_supplement_runs_without_rebinding_or_automatic_metadata(api_client, admin_user):
    session, edition = manual_report(api_client, admin_user, complete=False)
    assert edition.canonical_filename == ""
    content, key = pdf_bytes("EarlySupplement"), uuid4()
    first, item = submit_file(api_client, edition, content, key=key)
    replay, repeated = submit_file(api_client, edition, content, key=key)
    assert first.status_code == 202 and replay.status_code == 200 and repeated.pk == item.pk
    finished = run_pipeline(str(item.pk))
    assert finished.status == "ready"
    edition.refresh_from_db()
    session.refresh_from_db()
    assert finished.edition_id == edition.pk and session.edition_id == edition.pk
    assert session.source_type == "manual" and session.upload_item_id is None
    assert edition.work.title == "人工确认的社会调查报告" and edition.work.language == "zh-CN"
    assert Work.objects.count() == Edition.objects.count() == CatalogingSession.objects.count() == UploadItem.objects.count() == 1
    normalized = edition.assets.get(kind="normalized", is_current=True)
    assert normalized.validation_status == "valid" and normalized.pages.count() == 3
    assert normalized.document_revisions.exists()
    assert edition.assets.get(kind="original").file.read() == content
    assert not CatalogPublicationRevision.objects.exists()


@pytest.mark.parametrize("metadata_change", [False, True])
def test_A09_published_bibliography_adds_pdf_only_after_explicit_publication(api_client, admin_user, metadata_change):
    session, edition = manual_report(api_client, admin_user)
    publish(api_client, edition)
    acknowledge_catalog_projections(edition)
    old_revision = edition.active_catalog_revision_id
    _, item = submit_file(api_client, edition, pdf_bytes("PublishedBibliographySupplement"))
    assert run_pipeline(str(item.pk)).status == "ready"
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == old_revision
    assert edition.active_catalog_revision.reader_asset_id is None
    normalized = edition.assets.get(kind="normalized", is_current=True)
    from catalog.services.publication_commands import catalog_health
    assert catalog_health(edition)["publication"] == "changes_pending"
    if metadata_change:
        response = api_client.patch(f"/api/catalog/admin/library/works/{edition.work_id}/sections/work/?edition={edition.pk}",
                                    {"data": {"title": "明确发布的报告新题名"}, "confirm_section": True}, format="json")
        assert response.status_code == 202, response.data
        before_publish = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
        assert before_publish.data["title"] == "人工确认的社会调查报告"
    published, prepared = publish(api_client, edition)
    assert any(row["field"] in {"file", "reader_asset"} for row in prepared["changes"])
    pending = KnowledgePublicationEvent.objects.filter(catalog_revision__edition=edition, catalog_revision__reader_asset=normalized)
    assert pending.count() == 1, "Explicit publish must create the first PDF-bearing public revision."
    assert CatalogPublicationRevision.objects.filter(edition=edition).count() == 2, "Metadata and first PDF share one new public revision."
    event_id = pending.get().pk
    again = api_client.post(f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
                            {"confirm_warnings": True, "prepared_fingerprint": prepared["fingerprint"]}, format="json")
    assert again.status_code == 200, again.data
    assert again.data["request_receipt"]["id"] == published.data["request_receipt"]["id"]
    assert again.data["request_receipt"]["replayed"]
    assert pending.count() == 1 and pending.get().pk == event_id
    acknowledge_catalog_projections(edition)
    assert edition.active_catalog_revision.reader_asset_id == normalized.pk
    range_header(api_client, normalized)
    detail = api_client.get(f"/api/catalog/works/{edition.public_slug}/")
    assert detail.data["title"] == ("明确发布的报告新题名" if metadata_change else "人工确认的社会调查报告")
    session.refresh_from_db()
    assert session.source_type == "manual" and session.upload_item_id is None and session.edition_id == edition.pk
    assert Work.objects.count() == Edition.objects.count() == 1
    # A delayed retry of the old accepted request must not publish a later edit.
    later = api_client.patch(f"/api/catalog/admin/library/works/{edition.work_id}/sections/work/?edition={edition.pk}",
                             {"data": {"title": "随后保存但未批准的报告题名"}, "confirm_section": True}, format="json")
    assert later.status_code == 202
    replay = api_client.post(f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
                             {"confirm_warnings": True, "prepared_fingerprint": prepared["fingerprint"]}, format="json")
    assert replay.status_code == 200 and replay.data["request_receipt"]["replayed"]
    assert api_client.get(f"/api/catalog/works/{edition.public_slug}/").data["title"] == detail.data["title"]


def test_A13_never_accepted_stale_fingerprint_still_conflicts_without_publication(api_client, admin_user):
    _, edition = manual_report(api_client, admin_user)
    prepared = api_client.get(f"/api/catalog/admin/editions/{edition.pk}/publication/prepare/").data
    changed = api_client.patch(f"/api/catalog/admin/library/works/{edition.work_id}/sections/work/?edition={edition.pk}",
                               {"data": {"title": "预检后另一个修改"}, "confirm_section": True}, format="json")
    assert changed.status_code == 200
    response = api_client.post(f"/api/catalog/admin/library/works/{edition.work_id}/publication/?edition={edition.pk}",
                               {"confirm_warnings": True, "prepared_fingerprint": prepared["fingerprint"]}, format="json")
    assert response.status_code == 409
    assert not CatalogPublicationRevision.objects.exists()
    assert not AuditEvent.objects.filter(action="catalog.publication_requested").exists()


@pytest.mark.parametrize("fail_before_publication", [False, True])
def test_A06_A08_A13_A28_replacement_keeps_stable_reader_private_ids_and_recovers(api_client, admin_user, reader_user, fail_before_publication):
    session, edition = manual_report(api_client, admin_user)
    old_bytes = pdf_bytes("OriginalStableReader")
    _, initial = submit_file(api_client, edition, old_bytes)
    assert run_pipeline(str(initial.pk)).status == "ready"
    publish(api_client, edition)
    acknowledge_catalog_projections(edition)
    old_revision = edition.active_catalog_revision_id
    old_reader = edition.active_catalog_revision.reader_asset
    old_original = edition.assets.get(kind="original", is_current=True)
    page = old_reader.pages.get(index=1)
    api_client.force_authenticate(reader_user)
    note_response = api_client.post("/api/reading/annotations/", {"asset": str(old_reader.pk), "page": str(page.pk), "kind": "note",
                                                                "body": "private-lifecycle-fixture", "selector": {"page_id": str(page.pk)}}, format="json")
    assert note_response.status_code == 201, note_response.data
    annotation = Annotation.objects.get(pk=note_response.data["id"])
    encrypted_before = bytes(annotation.body_ciphertext)
    bookmark_response = api_client.post("/api/reading/bookmarks/", {"asset": str(old_reader.pk), "page": str(page.pk), "label": "原版位置"}, format="json")
    assert bookmark_response.status_code == 201, bookmark_response.data
    bookmark = Bookmark.objects.get(pk=bookmark_response.data["id"])
    progress_response = api_client.post("/api/reading/progress/", {"asset": str(old_reader.pk), "current_page": 2, "last_position": {"page": 2}}, format="json")
    assert progress_response.status_code in {200, 201}, progress_response.data
    progress = ReadingProgress.objects.get(pk=progress_response.data["id"])
    saved_response = api_client.post("/api/reading/saved/", {"work": str(edition.work_id)}, format="json")
    assert saved_response.status_code == 201, saved_response.data
    saved = SavedItem.objects.get(pk=saved_response.data["id"])
    api_client.force_authenticate(admin_user)
    lock = FieldLock.objects.create(edition=edition, field_name="title", locked_value=edition.work.title, locked_by=admin_user, reason="保留人工锁理由")
    page_ids = set(old_reader.pages.values_list("pk", flat=True))
    locks_before = list(edition.field_locks.values("id", "field_name", "locked_value", "locked_by_id", "reason"))
    replacement_bytes = pdf_bytes("ReplacementPendingThenPublished")
    key = uuid4()
    _, replacement = submit_file(api_client, edition, replacement_bytes, action="replace", key=key)
    _, repeat = submit_file(api_client, edition, replacement_bytes, action="replace", key=key)
    assert repeat.pk == replacement.pk
    range_header(api_client, old_reader)
    if fail_before_publication:
        with patch("ingestion.services.pipeline._finalize_item_publication", side_effect=RuntimeError("controlled late file failure")):
            with pytest.raises(RuntimeError, match="controlled late"):
                run_pipeline(str(replacement.pk))
        replacement.refresh_from_db()
        edition.refresh_from_db()
        assert replacement.status == "failed"
        assert replacement.attempts.filter(stage="replacement_activation", status="failed").exists()
        assert edition.active_catalog_revision_id == old_revision
        range_header(api_client, old_reader)
        staged_ids = set(edition.assets.values_list("pk", flat=True))
        staged_pages = set(Page.objects.filter(asset__edition=edition).values_list("pk", flat=True))
    completed = run_pipeline(str(replacement.pk))
    assert completed.status == "published"
    edition.refresh_from_db()
    assert edition.active_catalog_revision_id == old_revision
    assert KnowledgePublicationEvent.objects.filter(catalog_revision__edition=edition).count() == 2
    range_header(api_client, old_reader)
    if fail_before_publication:
        assert set(edition.assets.values_list("pk", flat=True)) == staged_ids
        assert set(Page.objects.filter(asset__edition=edition).values_list("pk", flat=True)) == staged_pages
    acknowledge_catalog_projections(edition)
    new_reader = edition.active_catalog_revision.reader_asset
    assert new_reader.pk != old_reader.pk and new_reader.version == 2
    range_header(api_client, new_reader)
    old_reader.refresh_from_db()
    old_original.refresh_from_db()
    assert not old_reader.is_current and not old_original.is_current
    assert old_reader.file.read() == old_original.file.read() == old_bytes
    assert new_reader.file.read() == replacement_bytes
    assert set(old_reader.pages.values_list("pk", flat=True)) == page_ids
    assert list(edition.field_locks.values("id", "field_name", "locked_value", "locked_by_id", "reason")) == locks_before
    annotation.refresh_from_db(); bookmark.refresh_from_db(); progress.refresh_from_db(); saved.refresh_from_db()
    assert annotation.page_id == bookmark.page_id == page.pk
    assert annotation.asset_id == bookmark.asset_id == progress.asset_id == old_reader.pk
    assert bytes(annotation.body_ciphertext) == encrypted_before and not annotation.orphaned
    assert progress.current_page == 2 and saved.work_id == edition.work_id
    assert Work.objects.count() == Edition.objects.count() == 1
    session.refresh_from_db()
    assert session.edition_id == edition.pk and session.upload_item_id is None and session.source_type == "manual"
    # Preserve the existing strict-current public URL semantics. There is no
    # historical alias or silent Page remap after successful activation.
    for path in (f"/api/catalog/assets/{old_reader.pk}/manifest/", f"/api/distribution/assets/{old_reader.pk}/access/",
                 f"/api/distribution/assets/{old_reader.pk}/file/"):
        assert api_client.get(path).status_code == 404
    assert api_client.get(f"/api/reading/annotations/{annotation.pk}/").status_code == 404
    api_client.force_authenticate(reader_user)
    own_note = api_client.get(f"/api/reading/annotations/{annotation.pk}/")
    assert own_note.status_code == 200 and own_note.data["body_text"] == "private-lifecycle-fixture"
    assert str(own_note.data["page"]) == str(page.pk) and str(own_note.data["asset"]) == str(old_reader.pk)
    assert api_client.get(f"/api/reading/bookmarks/{bookmark.pk}/").status_code == 200
    assert api_client.get(f"/api/reading/progress/{progress.pk}/").status_code == 200
    assert api_client.get(f"/api/reading/saved/{saved.pk}/").status_code == 200


@pytest.mark.parametrize("timing", ["before_validation", "during_asset_copy"])
def test_A13_duplicate_race_never_rebinds_requested_manual_edition(api_client, admin_user, timing):
    session, target = manual_report(api_client, admin_user)
    content = pdf_bytes(f"DuplicateRace-{timing}")
    _, item = submit_file(api_client, target, content)
    other = Edition.objects.create(work=Work.objects.create(title="并发进入的另一份馆藏"))
    def create_duplicate():
        return Asset.objects.create(edition=other, kind="original", status="ready", validation_status="valid", sha256=sha256(content).hexdigest(),
                                    file=SimpleUploadedFile("concurrent.pdf", content, content_type="application/pdf"))
    if timing == "before_validation":
        duplicate = create_duplicate()
        result = run_pipeline(str(item.pk))
        assert result.status == "needs_review" and result.error_code == "duplicate_edition_file"
        assert result.preflight_summary["duplicate_asset_id"] == str(duplicate.pk)
    else:
        from ingestion.services import pipeline
        real_copy = pipeline._copy_asset
        def competing_copy(requested, edition, kind, filename):
            if kind == "original":
                create_duplicate()
            return real_copy(requested, edition, kind, filename)
        with patch.object(pipeline, "_copy_asset", side_effect=competing_copy):
            with pytest.raises(IntegrityError):
                run_pipeline(str(item.pk))
    item.refresh_from_db(); target.refresh_from_db(); session.refresh_from_db()
    assert item.edition_id == session.edition_id == target.pk
    assert item.asset_id is None and not target.assets.exists()
    assert target.work.title == "人工确认的社会调查报告"
    assert session.source_type == "manual" and session.upload_item_id is None
    assert Asset.objects.filter(edition=other, kind="original").count() == 1
    assert not CatalogPublicationRevision.objects.filter(edition=target).exists()
