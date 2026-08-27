from __future__ import annotations

from uuid import uuid4

import pytest

from catalog.models import (
    Asset,
    DerivedClaim,
    DocumentRevision,
    Edition,
    EvidenceSpan,
    Page,
    PublicationState,
    Work,
)
from reading.library_query import LibraryQuery, LibraryScope, ResolvedLibraryScope
from reading.library_retrieval import (
    LibraryRetrievalService,
    _hydrate_evidence,
    _semantic_call,
)


def _query(*, max_passages: int = 8) -> LibraryQuery:
    return LibraryQuery(
        original_query="制度塑造行动",
        normalized_query="制度塑造行动",
        resolved_query="制度塑造行动",
        language="zh",
        query_type="general",
        scope=LibraryScope(context="global"),
        entity_anchors=(),
        conversation_context={},
        retrieval_limits={
            "max_passages": max_passages,
            "max_evidence_chars": 9000,
            "per_work_cap": 3,
            "comparison_per_anchor": 2,
            "max_entity_branches": 3,
        },
        retrieval_profile="stable",
        query_lexicon_revision=3,
    )


def _claim_source(*, title: str, state: str = PublicationState.PUBLISHED, seed: int = 1):
    work = Work.objects.create(document_type="book", title=title, language="zh")
    edition = Edition.objects.create(
        work=work,
        state=state,
        is_primary=True,
        public_slug=f"ask-v3-{seed}-{uuid4().hex[:8]}",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        status=Asset.Status.READY,
        is_current=True,
        file=f"public/ask-v3-{seed}.pdf",
        sha256=f"{12000 + seed:064x}",
        page_count=8,
    )
    page = Page.objects.create(asset=asset, index=3)
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        source_checksum=asset.sha256,
        text_checksum=f"{13000 + seed:064x}",
        parser_name="test",
        parser_version="1",
        extraction_method="native",
        extraction_version="1",
        is_active=True,
    )
    span = EvidenceSpan.objects.create(
        document_revision=revision,
        page=page,
        page_number=3,
        printed_page_label="17",
        start_offset=0,
        end_offset=18,
        original_text="制度会在具体条件下塑造行动者的选择。",
        normalized_text="制度会在具体条件下塑造行动者的选择",
        language="zh",
        section="第三章",
        content_hash=f"{14000 + seed:064x}",
        quality=0.91,
    )
    claim = DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=span,
        work=work,
        edition=edition,
        proposition="制度塑造行动者的选择",
        subject="制度",
        predicate="塑造",
        object="行动者的选择",
        polarity=DerivedClaim.Polarity.POSITIVE,
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        claim_type=DerivedClaim.ClaimType.CAUSAL,
        prompt_key="claim_extraction",
        prompt_version="1",
        model_provider="test",
        model_name="test-model",
        quality_score=0.9,
        importance_score=0.8,
        fingerprint=f"{15000 + seed:064x}",
        shadow=True,
    )
    return work, edition, asset, page, revision, span, claim


def test_ask_semantic_recall_uses_shared_reader_qa_profile(monkeypatch):
    calls = []

    def fake_unified(query, **kwargs):
        calls.append((query, kwargs))
        return {"results": [], "engine": "test", "search_version": "v2"}

    monkeypatch.setattr("reading.library_retrieval.unified_retrieve", fake_unified)
    scope = ResolvedLibraryScope(
        scope=LibraryScope(context="works"),
        semantic_filters={"work_ids": [str(uuid4())]},
    )

    result = _semantic_call(
        "制度塑造行动",
        resolved_scope=scope,
        retrieval_profile="stable",
        limit=9,
        max_per_work=2,
    )

    assert calls[0][1]["profile"] == "reader_qa"
    assert calls[0][1]["filters"] == scope.semantic_filters
    assert result["unified_retrieval_profile"] == "reader_qa"
    assert result["library_requested_profile"] == "stable"


@pytest.mark.django_db
def test_semantic_hit_is_rehydrated_from_current_evidence_span():
    work, edition, asset, page, revision, span, _claim = _claim_source(
        title="证据定位测试",
        seed=2,
    )
    rows = [
        {
            "id": str(uuid4()),
            "asset_id": str(asset.id),
            "edition_id": str(edition.id),
            "work_id": str(work.id),
            "title": work.title,
            "page_index": 3,
            "snippet": f"前文。{span.original_text}后文。",
            "language": "zh",
        }
    ]

    evidence = _hydrate_evidence(rows, retrieval_profile="stable")

    assert len(evidence) == 1
    assert evidence[0].original_passage == span.original_text
    assert evidence[0].page_id == str(page.id)
    assert evidence[0].reader_url == (
        f"/reader/{asset.id}?page=3&passage={span.id}"
    )
    assert evidence[0].retrieval_provenance["evidence_span_id"] == str(span.id)
    assert evidence[0].retrieval_provenance["document_revision_id"] == str(revision.id)


@pytest.mark.django_db
def test_claim_recall_only_contributes_its_public_original_evidence(monkeypatch):
    _work, _edition, _asset, _page, _revision, public_span, public_claim = _claim_source(
        title="公开 Claim 来源",
        seed=3,
    )
    *_draft, draft_span, draft_claim = _claim_source(
        title="未公开 Claim 来源",
        state=PublicationState.DRAFT,
        seed=4,
    )

    monkeypatch.setattr(
        "reading.library_retrieval._result_rows",
        lambda *_args, **_kwargs: ([], []),
    )
    monkeypatch.setattr(
        "reading.library_retrieval.active_semantic_index_uid",
        lambda: "semantic-test",
    )
    monkeypatch.setattr(
        "reading.library_retrieval.search_claim_index",
        lambda *_args, **_kwargs: {
            "backend": "test",
            "hits": [
                {
                    "claim_id": str(public_claim.id),
                    "document_revision_id": str(public_claim.document_revision_id),
                    "evidence_span_id": str(public_span.id),
                },
                {
                    "claim_id": str(draft_claim.id),
                    "document_revision_id": str(draft_claim.document_revision_id),
                    "evidence_span_id": str(draft_span.id),
                },
            ],
        },
    )

    result = LibraryRetrievalService().retrieve(
        library_query=_query(),
        resolved_scope=ResolvedLibraryScope(
            scope=LibraryScope(context="global"),
            semantic_filters={},
        ),
    )

    assert result.sufficient is True
    assert [row.original_passage for row in result.evidence] == [public_span.original_text]
    assert result.evidence[0].original_passage != public_claim.proposition
    assert result.evidence[0].retrieval_provenance["source_kind"] == "derived_claim_evidence"
    assert result.metadata["unified_retrieval_profile"] == "reader_qa"
    assert result.metadata["derived_claim_recall"]["validated_count"] == 1
    assert result.metadata["derived_claim_recall"]["rejected_count"] == 1
    assert result.metadata["answer_evidence_kind"] == "collection_original_text"


@pytest.mark.django_db
def test_claim_recall_failure_does_not_discard_semantic_original_evidence(monkeypatch):
    work, edition, asset, _page, _revision, span, _claim = _claim_source(
        title="Claim 降级来源",
        seed=5,
    )
    monkeypatch.setattr(
        "reading.library_retrieval._result_rows",
        lambda *_args, **_kwargs: (
            [
                {
                    "id": str(uuid4()),
                    "asset_id": str(asset.id),
                    "edition_id": str(edition.id),
                    "work_id": str(work.id),
                    "title": work.title,
                    "page_index": 3,
                    "snippet": span.original_text,
                    "language": "zh",
                    "_retrieval_branch": "primary",
                }
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        "reading.library_retrieval.search_claim_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("claim index down")),
    )
    monkeypatch.setattr(
        "reading.library_retrieval.active_semantic_index_uid",
        lambda: "semantic-test",
    )

    result = LibraryRetrievalService().retrieve(
        library_query=_query(),
        resolved_scope=ResolvedLibraryScope(
            scope=LibraryScope(context="global"),
            semantic_filters={},
        ),
    )

    assert result.sufficient is True
    assert [row.original_passage for row in result.evidence] == [span.original_text]
    assert result.metadata["derived_claim_recall"]["status"] == "degraded"
