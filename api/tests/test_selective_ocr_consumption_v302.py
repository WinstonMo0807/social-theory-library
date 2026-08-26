from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.models import User
from catalog.models import (
    Asset,
    DocumentQualityAssessment,
    DocumentRevision,
    Edition,
    EvidenceSpan,
    Page,
    Work,
)
from catalog.services.document_intelligence import synchronize_native_extraction
from ingestion.models import MetadataCandidate, ProcessingJob, UploadBatch, UploadItem
from ingestion.models import AuditEvent
from ingestion.services.ocr_inventory import decide_paused_ocr_job, paused_ocr_inventory
from ingestion.services.processing import run_ocr_job


pytestmark = pytest.mark.django_db


def _one_page_pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=595, height=842)
    payload = document.tobytes()
    document.close()
    return payload


def _read_asset(asset: Asset) -> bytes:
    with asset.file.open("rb") as handle:
        return handle.read()


def _ocr_payload(_path, page_numbers):
    assert page_numbers == [1]
    abstract = (
        "本书从个人困扰与公共议题的关系出发，讨论社会结构如何进入个人经验，"
        "并以历史比较说明社会学想象力怎样帮助读者理解制度变迁与日常生活。"
    )
    return (
        {
            "pages": [
                {
                    "index": 1,
                    "width": 595,
                    "height": 842,
                    "confidence": 0.98,
                    "blocks": [
                        {"text": "社会学的想象力", "bbox": [50, 50, 320, 85], "type": "title", "confidence": 0.99},
                        {"text": "作者：C. 赖特·米尔斯", "bbox": [50, 95, 320, 125], "type": "paragraph", "confidence": 0.98},
                        {"text": "译者：陈强", "bbox": [50, 130, 260, 160], "type": "paragraph", "confidence": 0.98},
                        {"text": "图书在版编目（CIP）数据", "bbox": [50, 180, 360, 210], "type": "paragraph", "confidence": 0.98},
                        {"text": "出版地：北京", "bbox": [50, 215, 260, 245], "type": "paragraph", "confidence": 0.98},
                        {"text": "中国社会科学出版社", "bbox": [50, 250, 360, 280], "type": "paragraph", "confidence": 0.98},
                        {"text": "2024年6月第2版", "bbox": [50, 285, 300, 315], "type": "paragraph", "confidence": 0.98},
                        {"text": "ISBN 978-7-5004-1234-5", "bbox": [50, 320, 360, 350], "type": "paragraph", "confidence": 0.99},
                        {"text": f"摘要：{abstract}", "bbox": [50, 370, 540, 520], "type": "paragraph", "confidence": 0.97},
                        {"text": "关键词：社会学想象力", "bbox": [50, 530, 360, 560], "type": "paragraph", "confidence": 0.98},
                    ],
                }
            ]
        },
        "paddleocr_nas",
    )


def test_selective_ocr_flows_to_revision_evidence_and_bibliographic_candidate(
    settings,
    tmp_path,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.OCR_PAGE_BATCH_SIZE = 2
    editor = User.objects.create_user(
        username="selective-ocr-editor",
        email="selective-ocr-editor@example.com",
        password="Selective-OCR-Test-2026!",
        role="editor",
    )
    batch = UploadBatch.objects.create(
        created_by=editor,
        expected_count=1,
        external_enrichment_enabled=False,
    )
    work = Work.objects.create(document_type="book", title="待 OCR 核对题名")
    edition = Edition.objects.create(work=work)
    payload = _one_page_pdf()
    digest = sha256(payload).hexdigest()
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file=SimpleUploadedFile("original.pdf", payload, content_type="application/pdf"),
        sha256=digest,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        validation_details={"immutable_original": True},
    )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("normalized.pdf", payload, content_type="application/pdf"),
        sha256=digest,
        byte_size=len(payload),
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        source_asset=original,
        validation_details={
            "ocr_required_page_indexes": [1],
            "ocr_reason_counts": {"low_text": 1},
        },
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="selective-ocr.pdf",
        status=UploadItem.Status.READY,
        edition=edition,
        asset=original,
    )
    page = Page.objects.create(
        asset=normalized,
        index=1,
        printed_label="封面",
        text="",
        normalized_text="",
        text_source=Page.TextSource.EMBEDDED,
        confidence=0.05,
        is_label_manual=True,
        label_source=Page.LabelSource.MANUAL,
    )
    native_revision_result = synchronize_native_extraction(
        normalized,
        actor=editor,
        schedule_claims=False,
    )
    native_revision = DocumentRevision.objects.get(
        pk=native_revision_result["revision_id"]
    )
    original_checksum_before = original.sha256
    original_bytes_before = _read_asset(original)
    normalized_bytes_before = _read_asset(normalized)
    stable_page_id = page.id
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PENDING,
        upload_item=item,
        edition=edition,
        asset=normalized,
        task_id="selective-ocr-controlled-task",
        settings_version="controlled-ocr-v1",
        created_by=editor,
    )

    with (
        patch(
            "ingestion.services.extract.parse_pdf_pages_with_ocr",
            side_effect=_ocr_payload,
        ) as provider,
        patch("ingestion.services.processing.index_asset"),
        patch("ingestion.services.processing.generate_theory_review_tasks", return_value=0),
        patch("ingestion.services.processing.queue_semantic_job"),
        patch("ingestion.services.processing.queue_page_label_job"),
        patch("ingestion.services.processing.detect_publication_places", return_value=[]),
        patch("ingestion.services.processing.controlled_vocabulary_candidates_for_asset", return_value=[]),
        patch("ingestion.services.processing.persist_controlled_vocabulary_candidates", return_value=0),
    ):
        completed = run_ocr_job(
            str(job.id),
            task_id="selective-ocr-controlled-task",
        )

    assert completed.status == ProcessingJob.Status.SUCCEEDED
    provider.assert_called_once()
    page.refresh_from_db()
    original.refresh_from_db()
    normalized.refresh_from_db()
    native_revision.refresh_from_db()

    assert page.id == stable_page_id
    assert page.text_source == Page.TextSource.OCR
    assert page.is_label_manual is True
    assert page.printed_label == "封面"
    assert "社会学的想象力" in page.text
    assert page.blocks.filter(text__contains="中国社会科学出版社").exists()
    assert page.passages.filter(text__contains="ISBN 978-7-5004-1234-5").exists()
    assert original.sha256 == original_checksum_before == digest
    assert _read_asset(original) == original_bytes_before
    assert _read_asset(normalized) == normalized_bytes_before
    assert original.validation_details == {"immutable_original": True}

    active_revision = DocumentRevision.objects.get(asset=normalized, is_active=True)
    assert active_revision.id != native_revision.id
    assert active_revision.revision == native_revision.revision + 1
    assert active_revision.extraction_method == "selective_ocr"
    assert active_revision.ocr_provider == "paddleocr_nas"
    assert active_revision.source_checksum == digest
    assert native_revision.is_active is False
    evidence = EvidenceSpan.objects.get(
        document_revision=active_revision,
        page_id=stable_page_id,
        is_stale=False,
    )
    assert "社会学的想象力" in evidence.original_text
    assert evidence.ocr_provenance == {
        "provider": "paddleocr_nas",
        "model": "",
        "version": "controlled-ocr-v1",
    }
    quality = DocumentQualityAssessment.objects.get(
        document_revision=active_revision,
        assessor="document-intelligence",
    )
    assert quality.ocr_quality == pytest.approx(0.98)
    assert quality.critical_pages == []

    title = item.metadata_candidates.get(
        field_name="title",
        source="front_matter_ocr_v1",
    )
    assert title.value == "社会学的想象力"
    assert title.evidence["document_revision_id"] == str(active_revision.id)
    assert title.evidence["evidence_span_id"] == str(evidence.id)
    assert title.evidence["page"] == 1
    assert title.evidence["reader_url"].endswith("?page=1")
    assert title.evidence_records.filter(
        asset=normalized,
        page_number=1,
        text_quote__contains="社会学的想象力",
    ).exists()
    assert item.metadata_candidates.filter(
        field_name="isbn13",
        value="9787500412345",
        source="front_matter_ocr_v1",
        lifecycle=MetadataCandidate.Lifecycle.PROPOSED,
    ).exists()


def _paused_job(
    *,
    label: str,
    category_setup: str,
    created_by: User,
) -> ProcessingJob:
    work = Work.objects.create(document_type="book", title=f"OCR inventory {label}")
    edition = Edition.objects.create(work=work)
    digest = sha256(label.encode("utf-8")).hexdigest()
    kind = Asset.Kind.ORIGINAL if category_setup == "obsolete" else Asset.Kind.NORMALIZED
    asset = Asset.objects.create(
        edition=edition,
        kind=kind,
        file=f"archive/{label}.pdf" if kind == Asset.Kind.ORIGINAL else f"public/{label}.pdf",
        sha256=digest,
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        validation_details={"ocr_required_page_indexes": [1]},
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        text="",
        normalized_text="",
        text_source=Page.TextSource.NONE,
        confidence=0,
    )
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.PAUSED,
        edition=edition,
        asset=asset,
        created_by=created_by,
    )
    if category_setup == "superseded":
        asset.is_current = False
        asset.save(update_fields=["is_current", "updated_at"])
    elif category_setup == "completed_by_newer_revision":
        page.text = "由较新 OCR revision 提供的文本"
        page.normalized_text = page.text
        page.text_source = Page.TextSource.OCR
        page.confidence = 0.95
        page.save(
            update_fields=[
                "text",
                "normalized_text",
                "text_source",
                "confidence",
                "updated_at",
            ]
        )
        ProcessingJob.objects.filter(pk=job.pk).update(
            created_at=timezone.now() - timedelta(hours=1)
        )
        job.refresh_from_db()
        DocumentRevision.objects.create(
            asset=asset,
            revision=1,
            extraction_method="selective_ocr",
            extraction_version="selective-page-ocr-v1",
            source_checksum=digest,
            text_checksum=sha256(page.text.encode("utf-8")).hexdigest(),
            is_active=True,
        )
    elif category_setup == "genuinely_failed":
        job.attempt = 3
        job.max_attempts = 3
        job.error_kind = ProcessingJob.ErrorKind.PERMANENT
        job.error_code = "invalid_pdf"
        job.save(
            update_fields=[
                "attempt",
                "max_attempts",
                "error_kind",
                "error_code",
                "updated_at",
            ]
        )
    return job


def test_paused_ocr_inventory_classifies_without_resuming_or_writing():
    editor = User.objects.create_user(
        username="ocr-inventory-editor",
        email="ocr-inventory-editor@example.com",
        password="OCR-Inventory-Test-2026!",
        role="editor",
    )
    jobs = [
        _paused_job(label=category, category_setup=category, created_by=editor)
        for category in (
            "obsolete",
            "superseded",
            "completed_by_newer_revision",
            "recoverable",
            "genuinely_failed",
        )
    ]
    before = {
        str(job.id): ProcessingJob.objects.values(
            "status",
            "task_id",
            "attempt",
            "pause_requested_at",
            "updated_at",
        ).get(pk=job.pk)
        for job in jobs
    }

    result = paused_ocr_inventory(
        ProcessingJob.objects.filter(pk__in=[job.pk for job in jobs])
    )

    assert result["read_only"] is True
    assert result["total"] == 5
    assert result["returned"] == 5
    assert result["truncated"] is False
    assert result["counts"] == {
        "obsolete": 1,
        "superseded": 1,
        "completed_by_newer_revision": 1,
        "recoverable": 1,
        "genuinely_failed": 1,
    }
    assert {
        item["category"] for item in result["items"]
    } == set(result["counts"])
    after = {
        str(job.id): ProcessingJob.objects.values(
            "status",
            "task_id",
            "attempt",
            "pause_requested_at",
            "updated_at",
        ).get(pk=job.pk)
        for job in jobs
    }
    assert after == before


def test_paused_ocr_decisions_are_single_job_category_guarded_and_audited(monkeypatch):
    editor = User.objects.create_user(
        username="ocr-decision-editor",
        email="ocr-decision-editor@example.com",
        password="OCR-Decision-Test-2026!",
        role="admin",
    )
    obsolete = _paused_job(label="decision-obsolete", category_setup="obsolete", created_by=editor)
    recoverable = _paused_job(label="decision-recoverable", category_setup="recoverable", created_by=editor)
    failed = _paused_job(label="decision-failed", category_setup="genuinely_failed", created_by=editor)
    dispatched = []
    monkeypatch.setattr(
        "ingestion.services.processing.dispatch_ocr_job",
        lambda job_id, task_id: dispatched.append((job_id, task_id)),
    )

    closed, closed_classification = decide_paused_ocr_job(
        obsolete,
        decision="close",
        actor=editor,
        reason="原始文件不是可执行 OCR 的 normalized asset。",
    )
    resumed, resumed_classification = decide_paused_ocr_job(
        recoverable,
        decision="resume",
        actor=editor,
        reason="当前版本仍缺少目标页文本，按现行运行配置恢复。",
    )
    acknowledged, failed_classification = decide_paused_ocr_job(
        failed,
        decision="acknowledge_failure",
        actor=editor,
        reason="任务已达到最大尝试次数且错误不可重试。",
    )

    assert closed_classification.category == "obsolete"
    assert closed.status == ProcessingJob.Status.CANCELED
    assert resumed_classification.category == "recoverable"
    assert resumed.status == ProcessingJob.Status.PENDING
    assert resumed.task_id
    assert failed_classification.category == "genuinely_failed"
    assert acknowledged.status == ProcessingJob.Status.FAILED
    for job in (closed, resumed, acknowledged):
        assert job.stats["latest_ocr_inventory_decision"]["reason"]
        assert AuditEvent.objects.filter(
            object_type="ProcessingJob",
            object_id=str(job.id),
            action__startswith="paused_ocr_",
        ).exists()
