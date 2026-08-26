from hashlib import sha256

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from catalog.models import (
    Asset,
    CuratedClaim,
    DebateCandidate,
    DerivedClaim,
    DocumentRevision,
    Edition,
    EnrichmentCandidate,
    EnrichmentEvidence,
    EnrichmentSourceClass,
    EvidencePack,
    EvidenceSpan,
    Page,
    ReadingPathCandidate,
    Work,
)
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.evidence_envelope import evidence_span_envelope


pytestmark = pytest.mark.django_db


def _growth_fixture():
    work = Work.objects.create(
        title="知识增长测试作品",
        document_type="book",
        language="zh-CN",
        is_featured=True,
    )
    edition = Edition.objects.create(
        work=work,
        state="published",
        public_slug="knowledge-growth-v302",
        is_primary=True,
    )
    content = b"%PDF-1.4 knowledge growth"
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("knowledge-growth.pdf", content),
        sha256=sha256(content).hexdigest(),
        byte_size=len(content),
        page_count=2,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    claim_page = Page.objects.create(
        asset=asset,
        index=1,
        printed_label="7",
        text="制度安排会改变行动者的策略选择。",
        normalized_text="制度安排会改变行动者的策略选择。",
        text_source=Page.TextSource.EMBEDDED,
    )
    raw_page = Page.objects.create(
        asset=asset,
        index=2,
        printed_label="8",
        text="新的原文材料尚未形成机器命题。",
        normalized_text="新的原文材料尚未形成机器命题。",
        text_source=Page.TextSource.EMBEDDED,
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="growth-test",
        source_checksum="a" * 64,
        text_checksum="b" * 64,
        is_active=True,
    )
    claim_span = EvidenceSpan.objects.create(
        document_revision=revision,
        page=claim_page,
        page_number=1,
        printed_page_label="7",
        original_text=claim_page.text,
        normalized_text=claim_page.normalized_text,
        content_hash="c" * 64,
        quality=0.95,
    )
    raw_span = EvidenceSpan.objects.create(
        document_revision=revision,
        page=raw_page,
        page_number=2,
        printed_page_label="8",
        original_text=raw_page.text,
        normalized_text=raw_page.normalized_text,
        content_hash="d" * 64,
        quality=0.86,
    )
    claim = DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=claim_span,
        work=work,
        edition=edition,
        proposition="制度安排会改变行动者的策略选择。",
        subject="制度安排",
        predicate="改变",
        object="行动者的策略选择",
        polarity=DerivedClaim.Polarity.POSITIVE,
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        claim_type=DerivedClaim.ClaimType.CAUSAL,
        prompt_key="claim_extraction",
        prompt_version="growth-test",
        model_provider="local",
        model_name="test-model",
        quality_score=0.92,
        importance_score=0.9,
        cluster_key="institution-action",
        fingerprint="e" * 64,
        shadow=True,
    )
    enrichment = EnrichmentCandidate.objects.create(
        target_type=EnrichmentCandidate.TargetType.WORK,
        target_id=work.id,
        field_name="abstract",
        candidate_kind=EnrichmentCandidate.CandidateKind.INTERPRETIVE,
        proposed_value={"text": "基于馆藏证据的作品摘要候选。"},
        source_class=EnrichmentSourceClass.NATIONAL_LIBRARY,
        confidence=0.84,
        conflict_group="knowledge-growth-abstract",
        policy_version="growth-test",
        extraction_version="growth-test",
        fingerprint="f" * 64,
    )
    EnrichmentEvidence.objects.create(
        candidate=enrichment,
        source_url="https://example.org/catalog/knowledge-growth",
        canonical_url="https://example.org/catalog/knowledge-growth",
        source_title="测试馆藏目录记录",
        source_domain="example.org",
        source_class=EnrichmentSourceClass.NATIONAL_LIBRARY,
        provider="test_catalog",
        supporting_text="目录记录与当前作品身份一致。",
        retrieved_at=timezone.now(),
        http_status=200,
        content_type="text/html",
        content_checksum="1" * 64,
        extraction_method="citation_meta",
        extraction_version="growth-test",
        confidence=0.9,
        fingerprint="2" * 64,
    )
    envelope = evidence_span_envelope(claim_span).as_dict()
    debate_pack = EvidencePack.objects.create(
        task_profile_key="debate_discovery",
        retrieval_profile="curation",
        subject_type="work",
        subject_id=str(work.id),
        envelope_snapshot=[envelope],
        fingerprint="3" * 64,
    )
    debate = DebateCandidate.objects.create(
        title="制度是否决定行动策略",
        canonical_question="制度是否决定行动者的策略选择？",
        summary="测试争论候选",
        evidence_pack=debate_pack,
        quality_score=0.82,
        importance_score=0.88,
        conflict_score=0.7,
    )
    reading_pack = EvidencePack.objects.create(
        task_profile_key="reading_path_generation",
        retrieval_profile="curation",
        subject_type="work",
        subject_id=str(work.id),
        envelope_snapshot=[envelope],
        fingerprint="4" * 64,
    )
    reading = ReadingPathCandidate.objects.create(
        title="制度与行动阅读路径",
        target_audience="初学者",
        learning_goal="理解制度与行动之间的关系",
        stages=[
            {
                "name": "问题起点",
                "works": [{"work_id": str(work.id), "reason": "代表性原文"}],
            }
        ],
        evidence_pack=reading_pack,
        quality_score=0.8,
        importance_score=0.83,
    )
    return work, edition, raw_span, claim, enrichment, debate, reading


def test_knowledge_growth_is_bounded_derived_read_model_with_existing_actions(
    api_client,
    admin_user,
):
    work, edition, raw_span, claim, enrichment, debate, reading = _growth_fixture()
    before = {
        "claims": DerivedClaim.objects.count(),
        "curated": CuratedClaim.objects.count(),
        "enrichment": EnrichmentCandidate.objects.count(),
        "debates": DebateCandidate.objects.count(),
        "reading": ReadingPathCandidate.objects.count(),
        "evidence": EvidenceSpan.objects.count(),
    }
    api_client.force_authenticate(admin_user)

    response = api_client.get(
        "/api/catalog/admin/knowledge-workspace/",
        {"selected_type": "work", "selected_id": str(work.id)},
    )

    assert response.status_code == 200
    studio = response.data["studio"]
    selected = studio["selection"]
    updates = selected["knowledge_update_suggestions"]
    assert len(updates) == 5
    assert {row["knowledge_update_kind"] for row in updates} == {
        "field_enrichment",
        "claim_curation",
        "debate_discovery",
        "reading_path_generation",
        "evidence_review",
    }
    assert selected["knowledge_update_signal_counts"] == {
        "evidence_spans": 1,
        "derived_claims": 1,
        "enrichment_candidates": 1,
        "debate_candidates": 1,
        "reading_path_candidates": 1,
    }
    assert selected["knowledge_update_read_model"] == {
        "visible_count": 5,
        "limit": 5,
        "derived_read_model": True,
        "persistent_model": None,
        "canonical_write_policy": "human_decision_only",
    }

    by_kind = {row["knowledge_update_kind"]: row for row in updates}
    assert by_kind["field_enrichment"]["id"] == str(enrichment.id)
    assert by_kind["claim_curation"]["id"] == str(claim.id)
    assert by_kind["debate_discovery"]["id"] == str(debate.id)
    assert by_kind["reading_path_generation"]["id"] == str(reading.id)
    assert by_kind["evidence_review"]["id"] == str(raw_span.id)

    for kind in (
        "field_enrichment",
        "claim_curation",
        "debate_discovery",
        "reading_path_generation",
    ):
        descriptors = {
            row["key"]: row for row in by_kind[kind]["action_descriptors"]
        }
        assert descriptors["accept"]["method"] == "POST"
        assert descriptors["accept"]["endpoint"] == by_kind[kind]["decision_url"]
        assert descriptors["accept"]["availability"]["available"] is True
    evidence_descriptors = by_kind["evidence_review"]["action_descriptors"]
    assert [row["key"] for row in evidence_descriptors] == ["inspect"]
    assert evidence_descriptors[0]["method"] == "CLIENT"
    assert evidence_descriptors[0]["availability"]["available"] is True

    assert {row["knowledge_update_kind"] for row in studio["knowledge_update_suggestions"]} >= {
        "field_enrichment",
        "claim_curation",
        "debate_discovery",
        "reading_path_generation",
        "evidence_review",
    }
    assert studio["knowledge_update_read_model"]["persistent_model"] is None

    workspace = build_admin_workspace(
        edition,
        user=admin_user,
        mode="maintenance",
    )
    assert workspace["candidates"]["knowledge_updates"] == workspace["data"]["curation"][
        "knowledge_update_suggestions"
    ]
    assert {row["knowledge_update_kind"] for row in workspace["candidates"]["knowledge_updates"]} == {
        "field_enrichment",
        "claim_curation",
        "debate_discovery",
        "reading_path_generation",
        "evidence_review",
    }

    assert {
        "claims": DerivedClaim.objects.count(),
        "curated": CuratedClaim.objects.count(),
        "enrichment": EnrichmentCandidate.objects.count(),
        "debates": DebateCandidate.objects.count(),
        "reading": ReadingPathCandidate.objects.count(),
        "evidence": EvidenceSpan.objects.count(),
    } == before
