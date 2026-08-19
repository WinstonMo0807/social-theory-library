from unittest.mock import patch

import pytest

from ingestion.models import ProcessingAttempt, ProcessingJob, UploadBatch, UploadItem
from ingestion.services.dispatch import (
    dispatch_upload_item,
    recover_ingestion_dispatches,
    schedule_upload_item,
)
from ingestion.services.files import SourceFileMissing
from ingestion.services.pipeline import run_pipeline
from ingestion.services.prerequisites import initial_ingestion_block_reason
from ingestion.tasks import process_upload_item


pytestmark = pytest.mark.django_db


def make_batch(admin_user, *, count=1):
    return UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=count,
        external_enrichment_enabled=False,
    )


def make_r2_item(admin_user, staging_status, **values):
    batch = values.pop("batch", None) or make_batch(admin_user)
    return UploadItem.objects.create(
        batch=batch,
        source_filename=values.pop("source_filename", f"{staging_status}.pdf"),
        processing_token=values.pop("processing_token", f"token-{staging_status}-v281"),
        staging_backend=UploadItem.StagingBackend.R2,
        staging_status=staging_status,
        staging_object_key=values.pop("staging_object_key", f"staging/{staging_status}-v281.pdf"),
        staging_upload_id=values.pop("staging_upload_id", f"upload-{staging_status}-v281"),
        **values,
    )


@pytest.mark.parametrize(
    "staging_status",
    [
        UploadItem.StagingStatus.UPLOADING,
        UploadItem.StagingStatus.UPLOADED,
        UploadItem.StagingStatus.IMPORTING,
        UploadItem.StagingStatus.IMPORT_FAILED,
    ],
)
def test_r2_pre_import_rows_are_excluded_from_normal_ingestion_recovery(
    admin_user,
    staging_status,
):
    item = make_r2_item(admin_user, staging_status)

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        result = recover_ingestion_dispatches()

    item.refresh_from_db()
    assert result == {"candidates": 0, "scheduled": 0, "reset": 0}
    assert item.dispatch_task_id == ""
    assert item.dispatch_status == UploadItem.DispatchStatus.PENDING
    task_factory.assert_not_called()


def test_schedule_and_dispatch_both_guard_r2_pre_import(admin_user):
    item = make_r2_item(admin_user, UploadItem.StagingStatus.UPLOADED)

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        assert schedule_upload_item(str(item.id)) is None
        task_factory.assert_not_called()

        legacy_task_id = "legacy-r2-dispatch"
        UploadItem.objects.filter(pk=item.pk).update(
            dispatch_status=UploadItem.DispatchStatus.QUEUED,
            dispatch_task_id=legacy_task_id,
        )
        assert dispatch_upload_item(str(item.id), legacy_task_id) is False

    item.refresh_from_db()
    assert item.dispatch_status == UploadItem.DispatchStatus.PENDING
    assert item.dispatch_task_id == ""
    assert item.dispatch_error == ""
    task_factory.assert_not_called()


def test_legacy_worker_message_exits_as_prerequisite_not_ready(admin_user):
    item = make_r2_item(
        admin_user,
        UploadItem.StagingStatus.UPLOADED,
        dispatch_status=UploadItem.DispatchStatus.QUEUED,
        dispatch_task_id="legacy-r2-worker-message",
    )

    result = process_upload_item.run(str(item.id))

    item.refresh_from_db()
    assert result == {
        "id": str(item.id),
        "status": "prerequisite_not_ready",
        "reason": "staging_not_ready",
    }
    assert item.status == UploadItem.Status.RECEIVED
    assert item.error_code == ""
    assert item.dispatch_status == UploadItem.DispatchStatus.PENDING
    assert item.dispatch_task_id == ""
    execution = ProcessingAttempt.objects.get(
        upload_item=item,
        stage="task_execution",
    )
    assert execution.status == "completed"
    assert execution.output_summary == {
        "outcome": "prerequisite_not_ready",
        "reason": "staging_not_ready",
    }


def test_imported_r2_and_normal_upload_recovery_remain_available(
    admin_user,
    django_capture_on_commit_callbacks,
):
    batch = make_batch(admin_user, count=2)
    imported = make_r2_item(
        admin_user,
        UploadItem.StagingStatus.IMPORTED,
        batch=batch,
        processing_token="token-imported-ready-v281",
        file="incoming/imported-ready-v281.pdf",
    )
    normal = UploadItem.objects.create(
        batch=batch,
        source_filename="normal-ready-v281.pdf",
        processing_token="token-normal-ready-v281",
        file="incoming/normal-ready-v281.pdf",
    )

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        with django_capture_on_commit_callbacks(execute=True):
            result = recover_ingestion_dispatches()

    imported.refresh_from_db()
    normal.refresh_from_db()
    assert result == {"candidates": 2, "scheduled": 2, "reset": 0}
    assert imported.dispatch_status == UploadItem.DispatchStatus.QUEUED
    assert normal.dispatch_status == UploadItem.DispatchStatus.QUEUED
    assert task_factory.return_value.apply_async.call_count == 2


def test_reviewed_dispatch_does_not_require_upload_item_file(
    admin_user,
    django_capture_on_commit_callbacks,
):
    item = UploadItem.objects.create(
        batch=make_batch(admin_user),
        source_filename="reviewed-without-source.pdf",
        status=UploadItem.Status.READY,
        dispatch_kind=UploadItem.DispatchKind.REVIEWED,
        dispatch_status=UploadItem.DispatchStatus.PENDING,
    )

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        with django_capture_on_commit_callbacks(execute=True):
            result = recover_ingestion_dispatches()

    item.refresh_from_db()
    assert result == {"candidates": 1, "scheduled": 1, "reset": 0}
    assert item.dispatch_status == UploadItem.DispatchStatus.QUEUED
    task_factory.return_value.apply_async.assert_called_once()


def test_missing_formal_source_is_a_named_storage_invariant(admin_user):
    item = UploadItem.objects.create(
        batch=make_batch(admin_user),
        source_filename="missing-source-v281.pdf",
    )

    with pytest.raises(SourceFileMissing) as raised:
        run_pipeline(str(item.id))

    item.refresh_from_db()
    assert raised.value.error_code == "source_file_missing"
    assert "file associated" not in str(raised.value)
    assert item.status == UploadItem.Status.FAILED
    assert item.error_code == "source_file_missing"


def test_imported_r2_without_file_is_reported_as_invariant(admin_user):
    item = make_r2_item(admin_user, UploadItem.StagingStatus.IMPORTED)

    assert initial_ingestion_block_reason(item) == "staging_import_missing_file"
    assert schedule_upload_item(str(item.id)) is None


@pytest.mark.parametrize(
    ("staging_status", "error_code", "detail"),
    [
        (UploadItem.StagingStatus.UPLOADING, "staging_not_ready", "PDF 尚未导入正式书库存储。"),
        (UploadItem.StagingStatus.UPLOADED, "staging_not_ready", "PDF 尚未导入正式书库存储。"),
        (UploadItem.StagingStatus.IMPORTING, "staging_not_ready", "PDF 尚未导入正式书库存储。"),
        (UploadItem.StagingStatus.EXPIRED, "staging_expired", "临时上传已过期，需要重新上传 PDF。"),
        (UploadItem.StagingStatus.ABORTED, "staging_aborted", "上传已取消，不能进入入库识别。"),
    ],
)
def test_generic_retry_never_runs_normal_ingestion_for_r2_pre_import(
    api_client,
    admin_user,
    staging_status,
    error_code,
    detail,
):
    item = make_r2_item(admin_user, staging_status)
    api_client.force_authenticate(admin_user)

    with patch("ingestion.views.schedule_upload_item") as schedule:
        response = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    assert response.status_code == 409
    assert response.data["error_code"] == error_code
    assert response.data["detail"] == detail
    schedule.assert_not_called()


def test_generic_retry_routes_import_failure_to_r2_import_job(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
):
    item = make_r2_item(
        admin_user,
        UploadItem.StagingStatus.IMPORT_FAILED,
        staging_error_code="temporary_r2_failure",
        staging_error_message="temporary import failure",
    )
    api_client.force_authenticate(admin_user)

    with patch("ingestion.services.r2_staging.dispatch_r2_staging_job", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    item.refresh_from_db()
    assert response.status_code == 202
    assert response.data["action"] == "retry_import"
    assert item.staging_status == UploadItem.StagingStatus.UPLOADED
    assert ProcessingJob.objects.filter(
        upload_item=item,
        job_type=ProcessingJob.JobType.R2_STAGING,
        stats__phase="import",
    ).exists()


def test_generic_retry_reports_imported_r2_without_formal_file(
    api_client,
    admin_user,
):
    item = make_r2_item(admin_user, UploadItem.StagingStatus.IMPORTED)
    api_client.force_authenticate(admin_user)

    response = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    assert response.status_code == 409
    assert response.data["error_code"] == "staging_import_missing_file"


def test_non_superuser_admin_can_retry_r2_import_without_permission_expansion(
    api_client,
    admin_user,
    django_capture_on_commit_callbacks,
):
    assert admin_user.role == "admin"
    assert admin_user.is_superuser is False
    item = make_r2_item(admin_user, UploadItem.StagingStatus.IMPORT_FAILED)
    api_client.force_authenticate(admin_user)

    with patch("ingestion.services.r2_staging.dispatch_r2_staging_job", return_value=True):
        with django_capture_on_commit_callbacks(execute=True):
            response = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    assert response.status_code == 202
    assert response.data["action"] == "retry_import"
