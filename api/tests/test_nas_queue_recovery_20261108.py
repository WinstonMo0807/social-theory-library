"""A busy broker is not a lost task; absent projection targets cannot block peers."""
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from common.broker_presence import delivery_id
from ingestion.models import ProcessingJob
from ingestion.services.processing import recover_stalled_processing_jobs


def test_long_native_pdf_keeps_text_labels_toc_and_geometry_across_batches(tmp_path):
    import fitz
    from ingestion.services.extract import extract_native_pages, ocr_required_page_indexes
    path = tmp_path / "long-native.pdf"
    with fitz.open() as document:
        for number in range(1, 68):
            page = document.new_page(width=400, height=600)
            page.insert_text((40, 200), f"Page {number}: " + "Native text remains searchable. " * 3)
            if number == 33:
                page.set_rotation(90)
        document.set_page_labels([{"startpage": 0, "prefix": "p-", "style": "D", "firstpagenum": 1}])
        document.set_toc([[1, "Opening", 1], [1, "Middle", 33], [1, "Ending", 65]])
        document.save(path)
    pages, needed = extract_native_pages(path)
    assert len(pages) == 67 and not needed and ocr_required_page_indexes(pages) == []
    assert [page.printed_label for page in pages] == [f"p-{n}" for n in range(1, 68)]
    assert all(f"Page {n}:" in page.text for n, page in enumerate(pages, 1))
    assert [pages[i].chapter_title for i in (0, 32, 64)] == ["Opening", "Middle", "Ending"]
    assert (pages[32].width, pages[32].height) == (600, 400)
    assert all(page.blocks and page.geometry for page in pages)


def test_delivery_id_in_queue_and_reserved_protocols():
    message = {"headers": {"id": "queued-id"}, "properties": {"correlation_id": "fallback"}}
    assert delivery_id(json.dumps(message)) == "queued-id"
    assert delivery_id(json.dumps([message, "", "celery"]), unacked=True) == "queued-id"
    assert delivery_id(json.dumps({"properties": {"correlation_id": "fallback"}})) == "fallback"


def test_document_heavy_tasks_share_the_bounded_worker(settings):
    for name in ['process_ocr_job', 'process_outline_job', 'process_outline_export']:
        assert settings.CELERY_TASK_ROUTES['ingestion.tasks.' + name]['queue'] == settings.INGESTION_TASK_QUEUE


def test_temporary_ocr_only_routes_unbound_explicit_test_jobs(settings):
    from ingestion.services.ocr_transfer import active_ocr_config, bound_ocr_service
    settings.OCR_TEST_SERVICE_URL = "http://test-pc:18091"
    settings.OCR_TEST_JOB_IDS = frozenset({"allowed"})
    settings.OCR_TEST_UPLOAD_IDS = frozenset({"test-upload"})
    config = {"mode": "nas_only", "nas_url": "http://rapidocr:8000"}
    with patch("ingestion.services.ocr_transfer.resolve_bound_config", return_value=config):
        with bound_ocr_service(None, job_id="allowed"):
            assert active_ocr_config.get()["nas_url"] == settings.OCR_TEST_SERVICE_URL
        with bound_ocr_service(None, job_id="new-job", upload_item_id="test-upload"):
            assert active_ocr_config.get()["nas_url"] == settings.OCR_TEST_SERVICE_URL
        for job_id, binding in [("other", None), ("allowed", {"target": "nas"})]:
            with bound_ocr_service(binding, job_id=job_id):
                assert active_ocr_config.get() == config
    assert active_ocr_config.get() is None


def test_local_ocr_disconnect_preserves_retry_instead_of_nas_fallback():
    import httpx
    from ingestion.services.ocr_provider import _parse_pdf, OCRServiceBusy
    from ingestion.services.ocr_transfer import active_ocr_config
    token = active_ocr_config.set({"mode": "nas_only", "nas_url": "http://test-pc:18091",
                                   "temporary_test_service": True})
    try:
        with patch("ingestion.services.ocr_provider._request_document_gateway",
                   side_effect=httpx.ConnectError("offline")) as gateway:
            with pytest.raises(OCRServiceBusy):
                _parse_pdf("unused.pdf", page_numbers=[7])
            assert gateway.call_count == 1
    finally:
        active_ocr_config.reset(token)


@pytest.mark.django_db
def test_long_uploaded_title_keeps_display_name_and_exact_original(settings, tmp_path, admin_user):
    import hashlib
    from pathlib import Path
    from django.core.files.base import ContentFile
    from catalog.models import Asset, Work, Edition
    from ingestion.models import UploadBatch, UploadItem
    from ingestion.services.pipeline import _copy_asset
    settings.MEDIA_ROOT = str(tmp_path)
    filename = "社会运行论及其发展" * 25 + ".pdf"
    data = b"%PDF-1.4\nretained original bytes"
    batch = UploadBatch.objects.create(created_by=admin_user)
    item = UploadItem.objects.create(batch=batch, source_filename=filename,
        file=ContentFile(data, name="bounded-upload.pdf"), sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data))
    edition = Edition.objects.create(work=Work.objects.create(title="Long title"))
    asset = _copy_asset(item, edition, Asset.Kind.ORIGINAL, filename)
    assert asset.original_filename == filename
    assert len(Path(asset.file.name).name.encode()) < 255
    with asset.file.open("rb") as stored:
        assert stored.read() == data
    assert _copy_asset(item, edition, Asset.Kind.ORIGINAL, filename).pk == asset.pk


@pytest.mark.django_db
@pytest.mark.parametrize("present,expected", [(frozenset({"existing"}), 0), (None, 0), (frozenset(), 1)])
def test_pending_recovery_requires_confirmed_missing_delivery(present, expected, django_capture_on_commit_callbacks):
    job = ProcessingJob.objects.create(job_type="ocr", status="pending", task_id="existing",
                                       stats={"processed_pages": 17}, progress=42)
    ProcessingJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(days=1))
    with patch("common.broker_presence.broker_delivery_ids", return_value=present), \
            patch("ingestion.services.processing._dispatch_processing_job") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            assert recover_stalled_processing_jobs()["requeued"] == expected
        assert dispatch.call_count == expected
        assert recover_stalled_processing_jobs()["requeued"] == 0
    job.refresh_from_db()
    assert job.task_id == "existing" and job.progress == 42 and job.stats["processed_pages"] == 17


@pytest.mark.django_db
def test_missing_projection_does_not_block_other_objects():
    from catalog.models import DomainChangeEvent, ProjectionState, Work
    from catalog.services.projection_refresh import reconcile_projection_runtime
    work = Work.objects.create(title="Surviving projection")
    missing = uuid4()
    for object_id in [missing, work.pk]:
        DomainChangeEvent.objects.create(object_type="work", object_id=object_id,
            canonical_revision=1, change_kind="updated", processed_at=timezone.now(),
            idempotency_key=str(uuid4()))
        ProjectionState.objects.create(object_type="work", object_id=object_id,
            projection_type="public", source_revision=1, status="stale")
    with patch("common.task_runtime.reconcile_capability_runtime", return_value={
        "executors_offline": 0, "demands_ready": 0, "demands_waiting": 0}), \
        patch("catalog.services.projection_refresh._schedule_job_capability"), \
        patch("catalog.services.projection_refresh.dispatch_ready_projection_demands", return_value={"dispatched": 0}):
        assert reconcile_projection_runtime()["objects_scheduled"] == 1
        state = ProjectionState.objects.get(object_id=missing)
        assert state.status == "failed" and state.last_error_code == "projection_target_missing"
        assert DomainChangeEvent.objects.filter(object_id=missing).exists()
        assert reconcile_projection_runtime()["objects_scheduled"] == 1
        state.refresh_from_db()
        assert state.projected_revision == 0


@pytest.mark.django_db
def test_health_batch_yields_after_budget():
    from catalog.services.system_health import HEALTH_CHECKS, run_due_health_probes
    probes = [SimpleNamespace(key=f"test.budget.{i}", interval_seconds=60) for i in range(3)]
    result = SimpleNamespace(id=uuid4(), probe_key=probes[0].key, status="healthy")
    with patch.object(HEALTH_CHECKS, "all", return_value=probes), \
        patch("catalog.services.system_health.run_health_probe", return_value=result) as run, \
        patch("catalog.services.system_health.time.monotonic", side_effect=[0, 9]):
        assert run_due_health_probes()["executed"] == 1
        run.assert_called_once_with(probes[0].key)
