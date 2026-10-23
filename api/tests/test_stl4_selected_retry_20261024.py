"""Deferred acceptance: selected retries must not rewrite completed or unselected pages."""
from contextlib import nullcontext
from unittest.mock import patch
from uuid import uuid4

import pytest

from catalog.models import Page
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.extract import ExtractedPage
from ingestion.services.processing_commands import task_version
from ingestion.services.processing_retry import failed_ocr_pages, selected_ocr_remaining
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def interrupted(settings, tmp_path):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    asset.page_count = 3
    asset.save(update_fields=["page_count", "updated_at"])
    saved = Page.objects.create(asset=asset, index=1, text="已保存的第一页", normalized_text="已保存的第一页", text_source="ocr")
    for index in (2, 3):
        Page.objects.create(asset=asset, index=index, text="", text_source="none")
    job = ProcessingJob.objects.create(job_type="ocr", status="failed", edition=edition, asset=asset, task_id=str(uuid4()),
        error_code="timeout", error_message="本次识别中断", attempt=3, progress=32,
        stats={"requested_mode": "all_pages", "requested_asset_id": str(asset.pk), "source_sha256": asset.sha256,
               "total_pages": 3, "target_pages": 3, "requested_page_indexes": [1, 2, 3],
               "completed_page_indexes": [1], "active_page_indexes": [1, 2, 3], "processed_pages": 1,
               "remaining_pages": 2, "ocr_phase": "recognizing"})
    return job, saved


def body(job, pages):
    return {"source": "processing_job", "job_id": str(job.pk), "action": "retry", "request_id": str(uuid4()),
            "expected_version": task_version(job), "page_indexes": pages}


def test_selected_page_finishes_without_publishing_or_touching_other_pages(api_client, admin_user, settings, tmp_path):
    from ingestion.services.processing import run_ocr_job, resume_processing_job, resume_paused_workload
    job, saved = interrupted(settings, tmp_path)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    request = body(job, [2])
    with patch("ingestion.services.processing.dispatch_ocr_job"):
        response = api_client.post(URL, request, format="json", **headers)
        assert response.status_code == 202, response.data
        replay = api_client.post(URL, request, format="json", **headers)
        assert replay.status_code == 200 and replay.data == response.data
        assert ProcessingJob.objects.filter(job_type="ocr").count() == 1
        job.refresh_from_db()
        task_id = job.task_id
        page = ExtractedPage(index=2, printed_label="", chapter_title="", width=100, height=200,
            text="重试保存的第二页", source="ocr", confidence=.9, blocks=[])
        with patch("ingestion.services.processing.materialize_field_file", return_value=("reader.pdf", lambda: None)), \
                patch("ingestion.services.ocr_heartbeat.ocr_request_lease", return_value=nullcontext()), \
                patch("ingestion.services.processing.extract_ocr_page_batch", return_value=([page], "paddleocr_nas")) as extract, \
                patch("ingestion.services.processing._publish_ocr_result", side_effect=AssertionError("Partial retry must not publish")):
            run_ocr_job(str(job.pk), task_id=task_id)
            extract.assert_called_once_with("reader.pdf", [2])
        job.refresh_from_db(); saved.refresh_from_db()
        assert job.status == "paused" and not job.task_id
        assert job.stats["completed_page_indexes"] == [1, 2] and job.stats["remaining_pages"] == 1
        assert job.stats["requested_page_indexes"] == [1, 2, 3] and job.stats["target_pages"] == 3
        assert job.stats["retry_selection"]["state"] == "completed"
        assert saved.text == "已保存的第一页" and job.asset.pages.get(index=3).text == ""
        assert resume_paused_workload("ocr", actor=admin_user) == 0
        resumed = resume_processing_job(job, actor=admin_user)
        assert resumed.stats["retry_selection"]["state"] == "continued"
        assert selected_ocr_remaining(resumed.stats, [3]) == [3]
    audit = AuditEvent.objects.get(action="ocr.retry_from_checkpoint", object_id=str(job.pk))
    assert audit.before["error_message"] == "本次识别中断" and audit.after["retry_selection"]["page_indexes"] == [2]


@pytest.mark.parametrize("pages,expected", [([1], 409), ([4], 409), ([], 400), ([-1], 400)])
def test_selection_cannot_include_completed_or_unrecorded_pages(api_client, admin_user, settings, tmp_path, pages, expected):
    job, _ = interrupted(settings, tmp_path)
    assert failed_ocr_pages(job) == [2, 3]
    api_client.force_authenticate(admin_user)
    response = api_client.post(URL, body(job, pages), format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert response.status_code == expected, response.data
    job.refresh_from_db()
    assert job.status == "failed" and job.stats["completed_page_indexes"] == [1]


def test_selection_rejects_changed_source_and_stopped_request(api_client, admin_user, settings, tmp_path):
    job, _ = interrupted(settings, tmp_path)
    request = body(job, [2])
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    stop = api_client.post(f"{URL}commands/{request['request_id']}/", {"action": "cancel_pending"}, format="json", **headers)
    assert stop.status_code == 200
    assert api_client.post(URL, request, format="json", **headers).data["state"] == "cancelled"
    job.asset.sha256 = "f" * 64
    job.asset.save(update_fields=["sha256", "updated_at"])
    response = api_client.post(URL, body(job, [2]), format="json", **headers)
    assert response.status_code == 409
    job.refresh_from_db()
    assert job.status == "failed"


def test_global_resume_keeps_normal_jobs_without_selection(settings, tmp_path, admin_user):
    from ingestion.services.processing import resume_paused_workload
    job, _ = interrupted(settings, tmp_path)
    job.status, job.attempt = "paused", 0
    job.save(update_fields=["status", "attempt", "updated_at"])
    with patch("ingestion.services.processing.dispatch_ocr_job"):
        assert resume_paused_workload("ocr", actor=admin_user) == 1
    job.refresh_from_db()
    assert job.status == "pending" and "retry_selection" not in job.stats
