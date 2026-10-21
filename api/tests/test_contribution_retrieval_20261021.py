"""Responsibility boundaries for unified acceptance; no evaluation/index rebuild."""
from copy import deepcopy
from uuid import uuid4

import pytest

from catalog.discovery_index_models import DiscoveryDocument
from catalog.models import Contribution, DerivedClaim, Edition, EvidenceSpan, Page, Person, SemanticIndexVersion
from catalog.services.catalog_search import SnapshotArrayMatch
from catalog.services.contribution_projection import ContributionProjection, SnapshotAuthorCandidate, author_range_q, contribution_projection
from catalog.services.discovery_projection import DiscoveryIndexError, _author_document_filter, discovery_candidates, validate_discovery_results
from catalog.services.discovery_sources import fingerprint, source_header
from .test_contribution_scope_20261021 import scoped_source
from .v304_helpers import activate_catalog_revision

pytestmark = pytest.mark.django_db


def responsibility_source():
    edition, asset, outline, scope = scoped_source()
    people = [Person.objects.create(preferred_name=name) for name in ("整版作者", "第一章作者", "第二章作者", "译者")]
    for index, person in enumerate(people):
        selected = {} if index in (0, 3) else {"kind": "chapter", "chapters": [deepcopy(scope["chapters"][index - 1])]}
        Contribution.objects.create(edition=edition, person=person, role="translator" if index == 3 else "author", scope=selected, approved=True)
    active = activate_catalog_revision(edition, reader_asset=asset, document_revision=edition.active_catalog_revision.document_revision)
    return edition, asset, active, people, scope


def discovery_documents(edition, asset):
    generation = SemanticIndexVersion.discovery_objects.create(uid=f"acceptance-{uuid4()}", provider="local", status="active", dimensions=384)
    header = source_header("edition", edition)
    documents = []
    for page in asset.pages.order_by("index"):
        documents.append(DiscoveryDocument.objects.create(generation=generation, channel="passages", source_type="edition",
            source_id=edition.pk, source_revision=header["source_revision"], scope_token=header["scope_token"], edition=edition,
            document_revision=edition.active_catalog_revision.document_revision, access_status="public", input_hash="f" * 64,
            text=page.text, normalized_text=page.text, start_offset=0, end_offset=len(page.text), keyword_ready=True,
            payload={"asset_id": str(asset.pk), "page_id": str(page.pk), "pdf_page": page.index, "unit_hash": fingerprint(page.text),
                     "authors": ["旧索引错误扩大作者"], "author_ids": [str(uuid4())]}))
    return generation, header, documents


def test_exact_range_whole_author_and_distinct_chapters_with_request_cache(django_assert_num_queries):
    edition, asset, active, people, _ = responsibility_source()
    cache = {}
    projection = contribution_projection(edition, cache=cache)
    with django_assert_num_queries(0):
        assert contribution_projection(edition, cache=cache) is projection
        assert projection.for_range(asset.pk, active.document_revision_id, 1)["authors"] == [people[0].preferred_name, people[1].preferred_name]
        assert projection.for_range(asset.pk, active.document_revision_id, 2)["authors"] == [people[0].preferred_name, people[2].preferred_name]
        # A cross-chapter span is not wholly attributable to either chapter author.
        assert projection.for_range(asset.pk, active.document_revision_id, 1, 2)["authors"] == [people[0].preferred_name]
        assert projection.for_range(asset.pk, active.document_revision_id, True)["authors"] == []
        assert projection.for_range(asset.pk, uuid4(), 1)["authors"] == []
    # Current drafts/authority renames cannot replace the activated identity.
    people[1].preferred_name = "未发布名称"
    people[1].save(update_fields=["preferred_name"])
    assert "未发布名称" not in ContributionProjection(edition).for_range(asset.pk, active.document_revision_id, 1)["authors"]


@pytest.mark.parametrize("change", ["restricted", "checksum", "inactive_document", "draft"])
def test_public_source_failure_never_uses_whole_or_cached_author(change):
    edition, asset, active, _, _ = responsibility_source()
    if change == "restricted":
        asset.access_status = "restricted"
        asset.save(update_fields=["access_status"])
    elif change == "checksum":
        asset.sha256 = "b" * 64
        asset.save(update_fields=["sha256"])
    elif change == "inactive_document":
        active.document_revision.is_active = False
        active.document_revision.save(update_fields=["is_active"])
    else:
        edition.state = "draft"
        edition.save(update_fields=["state"])
    edition.refresh_from_db()
    assert ContributionProjection(edition).for_range(asset.pk, active.document_revision_id, 1) == {"authors": [], "author_ids": []}



def test_authorized_registered_source_keeps_formal_identity_and_isolates_cache():
    edition, asset, active, people, _ = responsibility_source()
    asset.access_status = "registered"
    asset.save(update_fields=["access_status"])
    edition.refresh_from_db()
    cache = {}
    assert contribution_projection(edition, cache=cache).for_range(asset.pk, active.document_revision_id, 1)["authors"] == []
    permitted = contribution_projection(edition, cache=cache, access_statuses=["inherit", "public", "registered"])
    assert permitted.for_range(asset.pk, active.document_revision_id, 1)["authors"] == [people[0].preferred_name, people[1].preferred_name]
    assert contribution_projection(edition, cache=cache).for_range(asset.pk, active.document_revision_id, 1)["authors"] == []
    assert list(Page.objects.filter(author_range_q([people[1].pk], asset_field="asset_id", page_field="index",
        access_statuses=["public", "inherit", "registered"])).values_list("index", flat=True)) == [1]


def test_invalid_chapter_and_withdrawn_outline_never_become_whole_authors():
    edition, asset, active, people, _ = responsibility_source()
    active.snapshot["contributions"] = [row for row in active.snapshot["contributions"] if row["person_id"] != str(people[0].pk)]
    for row in active.snapshot["contributions"]:
        if row["role"] == "author":
            row["scope"]["chapters"][0]["outline_revision_id"] = str(uuid4())
    active.save(update_fields=["snapshot"])
    assert ContributionProjection(edition).for_range(asset.pk, active.document_revision_id, 1)["authors"] == []
    assert ContributionProjection(edition).matching_ranges([people[1].pk]) == []


def test_edition_catalog_filter_and_exact_page_filter_have_distinct_responsibility():
    edition, asset, _, people, _ = responsibility_source()
    assert not Edition.objects.filter(pk=edition.pk).filter(SnapshotArrayMatch("author", identifiers=[str(people[1].pk)])).exists()
    assert Edition.objects.filter(pk=edition.pk).filter(SnapshotArrayMatch("author", identifiers=[str(people[0].pk)])).exists()
    assert Edition.objects.filter(pk=edition.pk).filter(SnapshotAuthorCandidate([people[1].pk])).exists()
    condition = author_range_q([people[1].pk], asset_field="asset_id", page_field="index")
    assert list(Page.objects.filter(condition).values_list("index", flat=True)) == [1]


def test_discovery_prefilters_exact_document_before_rank_and_refreshes_old_author(monkeypatch):
    edition, asset, _, people, scope = responsibility_source()
    generation, header, documents = discovery_documents(edition, asset)
    monkeypatch.setattr("catalog.services.discovery_projection.meili", lambda *args, **kwargs: ["id"])
    predicate = _author_document_filter(generation, {header["scope_token"]: [scope["chapters"][0]]}, ["public"])
    assert str(documents[0].pk) in predicate and str(documents[1].pk) not in predicate
    rows = validate_discovery_results("passages", [{"id": str(doc.pk)} for doc in documents], ["public"], filters={"authors": [str(people[1].pk)]})
    assert len(rows) == 1 and rows[0]["authors"] == [people[0].preferred_name, people[1].preferred_name]
    assert rows[0]["pdf_page"] == 1 and "旧索引错误扩大作者" not in str(rows)


def test_legacy_index_capability_returns_chinese_warning_without_broad_recall(monkeypatch):
    edition, asset, _, people, _ = responsibility_source()
    discovery_documents(edition, asset)
    monkeypatch.setattr("catalog.services.discovery_projection.meili", lambda *args, **kwargs: [])
    monkeypatch.setattr("catalog.services.discovery_projection.normalize_texts", lambda values: {"texts": values})
    result = discovery_candidates("合成章节", "passages", {"authors": [str(people[1].pk)]}, ["public"])
    assert not result["sparse"] and not result["dense"]
    assert result["warnings"] == [{"code": "author_scope_index_pending", "message": "当前索引尚未支持准确章节范围，需通过现有索引任务更新后再按章节作者检索。"}]


def test_large_author_scope_is_explicit_before_sql(django_assert_num_queries):
    with django_assert_num_queries(0), pytest.raises(DiscoveryIndexError, match="400") as error:
        _author_document_filter(None, {f"edition:{number}": [{}] for number in range(401)}, ["public"])
    assert error.value.code == "author_scope_limit"


def test_library_and_claim_hydration_do_not_restore_stale_cached_authors():
    from reading.library_retrieval import _hydrate_evidence
    from catalog.services.claims.indexing import _current_claim_hits
    edition, asset, active, _, _ = responsibility_source()
    active.snapshot["contributions"] = []
    active.save(update_fields=["snapshot"])
    page = asset.pages.get(index=1)
    base = {"id": f"passage:{uuid4()}", "asset_id": str(asset.pk), "page_start": 1,
            "snippet": page.text, "authors": ["旧缓存作者"], "document_revision_id": str(active.document_revision_id)}
    rows = _hydrate_evidence([base], retrieval_profile="balanced")
    assert len(rows) == 1 and rows[0].authors == ()
    span = EvidenceSpan.objects.create(document_revision=active.document_revision, page=page, page_number=1,
        original_text=page.text, start_offset=0, end_offset=len(page.text))
    claim = DerivedClaim.objects.create(document_revision=active.document_revision, primary_evidence=span,
        edition=edition, work=edition.work, proposition="合成观点", claim_type="assertion", fingerprint="c" * 64)
    # Model saves reject this; simulate an old persisted locator that predates validation.
    EvidenceSpan.objects.filter(pk=span.pk).update(page_number=99)
    hits = _current_claim_hits([{"claim_id": str(claim.pk), "document_revision_id": str(active.document_revision_id),
        "evidence_span_id": str(span.pk), "authors": ["旧缓存作者"], "_rankingScore": 0.8}], {})
    assert len(hits) == 1 and hits[0]["authors"] == [] and hits[0]["page_number"] == 1
    edition.state = "withdrawn"
    edition.save(update_fields=["state"])
    assert _current_claim_hits(hits, {}) == []


def retrieval_rows(edition, asset, active):
    from catalog.models import Passage, SemanticChunk
    page = asset.pages.get(index=1)
    chunk = SemanticChunk.objects.create(asset=asset, work=edition.work, order=0, page_start=1, page_end=1,
        original_text=page.text, normalized_text=page.text, document_type="book", parser_version="acceptance",
        chunk_version="acceptance", document_id=uuid4().hex, content_hash="d" * 64)
    passage = Passage.objects.create(page=page, order=0, text=page.text)
    span = EvidenceSpan.objects.create(document_revision=active.document_revision, page=page, page_number=1,
        original_text=page.text, start_offset=0, end_offset=len(page.text))
    claim = DerivedClaim.objects.create(document_revision=active.document_revision, primary_evidence=span,
        edition=edition, work=edition.work, proposition="合成检索边界", claim_type="assertion", fingerprint="e" * 64)
    return chunk, passage, span, claim


@pytest.mark.parametrize("change", ["restricted", "checksum", "empty_checksum", "inactive_document", "file", "validation"])
def test_invalid_source_is_removed_from_all_text_hydration_not_only_authors(change):
    from catalog.services.discovery_sources import source_queryset
    from catalog.services.semantic_search import _base_queryset, _passage_base_queryset
    from catalog.services.claims.indexing import visible_claim_queryset
    from reading.library_retrieval import _hydrate_evidence, _evidence_spans_by_page
    edition, asset, active, _, _ = responsibility_source()
    _, _, documents = discovery_documents(edition, asset)
    chunk, passage, span, claim = retrieval_rows(edition, asset, active)
    filters = {"_allowed_access_statuses": ["public", "inherit"]}
    assert _base_queryset(filters).filter(pk=chunk.pk).exists()
    assert _passage_base_queryset(filters).filter(pk=passage.pk).exists()
    assert visible_claim_queryset(filters).filter(pk=claim.pk).exists()
    if change == "inactive_document":
        active.document_revision.is_active = False
        active.document_revision.save(update_fields=["is_active"])
    else:
        field, value = {"restricted": ("access_status", "restricted"), "checksum": ("sha256", "b" * 64),
            "empty_checksum": ("sha256", ""), "file": ("file", ""), "validation": ("validation_status", "pending")}[change]
        setattr(asset, field, value)
        asset.save(update_fields=[field])
        if change == "empty_checksum":
            active.document_revision.source_checksum = ""
            active.document_revision.save(update_fields=["source_checksum"])
    assert not source_queryset("edition", ["public", "inherit"]).filter(pk=edition.pk).exists()
    assert not _base_queryset(filters).filter(pk=chunk.pk).exists()
    assert not _passage_base_queryset(filters).filter(pk=passage.pk).exists()
    assert not visible_claim_queryset(filters).filter(pk=claim.pk).exists()
    assert validate_discovery_results("passages", [{"id": str(row.pk)} for row in documents], ["public", "inherit"]) == []
    stale = {"id": str(chunk.pk), "asset_id": str(asset.pk), "page_start": 1, "snippet": span.original_text}
    assert _evidence_spans_by_page([stale], access_statuses=["public", "inherit"]) == {}
    assert _hydrate_evidence([stale], retrieval_profile="balanced", access_statuses=["public", "inherit"]) == []


def test_explicit_empty_access_does_not_fall_back_to_public_sources():
    from catalog.services.semantic_search import _base_queryset, _passage_base_queryset
    from catalog.services.claims.indexing import visible_claim_queryset
    from reading.library_retrieval import _hydrate_evidence
    edition, asset, active, _, _ = responsibility_source()
    chunk, passage, span, claim = retrieval_rows(edition, asset, active)
    filters = {"_allowed_access_statuses": []}
    assert not _base_queryset(filters).exists() and not _passage_base_queryset(filters).exists()
    assert not visible_claim_queryset(filters).exists()
    assert _hydrate_evidence([{"id": str(chunk.pk), "asset_id": str(asset.pk), "page_start": 1,
        "snippet": span.original_text}], retrieval_profile="balanced", access_statuses=[]) == []


def test_author_filter_survives_merge_cached_deep_context_and_document_receipts(monkeypatch):
    from catalog.models import DocumentOutlineRevision
    from catalog.services import discovery_sessions as sessions
    from catalog.services.discovery_documents import DOCUMENTS_KEY, begin_document_query
    from catalog.services.discovery_context import session_context
    from rest_framework.exceptions import NotFound
    from .test_discovery_sessions_v308 import make_session
    edition, asset, active, people, scope = responsibility_source()
    generation, header, documents = discovery_documents(edition, asset)
    session = make_session(documents, status="running")
    session.filters = {"authors": [str(people[1].pk)]}
    session.results[sessions.DEEP_RESULTS_KEY] = list(session.results["passages"])
    session.save(update_fields=["filters", "results"])
    assert len(sessions._rehydrate(session, session.access_statuses)["passages"]) == 1
    assert len(sessions._rehydrate_deep(session, session.access_statuses)) == 1
    begin_document_query(session.pk, session.generation, session.task_id, [header["scope_token"]], generation)
    session.refresh_from_db()
    assert [row["edition_id"] for row in session.results[DOCUMENTS_KEY]["rows"]] == [str(edition.pk)]
    # The catalog pointer stays unchanged; directory validity is checked anew.
    DocumentOutlineRevision.objects.filter(pk=scope["chapters"][0]["outline_revision_id"]).update(is_active=False)
    assert edition.active_catalog_revision_id == active.pk
    assert sessions._rehydrate(session, session.access_statuses)["passages"] == []
    assert sessions._rehydrate_deep(session, session.access_statuses) == []
    with pytest.raises(NotFound):
        session_context(session, str(documents[0].pk), session.access_statuses)
    monkeypatch.setattr("catalog.services.discovery_projection.discovery_candidates", lambda *args, **kwargs: {
        "sparse": session.results["passages"], "dense": [], "warnings": [], "version": str(generation.pk)})
    result = sessions.retrieve_discovery_channel("合成章节", "passages", session.filters, session.access_statuses)
    assert result["rows"] == []
