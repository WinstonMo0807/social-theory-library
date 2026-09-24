from unittest.mock import patch

import pytest

from catalog.models import Page, SiteSetting
from ingestion.models import AuditEvent, ProcessingJob
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-center/"


def test_requeued_wait_excludes_previous_attempt_time(failed_job):
    from datetime import timedelta
    from django.utils import timezone
    from ingestion.services.catalog_ocr import progress_row

    now = timezone.now()
    failed_job.status = "pending"
    failed_job.updated_at = now - timedelta(seconds=40)
    failed_job.started_at = now - timedelta(days=2)
    failed_job.finished_at = None
    failed_job.stats = {**failed_job.stats, "phase_started_at": failed_job.started_at.isoformat()}
    with patch("ingestion.services.catalog_ocr.timezone.now", return_value=now):
        row = progress_row(failed_job, actor=None)
    assert row["phase_elapsed_seconds"] == 40
    assert row["completed_pages"] == 1 and row["status"] == "pending"


def test_busy_service_requeues_same_checkpoint_without_spending_retry_budget(failed_job):
    from ingestion.services.ocr_provider import OCRServiceBusy
    from ingestion.services.processing import run_ocr_job
    failed_job.status = "pending"
    failed_job.task_id = "busy-first"
    failed_job.save()
    with patch("ingestion.services.processing.materialize_field_file", return_value=("fixture.pdf", None)), patch("ingestion.services.processing.extract_ocr_page_batch", side_effect=OCRServiceBusy("busy")), patch("ingestion.services.processing.dispatch_ocr_job") as dispatch:
        for _ in range(2):
            run_ocr_job(str(failed_job.pk), task_id=failed_job.task_id)
            failed_job.refresh_from_db()
            assert failed_job.status == "pending" and failed_job.attempt == 1
            assert failed_job.stats["processed_pages"] == 1
            assert failed_job.stats["service_activity"] == "queued"
            dispatch.assert_called_with(str(failed_job.pk), failed_job.task_id, countdown=30)


@pytest.fixture
def failed_job(settings, tmp_path):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    asset.page_count = 3
    asset.validation_details = {"ocr_required_page_indexes": [1, 2, 3]}
    asset.save()
    Page.objects.create(asset=asset, index=1, text="已保存文字", text_source=Page.TextSource.OCR)
    return ProcessingJob.objects.create(edition=edition, asset=asset, job_type="ocr", status="failed", attempt=1,
        error_code="OCRServiceUnavailable", error_message="Previous NAS request failed",
        stats={"processed_pages": 1, "target_pages": 3, "batch_session_started": True})


def test_monitor_is_readonly_and_does_not_probe_or_scan_paused_inventory(api_client, admin_user, failed_job):
    api_client.force_authenticate(admin_user)
    with patch("ingestion.views.paused_ocr_inventory", side_effect=AssertionError("inventory not needed")):
        response = api_client.get(URL, {"ocr_monitor": "1", "job_type": "external_enrichment", "status": "failed"})
    assert response.status_code == 200
    assert response["Cache-Control"] == "no-store"
    row = response.data["results"][0]
    assert row["id"] == str(failed_job.pk)
    assert row["ocr_progress"]["completed_pages"] == 1
    assert row["ocr_progress"]["percent"] == 33.3
    assert row["ocr_progress"]["can_resume"] is True
    assert not AuditEvent.objects.filter(action="ocr.retry_from_checkpoint").exists()
    failed_job.refresh_from_db()
    assert failed_job.status == "failed"


def test_retry_reuses_checkpoint_and_audits_failure_once(api_client, admin_user, failed_job, django_capture_on_commit_callbacks):
    api_client.force_authenticate(admin_user)
    page_id = failed_job.asset.pages.get(index=1).pk
    with patch("ingestion.services.processing.dispatch_ocr_job") as dispatch, django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json")
        replay = api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json")
    assert response.status_code == replay.status_code == 202
    assert response.data["job_id"] == replay.data["job_id"] == str(failed_job.pk)
    assert dispatch.call_count == 1
    failed_job.refresh_from_db()
    assert failed_job.status == "pending" and failed_job.stats["processed_pages"] == 1
    assert failed_job.stats["retry_page_batch_size"] == 1
    assert failed_job.stats["batch_session_started"] is False
    assert failed_job.asset.pages.get(index=1).pk == page_id
    audit = AuditEvent.objects.get(action="ocr.retry_from_checkpoint")
    assert audit.before["error_code"] == "OCRServiceUnavailable"
    assert ProcessingJob.objects.filter(job_type="ocr").count() == 1


@pytest.mark.parametrize("block", ["historical", "newer", "permanent", "global_pause"])
def test_retry_protects_replaced_sources_and_safety_gates(api_client, admin_user, failed_job, block):
    api_client.force_authenticate(admin_user)
    if block == "historical":
        failed_job.asset.is_current = False
        failed_job.asset.save()
    elif block == "newer":
        ProcessingJob.objects.create(edition=failed_job.edition, asset=failed_job.asset, job_type="ocr", status="succeeded")
    elif block == "permanent":
        failed_job.error_kind = "permanent"
        failed_job.save()
    else:
        SiteSetting.objects.update_or_create(key="ocr_processing_paused", defaults={"value": True})
    with patch("ingestion.services.processing.dispatch_ocr_job") as dispatch:
        response = api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json")
    assert response.status_code == 409, response.data
    assert not dispatch.called
    failed_job.refresh_from_db()
    assert failed_job.status == "failed"
    assert failed_job.error_code == "OCRServiceUnavailable"


def test_reader_cannot_monitor_or_retry(api_client, reader_user, failed_job):
    api_client.force_authenticate(reader_user)
    assert api_client.get(URL, {"ocr_monitor": "1"}).status_code == 403
    assert api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json").status_code == 403


def test_explicit_retry_starts_one_bounded_cycle_after_automatic_attempts_exhausted(api_client, admin_user, failed_job):
    api_client.force_authenticate(admin_user)
    failed_job.attempt = failed_job.max_attempts
    failed_job.save()
    progress = api_client.get(URL, {"ocr_monitor": "1"}).data["results"][0]["ocr_progress"]
    assert progress["can_resume"] is True
    response = api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json")
    assert response.status_code == 202
    failed_job.refresh_from_db()
    assert failed_job.attempt == 0
    assert failed_job.max_attempts == 3
    assert failed_job.stats["manual_retry_count"] == 1
    assert AuditEvent.objects.get(action="ocr.retry_from_checkpoint").before["attempt"] == 3


def test_retried_legacy_job_saves_one_new_page_and_keeps_completed_page(api_client, admin_user, failed_job):
    from ingestion.services.processing import run_ocr_job
    from ingestion.services.extract import ExtractedPage

    api_client.force_authenticate(admin_user)
    original_page = failed_job.asset.pages.get(index=1)
    response = api_client.post(URL, {"action": "retry", "job_id": str(failed_job.pk)}, format="json")
    assert response.status_code == 202
    failed_job.refresh_from_db()
    def extract(_path, indexes):
        assert indexes == [2]
        progress = api_client.get(URL, {"ocr_monitor": "1"}).data["results"][0]["ocr_progress"]
        assert progress["completed_pages"] == 1 and progress["active_pages"] == [2]
        return [ExtractedPage(index=2, text="第二页文字", width=595, height=842, source="ocr", confidence=.98, printed_label="", chapter_title="", blocks=[])], "controlled_ocr"
    with patch("ingestion.services.processing.materialize_field_file", return_value=("fixture.pdf", None)), patch("ingestion.services.processing.extract_ocr_page_batch", side_effect=extract), patch("ingestion.services.processing.dispatch_ocr_job"):
        run_ocr_job(str(failed_job.pk), task_id=failed_job.task_id)
    failed_job.refresh_from_db()
    assert failed_job.status == "pending"
    assert failed_job.stats["processed_pages"] == 2
    assert failed_job.stats["remaining_pages"] == 1
    original_page.refresh_from_db()
    assert original_page.text == "已保存文字"
