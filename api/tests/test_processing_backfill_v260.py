from io import StringIO
import json
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command

from catalog.models import (
    OcrStatus,
    Page,
    SemanticChunk,
    SiteSetting,
    SemanticIndexJob,
    SemanticIndexVersion,
)
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.extract import ExtractedBlock, ExtractedPage
from ingestion.services.processing import run_ocr_job
from catalog.services.semantic_indexing import (
    activate_semantic_index_version,
    dispatch_semantic_version_batch,
    index_semantic_asset,
    maybe_activate_semantic_index_version,
    stage_semantic_index_version,
    stage_semantic_snapshot_version,
)

from .test_resilient_publication_v260 import create_item_with_files


def semantic_runtime(tmp_path):
    return {
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "model_repo_id": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "model_local_path": str(tmp_path / "models"),
        "model_revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42",
        "dimensions": 384,
        "pooling": "useModel",
        "offline_mode": True,
        "embedder_name": "social-science-library",
    }


@pytest.mark.django_db(transaction=True)
def test_semantic_candidate_stays_paused_and_advances_one_batch_at_a_time(
    settings,
    tmp_path,
):
    assets = []
    for title in ("候选索引甲", "候选索引乙"):
        _work, edition, _original, normalized = create_item_with_files(
            settings,
            tmp_path,
            title=title,
        )
        edition.ocr_status = OcrStatus.NOT_REQUIRED
        edition.save(update_fields=["ocr_status", "updated_at"])
        assets.append(normalized)

    old_active = SemanticIndexVersion.objects.create(
        uid="semantic_passages_old",
        provider="huggingFace",
        status=SemanticIndexVersion.Status.ACTIVE,
    )
    with patch("catalog.services.semantic_indexing.ensure_semantic_index"):
        candidate = stage_semantic_index_version(
            semantic_runtime(tmp_path),
            auto_dispatch=False,
        )

    assert candidate.jobs.count() == 2
    assert candidate.jobs.filter(status=SemanticIndexJob.Status.PAUSED).count() == 2
    assert maybe_activate_semantic_index_version(candidate) is False

    with patch("catalog.services.semantic_indexing.dispatch_semantic_job", return_value=True):
        first = dispatch_semantic_version_batch(candidate, batch_size=1)
    assert first["queued"] == 1
    assert first["remaining"] == 1

    blocked = dispatch_semantic_version_batch(candidate, batch_size=1)
    assert blocked["queued"] == 0
    assert blocked["active"] == 1

    first_job = candidate.jobs.get(status=SemanticIndexJob.Status.QUEUED)
    first_job.status = SemanticIndexJob.Status.COMPLETED
    first_job.save(update_fields=["status", "updated_at"])
    with patch("catalog.services.semantic_indexing.dispatch_semantic_job", return_value=True):
        second = dispatch_semantic_version_batch(candidate, batch_size=1)
    assert second["queued"] == 1
    assert second["remaining"] == 0
    assert maybe_activate_semantic_index_version(candidate) is False

    candidate.jobs.filter(status=SemanticIndexJob.Status.QUEUED).update(
        status=SemanticIndexJob.Status.COMPLETED
    )
    assert maybe_activate_semantic_index_version(candidate) is True
    candidate.refresh_from_db()
    old_active.refresh_from_db()
    assert candidate.status == SemanticIndexVersion.Status.ACTIVE
    assert old_active.status == SemanticIndexVersion.Status.RETIRED


@pytest.mark.django_db(transaction=True)
def test_semantic_snapshot_waits_for_validation_before_switching_active_index(
    settings,
    tmp_path,
):
    work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="可验证语义快照",
    )
    edition.ocr_status = OcrStatus.NOT_REQUIRED
    edition.save(update_fields=["ocr_status", "updated_at"])
    runtime = semantic_runtime(tmp_path)
    SemanticChunk.objects.create(
        asset=normalized,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text="社会理论候选索引测试",
        normalized_text="社会理论候选索引测试",
        document_type=work.document_type,
        parser_version="page-blocks-v2",
        chunk_version="natural-paragraph-v1",
        embedding_model=runtime["model"],
        embedding_version="1",
        document_id="0" * 64,
        content_hash="1" * 64,
        index_status=SemanticChunk.IndexStatus.READY,
    )
    old_active = SemanticIndexVersion.objects.create(
        uid="semantic_passages_snapshot_old",
        provider="huggingFace",
        status=SemanticIndexVersion.Status.ACTIVE,
    )

    with patch("catalog.services.semantic_indexing.ensure_semantic_index"):
        candidate = stage_semantic_snapshot_version(
            runtime,
            auto_dispatch=False,
        )

    assert candidate.expected_document_count == 1
    assert candidate.validation_details["activation_mode"] == "manual"
    job = candidate.jobs.get()
    assert job.operation == SemanticIndexJob.Operation.BUILD
    job.status = SemanticIndexJob.Status.COMPLETED
    job.stats = {"documents": 1}
    job.save(update_fields=["status", "stats", "updated_at"])

    assert maybe_activate_semantic_index_version(candidate) is False
    candidate.refresh_from_db()
    old_active.refresh_from_db()
    assert candidate.status == SemanticIndexVersion.Status.READY
    assert old_active.status == SemanticIndexVersion.Status.ACTIVE

    with patch(
        "catalog.services.semantic_search.current_semantic_runtime",
        return_value=runtime,
    ), patch(
        "catalog.services.semantic_search.semantic_model_health",
        return_value={"available": True, "reason": "模型已就绪"},
    ), patch(
        "catalog.services.semantic_indexing.semantic_index_document_count",
        return_value=1,
    ):
        activated = activate_semantic_index_version(candidate)

    activated.refresh_from_db()
    old_active.refresh_from_db()
    assert activated.status == SemanticIndexVersion.Status.ACTIVE
    assert activated.document_count == 1
    assert old_active.status == SemanticIndexVersion.Status.RETIRED
    assert SemanticIndexVersion.objects.filter(pk=old_active.pk).exists()


@pytest.mark.django_db
def test_admin_semantic_activation_requires_explicit_confirmation(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    candidate = SemanticIndexVersion.objects.create(
        uid="semantic_passages_confirmation_required",
        provider="huggingFace",
        status=SemanticIndexVersion.Status.READY,
    )

    response = api_client.post(
        "/api/catalog/admin/semantic-index/",
        {"action": "activate_version", "version_id": str(candidate.id)},
        format="json",
    )

    assert response.status_code == 400
    candidate.refresh_from_db()
    assert candidate.status == SemanticIndexVersion.Status.READY


@pytest.mark.django_db(transaction=True)
def test_retry_failed_semantic_version_requeues_partial_job(
    settings,
    tmp_path,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="候选索引部分完成",
    )
    candidate = SemanticIndexVersion.objects.create(
        uid="semantic_passages_retry_partial",
        provider="huggingFace",
        status=SemanticIndexVersion.Status.FAILED,
        error_message="等待任务超时",
    )
    job = SemanticIndexJob.objects.create(
        operation=SemanticIndexJob.Operation.REBUILD,
        status=SemanticIndexJob.Status.PARTIAL,
        asset=normalized,
        index_version=candidate,
        progress=100,
        task_id="expired-task-id",
        error_code="TimeoutError",
        error_message="等待 Meilisearch 任务超时。",
    )

    with patch("catalog.services.semantic_indexing.dispatch_semantic_job", return_value=True):
        result = dispatch_semantic_version_batch(
            candidate,
            batch_size=1,
            retry_failed=True,
        )

    job.refresh_from_db()
    candidate.refresh_from_db()
    assert result["queued"] == 1
    assert candidate.status == SemanticIndexVersion.Status.BUILDING
    assert candidate.error_message == ""
    assert job.status == SemanticIndexJob.Status.QUEUED
    assert job.progress == 0
    assert job.task_id and job.task_id != "expired-task-id"
    assert job.error_code == ""
    assert job.error_message == ""


@pytest.mark.django_db
def test_semantic_index_wait_uses_processing_task_timeout(
    settings,
    tmp_path,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="长任务等待配置",
    )
    settings.SEMANTIC_INDEX_TASK_TIMEOUT_SECONDS = 901

    with patch(
        "catalog.services.semantic_indexing.semantic_documents",
        return_value=[{"id": "chunk-1", "asset_id": str(normalized.id)}],
    ), patch(
        "catalog.services.semantic_indexing.ensure_semantic_index"
    ), patch(
        "catalog.services.semantic_indexing.httpx.post"
    ) as posted, patch(
        "catalog.services.semantic_indexing._wait_task",
        return_value={"status": "succeeded"},
    ) as waited:
        posted.return_value.json.return_value = {"taskUid": 38}
        result = index_semantic_asset(normalized)

    assert result["backend"] == "meilisearch"
    waited.assert_called_once_with({"taskUid": 38}, timeout=901)


@pytest.mark.django_db
def test_semantic_asset_sync_removes_stale_chunk_ids(settings, tmp_path):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="语义旧分块清理",
    )
    document_response = Mock()
    document_response.json.return_value = {"taskUid": 51}
    fetch_response = Mock()
    fetch_response.json.return_value = {
        "results": [{"id": "current-chunk"}, {"id": "stale-chunk"}],
        "total": 2,
    }
    delete_response = Mock()
    delete_response.json.return_value = {"taskUid": 52}

    with patch(
        "catalog.services.semantic_indexing.semantic_documents",
        return_value=[{"id": "current-chunk", "asset_id": str(normalized.id)}],
    ), patch(
        "catalog.services.semantic_indexing.ensure_semantic_index"
    ), patch(
        "catalog.services.semantic_indexing.httpx.post",
        side_effect=[document_response, fetch_response, delete_response],
    ) as posted, patch(
        "catalog.services.semantic_indexing._wait_task",
        return_value={"status": "succeeded"},
    ):
        result = index_semantic_asset(normalized)

    assert result["removed_stale_documents"] == 1
    assert posted.call_count == 3
    assert posted.call_args_list[-1].kwargs["json"] == ["stale-chunk"]


@pytest.mark.django_db
def test_ocr_job_persists_and_dispatches_resumable_page_batches(
    settings,
    tmp_path,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="分批 OCR",
    )
    normalized.page_count = 5
    normalized.save(update_fields=["page_count", "updated_at"])
    Page.objects.bulk_create(
        [
            Page(
                asset=normalized,
                index=index,
                text_source=Page.TextSource.NONE,
                label_source=Page.LabelSource.FILE_INDEX,
            )
            for index in range(1, 6)
        ]
    )
    first_page = normalized.pages.get(index=1)
    first_page.printed_label = "i"
    first_page.label_source = Page.LabelSource.MANUAL
    first_page.label_confidence = 1
    first_page.is_label_manual = True
    first_page.is_label_anchor = True
    first_page.save()
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PENDING,
        edition=edition,
        asset=normalized,
        task_id="ocr-batch-1",
    )
    settings.OCR_PAGE_BATCH_SIZE = 2
    requested_batches = []
    dispatched = []

    def fake_extract(_path, page_numbers):
        requested_batches.append(list(page_numbers))
        return (
            [
                ExtractedPage(
                    index=index,
                    printed_label="",
                    chapter_title="",
                    width=100,
                    height=200,
                    text=f"第 {index} 页 OCR 文本",
                    source=Page.TextSource.OCR,
                    confidence=0.95,
                    blocks=[
                        ExtractedBlock(
                            order=0,
                            text=f"第 {index} 页 OCR 文本",
                            bbox=[1, 2, 80, 30],
                            confidence=0.95,
                        )
                    ],
                    label_source=Page.LabelSource.FILE_INDEX,
                    label_confidence=0.25,
                )
                for index in page_numbers
            ],
            "paddleocr_nas",
        )

    def fake_dispatch(job_id, task_id):
        dispatched.append((job_id, task_id))
        return True

    with patch(
        "ingestion.services.processing.materialize_field_file",
        return_value=("reader.pdf", lambda: None),
    ), patch(
        "ingestion.services.processing.extract_ocr_page_batch",
        side_effect=fake_extract,
    ), patch(
        "ingestion.services.processing.dispatch_ocr_job",
        side_effect=fake_dispatch,
    ), patch(
        "ingestion.services.processing.index_asset"
    ) as indexed, patch(
        "ingestion.services.processing.queue_semantic_job"
    ) as semantic, patch(
        "ingestion.services.processing.queue_page_label_job"
    ) as page_labels, patch(
        "ingestion.services.processing.detect_publication_places",
        return_value=[],
    ) as publication_places:
        run_ocr_job(str(job.id), task_id="ocr-batch-1")
        job.refresh_from_db()
        assert job.status == ProcessingJob.Status.PENDING
        assert job.attempt == 1
        assert job.stats["processed_pages"] == 2
        second_task_id = job.task_id

        run_ocr_job(str(job.id), task_id=second_task_id)
        job.refresh_from_db()
        assert job.status == ProcessingJob.Status.PENDING
        assert job.attempt == 1
        assert job.stats["processed_pages"] == 4
        third_task_id = job.task_id

        run_ocr_job(str(job.id), task_id=third_task_id)

    job.refresh_from_db()
    edition.refresh_from_db()
    normalized.refresh_from_db()
    assert requested_batches == [[1, 2], [3, 4], [5]]
    assert len(dispatched) == 2
    assert job.status == ProcessingJob.Status.SUCCEEDED
    assert job.progress == 100
    assert job.attempt == 1
    assert job.stats["completed_batches"] == 3
    assert job.stats["processed_pages"] == 5
    assert normalized.pages.filter(text_source=Page.TextSource.OCR).count() == 5
    assert normalized.pages.get(index=1).blocks.count() == 1
    first_page.refresh_from_db()
    assert first_page.printed_label == "i"
    assert first_page.label_source == Page.LabelSource.MANUAL
    assert first_page.is_label_manual is True
    assert first_page.is_label_anchor is True
    assert normalized.extraction_method == "paddleocr_nas"
    assert edition.ocr_status == OcrStatus.SUCCEEDED
    indexed.assert_called_once()
    semantic.assert_called_once()
    page_labels.assert_called_once()
    publication_places.assert_called_once_with(
        normalized,
        force=True,
        allow_targeted_ocr=False,
    )


@pytest.mark.django_db
def test_ocr_backfill_dry_run_does_not_queue_and_real_run_is_bounded(
    settings,
    tmp_path,
):
    for title in ("OCR 回填甲", "OCR 回填乙"):
        create_item_with_files(settings, tmp_path, title=title)

    output = StringIO()
    with patch(
        "catalog.management.commands.backfill_library_processing.queue_ocr_job"
    ) as queue:
        call_command(
            "backfill_library_processing",
            phase="ocr",
            batch_size=1,
            dry_run=True,
            stdout=output,
        )
        queue.assert_not_called()
        call_command(
            "backfill_library_processing",
            phase="ocr",
            batch_size=1,
            stdout=output,
        )
        assert queue.call_count == 1
    assert "eligible=2 selected=1" in output.getvalue()


@pytest.mark.django_db
def test_ocr_reclassification_only_queues_pages_that_need_a_reliable_text_layer(
    settings,
    tmp_path,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="原生文字层重新分类",
    )
    edition.ocr_status = OcrStatus.NOT_REQUIRED
    edition.save(update_fields=["ocr_status", "updated_at"])
    extracted_pages = [
        ExtractedPage(
            index=1,
            printed_label="",
            chapter_title="",
            width=100,
            height=200,
            text="可以可靠复制的原生文字",
            source=Page.TextSource.EMBEDDED,
            confidence=1,
            blocks=[],
        ),
        ExtractedPage(
            index=2,
            printed_label="",
            chapter_title="",
            width=100,
            height=200,
            text="乱码文字层",
            source=Page.TextSource.EMBEDDED,
            confidence=0.4,
            blocks=[],
            ocr_reasons=("missing_tounicode",),
        ),
    ]
    output = StringIO()

    with patch(
        "catalog.management.commands.backfill_library_processing.materialize_field_file",
        return_value=("reader.pdf", lambda: None),
    ), patch(
        "catalog.management.commands.backfill_library_processing.extract_native_pages",
        return_value=(extracted_pages, True),
    ), patch(
        "catalog.management.commands.backfill_library_processing.queue_ocr_job"
    ) as queue:
        call_command(
            "backfill_library_processing",
            phase="ocr",
            batch_size=1,
            asset_id=[str(normalized.id)],
            reclassify_native=True,
            dry_run=True,
            stdout=output,
        )
        queue.assert_not_called()
        edition.refresh_from_db()
        normalized.refresh_from_db()
        assert edition.ocr_status == OcrStatus.NOT_REQUIRED
        assert "ocr_required_page_indexes" not in normalized.validation_details

        call_command(
            "backfill_library_processing",
            phase="ocr",
            batch_size=1,
            asset_id=[str(normalized.id)],
            reclassify_native=True,
            stdout=output,
        )

    edition.refresh_from_db()
    normalized.refresh_from_db()
    assert edition.ocr_status == OcrStatus.PENDING
    assert normalized.validation_details["ocr_required_page_indexes"] == [2]
    assert normalized.validation_details["ocr_reason_counts"] == {
        "missing_tounicode": 1,
    }
    queue.assert_called_once_with(normalized, force=False)
    assert "targets=1/2" in output.getvalue()


@pytest.mark.django_db
def test_offline_semantic_configuration_updates_effective_setting_with_audit(
    tmp_path,
):
    revision = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    repo = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    snapshot = (
        tmp_path
        / "models"
        / "hub"
        / "models--sentence-transformers--paraphrase-multilingual-MiniLM-L12-v2"
        / "snapshots"
        / revision
    )
    snapshot.mkdir(parents=True)
    revision_ref = snapshot.parent.parent / "refs" / revision
    revision_ref.parent.mkdir(parents=True)
    revision_ref.write_text(revision, encoding="utf-8")
    (snapshot / "config.json").write_text(
        json.dumps({"hidden_size": 384}),
        encoding="utf-8",
    )
    (snapshot / "tokenizer.json").write_text("{}", encoding="utf-8")
    (snapshot / "model.safetensors").write_bytes(b"model")

    output = StringIO()
    call_command(
        "configure_offline_semantic_model",
        repo_id=repo,
        revision=revision,
        model_local_path=str(tmp_path / "models"),
        dimensions=384,
        pooling="useModel",
        require_files=True,
        stdout=output,
    )
    value = SiteSetting.objects.get(key="semantic_search_runtime").value
    assert value["model_revision"] == revision
    assert value["model_repo_id"] == repo
    assert value["offline_mode"] is True
    assert AuditEvent.objects.filter(
        action="semantic_offline_model_configured"
    ).exists()
    assert '"available": true' in output.getvalue()


@pytest.mark.django_db
def test_semantic_prewarm_uses_and_deletes_an_isolated_index():
    runtime = {
        "enabled": True,
        "engine": "meilisearch_hybrid",
        "provider": "huggingFace",
        "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "offline_mode": True,
    }

    class Response:
        status_code = 202

        def raise_for_status(self):
            return None

        def json(self):
            return {"taskUid": 1}

    output = StringIO()
    with patch(
        "catalog.management.commands.prewarm_semantic_model.current_semantic_runtime",
        return_value=runtime,
    ), patch(
        "catalog.management.commands.prewarm_semantic_model.semantic_model_health",
        return_value={"available": True},
    ), patch(
        "catalog.management.commands.prewarm_semantic_model.ensure_semantic_index"
    ) as ensure, patch(
        "catalog.management.commands.prewarm_semantic_model.httpx.post",
        return_value=Response(),
    ) as posted, patch(
        "catalog.management.commands.prewarm_semantic_model.httpx.delete",
        return_value=Response(),
    ) as deleted, patch(
        "catalog.management.commands.prewarm_semantic_model._wait_task"
    ):
        call_command("prewarm_semantic_model", timeout=60, stdout=output)

    index_uid = ensure.call_args.kwargs["index_uid"]
    assert index_uid.startswith("semantic_model_probe_")
    assert f"/indexes/{index_uid}/documents" in posted.call_args.args[0]
    assert deleted.call_args.args[0].endswith(f"/indexes/{index_uid}")
    assert "/documents/" not in deleted.call_args.args[0]
