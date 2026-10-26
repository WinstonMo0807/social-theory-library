"""Deferred acceptance: pin the real OCR service, preserve checkpoints and deny stale writes."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from ingestion.models import AuditEvent
from ingestion.services.ocr_provider import OCRConfigurationError, ocr_runtime_config
from ingestion.services.ocr_transfer import resolve_bound_config, target_version
from ingestion.services.processing_commands import task_version
from .test_stl4_selected_retry_20261024 import interrupted

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def command(job, target="nas", acknowledge=False):
    return {"source": "processing_job", "job_id": str(job.pk), "action": "transfer", "request_id": str(uuid4()),
            "expected_version": task_version(job), "target": target,
            "target_version": target_version(ocr_runtime_config(), target), "acknowledge_remote": acknowledge}


def test_transfer_preserves_saved_page_and_rejects_late_delivery(api_client, admin_user, settings, tmp_path):
    from ingestion.services.processing import run_ocr_job
    settings.RAPIDOCR_SERVICE_URL = "http://ocr.internal"
    job, saved = interrupted(settings, tmp_path)
    old_delivery = job.task_id
    body = command(job)
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.processing.dispatch_ocr_job"), patch("ingestion.services.processing.extract_ocr_page_batch") as extract:
        response = api_client.post(URL, body, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
        assert response.status_code == 202, response.data
        assert api_client.post(URL, body, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk)).data == response.data
        job.refresh_from_db(); saved.refresh_from_db()
        assert job.status == "pending" and job.task_id != old_delivery
        assert job.stats["completed_page_indexes"] == [1] and saved.text == "已保存的第一页"
        run_ocr_job(str(job.pk), task_id=old_delivery)
        extract.assert_not_called()
    assert AuditEvent.objects.filter(action="processing.transfer_ocr", object_id=str(job.pk)).count() == 1
    binding = job.stats["ocr_service_binding"]
    assert resolve_bound_config(binding)["mode"] == "nas_only"
    settings.RAPIDOCR_SERVICE_URL = "http://changed.internal"
    with pytest.raises(OCRConfigurationError):
        resolve_bound_config(binding)


def test_remote_requires_ack_and_current_config(api_client, admin_user, settings, tmp_path):
    settings.OCR_REMOTE_API_URL = "https://ocr.example.invalid"
    settings.OCR_REMOTE_API_KEY = "test-placeholder"
    job, _ = interrupted(settings, tmp_path)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    assert api_client.post(URL, command(job, "remote"), format="json", **headers).status_code == 409
    body = command(job, "remote", True)
    settings.OCR_REMOTE_API_URL = "https://changed.example.invalid"
    assert api_client.post(URL, body, format="json", **headers).status_code == 409
    job.refresh_from_db()
    assert job.status == "failed" and "ocr_service_binding" not in job.stats


def test_transfer_cannot_interrupt_active_or_finalizing_job(api_client, admin_user, settings, tmp_path):
    settings.RAPIDOCR_SERVICE_URL = "http://ocr.internal"
    job, _ = interrupted(settings, tmp_path)
    job.status, job.attempt, job.heartbeat_at, job.started_at = "running", 1, timezone.now(), timezone.now()
    job.save()
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    assert api_client.post(URL, command(job), format="json", **headers).status_code == 409
    job.heartbeat_at = timezone.now() - timedelta(days=1)
    job.stats["ocr_phase"] = "publishing"
    job.save()
    assert api_client.post(URL, command(job), format="json", **headers).status_code == 409
