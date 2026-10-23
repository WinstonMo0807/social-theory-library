"""Deferred acceptance: recovery must retain checkpoints and reject stale intent.

Written during implementation; execution belongs to the final acceptance phase.
"""
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.services.discovery_projection import DiscoveryIndexError
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.processing_commands import task_version
from ingestion.services.processing_recovery import recovery_state
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def stalled_outline(settings, tmp_path, *, status="running"):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    old = timezone.now() - timedelta(days=2)
    job = ProcessingJob.objects.create(job_type="text_extraction", status=status, asset=asset, edition=edition,
        task_id=str(uuid4()), attempt=1, started_at=old, heartbeat_at=old,
        stats={"operation": "outline_rebuild", "source_sha256": asset.sha256, "document_revision_id": None,
               "completed_units": 3}, progress=35)
    ProcessingJob.objects.filter(pk=job.pk).update(updated_at=old)
    job.refresh_from_db()
    return job, asset


def command(job):
    return {"source": "processing_job", "job_id": str(job.pk), "action": "recover",
            "request_id": str(uuid4()), "expected_version": task_version(job)}


def test_activity_uses_each_original_clock_and_excludes_waiting_coordinator(settings):
    now = timezone.now()
    job = ProcessingJob(job_type="discovery_index", status="running", updated_at=now,
                        heartbeat_at=now - timedelta(days=2), stats={"action": "source"})
    assert recovery_state(job, now=now)["state"] == "active"
    job.updated_at = now - timedelta(minutes=16)
    assert recovery_state(job, now=now)["can_recover"]
    job.stats = {"action": "build", "generation_id": str(uuid4())}
    job.progress = 5
    assert recovery_state(job, now=now)["state"] == "waiting_sources"
    assert recovery_state(job, now=now)["eligible_at"] is None
    job.stats, job.status = {"action": "source"}, "pending"
    assert not recovery_state(job, now=now)["can_recover"]  # The queued window is longer.
    job.updated_at = now - timedelta(minutes=61)
    assert recovery_state(job, now=now)["can_recover"]
    job.job_type, job.status = "ocr", "running"
    job.updated_at = now
    job.heartbeat_at = now - timedelta(seconds=settings.INGESTION_STAGE_STALLED_SECONDS + 1)
    assert recovery_state(job, now=now)["can_recover"]
    job.attempt = job.max_attempts
    assert not recovery_state(job, now=now)["can_recover"]


@pytest.mark.parametrize("status", ["pending", "running"])
def test_recovery_scopes_one_task_preserves_progress_and_replays_once(
        api_client, admin_user, settings, tmp_path, django_capture_on_commit_callbacks, status):
    job, _ = stalled_outline(settings, tmp_path, status=status)
    original_id = job.task_id
    untouched = ProcessingJob.objects.create(job_type="text_extraction", status="running", task_id=str(uuid4()),
        started_at=job.started_at, heartbeat_at=job.heartbeat_at)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    body = command(job)
    with patch("ingestion.services.processing._dispatch_processing_job") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            first = api_client.post(URL, body, format="json", **headers)
            assert first.status_code == 202, first.data
        replay = api_client.post(URL, body, format="json", **headers)
        assert replay.status_code == 200 and replay.data == first.data
        assert dispatch.call_count == 1
    job.refresh_from_db(); untouched.refresh_from_db()
    assert job.status == "pending" and job.progress == 35 and job.stats["completed_units"] == 3
    assert (job.task_id == original_id) == (status == "pending")
    assert untouched.status == "running"
    assert AuditEvent.objects.filter(action="processing.recover_from_checkpoint", object_id=str(job.pk)).count() == 1
    if status == "running":
        from ingestion.services.processing import _claim_processing_job
        assert _claim_processing_job(job.pk, task_id=original_id)[1] is False


@pytest.mark.parametrize("changed", ["heartbeat", "source", "token", "owner"])
def test_fresh_activity_source_and_account_are_rechecked(api_client, admin_user, settings, tmp_path, changed):
    job, asset = stalled_outline(settings, tmp_path)
    body = command(job)
    api_client.force_authenticate(admin_user)
    owner = str(admin_user.pk)
    if changed == "heartbeat":
        ProcessingJob.objects.filter(pk=job.pk).update(heartbeat_at=timezone.now())
    elif changed == "source":
        asset.sha256 = "f" * 64
        asset.save(update_fields=["sha256", "updated_at"])
    elif changed == "token":
        type(admin_user).objects.filter(pk=admin_user.pk).update(token_version=admin_user.token_version + 1)
    else:
        owner = str(uuid4())
    with patch("ingestion.services.processing._dispatch_processing_job") as dispatch:
        response = api_client.post(URL, body, format="json", HTTP_X_EDITOR_OWNER=owner)
        assert response.status_code == (403 if changed in {"token", "owner"} else 409), response.data
        dispatch.assert_not_called()
    job.refresh_from_db()
    assert job.status == "running" and job.stats["completed_units"] == 3
    assert not AuditEvent.objects.filter(action="processing.recover_from_checkpoint", object_id=str(job.pk)).exists()


def test_stopped_recovery_cannot_be_applied_by_late_request(api_client, admin_user, settings, tmp_path):
    job, _ = stalled_outline(settings, tmp_path)
    body = command(job)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    stop = api_client.post(f"{URL}commands/{body['request_id']}/", {"action": "cancel_pending"}, format="json", **headers)
    assert stop.status_code == 200
    response = api_client.post(URL, body, format="json", **headers)
    assert response.status_code == 200 and response.data["state"] == "cancelled"
    job.refresh_from_db()
    assert job.status == "running"


def test_lost_ocr_worker_acknowledges_pause_and_retains_completed_pages(settings, tmp_path):
    from ingestion.services.processing import recover_stalled_processing_jobs
    job, _ = stalled_outline(settings, tmp_path)
    ProcessingJob.objects.filter(pk=job.pk).update(job_type="ocr", pause_requested_at=timezone.now(),
        stats={"completed_page_indexes": [1, 2], "text_stage_key": "original-stage"})
    with patch("ingestion.services.processing._dispatch_processing_job") as dispatch:
        result = recover_stalled_processing_jobs(job_id=job.pk, limit=1)
        assert result["candidates"] == 1 and result["requeued"] == 0
        dispatch.assert_not_called()
    job.refresh_from_db()
    assert job.status == "paused" and not job.task_id
    assert job.stats["completed_page_indexes"] == [1, 2] and job.stats["text_stage_key"] == "original-stage"


def test_discovery_busy_writer_or_changed_source_cannot_be_replaced():
    from catalog.services.discovery_indexing import recover_interrupted_job
    from .test_stl4_index_result_exports_20261024 import index_job
    job, state, _, _ = index_job()
    ProcessingJob.objects.filter(pk=job.pk).update(status="running", task_id=str(uuid4()),
        updated_at=timezone.now() - timedelta(minutes=16))
    job.refresh_from_db()
    original_id = job.task_id

    @contextmanager
    def busy():
        yield False

    with patch("catalog.services.discovery_indexing.index_writer", busy):
        with pytest.raises(DiscoveryIndexError) as error:
            recover_interrupted_job(job.pk)
        assert error.value.code == "writer_busy"
    state.job = None
    state.save(update_fields=["job", "updated_at"])
    with pytest.raises(DiscoveryIndexError) as error:
        recover_interrupted_job(job.pk)
    assert error.value.code == "superseded"
    job.refresh_from_db()
    assert job.status == "running" and job.task_id == original_id


@pytest.mark.parametrize("status", ["running", "pending"])
def test_discovery_recovery_keeps_original_generation_and_saved_fragments(status, django_capture_on_commit_callbacks):
    from catalog.services.discovery_indexing import recover_interrupted_job
    from .test_stl4_index_result_exports_20261024 import index_job
    job, state, _, documents = index_job()
    original_id = str(uuid4())
    ProcessingJob.objects.filter(pk=job.pk).update(status=status, task_id=original_id,
        updated_at=timezone.now() - timedelta(hours=2), progress=40,
        stats={**job.stats, "completed_units": 3})
    with patch("catalog.services.discovery_indexing._dispatch") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            result = recover_interrupted_job(job.pk)
        dispatch.assert_called_once_with(job.pk if status == "running" else str(job.pk), result.task_id)
    job.refresh_from_db(); state.refresh_from_db()
    assert job.status == "pending" and job.progress == 40 and job.stats["completed_units"] == 3
    assert (job.task_id == original_id) == (status == "pending")
    assert job.attempt == (1 if status == "running" else 0)
    assert state.job_id == job.pk and str(state.generation_id) == job.stats["generation_id"]
    for document in documents:
        saved_text = document.text
        document.refresh_from_db()
        assert document.text == saved_text and document.indexed_at is not None


@pytest.mark.parametrize("status", ["running", "succeeded"])
def test_late_broker_error_cannot_overwrite_started_outline(status):
    from catalog.services.document_outline import dispatch_outline_job
    job = ProcessingJob.objects.create(job_type="text_extraction", status=status, task_id=str(uuid4()))
    with patch("ingestion.tasks.process_outline_job.apply_async", side_effect=ConnectionError):
        assert dispatch_outline_job(str(job.pk), job.task_id) is False
    job.refresh_from_db()
    assert job.status == status and not job.error_code
