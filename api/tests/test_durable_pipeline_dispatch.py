from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from catalog.models import Asset, DocumentType, Edition, SemanticIndexJob, Work
from catalog.services.semantic_indexing import recover_semantic_index_jobs
from ingestion.management.commands.check_library_pipeline import run_worker_task_probe
from ingestion.models import ProcessingAttempt, UploadBatch, UploadItem
from ingestion.services.dispatch import recover_ingestion_dispatches, schedule_upload_item


@pytest.mark.django_db
def test_ingestion_dispatch_survives_broker_failure_and_recovers(
    admin_user,
    django_capture_on_commit_callbacks,
):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="待恢复.pdf",
        file="incoming/待恢复.pdf",
        byte_size=2048,
    )

    with patch("ingestion.services.dispatch._task_for_kind") as task_for_kind:
        task_for_kind.return_value.apply_async.side_effect = ConnectionError("redis offline")
        with django_capture_on_commit_callbacks(execute=True):
            first_task_id = schedule_upload_item(str(item.id))

    item.refresh_from_db()
    assert first_task_id
    assert item.status == UploadItem.Status.RECEIVED
    assert item.dispatch_status == UploadItem.DispatchStatus.FAILED
    assert item.error_code == "queue_unavailable"
    assert ProcessingAttempt.objects.filter(
        upload_item=item,
        stage="task_dispatch",
        status="failed",
    ).exists()

    with patch("ingestion.services.dispatch._task_for_kind") as task_for_kind:
        with django_capture_on_commit_callbacks(execute=True):
            recovered = recover_ingestion_dispatches()

    item.refresh_from_db()
    assert recovered["scheduled"] == 1
    assert item.dispatch_task_id != first_task_id
    assert item.dispatch_status == UploadItem.DispatchStatus.QUEUED
    assert item.error_code == ""
    task_for_kind.return_value.apply_async.assert_called_once_with(
        args=[str(item.id)],
        task_id=item.dispatch_task_id,
        ignore_result=True,
    )


@pytest.mark.django_db
def test_recovery_does_not_replace_a_successfully_queued_upload(admin_user, settings):
    settings.INGESTION_QUEUE_STALLED_SECONDS = 1
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="已在队列.pdf",
        status=UploadItem.Status.RECEIVED,
        dispatch_status=UploadItem.DispatchStatus.QUEUED,
        dispatch_task_id="durable-message-id",
        last_dispatched_at=timezone.now() - timedelta(hours=2),
    )
    UploadItem.objects.filter(pk=item.pk).update(
        updated_at=timezone.now() - timedelta(hours=2),
    )

    with patch("ingestion.services.dispatch._task_for_kind") as task_for_kind:
        recovered = recover_ingestion_dispatches()

    item.refresh_from_db()
    assert recovered == {"candidates": 0, "scheduled": 0, "reset": 0}
    assert item.dispatch_task_id == "durable-message-id"
    task_for_kind.assert_not_called()


def test_interactive_ingestion_tasks_have_a_dedicated_queue(settings):
    assert settings.CELERY_TASK_ROUTES["ingestion.tasks.process_upload_item"] == {
        "queue": "ingestion",
    }
    assert settings.CELERY_TASK_ROUTES["ingestion.tasks.process_reviewed_upload_item"] == {
        "queue": "ingestion",
    }
    assert "ingestion.tasks.process_ocr_job" not in settings.CELERY_TASK_ROUTES


@pytest.mark.django_db
def test_semantic_job_survives_broker_failure_and_recovers(
    settings,
    django_capture_on_commit_callbacks,
):
    settings.SEMANTIC_INDEX_RECOVERY_BATCH_SIZE = 20
    settings.SEMANTIC_INDEX_QUEUE_STALLED_SECONDS = 1
    settings.SEMANTIC_INDEX_RUNNING_STALLED_SECONDS = 1
    work = Work.objects.create(document_type=DocumentType.BOOK, title="索引恢复测试")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/index-recovery.pdf",
        sha256="a" * 64,
        byte_size=4096,
        status=Asset.Status.READY,
    )
    job = SemanticIndexJob.objects.create(
        operation=SemanticIndexJob.Operation.BUILD,
        status=SemanticIndexJob.Status.FAILED,
        asset=asset,
        task_id="lost-task",
        error_code="queue_unavailable",
        error_message="redis offline",
        finished_at=timezone.now() - timedelta(minutes=5),
    )

    with patch("catalog.services.semantic_indexing.dispatch_semantic_job") as dispatch:
        with django_capture_on_commit_callbacks(execute=True):
            recovered = recover_semantic_index_jobs()

    job.refresh_from_db()
    assert recovered == {"requeued": 1, "paused": 0}
    assert job.status == SemanticIndexJob.Status.QUEUED
    assert job.task_id != "lost-task"
    assert job.error_code == ""
    assert job.error_message == ""
    dispatch.assert_called_once_with(str(job.id), job.task_id)


def test_worker_task_probe_confirms_fresh_task_execution(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True

    result = run_worker_task_probe(timeout_seconds=2)

    assert result["executed"] is True
    assert result["detail"] == "新任务已由 Worker 执行"
    assert result["executed_at"]


def test_worker_task_probe_reports_broker_failure():
    with patch(
        "ingestion.management.commands.check_library_pipeline."
        "record_ingestion_worker_probe.apply_async",
        side_effect=ConnectionError("redis://secret@example.invalid unavailable"),
    ):
        result = run_worker_task_probe(timeout_seconds=1)

    assert result["executed"] is False
    assert "secret" not in result["detail"]
    assert "redis://***@example.invalid" in result["detail"]
