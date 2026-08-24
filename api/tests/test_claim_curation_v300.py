from __future__ import annotations

from django.core.files.uploadedfile import SimpleUploadedFile
import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    ClaimEvidence,
    CuratedClaim,
    DerivedClaim,
    DocumentRevision,
    DocumentType,
    Edition,
    EvidenceSpan,
    IntelligenceFeedback,
    Page,
    ProjectionState,
    PublicationState,
    Work,
)
from catalog.services.claims.curation import (
    _publishable_draft_claims_queryset,
    decide_claim_curation_candidate,
    high_value_claim_candidates,
    publish_work_curated_claims,
)
from ingestion.services.publication import publish_edition


def _source():
    work = Work.objects.create(document_type=DocumentType.BOOK, title="命题策展测试", language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        publication_year=2026,
        public_slug=f"claim-curation-{work.id}",
        state=PublicationState.PUBLISHED,
    )
    Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file=SimpleUploadedFile("original.pdf", b"%PDF-1.4 original"),
        sha256="1" * 64,
        byte_size=17,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
    )
    normalized = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("normalized.pdf", b"%PDF-1.4 normalized"),
        sha256="2" * 64,
        byte_size=19,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status=Asset.AccessStatus.PUBLIC,
    )
    page = Page.objects.create(
        asset=normalized,
        index=1,
        printed_label="1",
        text="制度会改变行动策略，但制度并不必然带来服从。",
        normalized_text="制度会改变行动策略，但制度并不必然带来服从。",
        text_source=Page.TextSource.EMBEDDED,
    )
    revision = DocumentRevision.objects.create(
        asset=normalized,
        revision=1,
        source_checksum="3" * 64,
        text_checksum="4" * 64,
        is_active=True,
    )
    evidence = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        page_number=1,
        printed_page_label="1",
        original_text=page.text,
        normalized_text=page.normalized_text,
        content_hash="5" * 64,
        quality=0.92,
        is_stale=False,
    )
    return work, edition, revision, evidence


def _claim(*, work, edition, revision, evidence, index, cluster, claim_type, polarity="positive"):
    return DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=evidence,
        work=work,
        edition=edition,
        proposition=f"命题 {index} 说明制度如何塑造行动。",
        subject="制度",
        predicate="塑造",
        object=f"行动 {cluster}",
        polarity=polarity,
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        claim_type=claim_type,
        prompt_key="research.claim_extraction",
        prompt_version="1",
        model_provider="local",
        model_name="test-model",
        quality_score=0.75 + (index % 4) * 0.05,
        importance_score=0.7 + (index % 5) * 0.04,
        cluster_key=cluster,
        fingerprint=f"{index:064x}",
        shadow=True,
    )


@pytest.mark.django_db
def test_claim_volume_is_compressed_to_five_decisions_then_human_adoption_publishes():
    work, edition, revision, evidence = _source()
    claims = []
    types = [
        DerivedClaim.ClaimType.ASSERTION,
        DerivedClaim.ClaimType.CRITICISM,
        DerivedClaim.ClaimType.RESPONSE,
    ]
    for index in range(24):
        claims.append(
            _claim(
                work=work,
                edition=edition,
                revision=revision,
                evidence=evidence,
                index=index + 1,
                cluster=f"{types[index % len(types)]}-cluster-{index % 6}",
                claim_type=types[index % len(types)],
                polarity="negative" if index == 8 else "positive",
            )
        )
    editor = User.objects.create_user(
        username="claim-curation-editor@example.test",
        email="claim-curation-editor@example.test",
        password="Claim-Curation-2026",
        role=User.Role.EDITOR,
        is_staff=True,
    )

    candidates = high_value_claim_candidates(work, reviewer=editor)

    assert len(candidates) == 5
    assert {row["field_name"] for row in candidates} >= {
        "core_viewpoint",
        "major_criticism",
        "major_response",
    }
    assert all(row["evidence_count"] == 1 and row["evidence"] for row in candidates)
    assert any(row["cluster_size"] > 1 for row in candidates)
    chosen = DerivedClaim.objects.get(pk=candidates[0]["id"])
    curated = decide_claim_curation_candidate(
        work=work,
        claim=chosen,
        decision=IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT,
        actor=editor,
        proposition="经编辑确认，制度会在特定条件下塑造行动策略。",
    )

    assert curated is not None
    assert curated.status == CuratedClaim.Status.DRAFT
    assert curated.evidence_links.get().evidence_span_id == evidence.id
    chosen.refresh_from_db()
    assert chosen.status == DerivedClaim.Status.ACTIVE
    assert IntelligenceFeedback.objects.get(candidate_id=str(chosen.id)).decision == "accept_with_edit"

    publish_edition(edition, actor=editor, confirm_warnings=True)
    curated.refresh_from_db()
    assert curated.status == CuratedClaim.Status.PUBLISHED
    assert curated.published_by_id == editor.id
    projection = ProjectionState.objects.get(
        object_type="curated_claim",
        object_id=curated.id,
        projection_type=ProjectionState.ProjectionType.PUBLIC,
    )
    assert projection.source_revision >= 2
    assert projection.projected_revision < projection.source_revision


@pytest.mark.django_db
def test_publish_query_locks_claim_rows_without_postgres_distinct_conflict():
    work, _edition, _revision, evidence = _source()
    editor = User.objects.create_user(
        username="claim-publish-lock-editor@example.test",
        email="claim-publish-lock-editor@example.test",
        password="Claim-Publish-Lock-2026",
        role=User.Role.EDITOR,
        is_staff=True,
    )
    publishable = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.CORE_VIEWPOINT,
        proposition="有有效原文依据的策展命题。",
        created_by=editor,
    )
    ClaimEvidence.objects.create(
        curated_claim=publishable,
        evidence_span=evidence,
        role=ClaimEvidence.Role.PRIMARY,
    )
    without_evidence = CuratedClaim.objects.create(
        work=work,
        kind=CuratedClaim.Kind.MAJOR_CRITICISM,
        proposition="没有原文依据的草稿不能发布。",
        created_by=editor,
    )

    queryset = _publishable_draft_claims_queryset(work)
    sql = str(queryset.query).upper()

    assert queryset.query.select_for_update is True
    assert queryset.query.distinct is False
    assert "EXISTS" in sql
    assert "SELECT DISTINCT" not in sql

    published = publish_work_curated_claims(work=work, actor=editor)

    assert [claim.id for claim in published] == [publishable.id]
    publishable.refresh_from_db()
    without_evidence.refresh_from_db()
    assert publishable.status == CuratedClaim.Status.PUBLISHED
    assert without_evidence.status == CuratedClaim.Status.DRAFT
