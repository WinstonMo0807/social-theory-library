"""Document stages must not depend on the independently paginated jobs list."""
import pytest

from catalog.models import Asset, Edition, SemanticIndexJob, Work
from ingestion.models import ProcessingAttempt, ProcessingJob, UploadBatch, UploadItem
from ingestion.services.document_stages import attach_document_stages, with_document_stage_ids

pytestmark = pytest.mark.django_db


def test_document_page_uses_latest_own_stages_despite_newer_unrelated_tasks(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="分阶段真实状态"))
    asset = Asset.objects.create(edition=edition, kind="normalized", file="synthetic/stages.pdf", sha256="a" * 64, byte_size=20, status="ready", is_current=True)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, asset=asset, source_filename="document-stage-target.pdf", status="failed", error_message="OCR已失败，文件不应被改为失败")
    file_attempt = ProcessingAttempt.objects.create(upload_item=item, stage="text_extraction", status="completed")
    ProcessingJob.objects.create(upload_item=item, job_type="ocr", status="failed", error_message="旧失败")
    latest_ocr = ProcessingJob.objects.create(edition=edition, asset=asset, job_type="ocr", status="paused", progress=42)
    ProcessingJob.objects.create(edition=edition, job_type="semantic_index", status="succeeded", progress=100)
    semantic = SemanticIndexJob.objects.create(asset=asset, operation="build", status="failed", progress=12, error_message="当前索引失败")
    for _ in range(35):
        ProcessingJob.objects.create(job_type="ocr", status="running")
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/ingestion/items/", {"scope": "processing", "search": "document-stage-target"})
    assert response.status_code == 200, response.data
    assert response.data["count"] == 1
    stages = response.data["results"][0]["document_stages"]
    assert stages["file"]["status"] == "completed"
    assert stages["file"]["attempt_id"] == str(file_attempt.pk)
    assert stages["file"]["progress"] is None
    assert stages["ocr"]["job_id"] == str(latest_ocr.pk)
    assert stages["ocr"]["status"] == "paused" and stages["ocr"]["progress"] == 42
    assert stages["index"]["job_id"] == str(semantic.pk)
    assert stages["index"]["error"] == "当前索引失败"


def test_missing_document_tasks_are_unknown_and_stale_assets_are_not_used(admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="无当前任务"))
    old = Asset.objects.create(edition=edition, kind="normalized", file="synthetic/old.pdf", sha256="b" * 64, byte_size=20, is_current=False)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="waiting.pdf", status="received")
    ProcessingJob.objects.create(asset=old, edition=edition, job_type="ocr", status="succeeded", progress=100)
    SemanticIndexJob.objects.create(asset=old, operation="build", status="completed", progress=100)
    row = attach_document_stages(with_document_stage_ids(UploadItem.objects.filter(pk=item.pk)))[0]
    assert row.document_stages["file"]["status"] == "received"
    assert row.document_stages["ocr"] is None
    assert row.document_stages["index"] is None
