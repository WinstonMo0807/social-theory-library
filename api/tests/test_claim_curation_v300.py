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
    decide_claim_curation_candidate,
    high_value_claim_candidates,
    publish_work_curated_claims,
)
from ingestion.services.publication import publish_edition
from .publication_fixtures import confirm_book_identity


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
    from catalog.services.document_intelligence import document_text_checksum
    from catalog.services.knowledge_sources import digest
    revision.source_checksum=normalized.sha256;revision.text_checksum=document_text_checksum(normalized);revision.save()
    evidence.start_offset=0;evidence.end_offset=len(page.text);evidence.content_hash=digest(page.text);evidence.save()
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
def test_legacy_claim_adoption_uses_reviewed_changeset_and_separate_publication():
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

    from catalog import models as m
    assert curated is not None and curated["status"]=="draft"
    assert not CuratedClaim.objects.exists()
    changeset=m.ChangeSet.objects.get(pk=curated["changeset_id"])
    statement=m.Assertion.objects.get(pk=changeset.items.get(kind="assertion").application["id"])
    assert statement.status=="draft" and statement.evidence.get().anchor.document_revision==revision
    assert IntelligenceFeedback.objects.get(candidate_id=str(chosen.id)).decision=="accept_with_edit"
    repeat=decide_claim_curation_candidate(work=work,claim=chosen,decision="accept_with_edit",actor=editor,
        proposition="经编辑确认，制度会在特定条件下塑造行动策略。")
    assert repeat["changeset_id"]==curated["changeset_id"] and m.Assertion.objects.count()==1
    with pytest.raises(ValueError,match="不能重复采用覆盖"):
        decide_claim_curation_candidate(work=work,claim=chosen,decision="accept_with_edit",actor=editor,proposition="另一项修改")
    edition.state=PublicationState.DRAFT;edition.save()
    confirm_book_identity(edition, editor)
    publish_edition(edition, actor=editor, confirm_warnings=True)
    statement.refresh_from_db()
    assert statement.status=="draft"  # Catalogue publication cannot publish knowledge implicitly.
    assert m.KnowledgePage.objects.get(work=work).status=="draft"


@pytest.mark.django_db
def test_legacy_work_publisher_preserves_human_drafts_without_implicit_publication():
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

    published = publish_work_curated_claims(work=work, actor=editor)
    assert published == []
    publishable.refresh_from_db();without_evidence.refresh_from_db()
    assert publishable.status == without_evidence.status == CuratedClaim.Status.DRAFT
    assert ClaimEvidence.objects.filter(curated_claim=publishable).count()==1
