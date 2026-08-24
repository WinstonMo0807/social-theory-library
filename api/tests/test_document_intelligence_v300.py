from hashlib import sha256
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from catalog.models import (
    Asset,
    CapabilityDemand,
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    DocumentQualityAssessment,
    DocumentRevision,
    Edition,
    EvidenceSpan,
    Page,
    Passage,
    Work,
)
from catalog.services.claims.indexing import visible_claim_queryset
from catalog.services.claims.pipeline import schedule_document_claim_extraction
from catalog.services.document_intelligence import (
    best_effort_native_extraction,
    synchronize_native_extraction,
    synchronize_ocr_completion,
)


pytestmark = pytest.mark.django_db


def _document(*, title: str = "文档智能测试"):
    work = Work.objects.create(document_type="book", title=title, language="zh-CN")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{title}.pdf",
        sha256=sha256(title.encode("utf-8")).hexdigest(),
        byte_size=1024,
        page_count=2,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        extraction_method="embedded",
        validation_details={"ocr_required_page_indexes": [1]},
    )
    pages = []
    for index in (1, 2):
        text = f"第 {index} 页的社会科学命题原文，包含足够长度用于证据与命题质量评估。" * 3
        page = Page.objects.create(
            asset=asset,
            index=index,
            printed_label=str(index),
            chapter_title="导论" if index == 1 else "讨论",
            text=text,
            normalized_text=text,
            text_source=Page.TextSource.EMBEDDED,
            confidence=1,
        )
        Passage.objects.create(
            page=page,
            order=0,
            text=text,
            normalized_text=text,
            start_offset=0,
            end_offset=len(text),
            bbox_union=[10, 20, 300, 500],
        )
        pages.append(page)
    return work, edition, asset, pages


def _claim(*, revision, evidence, work, edition, fingerprint: str):
    return DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=evidence,
        work=work,
        edition=edition,
        proposition=evidence.original_text,
        claim_type=DerivedClaim.ClaimType.ASSERTION,
        prompt_key="claim_extraction",
        prompt_version="test-v1",
        model_provider="test",
        model_name="test-model",
        fingerprint=fingerprint,
    )


def test_native_extraction_creates_idempotent_revision_quality_and_passage_evidence():
    _work, _edition, asset, _pages = _document()

    first = synchronize_native_extraction(asset)
    repeated = synchronize_native_extraction(asset)

    assert first["status"] == "ready"
    assert first["created"] is True
    assert first["evidence_spans"] == 2
    assert first["critical_pages"] == [1]
    assert repeated["created"] is False
    assert DocumentRevision.objects.filter(asset=asset).count() == 1
    revision = DocumentRevision.objects.get(asset=asset)
    assert revision.is_active is True
    assert revision.source_checksum == asset.sha256
    assert revision.quality_assessments.count() == 1
    assessment = DocumentQualityAssessment.objects.get(document_revision=revision)
    assert assessment.fulltext_quality > 0
    assert assessment.critical_pages == [1]
    assert EvidenceSpan.objects.filter(
        document_revision=revision,
        passage__isnull=False,
        is_stale=False,
    ).count() == 2


def test_selective_ocr_preserves_page_identity_and_only_stales_affected_evidence_and_claims():
    work, edition, asset, pages = _document(title="选择性 OCR")
    synchronize_native_extraction(asset)
    native_revision = DocumentRevision.objects.get(asset=asset, is_active=True)
    native_evidence = {
        span.page_number: span
        for span in EvidenceSpan.objects.filter(document_revision=native_revision)
    }
    changed_claim = _claim(
        revision=native_revision,
        evidence=native_evidence[1],
        work=work,
        edition=edition,
        fingerprint="changed-page-claim",
    )
    unchanged_claim = _claim(
        revision=native_revision,
        evidence=native_evidence[2],
        work=work,
        edition=edition,
        fingerprint="unchanged-page-claim",
    )
    curated = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.CORE_VIEWPOINT,
        proposition="第二页的人工策展观点应沿用有效依据。",
        status=CuratedClaim.Status.PUBLISHED,
    )
    ClaimEvidence.objects.create(
        curated_claim=curated,
        evidence_span=native_evidence[2],
        role=ClaimEvidence.Role.PRIMARY,
    )
    stable_page_id = pages[0].pk

    Passage.objects.filter(page=pages[0]).delete()
    ocr_text = "OCR 后的第一页原文，命题与定位都只影响当前页面。" * 4
    pages[0].text = ocr_text
    pages[0].normalized_text = ocr_text
    pages[0].text_source = Page.TextSource.OCR
    pages[0].confidence = 0.94
    pages[0].save(
        update_fields=[
            "text",
            "normalized_text",
            "text_source",
            "confidence",
            "updated_at",
        ]
    )
    Passage.objects.create(
        page=pages[0],
        order=0,
        text=ocr_text,
        normalized_text=ocr_text,
        start_offset=0,
        end_offset=len(ocr_text),
        bbox_union=[11, 21, 301, 501],
    )

    result = synchronize_ocr_completion(
        asset,
        page_indexes=[1],
        provider="paddleocr_nas",
        provider_version="runtime-v1",
        schedule_claims=False,
    )
    repeated = synchronize_ocr_completion(
        asset,
        page_indexes=[1],
        provider="paddleocr_nas",
        provider_version="runtime-v1",
        schedule_claims=False,
    )

    assert result["created"] is True
    assert result["stale_evidence_spans"] == 1
    assert result["stale_derived_claims"] == 1
    assert repeated["created"] is False
    assert DocumentRevision.objects.filter(asset=asset).count() == 2
    assert Page.objects.get(asset=asset, index=1).pk == stable_page_id
    native_evidence[1].refresh_from_db()
    native_evidence[2].refresh_from_db()
    changed_claim.refresh_from_db()
    unchanged_claim.refresh_from_db()
    assert native_evidence[1].is_stale is True
    assert native_evidence[2].is_stale is False
    assert changed_claim.status == DerivedClaim.Status.STALE
    assert unchanged_claim.status == DerivedClaim.Status.SUPERSEDED
    ocr_revision = DocumentRevision.objects.get(asset=asset, is_active=True)
    assert ocr_revision.revision == 2
    assert ocr_revision.ocr_provider == "paddleocr_nas"
    assert EvidenceSpan.objects.filter(
        document_revision=ocr_revision,
        passage__isnull=False,
        is_stale=False,
    ).count() == 2
    carried = DerivedClaim.objects.get(
        document_revision=ocr_revision,
        fingerprint="unchanged-page-claim",
    )
    assert carried.status == DerivedClaim.Status.ACTIVE
    assert carried.primary_evidence.page_number == 2
    assert not DerivedClaim.objects.filter(
        document_revision=ocr_revision,
        fingerprint="changed-page-claim",
    ).exists()
    assert result["carried_forward_claims"] == 1
    assert result["carried_forward_curated_evidence"] == 1
    assert ClaimEvidence.objects.filter(
        curated_claim=curated,
        evidence_span__document_revision=ocr_revision,
        evidence_span__page_number=2,
    ).exists()

    edition.state = "published"
    edition.save(update_fields=["state", "updated_at"])
    assert visible_claim_queryset({"work_ids": [str(work.id)]}).filter(
        pk=carried.pk
    ).exists()

    scheduled = schedule_document_claim_extraction(
        ocr_revision,
        page_indexes=[1],
    )
    assert scheduled["evidence_spans"] == 1
    assert scheduled["scheduled"] == 1
    demand = CapabilityDemand.objects.get(pk=scheduled["demand_ids"][0])
    assert demand.owner_key == str(
        EvidenceSpan.objects.get(
            document_revision=ocr_revision,
            page_number=1,
            is_stale=False,
        ).id
    )


def test_best_effort_document_intelligence_failure_is_non_blocking():
    _work, _edition, asset, _pages = _document(title="降级不阻断")

    with patch(
        "catalog.services.document_intelligence.synchronize_native_extraction",
        side_effect=RuntimeError("optional derived processing unavailable"),
    ):
        result = best_effort_native_extraction(asset)

    assert result == {
        "status": "degraded",
        "error_code": "RuntimeError",
        "message": "optional derived processing unavailable",
    }
    assert DocumentRevision.objects.filter(asset=asset).exists() is False


def test_evidence_and_claim_writers_reject_cross_document_identity():
    work_a, edition_a, asset_a, _pages_a = _document(title="一致性来源 A")
    work_b, edition_b, asset_b, pages_b = _document(title="一致性来源 B")
    synchronize_native_extraction(asset_a, schedule_claims=False)
    synchronize_native_extraction(asset_b, schedule_claims=False)
    revision_a = DocumentRevision.objects.get(asset=asset_a, is_active=True)
    revision_b = DocumentRevision.objects.get(asset=asset_b, is_active=True)
    evidence_a = EvidenceSpan.objects.filter(document_revision=revision_a).first()
    evidence_b = EvidenceSpan.objects.filter(document_revision=revision_b).first()

    with pytest.raises(ValidationError, match="DocumentRevision"):
        EvidenceSpan.objects.create(
            document_revision=revision_a,
            page=pages_b[0],
            page_number=pages_b[0].index,
            original_text="错误跨文档证据",
            normalized_text="错误跨文档证据",
            content_hash="6" * 64,
        )

    with pytest.raises(ValidationError, match="Edition"):
        DerivedClaim.objects.create(
            document_revision=revision_a,
            primary_evidence=evidence_a,
            work=work_b,
            edition=edition_b,
            proposition="错误跨作品命题",
            claim_type=DerivedClaim.ClaimType.ASSERTION,
            prompt_key="test",
            prompt_version="1",
            model_provider="test",
            model_name="test",
            fingerprint="5" * 64,
        )

    valid_claim = _claim(
        revision=revision_a,
        evidence=evidence_a,
        work=work_a,
        edition=edition_a,
        fingerprint="valid-for-link-check",
    )
    with pytest.raises(ValidationError, match="同一 DocumentRevision"):
        ClaimEvidence.objects.create(
            derived_claim=valid_claim,
            evidence_span=evidence_b,
            role=ClaimEvidence.Role.SUPPORTS,
        )


def test_claim_shadow_is_scheduled_only_after_revision_evidence_commit(
    django_capture_on_commit_callbacks,
):
    _work, _edition, asset, _pages = _document(title="提交后命题调度")

    with patch(
        "catalog.services.document_intelligence._schedule_claim_shadow"
    ) as schedule:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            result = synchronize_native_extraction(asset)
            assert schedule.called is False

    assert len(callbacks) == 1
    schedule.assert_called_once_with(result["revision_id"], page_indexes=None)
    revision = DocumentRevision.objects.get(pk=result["revision_id"])
    assert revision.evidence_spans.filter(is_stale=False).count() == 2


def test_backfill_command_builds_evidence_without_eager_claim_fanout():
    _work, _edition, asset, _pages = _document(title="历史文档回填")
    output = StringIO()

    call_command(
        "backfill_v3_document_intelligence",
        phase="document",
        batch_size=1,
        asset_id=[str(asset.id)],
        stdout=output,
    )

    revision = DocumentRevision.objects.get(asset=asset, is_active=True)
    assert revision.parser_version == "4b97a3484db0c3918f5b0fef8bfc75c35bd0dcee"
    assert revision.evidence_spans.filter(is_stale=False).count() == 2
    assert CapabilityDemand.objects.count() == 0
    assert "已回填 1 个 DocumentRevision" in output.getvalue()
