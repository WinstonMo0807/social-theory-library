"""Deferred acceptance: a failed original check must never delete a staging object."""
from hashlib import sha256
from unittest.mock import Mock, patch
import pytest
from django.core.files.base import ContentFile
from catalog.models import Asset, Edition, Work
from ingestion.models import AuditEvent, UploadBatch, UploadItem
from ingestion.services.r2_staging import R2CleanupBlocked, cleanup_r2_staging_object, recover_r2_staging_jobs

pytestmark = pytest.mark.django_db


@pytest.fixture
def cleanup_item(admin_user, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    payload = b"%PDF-synthetic-original-for-deferred-check"
    work = Work.objects.create(title="合成原件保护样本", document_type="book")
    asset = Asset.objects.create(edition=Edition.objects.create(work=work), kind="original", sha256=sha256(payload).hexdigest(), byte_size=len(payload))
    asset.file.save("original.pdf", ContentFile(payload), save=True)
    item = UploadItem.objects.create(batch=UploadBatch.objects.create(created_by=admin_user),
        source_filename="synthetic.pdf", asset=asset, status="ready", staging_status="cleanup_pending",
        staging_backend="r2", sha256=asset.sha256, byte_size=len(payload), staging_file_size=len(payload), file="incoming/synthetic.pdf")
    item.staging_object_key = f"staging/{item.pk}.pdf"
    item.save(update_fields=["staging_object_key"])
    return item, asset


@pytest.mark.parametrize("damage", ["missing", "same_size_corruption", "size", "digest", "other_object", "not_ready", "derivative"])
def test_cleanup_retains_staging_when_permanent_copy_cannot_be_proven(cleanup_item, damage):
    item, asset = cleanup_item
    if damage == "missing":
        asset.file.storage.delete(asset.file.name)
    elif damage == "same_size_corruption":
        with open(asset.file.path, "wb") as output:
            output.write(b"x" * asset.byte_size)
    elif damage == "size":
        item.staging_file_size += 1
    elif damage == "digest":
        item.sha256 = "b" * 64
    elif damage == "other_object":
        item.staging_object_key = "staging/someone-else.pdf"
    elif damage == "not_ready":
        item.status = "failed"
    else:
        asset.kind = "ocr_pdf"
        asset.save(update_fields=["kind"])
    item.save()
    with patch("ingestion.services.r2_staging.r2_client") as client:
        with pytest.raises(R2CleanupBlocked):
            cleanup_r2_staging_object(item.pk)
        client.assert_not_called()
    item.refresh_from_db()
    assert item.staging_status == "cleanup_pending" and item.staging_error_code == R2CleanupBlocked.error_code
    assert item.staging_cleanup_attempts == 1
    assert not AuditEvent.objects.filter(action="r2_staging_cleanup_completed", object_id=str(item.pk)).exists()
    with patch("ingestion.services.r2_staging.queue_r2_staging_job") as queue:
        recover_r2_staging_jobs()
        queue.assert_not_called()


def test_success_preserves_original_and_records_actual_full_verification(cleanup_item):
    item, asset = cleanup_item
    with open(asset.file.path, "rb") as original:
        before = original.read()
    client = Mock()
    with patch("ingestion.services.r2_staging.r2_client", return_value=client):
        result = cleanup_r2_staging_object(item.pk)
        repeated = cleanup_r2_staging_object(item.pk)
    assert result["status"] == "cleaned" and repeated["idempotent"]
    client.delete_object.assert_called_once()
    assert client.delete_object.call_args.kwargs["Key"] == f"staging/{item.pk}.pdf"
    with open(asset.file.path, "rb") as original:
        assert original.read() == before
    event = AuditEvent.objects.get(action="r2_staging_cleanup_completed", object_id=str(item.pk))
    assert event.after["verification"] == "full_local_sha256"
    assert event.after["original_sha256"] == sha256(before).hexdigest()
