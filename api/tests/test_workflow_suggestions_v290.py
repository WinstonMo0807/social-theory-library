from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.utils import timezone

from accounts.models import User
from catalog.models import (
    Asset,
    Discipline,
    DocumentType,
    Edition,
    EnrichmentCandidate,
    EnrichmentSourceClass,
    KnowledgeNode,
    Page,
    QueryLexiconCandidate,
    QueryLexiconCandidateEvidence,
    QueryLexiconChangeEvent,
    SemanticChunk,
    Work,
    WorkDisciplineRelation,
)
from catalog.services.field_enrichment.mutations import (
    accept_enrichment_candidate,
    reject_enrichment_candidate,
)
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.field_enrichment.service import FieldEnrichmentService
from catalog.services.field_enrichment.types import (
    FetchedDocument,
    FieldEnrichmentRequest,
    FieldObservation,
    SearchResult,
)
from catalog.services.query_lexicon.sync import rebuild_query_lexicon
from catalog.services.workflow_suggestion_policies import (
    SOURCE_PROFILES,
    WORKFLOW_SUGGESTION_POLICIES,
)
from catalog.services.workflow_suggestions import WorkflowSuggestionAggregator
from ingestion.models import EntityResolutionCandidate, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


def _edition(*, document_type=DocumentType.BOOK, title="候选研究作品"):
    work = Work.objects.create(
        document_type=document_type,
        title=title,
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        publication_year=2026,
        publisher="测试出版社",
        journal_title="社会理论研究" if document_type == DocumentType.JOURNAL_ARTICLE else "",
    )
    return work, edition


def _item(admin_user, edition):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        source_filename="candidate.pdf",
        edition=edition,
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )


def _asset(work, edition, text="候选研究作品讨论历史社会学和国家形成。"):
    digest = uuid4().hex * 2
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/test/{digest}.pdf",
        sha256=digest,
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        is_current=True,
    )
    page = Page.objects.create(
        asset=asset,
        index=1,
        printed_label="1",
        text=text,
        normalized_text=text.casefold(),
        text_source=Page.TextSource.OCR,
    )
    chunk = SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text=text,
        normalized_text=text.casefold(),
        language="zh",
        document_type=work.document_type,
        parser_version="test-parser",
        chunk_version="test-chunk",
        document_id=sha256(f"{asset.id}:1".encode()).hexdigest(),
        content_hash=sha256(text.encode()).hexdigest(),
        index_status=SemanticChunk.IndexStatus.READY,
    )
    return asset, page, chunk


class FakeStructuredAdapter:
    def __init__(self, observations):
        self.observations = observations

    def collect(self, **kwargs):
        return list(self.observations), []


class FakeSearchAdapter:
    name = "fake-search"

    def __init__(self, result):
        self.result = result
        self.calls = 0

    def search(self, query, *, limit):
        self.calls += 1
        return [self.result], None


class FakeFetcher:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    def fetch(self, url):
        self.calls += 1
        return self.document


def test_classification_candidate_is_grouped_and_requires_human_acceptance(admin_user):
    work, edition = _edition()
    discipline = Discipline.objects.create(
        name="历史社会学",
        slug="historical-sociology-v290",
        code="historical-sociology-v290",
        editorial_status="published",
    )
    document = FetchedDocument(
        source_url="https://journal.example/article",
        canonical_url="https://journal.example/article",
        title="候选研究作品书评",
        domain="journal.example",
        text="候选研究作品是历史社会学的重要研究，集中讨论国家形成。",
        retrieved_at=timezone.now(),
        content_checksum="a" * 64,
        http_status=200,
        content_type="text/html",
        source_class=EnrichmentSourceClass.ACADEMIC_JOURNAL,
    )
    service = FieldEnrichmentService(
        search_adapter=FakeSearchAdapter(
            SearchResult(
                url=document.source_url,
                title=document.title,
                snippet="搜索摘要不能成为证据",
                source_class=EnrichmentSourceClass.ACADEMIC_JOURNAL,
            )
        ),
        fetcher=FakeFetcher(document),
    )
    result = service.enrich(
        FieldEnrichmentRequest(
            target_type="work",
            target_id=work.id,
            field_names=("discipline",),
            requested_mode="web",
            visibility="admin",
        ),
        actor=admin_user,
    )

    assert result.candidates
    candidate = next(
        row
        for row in result.candidates
        if row.proposed_value["discipline_id"] == str(discipline.id)
    )
    assert candidate.proposed_value["discipline_id"] == str(discipline.id)
    assert WorkDisciplineRelation.objects.filter(work=work).count() == 0
    payload = WorkflowSuggestionAggregator(edition).aggregate(step="classification")
    suggestion = next(row for row in payload["suggestions"] if row["id"] == str(candidate.id))
    assert suggestion["field"] == "related_disciplines"
    assert suggestion["source_tier"] == "web_evidence"
    assert suggestion["human_confirmation_required"] is True

    accept_enrichment_candidate(candidate, actor=admin_user, reason="人工核对学术来源")
    relation = WorkDisciplineRelation.objects.get(work=work, discipline=discipline)
    assert relation.review_status == "approved"


def test_query_lexicon_match_and_pdf_chunk_are_separate_groups():
    work, edition = _edition()
    discipline = Discipline.objects.create(
        name="历史社会学",
        foreign_name="Historical Sociology",
        slug="historical-sociology-query-v290",
        code="historical-sociology-query-v290",
        editorial_status="published",
    )
    _asset(work, edition)
    rebuild_query_lexicon()

    payload = WorkflowSuggestionAggregator(edition).aggregate(
        step="classification",
        field="related_disciplines",
        query="Historical Sociology",
    )
    tiers = {row["source_tier"] for row in payload["suggestions"]}
    assert "query_lexicon" in tiers
    assert "pdf_evidence" in tiers
    lexicon = next(row for row in payload["suggestions"] if row["source_tier"] == "query_lexicon")
    assert lexicon["entity_id"] == str(discipline.id)
    assert WorkDisciplineRelation.objects.filter(work=work).count() == 0


def test_query_lexicon_pdf_candidate_uses_existing_review_endpoint():
    work, edition = _edition()
    asset, page, chunk = _asset(work, edition, "habitus（惯习）是作品中的核心概念。")
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="惯习理论",
        canonical_name_en="habitus",
        slug="habitus-workflow-v290",
        status="draft",
    )
    candidate = QueryLexiconCandidate.objects.create(
        candidate_type=QueryLexiconCandidate.CandidateType.KNOWLEDGE_NODE_ALIAS,
        target_entity_type=QueryLexiconCandidate.TargetEntityType.KNOWLEDGE_NODE,
        target_entity_id=node.id,
        anchor_term="habitus",
        proposed_term="惯习",
        proposed_term_type="translation",
        confidence=0.91,
        linking_status=QueryLexiconCandidate.LinkingStatus.LINKED,
        displayable=True,
        extraction_version="test-v290",
        fingerprint=uuid4().hex * 2,
    )
    QueryLexiconCandidateEvidence.objects.create(
        candidate=candidate,
        work=work,
        edition=edition,
        asset=asset,
        page=page,
        semantic_chunk=chunk,
        document_id=chunk.document_id,
        page_number=1,
        printed_page_label="1",
        evidence_text="habitus（惯习）是作品中的核心概念。",
        start_offset=0,
        end_offset=12,
        left_term="habitus",
        right_term="惯习",
        extraction_method="explicit_parentheses",
        confidence=0.91,
        source_text_checksum=sha256(chunk.original_text.encode()).hexdigest(),
        extraction_version="test-v290",
        fingerprint=uuid4().hex * 2,
    )

    payload = WorkflowSuggestionAggregator(edition).aggregate(step="knowledge")
    row = next(item for item in payload["suggestions"] if item["id"] == str(candidate.id))
    assert row["source_tier"] == "pdf_evidence"
    assert row["decision_url"].endswith(f"query_lexicon/{candidate.id}/decision/")
    assert row["available_actions"] == ["inspect", "accept", "reject"]


def test_entity_reconciliation_stays_in_contributor_context(admin_user):
    _work, edition = _edition()
    item = _item(admin_user, edition)
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="马克斯·韦伯",
        candidate_entity_type="person",
        candidate_entity_id=str(uuid4()),
        label="Max Weber",
        match_score=0.88,
        match_reasons=["姓名别名匹配"],
    )
    payload = WorkflowSuggestionAggregator(edition, item=item).aggregate(step="contributors")
    row = next(item for item in payload["suggestions"] if item["id"] == str(candidate.id))
    assert row["source_tier"] == "in_library"
    assert "link_existing" in row["available_actions"]
    assert row["human_confirmation_required"] is True


def test_syllabus_page_is_evidence_but_search_snippet_is_not(monkeypatch):
    work, edition = _edition()
    result = SearchResult(
        url="https://university.example/course/syllabus",
        title="社会理论课程大纲",
        snippet="摘要声称这是必读书",
        source_class=EnrichmentSourceClass.SYLLABUS,
    )
    document = FetchedDocument(
        source_url=result.url,
        canonical_url=result.url,
        title=result.title,
        domain="university.example",
        text="社会理论课程将候选研究作品列为第二周必读，并配合历史社会学专题。",
        retrieved_at=timezone.now(),
        content_checksum="b" * 64,
        http_status=200,
        content_type="text/html",
        source_class=EnrichmentSourceClass.SYLLABUS,
    )
    search = FakeSearchAdapter(result)
    fetcher = FakeFetcher(document)
    monkeypatch.setattr("catalog.services.workflow_suggestions.configured_web_search_adapter", lambda: search)
    monkeypatch.setattr("catalog.services.workflow_suggestions.SafeWebFetcher", lambda: fetcher)

    payload = WorkflowSuggestionAggregator(edition).run_step(step="curation", mode="web")
    row = next(item for item in payload["suggestions"] if item["source_tier"] == "web_evidence")
    assert row["source_class"] == EnrichmentSourceClass.SYLLABUS
    assert row["evidence_status"] == "evidence"
    assert "第二周必读" in row["evidence_records"][0]["supporting_text"]
    assert "摘要声称" not in row["evidence_records"][0]["supporting_text"]


def test_general_web_result_remains_lead_and_never_becomes_evidence(monkeypatch):
    _work, edition = _edition()
    result = SearchResult(
        url="https://blog.example/post",
        title="普通网页",
        snippet="普通搜索摘要",
        source_class=EnrichmentSourceClass.GENERAL_WEB,
    )
    search = FakeSearchAdapter(result)
    fetcher = FakeFetcher(
        FetchedDocument(
            source_url=result.url,
            canonical_url=result.url,
            title=result.title,
            domain="blog.example",
            text="候选研究作品的普通网页介绍。",
            retrieved_at=timezone.now(),
            content_checksum="c" * 64,
            http_status=200,
            content_type="text/html",
            source_class=EnrichmentSourceClass.GENERAL_WEB,
        )
    )
    monkeypatch.setattr("catalog.services.workflow_suggestions.configured_web_search_adapter", lambda: search)
    monkeypatch.setattr("catalog.services.workflow_suggestions.SafeWebFetcher", lambda: fetcher)

    payload = WorkflowSuggestionAggregator(edition).run_step(step="curation", mode="web")
    rows = [item for item in payload["suggestions"] if item["kind"] == "research_lead"]
    assert rows and all(row["source_tier"] == "research_lead" for row in rows)
    assert all(row["evidence_records"] == [] and row["evidence_status"] == "lead_only" for row in rows)
    assert fetcher.calls == 0


def test_journal_structured_metadata_candidate_is_first_class(admin_user):
    work, edition = _edition(document_type=DocumentType.JOURNAL_ARTICLE)
    edition.journal_title = ""
    edition.save(update_fields=["journal_title", "updated_at"])
    observation = FieldObservation(
        field_name="journal_title",
        value="American Journal of Sociology",
        provider="crossref",
        source_class=EnrichmentSourceClass.ACADEMIC_JOURNAL,
        source_url="https://api.crossref.org/works/10.1/test",
        canonical_url="https://api.crossref.org/works/10.1/test",
        source_title="Crossref record",
        supporting_text="journal_title: American Journal of Sociology",
        content_checksum="d" * 64,
        retrieved_at=timezone.now(),
        identity_claims={"title": work.title, "publisher": edition.publisher},
        extraction_method="structured_provider",
    )
    result = FieldEnrichmentService(
        structured_adapters={"bibliographic": FakeStructuredAdapter([observation])}
    ).enrich(
        FieldEnrichmentRequest(
            target_type="edition",
            target_id=edition.id,
            field_names=("journal_title",),
            requested_mode="structured",
            visibility="admin",
        ),
        actor=admin_user,
    )
    assert len(result.candidates) == 1
    payload = WorkflowSuggestionAggregator(edition).aggregate(step="bibliography", field="journal_title")
    row = next(item for item in payload["suggestions"] if item["id"] == str(result.candidates[0].id))
    assert row["source_tier"] == "structured_source"
    assert row["proposed_value"] == "American Journal of Sociology"


def test_step_research_groups_fields_into_one_enrichment_run(monkeypatch, admin_user):
    _work, edition = _edition(document_type=DocumentType.JOURNAL_ARTICLE)
    calls = []

    def fake_enrich(self, request, actor):
        calls.append(request)
        return SimpleNamespace(candidates=[], errors=[], stats={})

    monkeypatch.setattr(FieldEnrichmentService, "enrich", fake_enrich)
    payload = WorkflowSuggestionAggregator(edition).run_step(
        step="bibliography",
        fields=["publication_year", "publisher", "journal_title", "volume", "issue", "page_range", "doi"],
        mode="structured",
        actor=admin_user,
    )
    assert payload["run"]["enrichment_runs"] == 1
    assert len(calls) == 1
    assert set(calls[0].field_names) == {"publication_year", "publisher", "journal_title", "volume", "issue", "page_range", "doi"}


def test_rejected_web_candidate_does_not_write_query_lexicon(admin_user):
    work, edition = _edition()
    policy = FIELD_POLICIES.get("work", "title")
    candidate = EnrichmentCandidate.objects.create(
        target_type=EnrichmentCandidate.TargetType.WORK,
        target_id=work.id,
        field_name="title",
        candidate_kind=policy.candidate_kind,
        proposed_value="网页误识别题名",
        normalized_value="网页误识别题名",
        current_value=work.title,
        source_class=EnrichmentSourceClass.GENERAL_WEB,
        confidence=0.3,
        identity_status=EnrichmentCandidate.IdentityStatus.CONFIRMED,
        requested_mode=EnrichmentCandidate.RequestedMode.WEB,
        conflict_group=uuid4().hex,
        policy_version=policy.policy_version,
        extraction_version=policy.extraction_version,
        fingerprint=uuid4().hex * 2,
    )
    before = QueryLexiconChangeEvent.objects.count()
    reject_enrichment_candidate(candidate, actor=admin_user, reason="网页来源不可靠")
    assert QueryLexiconChangeEvent.objects.count() == before
    work.refresh_from_db()
    assert work.title == "候选研究作品"


def test_policy_registry_preserves_theory_threshold_and_source_profiles():
    relation = FIELD_POLICIES.get("knowledge_node", "relation")
    assert relation.evidence_min_count == 2
    assert relation.independent_source_min == 2
    assert WORKFLOW_SUGGESTION_POLICIES.get("knowledge", "relations").human_confirmation is True
    assert SOURCE_PROFILES.for_source_class(EnrichmentSourceClass.SYLLABUS).key == "syllabus"
    assert SOURCE_PROFILES.for_source_class(EnrichmentSourceClass.UNIVERSITY).key == "academic"
    assert SOURCE_PROFILES.for_source_class(EnrichmentSourceClass.GENERAL_WEB).is_evidence is False


def test_workflow_suggestion_api_permissions(api_client, admin_user, monkeypatch):
    _work, edition = _edition()
    item = _item(admin_user, edition)
    monkeypatch.setattr(
        WorkflowSuggestionAggregator,
        "run_step",
        lambda self, **kwargs: {"suggestions": [], "groups": [], "stats": {}, "errors": []},
    )

    reader = User.objects.create_user(
        username="suggestion-reader@example.test",
        email="suggestion-reader@example.test",
        password="Reader-Suggestion-2026",
        role=User.Role.READER,
    )
    api_client.force_authenticate(reader)
    url = f"/api/catalog/admin/intake/{item.id}/suggestions/"
    assert api_client.get(url, {"step": "classification"}).status_code == 403
    assert api_client.post(url, {"step": "classification"}, format="json").status_code == 403

    api_client.force_authenticate(admin_user)
    assert api_client.get(url, {"step": "classification"}).status_code == 200
    assert api_client.post(url, {"step": "classification"}, format="json").status_code == 200
