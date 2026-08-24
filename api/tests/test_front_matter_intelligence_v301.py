from hashlib import sha256

import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    Contribution,
    DocumentRevision,
    Edition,
    EvidencePack,
    Page,
    Passage,
    Work,
)
from catalog.services.document_intelligence import synchronize_native_extraction
from catalog.services.front_matter_intelligence import run_front_matter_intelligence
from catalog.services.workflow_suggestions import WorkflowSuggestionAggregator
from catalog.services.work_editor import save_workflow_section
from ingestion.models import (
    DecisionLog,
    EntityResolutionCandidate,
    MetadataCandidate,
    ProcessingJob,
    UploadBatch,
    UploadItem,
)
from ingestion.services.entity_resolution_decisions import decide_entity_resolution


pytestmark = pytest.mark.django_db


def _library_document(page_texts: list[str], *, confidences: list[float] | None = None):
    user = User.objects.create_user(
        username="front-matter-editor",
        email="front-matter-editor@example.com",
        password="FrontMatter-Test-Password-2026!",
        role="editor",
    )
    batch = UploadBatch.objects.create(created_by=user, expected_count=1)
    work = Work.objects.create(document_type="book", title="待核对题名", language="zh-CN")
    edition = Edition.objects.create(work=work)
    digest = sha256("front-matter-v301".encode()).hexdigest()
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="archive/front-matter-original.pdf",
        sha256=digest,
        byte_size=2048,
        page_count=len(page_texts),
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        validation_details={"original_marker": True},
    )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="public/front-matter-normalized.pdf",
        sha256=digest,
        byte_size=2048,
        page_count=len(page_texts),
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        validation_details={"ocr_required_page_indexes": []},
        source_asset=original,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="front-matter.pdf",
        status=UploadItem.Status.READY,
        edition=edition,
        asset=original,
    )
    for offset, text in enumerate(page_texts):
        index = offset + 1
        confidence = (confidences or [1.0] * len(page_texts))[offset]
        page = Page.objects.create(
            asset=normalized,
            index=index,
            printed_label=str(index),
            text=text,
            normalized_text=text,
            text_source=Page.TextSource.EMBEDDED,
            confidence=confidence,
        )
        if text:
            Passage.objects.create(
                page=page,
                order=0,
                text=text,
                normalized_text=text,
                start_offset=0,
                end_offset=len(text),
                bbox_union=[10, 20, 400, 700],
            )
    synchronize_native_extraction(normalized, schedule_claims=False, actor=user)
    return user, batch, item, original, normalized


def test_front_matter_candidates_are_locator_backed_and_use_normalized_asset():
    page_texts = [
        "社会学的想象力：经典导读\nC. 赖特·米尔斯 著\n张三 译",
        (
            "图书在版编目（CIP）数据\n社会理论经典丛书\n"
            "首次出版 1959 年\n2024 年 6 月第 2 版\n"
            "出版地：北京\n中国社会科学出版社\nISBN 978-7-5004-1234-5"
        ),
        "摘要：本书讨论个人困扰与公共议题之间的关系，并说明社会结构如何进入个人经验。"
        "这一摘要来自当前馆藏版本的前置页，足以形成可核实的来源摘要候选。\n关键词：社会学想象力",
    ]
    user, _batch, item, original, normalized = _library_document(page_texts)

    result = run_front_matter_intelligence(
        normalized,
        upload_item=item,
        actor=user,
        schedule_ocr=False,
    )

    assert result["status"] == "ready"
    expected_fields = {
        "title",
        "subtitle",
        "authors",
        "translators",
        "publisher",
        "publication_place",
        "publication_year",
        "publication_date",
        "first_publication_date",
        "version_label",
        "isbn13",
        "abstract",
    }
    assert expected_fields.issubset(result["candidate_fields"]), sorted(
        expected_fields - set(result["candidate_fields"])
    )
    assert result["abstract"]["kind"] == "source_abstract"
    assert EvidencePack.objects.filter(
        pk=result["evidence_pack_id"],
        subject_type="edition",
        subject_id=str(normalized.edition_id),
    ).exists()

    isbn = item.metadata_candidates.get(field_name="isbn13")
    evidence = isbn.evidence_records.get()
    assert evidence.asset_id == normalized.id
    assert evidence.page_number == 2
    assert isbn.evidence["document_revision_id"]
    assert isbn.evidence["evidence_span_id"]
    assert isbn.evidence["reader_url"].endswith("?page=2")

    original.refresh_from_db()
    assert original.validation_details == {"original_marker": True}
    assert not DocumentRevision.objects.filter(asset=original).exists()


def test_missing_high_value_fields_add_only_low_quality_front_matter_ocr_targets():
    texts = [
        "待核对题名\n某某 著",
        "",
        "版权信息页文字不足",
        "正常前言内容" * 30,
        "正常前言内容" * 30,
        "正常正文内容" * 30,
        "正常正文内容" * 30,
        "正常正文内容" * 30,
        "低质量但已由既有检测安排的页面",
        "正常正文内容" * 30,
        "正常正文内容" * 30,
        "正常正文内容" * 30,
    ]
    confidences = [1, 0.05, 0.4, 1, 1, 1, 1, 1, 0.3, 1, 1, 1]
    user, _batch, item, _original, normalized = _library_document(
        texts,
        confidences=confidences,
    )
    normalized.validation_details = {"ocr_required_page_indexes": [9]}
    normalized.save(update_fields=["validation_details", "updated_at"])

    result = run_front_matter_intelligence(
        normalized,
        upload_item=item,
        actor=user,
        schedule_ocr=False,
    )

    assert result["ocr_page_indexes"] == [2, 3, 9]
    assert "publication_date" in result["missing_fields"]
    normalized.refresh_from_db()
    assert normalized.validation_details["ocr_required_page_indexes"] == [2, 3, 9]
    assert normalized.validation_details["front_matter_ocr_page_indexes"] == [2, 3, 9]
    assert ProcessingJob.objects.filter(job_type=ProcessingJob.JobType.OCR).count() == 0
    assert result["publication_blocking"] is False


def test_front_matter_people_candidates_flow_into_contributors_and_acceptance_audit():
    user, _batch, item, _original, normalized = _library_document(
        ["作者：李明\n译者：王芳", "版权信息\n2024 年\n证据出版社"]
    )

    run_front_matter_intelligence(
        normalized,
        upload_item=item,
        actor=user,
        schedule_ocr=False,
    )

    suggestions = WorkflowSuggestionAggregator(
        item.edition,
        item=item,
    ).aggregate(step="contributors")["suggestions"]
    assert {row["field"] for row in suggestions if row["kind"] == "metadata"} >= {
        "authors",
        "translators",
    }
    candidates = list(
        item.entity_resolution_candidates.filter(
            target_type="person",
            candidate_entity_type="person_draft",
        ).order_by("source_name")
    )
    assert {
        (row.source_name, row.supporting_properties["contribution_role"])
        for row in candidates
    } == {
        ("李明", Contribution.Role.AUTHOR),
        ("王芳", Contribution.Role.TRANSLATOR),
    }
    for candidate in candidates:
        decide_entity_resolution(
            candidate,
            action="keep_unresolved",
            target_type="person",
            actor=user,
        )
    contributor_rows = [
        {
            "person_id": row.person_id,
            "role": row.role,
            "order": index,
        }
        for index, row in enumerate(
            item.edition.contributions.order_by("role", "created_at")
        )
    ]

    save_workflow_section(
        item.edition,
        "contributors",
        {"contributors": contributor_rows},
        actor=user,
        confirm_section=True,
    )

    assert not EntityResolutionCandidate.objects.filter(
        upload_item=item,
        target_type="person",
        status=EntityResolutionCandidate.Status.PROPOSED,
    ).exists()
    assert set(
        MetadataCandidate.objects.filter(
            upload_item=item,
            field_name__in={"authors", "translators"},
        ).values_list("field_name", "lifecycle")
    ) == {
        ("authors", MetadataCandidate.Lifecycle.ACCEPTED),
        ("translators", MetadataCandidate.Lifecycle.ACCEPTED),
    }
    assert DecisionLog.objects.filter(
        upload_item=item,
        action="accept_metadata_candidate",
        target_id__in={"authors", "translators"},
    ).count() == 2


def test_skip_ocr_policy_does_not_add_front_matter_targets():
    texts = ["待核对题名\n某某 著", "", "版权信息页文字不足"]
    confidences = [1, 0.05, 0.4]
    user, batch, item, _original, normalized = _library_document(
        texts,
        confidences=confidences,
    )
    batch.ocr_strategy = UploadBatch.OcrStrategy.SKIP
    batch.save(update_fields=["ocr_strategy", "updated_at"])

    result = run_front_matter_intelligence(
        normalized,
        upload_item=item,
        actor=user,
        schedule_ocr=True,
    )

    normalized.refresh_from_db()
    assert result["ocr_page_indexes"] == []
    assert result["combined_ocr_targets"] == []
    assert normalized.validation_details["ocr_required_page_indexes"] == []
    assert "front_matter_ocr_page_indexes" not in normalized.validation_details
    assert ProcessingJob.objects.filter(job_type=ProcessingJob.JobType.OCR).count() == 0


def test_abstract_reports_no_reliable_candidate_without_source_evidence():
    user, _batch, item, _original, normalized = _library_document(
        ["可靠题名\n作者：李四", "版权信息\n2020 年\n某某出版社"]
    )

    result = run_front_matter_intelligence(
        normalized,
        upload_item=item,
        actor=user,
    )

    assert result["abstract"] == {
        "kind": "no_reliable_candidate",
        "reason": "source_abstract_not_found_and_library_synthesis_not_completed",
        "evidence_available": True,
    }
    assert result["publication_blocking"] is False
