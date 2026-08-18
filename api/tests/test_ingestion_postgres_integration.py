from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import close_old_connections, connection, connections, transaction
from django.utils import timezone

from catalog.models import Asset, Edition, OcrStatus, Page, TextBlock, Work
from ingestion.models import (
    FieldLock,
    MetadataCandidate,
    ProcessingAttempt,
    ProcessingJob,
    SourceRecord,
    UploadBatch,
    UploadItem,
)
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.dispatch import recover_ingestion_dispatches
from ingestion.services.metadata import Candidate
from ingestion.services.ocr_pdf import create_searchable_ocr_pdf
from ingestion.services.pipeline import run_pipeline
from ingestion.services.processing import (
    recover_stalled_processing_jobs,
    run_external_enrichment_job,
)
from ingestion.tasks import _run_tracked

from .test_ingestion_integration import build_test_pdf


pytestmark = [
    pytest.mark.postgres_integration,
    pytest.mark.django_db(transaction=True),
]


@pytest.fixture(autouse=True)
def require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL")


def _item(admin_user, *, edition=None, status=UploadItem.Status.RECEIVED):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        external_enrichment_enabled=False,
    )
    return UploadItem.objects.create(
        batch=batch,
        source_filename="postgres-locking.pdf",
        edition=edition,
        status=status,
    )


def _edition(title="PostgreSQL metadata review"):
    work = Work.objects.create(document_type="book", title=title)
    return Edition.objects.create(work=work, canonical_filename="postgres-locking.pdf")


def _one_page_pdf(path: Path) -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((60, 90), "OCR source text", fontname="helv", fontsize=12)
    document.save(path)
    document.close()
    return path.read_bytes()


@contextmanager
def _harmless_pipeline_side_effects():
    with (
        patch("ingestion.services.pipeline.index_asset", return_value={"indexed": 0}),
        patch("ingestion.services.pipeline.queue_semantic_job"),
        patch("ingestion.services.pipeline.queue_page_label_job"),
        patch("ingestion.services.pipeline.generate_cover_candidates", return_value=[]),
        patch("ingestion.services.pipeline.generate_theory_review_tasks", return_value=0),
        patch("ingestion.services.pipeline.detect_publication_places", return_value=[]),
    ):
        yield


def test_postgres_metadata_candidates_lock_parent_and_nullable_source_record(admin_user):
    item = _item(admin_user)
    candidate = Candidate("title", "Shared title", "embedded_pdf", 0.9)
    first_insert = Event()
    second_entered = Event()
    release = Event()
    results = []
    original_create = MetadataCandidate.objects.create
    first_create_lock = Lock()
    first_create_seen = False

    def controlled_create(*args, **kwargs):
        nonlocal first_create_seen
        with first_create_lock:
            is_first = not first_create_seen
            first_create_seen = True
        if is_first:
            first_insert.set()
            release.wait(timeout=5)
        return original_create(*args, **kwargs)

    def persist_once(mark_second=False):
        close_old_connections()
        try:
            if mark_second:
                second_entered.set()
            results.append(persist_metadata_candidates(item, [candidate], {"title": "Shared title"}))
        finally:
            connections.close_all()

    with patch.object(MetadataCandidate.objects, "create", side_effect=controlled_create):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(persist_once, False)
            assert first_insert.wait(timeout=5)
            second = executor.submit(persist_once, True)
            assert second_entered.wait(timeout=5)
            with pytest.raises(FutureTimeoutError):
                second.result(timeout=0.25)
            release.set()
            first.result(timeout=10)
            second.result(timeout=10)

    assert MetadataCandidate.objects.filter(upload_item=item, field_name="title").count() == 1
    assert sorted(result["added"] for result in results) == [0, 1]
    stored = MetadataCandidate.objects.get(upload_item=item, field_name="title")
    assert stored.source_record_id is None

    source = SourceRecord.objects.create(
        upload_item=item,
        provider="test-provider",
        operation="metadata",
        status=SourceRecord.Status.SUCCEEDED,
    )
    with_source = Candidate(
        "publisher",
        "Source-backed publisher",
        "provider:test",
        0.8,
        evidence={"source_record_id": str(source.id)},
    )
    persist_metadata_candidates(item, [with_source], {})
    assert MetadataCandidate.objects.get(
        upload_item=item,
        field_name="publisher",
    ).source_record_id == source.id


@pytest.mark.parametrize("has_source_asset", [False, True])
def test_postgres_ocr_pdf_locks_only_asset_with_nullable_source_asset(
    admin_user,
    tmp_path,
    settings,
    has_source_asset,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    edition = _edition(f"OCR lock {has_source_asset}")
    payload = _one_page_pdf(tmp_path / f"ocr-{has_source_asset}.pdf")
    original = None
    if has_source_asset:
        original = Asset.objects.create(
            edition=edition,
            kind=Asset.Kind.ORIGINAL,
            file=SimpleUploadedFile("original.pdf", payload, content_type="application/pdf"),
            sha256="1" * 64,
            byte_size=len(payload),
            page_count=1,
            status=Asset.Status.READY,
            validation_status=Asset.ValidationStatus.VALID,
        )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("normalized.pdf", payload, content_type="application/pdf"),
        sha256="2" * 64,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        source_asset=original,
    )
    page = Page.objects.create(
        asset=normalized,
        index=1,
        text="OCR source text",
        normalized_text="ocr source text",
        text_source=Page.TextSource.OCR,
        width=595,
        height=842,
    )
    TextBlock.objects.create(
        page=page,
        order=0,
        text="OCR source text",
        normalized_text="ocr source text",
        bbox=[50, 50, 260, 110],
        confidence=0.99,
    )

    derivative = create_searchable_ocr_pdf(
        normalized,
        processor="postgres-test",
        processor_version="1",
    )

    assert derivative.kind == Asset.Kind.OCR_PDF
    assert derivative.status == Asset.Status.READY
    assert derivative.source_asset_id == (original.id if original else normalized.id)


def test_postgres_failed_item_opens_and_saves_metadata_review_without_reupload(
    api_client,
    admin_user,
):
    no_edition = _item(admin_user, status=UploadItem.Status.FAILED)
    edition = _edition("Failed metadata")
    edition.ocr_status = OcrStatus.SUCCEEDED
    edition.save(update_fields=["ocr_status", "updated_at"])
    failed = _item(admin_user, edition=edition, status=UploadItem.Status.FAILED)
    failed.workflow_state = UploadItem.WorkflowState.FAILED
    failed.error_code = "metadata_failed"
    failed.error_message = "旧版本的元数据阶段失败"
    failed.save(
        update_fields=["workflow_state", "error_code", "error_message", "updated_at"]
    )
    MetadataCandidate.objects.create(
        upload_item=failed,
        field_name="title",
        value="Recovered metadata",
        source="embedded_pdf",
        confidence=0.9,
    )
    api_client.force_authenticate(admin_user)

    without_relation = api_client.get(f"/api/ingestion/items/{no_edition.id}/")
    detail = api_client.get(f"/api/ingestion/items/{failed.id}/")

    assert without_relation.status_code == 200
    assert without_relation.data["review_data"] is None
    assert detail.status_code == 200
    assert detail.data["status"] == UploadItem.Status.FAILED
    assert detail.data["review_data"]["ocr_status"] == OcrStatus.SUCCEEDED
    assert len(detail.data["metadata_candidates"]) == 1

    response = api_client.put(
        f"/api/ingestion/items/{failed.id}/review/",
        {
            "title": "Recovered metadata",
            "document_type": "book",
            "language": "en",
            "authors": [],
            "lock_fields": ["title"],
            "retry_publication": False,
        },
        format="json",
    )

    assert response.status_code == 200
    failed.refresh_from_db()
    edition.refresh_from_db()
    edition.work.refresh_from_db()
    assert failed.status == UploadItem.Status.READY
    assert failed.edition_id == edition.id
    assert edition.work.title == "Recovered metadata"
    assert FieldLock.objects.filter(edition=edition, field_name="title").exists()
    assert MetadataCandidate.objects.get(
        upload_item=failed,
        field_name="title",
    ).lifecycle == MetadataCandidate.Lifecycle.ACCEPTED


def test_postgres_historical_metadata_failure_retry_is_idempotent_and_reuses_catalog(
    api_client,
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.REQUIRE_EXTERNAL_SEARCH = False
    settings.CELERY_TASK_ALWAYS_EAGER = False
    source = tmp_path / "metadata-retry.pdf"
    payload = build_test_pdf(source, marker="metadata retry")
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        external_enrichment_enabled=False,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="metadata-retry.pdf",
        file=SimpleUploadedFile("metadata-retry.pdf", payload, content_type="application/pdf"),
    )
    with _harmless_pipeline_side_effects():
        run_pipeline(str(item.id))

    item.refresh_from_db()
    edition_id = item.edition_id
    work_id = item.edition.work_id
    asset_ids = set(item.edition.assets.values_list("id", flat=True))
    candidate_count = item.metadata_candidates.count()
    item.edition.work.title = "Administrator-confirmed title"
    item.edition.work.save(update_fields=["title", "updated_at"])
    FieldLock.objects.create(
        edition=item.edition,
        field_name="title",
        locked_by=admin_user,
        locked_value="Administrator-confirmed title",
        reason="recovery test",
    )
    Edition.objects.filter(pk=edition_id).update(ocr_status=OcrStatus.SUCCEEDED)
    UploadItem.objects.filter(pk=item.pk).update(
        status=UploadItem.Status.FAILED,
        workflow_state=UploadItem.WorkflowState.FAILED,
        dispatch_status=UploadItem.DispatchStatus.FAILED,
        error_code="metadata_failed",
        error_message="metadata extraction interrupted after OCR",
    )
    api_client.force_authenticate(admin_user)

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        first = api_client.post(f"/api/ingestion/items/{item.id}/retry/")
        item.refresh_from_db()
        retry_count = item.retry_count
        second = api_client.post(f"/api/ingestion/items/{item.id}/retry/")

    assert first.status_code == second.status_code == 202
    assert second.data["reused"] is True
    item.refresh_from_db()
    assert item.retry_count == retry_count
    assert task_factory.return_value.apply_async.call_count == 1

    with _harmless_pipeline_side_effects():
        recovered = run_pipeline(str(item.id))

    recovered.edition.work.refresh_from_db()
    assert recovered.status == UploadItem.Status.READY
    assert recovered.edition_id == edition_id
    assert recovered.edition.work_id == work_id
    assert recovered.edition.work.title == "Administrator-confirmed title"
    assert set(recovered.edition.assets.values_list("id", flat=True)) == asset_ids
    assert recovered.metadata_candidates.count() == candidate_count


def test_postgres_duplicate_upload_task_delivery_has_one_database_claim(
    admin_user,
):
    item = _item(admin_user)
    task_id = "postgres-duplicate-upload-task"
    UploadItem.objects.filter(pk=item.pk).update(
        dispatch_status=UploadItem.DispatchStatus.QUEUED,
        dispatch_task_id=task_id,
    )
    entered = Event()
    release = Event()
    call_lock = Lock()
    calls = 0

    def processor(item_id):
        nonlocal calls
        with call_lock:
            calls += 1
        entered.set()
        release.wait(timeout=10)
        return UploadItem.objects.get(pk=item_id)

    def execute():
        close_old_connections()
        try:
            fake_task = SimpleNamespace(
                request=SimpleNamespace(id=task_id, hostname="postgres-worker")
            )
            return _run_tracked(fake_task, str(item.id), processor)
        finally:
            connections.close_all()

    with patch("ingestion.tasks.cache.add", side_effect=ConnectionError("redis unavailable")):
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(execute)
            assert entered.wait(timeout=5)
            second = executor.submit(execute)
            duplicate = second.result(timeout=10)
            release.set()
            completed = first.result(timeout=10)

    assert calls == 1
    assert duplicate["status"] == "already_running"
    assert completed["status"] == UploadItem.Status.RECEIVED
    assert ProcessingAttempt.objects.filter(
        upload_item=item,
        idempotency_key=f"dispatch:{task_id}",
        status="completed",
    ).count() == 1


def test_postgres_interrupted_upload_worker_is_requeued_with_new_claim(
    admin_user,
    settings,
):
    settings.INGESTION_STAGE_STALLED_SECONDS = 1
    item = _item(admin_user, status=UploadItem.Status.METADATA)
    old_task_id = "crashed-upload-worker"
    stale_time = timezone.now() - timedelta(minutes=5)
    UploadItem.objects.filter(pk=item.pk).update(
        dispatch_status=UploadItem.DispatchStatus.RUNNING,
        dispatch_task_id=old_task_id,
        last_dispatched_at=stale_time,
        updated_at=stale_time,
    )
    ProcessingAttempt.objects.create(
        upload_item=item,
        stage="task_execution",
        status="started",
        idempotency_key=f"dispatch:{old_task_id}",
        correlation_id=old_task_id,
        started_at=stale_time,
    )

    with patch("ingestion.services.dispatch._task_for_kind") as task_factory:
        recovered = recover_ingestion_dispatches()

    item.refresh_from_db()
    assert recovered == {"candidates": 1, "scheduled": 1, "reset": 1}
    assert item.status == UploadItem.Status.RECEIVED
    assert item.dispatch_status == UploadItem.DispatchStatus.QUEUED
    assert item.dispatch_task_id != old_task_id
    task_factory.return_value.apply_async.assert_called_once_with(
        args=[str(item.id)],
        task_id=item.dispatch_task_id,
        ignore_result=True,
    )

    fake_task = SimpleNamespace(
        request=SimpleNamespace(id=item.dispatch_task_id, hostname="recovery-worker")
    )
    result = _run_tracked(
        fake_task,
        str(item.id),
        lambda item_id: UploadItem.objects.get(pk=item_id),
    )
    assert result["status"] == UploadItem.Status.RECEIVED
    assert ProcessingAttempt.objects.filter(
        upload_item=item,
        idempotency_key=f"dispatch:{item.dispatch_task_id}",
        status="completed",
    ).exists()


def test_postgres_processing_job_claim_crash_recovery_and_duplicate_retry(
    admin_user,
    settings,
):
    settings.INGESTION_QUEUE_STALLED_SECONDS = 1
    settings.INGESTION_STAGE_STALLED_SECONDS = 1
    edition = _edition("Processing claim")
    item = _item(admin_user, edition=edition)
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        status=ProcessingJob.Status.RUNNING,
        upload_item=item,
        edition=edition,
        task_id="crashed-worker-task",
        attempt=1,
        max_attempts=3,
        started_at=timezone.now() - timedelta(minutes=5),
    )
    ProcessingJob.objects.filter(pk=job.pk).update(
        updated_at=timezone.now() - timedelta(minutes=5)
    )

    with patch(
        "ingestion.services.processing.dispatch_external_enrichment_job",
        return_value=True,
    ) as dispatch:
        recovered = recover_stalled_processing_jobs()

    job.refresh_from_db()
    assert recovered == {"candidates": 1, "requeued": 1, "exhausted": 0}
    assert job.status == ProcessingJob.Status.PENDING
    assert job.task_id != "crashed-worker-task"
    assert job.stats["recovery"]["reason"] == "worker_interrupted"
    dispatch.assert_called_once_with(str(job.id), job.task_id)

    loader_calls = 0

    def loader(*_args, **_kwargs):
        nonlocal loader_calls
        loader_calls += 1
        return [], []

    first = run_external_enrichment_job(
        str(job.id),
        task_id=job.task_id,
        candidate_loader=loader,
    )
    repeated = run_external_enrichment_job(
        str(job.id),
        task_id=job.task_id,
        candidate_loader=loader,
    )

    first.refresh_from_db()
    repeated.refresh_from_db()
    assert first.status == repeated.status == ProcessingJob.Status.SUCCEEDED
    assert loader_calls == 1
    assert first.attempt == 2


def test_postgres_processing_recovery_skip_locked_uses_independent_connections(
    admin_user,
    settings,
):
    settings.INGESTION_QUEUE_STALLED_SECONDS = 1
    settings.INGESTION_STAGE_STALLED_SECONDS = 1
    edition = _edition("SKIP LOCKED recovery")
    item = _item(admin_user, edition=edition)
    stale_time = timezone.now() - timedelta(minutes=5)
    locked_job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        status=ProcessingJob.Status.RUNNING,
        upload_item=item,
        edition=edition,
        task_id="locked-stale-task",
        attempt=1,
        started_at=stale_time,
    )
    available_job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        status=ProcessingJob.Status.RUNNING,
        upload_item=item,
        edition=edition,
        task_id="available-stale-task",
        attempt=1,
        started_at=stale_time,
    )
    ProcessingJob.objects.filter(pk__in=[locked_job.pk, available_job.pk]).update(
        updated_at=stale_time
    )
    locked = Event()
    release = Event()

    def hold_row_lock():
        close_old_connections()
        try:
            with transaction.atomic():
                ProcessingJob.objects.select_for_update().get(pk=locked_job.pk)
                locked.set()
                release.wait(timeout=10)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as executor:
        holder = executor.submit(hold_row_lock)
        assert locked.wait(timeout=5)
        with patch(
            "ingestion.services.processing.dispatch_external_enrichment_job",
            return_value=True,
        ) as dispatch:
            first = recover_stalled_processing_jobs(limit=10)
            assert first == {"candidates": 1, "requeued": 1, "exhausted": 0}
            available_job.refresh_from_db()
            locked_job.refresh_from_db()
            assert available_job.status == ProcessingJob.Status.PENDING
            assert locked_job.status == ProcessingJob.Status.RUNNING
            assert dispatch.call_count == 1
        release.set()
        holder.result(timeout=10)

    with patch(
        "ingestion.services.processing.dispatch_external_enrichment_job",
        return_value=True,
    ) as dispatch:
        second = recover_stalled_processing_jobs(limit=10)
    locked_job.refresh_from_db()
    assert second == {"candidates": 1, "requeued": 1, "exhausted": 0}
    assert locked_job.status == ProcessingJob.Status.PENDING
    dispatch.assert_called_once_with(str(locked_job.id), locked_job.task_id)
