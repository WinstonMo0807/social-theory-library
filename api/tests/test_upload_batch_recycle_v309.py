import pytest

from ingestion.models import UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


def test_clearing_upload_batch_recycles_queue_without_relabeling_completed_items(api_client, admin_user):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=2,
        completed_count=1,
        failed_count=0,
        status=UploadBatch.Status.PARTIAL,
    )
    UploadItem.objects.create(batch=batch, source_filename="done.pdf", status=UploadItem.Status.READY)
    UploadItem.objects.create(batch=batch, source_filename="waiting.pdf", status=UploadItem.Status.FAILED)
    api_client.force_authenticate(admin_user)

    response = api_client.delete(f"/api/ingestion/batches/{batch.pk}/")
    assert response.status_code == 200, response.data
    batch.refresh_from_db()
    assert batch.status == UploadBatch.Status.PARTIAL
    assert batch.completed_count == 1 and batch.failed_count == 1
    assert not UploadItem.objects.filter(batch=batch).exists()
    assert UploadItem.all_objects.filter(batch=batch).count() == 2


def test_clearing_fully_completed_batch_preserves_completed_status(api_client, admin_user):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        completed_count=1,
        failed_count=0,
        status=UploadBatch.Status.COMPLETED,
    )
    UploadItem.objects.create(batch=batch, source_filename="done.pdf", status=UploadItem.Status.PUBLISHED)
    api_client.force_authenticate(admin_user)

    response = api_client.delete(f"/api/ingestion/batches/{batch.pk}/")

    assert response.status_code == 200, response.data
    batch.refresh_from_db()
    assert batch.status == UploadBatch.Status.COMPLETED
