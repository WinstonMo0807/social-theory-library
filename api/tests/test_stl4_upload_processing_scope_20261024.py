"""Deferred acceptance: a batch must never control another file by edition alone."""
import pytest

from catalog.models import Asset, Edition, SemanticIndexJob, Work
from ingestion.models import ProcessingJob, UploadBatch, UploadItem
from ingestion.services.document_stages import with_document_stage_ids
from ingestion.services.processing_center import task_querysets

pytestmark = pytest.mark.django_db


def sample(actor):
    edition = Edition.objects.create(work=Work.objects.create(title="文件身份验收材料"))
    original = Asset.objects.create(edition=edition, kind="original", file="synthetic/source.pdf", sha256="a" * 64)
    derived = Asset.objects.create(edition=edition, kind="normalized", source_asset=original, file="synthetic/read.pdf", sha256="b" * 64)
    other = Asset.objects.create(edition=edition, kind="normalized", file="synthetic/other.pdf", sha256="c" * 64, is_current=True)
    batch = UploadBatch.objects.create(created_by=actor, expected_count=1)
    item = UploadItem.objects.create(batch=batch, edition=edition, asset=original, source_filename="source.pdf")
    return edition, original, derived, other, batch, item


def test_item_stages_and_batch_scope_follow_exact_derivation(admin_user):
    edition, original, derived, other, batch, item = sample(admin_user)
    own = ProcessingJob.objects.create(job_type="ocr", asset=derived, edition=edition, status="paused")
    intake = ProcessingJob.objects.create(job_type="text_extraction", upload_item=item)
    foreign = ProcessingJob.objects.create(job_type="ocr", asset=other, edition=edition, status="running")
    edition_only = ProcessingJob.objects.create(job_type="ocr", edition=edition)
    semantic = SemanticIndexJob.objects.create(asset=derived, operation="build", status="completed")
    SemanticIndexJob.objects.create(asset=other, operation="build", status="running")
    discovery = ProcessingJob.objects.create(job_type="discovery_index", asset=derived, edition=edition)
    row = with_document_stage_ids(UploadItem.objects.filter(pk=item.pk)).get()
    assert row.document_ocr_job_id == own.pk
    assert row.document_index_job_id == discovery.pk
    assert row.document_semantic_job_id == semantic.pk
    jobs, indexes, _, _ = task_querysets({"batch_id": str(batch.pk)}, admin_user)
    assert set(jobs.values_list("pk", flat=True)) == {own.pk, intake.pk, discovery.pk}
    assert not jobs.filter(pk__in=[foreign.pk, edition_only.pk]).exists()
    assert list(indexes.values_list("pk", flat=True)) == [semantic.pk]
    # A batch can hold an explicitly derived file; its root remains the identity.
    item.asset = derived
    item.save(update_fields=["asset"])
    source_job = ProcessingJob.objects.create(job_type="ocr", asset=original, edition=edition)
    assert with_document_stage_ids(UploadItem.objects.filter(pk=item.pk)).get().document_ocr_job_id == source_job.pk


def test_batch_link_rejects_foreign_owner_and_invalid_id(api_client, admin_user, reader_user):
    _, _, _, _, batch, _ = sample(reader_user)
    api_client.force_authenticate(admin_user)
    url = "/api/ingestion/processing-workspace/"
    assert api_client.get(url, {"batch_id": str(batch.pk)}).status_code == 404
    assert api_client.get(url, {"batch_id": "not-a-batch"}).status_code == 400


def test_item_without_file_does_not_borrow_current_edition_tasks(admin_user):
    edition, _, _, other, batch, _ = sample(admin_user)
    waiting = UploadItem.objects.create(batch=batch, edition=edition, source_filename="waiting.pdf")
    ProcessingJob.objects.create(job_type="ocr", asset=other, edition=edition)
    assert with_document_stage_ids(UploadItem.objects.filter(pk=waiting.pk)).get().document_ocr_job_id is None
