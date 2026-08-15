from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from catalog.models import (
    OcrStatus,
    Page,
    SemanticIndexJob,
    SemanticIndexVersion,
    SiteSetting,
)
from ingestion.models import ProcessingJob, UploadBatch, UploadItem
from ingestion.services.ai_candidate_filter import reconcile_candidate_group
from ingestion.services.ai_client import AIInvalidOutput, AIResult
from ingestion.services.extract import ExtractedBlock, ExtractedPage
from ingestion.services.processing import (
    resume_processing_job,
    run_ocr_job,
    set_processing_workload_paused,
)
from catalog.services.semantic_indexing import set_semantic_index_paused

from .test_resilient_publication_v260 import create_item_with_files


def _upload_item(admin_user, edition, asset):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        source_filename="pause-test.pdf",
        edition=edition,
        asset=asset,
        status=UploadItem.Status.NEEDS_REVIEW,
    )


@pytest.mark.django_db(transaction=True)
def test_metadata_refresh_queues_without_network_and_global_resume_reuses_job(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="联网暂停测试",
    )
    item = _upload_item(admin_user, edition, normalized)
    set_processing_workload_paused(
        ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        True,
        actor=admin_user,
    )
    api_client.force_authenticate(admin_user)

    with patch(
        "ingestion.views.refresh_remote_candidates",
        side_effect=AssertionError("暂停状态不得访问外部来源"),
    ):
        response = api_client.post(
            f"/api/ingestion/items/{item.id}/metadata-suggestions/",
            {},
            format="json",
        )

    assert response.status_code == 202
    assert response.data["queued"] is True
    job = ProcessingJob.objects.get(
        job_type=ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
        upload_item=item,
    )
    assert job.status == ProcessingJob.Status.PAUSED
    original_job_id = job.id

    with patch(
        "ingestion.services.processing.dispatch_external_enrichment_job",
        return_value=True,
    ) as dispatch:
        resumed = api_client.post(
            "/api/ingestion/processing-center/",
            {
                "action": "resume_workload",
                "job_type": ProcessingJob.JobType.EXTERNAL_ENRICHMENT,
            },
            format="json",
        )

    assert resumed.status_code == 200
    assert resumed.data["queued"] == 1
    job.refresh_from_db()
    assert job.id == original_job_id
    assert job.status == ProcessingJob.Status.PENDING
    assert job.task_id
    assert job.pause_requested_at is None
    dispatch.assert_called_once_with(str(job.id), job.task_id)


@pytest.mark.django_db(transaction=True)
def test_ocr_pauses_after_persisted_batch_and_resumes_same_job_from_remaining_page(
    settings,
    tmp_path,
    admin_user,
):
    _work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="OCR 安全暂停",
    )
    normalized.page_count = 3
    normalized.save(update_fields=["page_count", "updated_at"])
    Page.objects.bulk_create(
        [
            Page(
                asset=normalized,
                index=index,
                printed_label=str(index),
                text="",
                text_source=Page.TextSource.NONE,
                label_source=Page.LabelSource.FILE_INDEX,
            )
            for index in range(1, 4)
        ]
    )
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PENDING,
        edition=edition,
        asset=normalized,
        task_id="ocr-pause-batch-1",
        created_by=admin_user,
    )
    settings.OCR_PAGE_BATCH_SIZE = 2
    requested_batches = []
    extraction_calls = 0

    def fake_extract(_path, page_numbers):
        nonlocal extraction_calls
        extraction_calls += 1
        requested_batches.append(list(page_numbers))
        pages = [
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
        ]
        if extraction_calls == 1:
            set_processing_workload_paused(
                ProcessingJob.JobType.OCR,
                True,
                actor=admin_user,
            )
        return pages, "paddleocr_nas"

    common_patches = (
        patch(
            "ingestion.services.processing.materialize_field_file",
            return_value=("reader.pdf", lambda: None),
        ),
        patch("ingestion.services.processing.extract_ocr_page_batch", side_effect=fake_extract),
        patch("ingestion.services.processing.index_asset"),
        patch("ingestion.services.processing.queue_semantic_job"),
        patch("ingestion.services.processing.queue_page_label_job"),
        patch("ingestion.services.processing.detect_publication_places", return_value=[]),
        patch("ingestion.services.processing.generate_theory_review_tasks", return_value=0),
    )
    with common_patches[0], common_patches[1], common_patches[2], common_patches[3], common_patches[4], common_patches[5], common_patches[6], patch(
        "ingestion.services.processing.dispatch_ocr_job",
        return_value=True,
    ) as dispatch:
        run_ocr_job(str(job.id), task_id="ocr-pause-batch-1")
        job.refresh_from_db()
        assert job.status == ProcessingJob.Status.PAUSED
        assert job.task_id == ""
        assert job.stats["processed_pages"] == 2
        assert normalized.pages.filter(text_source=Page.TextSource.OCR).count() == 2
        dispatch.assert_not_called()

        set_processing_workload_paused(
            ProcessingJob.JobType.OCR,
            False,
            actor=admin_user,
        )
        resume_processing_job(job, actor=admin_user)
        job.refresh_from_db()
        resumed_task_id = job.task_id
        dispatch.assert_called_once_with(str(job.id), resumed_task_id)
        run_ocr_job(str(job.id), task_id=resumed_task_id)

    job.refresh_from_db()
    edition.refresh_from_db()
    assert requested_batches == [[1, 2], [3]]
    assert job.status == ProcessingJob.Status.SUCCEEDED
    assert job.stats["processed_pages"] == 3
    assert normalized.pages.filter(text_source=Page.TextSource.OCR).count() == 3
    assert edition.ocr_status == OcrStatus.SUCCEEDED


@pytest.mark.django_db
def test_processing_center_semantic_retry_preserves_index_version(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="版本化语义恢复",
    )
    version = SemanticIndexVersion.objects.create(
        uid="semantic_candidate_pause_test",
        provider="userProvided",
        status=SemanticIndexVersion.Status.BUILDING,
    )
    job = SemanticIndexJob.objects.create(
        asset=normalized,
        index_version=version,
        status=SemanticIndexJob.Status.PAUSED,
        operation=SemanticIndexJob.Operation.REBUILD,
    )
    api_client.force_authenticate(admin_user)
    replacement = SimpleNamespace(id="replacement-job", status=SemanticIndexJob.Status.QUEUED)

    with patch("ingestion.views.queue_semantic_job", return_value=replacement) as queue:
        response = api_client.post(
            "/api/ingestion/processing-center/",
            {
                "action": "retry",
                "source": "semantic_index_job",
                "job_id": str(job.id),
            },
            format="json",
        )

    assert response.status_code == 202
    assert queue.call_args.kwargs["index_version"] == version


@pytest.mark.django_db
def test_global_semantic_resume_preserves_running_job_and_index_version(
    settings,
    tmp_path,
    api_client,
    admin_user,
):
    _work, _edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="全局语义恢复",
    )
    version = SemanticIndexVersion.objects.create(
        uid="semantic_global_resume_test",
        provider="userProvided",
        status=SemanticIndexVersion.Status.BUILDING,
    )
    job = SemanticIndexJob.objects.create(
        asset=normalized,
        index_version=version,
        status=SemanticIndexJob.Status.RUNNING,
        task_id="semantic-global-pause-task",
        operation=SemanticIndexJob.Operation.BUILD,
    )
    set_semantic_index_paused(True, actor=admin_user)
    api_client.force_authenticate(admin_user)

    with patch("catalog.views.resume_semantic_job", return_value=job) as resume, patch(
        "catalog.views.dispatch_semantic_version_batch",
        return_value={"queued": 0},
    ):
        response = api_client.post(
            "/api/catalog/admin/semantic-index/",
            {"action": "resume"},
            format="json",
        )

    assert response.status_code == 200
    assert response.data["queued"] == 1
    assert resume.call_args.args[0].id == job.id
    assert resume.call_args.args[0].index_version == version


def test_candidate_reconciliation_forces_review_and_rejects_unknown_provenance():
    valid_result = AIResult(
        data={
            "candidate_group_id": "agent-fei-xiaotong",
            "target_type": "agent",
            "proposals": [
                {
                    "candidate_id": "person-1",
                    "decision": "retain",
                    "source_record_ids": ["source-1"],
                    "evidence_ids": ["evidence-1"],
                    "match_reasons": ["姓名与出生年一致"],
                    "conflicts": [],
                    "warnings": [],
                    "requires_human_review": False,
                }
            ],
        },
        provider="openai_compatible",
        model="local-model",
        prompt_version="candidate-reconciliation-v2",
        latency_ms=10,
        attempts=1,
    )
    client = Mock()
    client.generate_json.return_value = valid_result

    result = reconcile_candidate_group(
        candidate_group_id="agent-fei-xiaotong",
        target_type="agent",
        candidates=[{"candidate_id": "person-1", "label": "费孝通", "birth_year": 1910}],
        allowed_source_record_ids={"source-1"},
        allowed_evidence_ids={"evidence-1"},
        client=client,
    )

    assert result.data["proposals"][0]["requires_human_review"] is True
    prompt = client.generate_json.call_args.kwargs["system_prompt"]
    assert "仅凭姓名相同不得合并" in prompt
    assert "不得根据出版社今天的总部推断历史出版地" in prompt

    invalid = AIResult(
        data={
            **valid_result.data,
            "proposals": [
                {
                    **valid_result.data["proposals"][0],
                    "source_record_ids": ["invented-source"],
                }
            ],
        },
        provider=valid_result.provider,
        model=valid_result.model,
        prompt_version=valid_result.prompt_version,
        latency_ms=valid_result.latency_ms,
        attempts=valid_result.attempts,
    )
    client.generate_json.return_value = invalid
    with pytest.raises(AIInvalidOutput, match="source_record_id"):
        reconcile_candidate_group(
            candidate_group_id="agent-fei-xiaotong",
            target_type="agent",
            candidates=[{"candidate_id": "person-1", "label": "费孝通"}],
            allowed_source_record_ids={"source-1"},
            allowed_evidence_ids={"evidence-1"},
            client=client,
        )
