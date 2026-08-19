from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from django.test import override_settings
from django.utils import timezone

from catalog.models import (
    Discipline,
    DocumentType,
    Edition,
    EnrichmentCandidate,
    EnrichmentEvidence,
    EnrichmentSourceClass,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeRelation,
    Person,
    PersonNameVariant,
    QueryLexiconChangeEvent,
    QueryLexiconEntry,
    ScholarProfile,
    Work,
)
from catalog.services.field_enrichment.extraction import extract_web_observations
from catalog.services.field_enrichment.mutations import (
    accept_enrichment_candidate,
    reject_enrichment_candidate,
)
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.field_enrichment.service import FieldEnrichmentService
from catalog.services.field_enrichment.types import (
    EnrichmentError,
    FetchedDocument,
    FieldEnrichmentRequest,
    FieldObservation,
    SearchResult,
)
from catalog.services.field_enrichment.web import SafeWebFetcher, WebFetchError, validate_public_url
from ingestion.models import FieldLock, SourceRecord


pytestmark = pytest.mark.django_db


def test_public_compose_pins_internal_searxng_with_json_api():
    root = Path(__file__).resolve().parents[2]
    compose = (root / "compose.public.yaml").read_text(encoding="utf-8")
    start = compose.index("  searxng:")
    end = compose.index("\n  api:", start)
    service = compose[start:end]
    settings_text = (root / "deploy" / "searxng" / "settings.yml").read_text(encoding="utf-8")

    assert "docker.io/searxng/searxng:2026.8.4-c63835bd2" in service
    assert 'expose:\n      - "8080"' in service
    assert "ports:" not in service
    assert "SEARXNG_SECRET" in service
    assert "formats:\n    - html\n    - json" in settings_text
    assert "limiter: false" in settings_text


def _person(name="Pierre Bourdieu", *, birth_year=1930):
    person = Person.objects.create(
        preferred_name=name,
        original_name=name,
        birth_year=birth_year,
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    ScholarProfile.objects.create(person=person, slug=f"person-{person.id}")
    return person


def _edition(*, title="Distinction", year=None, publisher="Known Press", isbn=""):
    work = Work.objects.create(document_type=DocumentType.BOOK, title=title)
    return Edition.objects.create(
        work=work,
        publication_year=year,
        publisher=publisher,
        isbn=isbn,
    )


def _observation(
    *,
    field_name,
    value,
    url="https://authority.example/record/1",
    source_class=EnrichmentSourceClass.IDENTIFIER_REGISTRY,
    identity_claims=None,
    method="structured_provider",
    supporting_text="Authoritative record supporting this exact value.",
):
    return FieldObservation(
        field_name=field_name,
        value=value,
        provider="test-provider",
        source_class=source_class,
        source_url=url,
        canonical_url=url,
        source_title="Authoritative source",
        supporting_text=supporting_text,
        content_checksum="a" * 64,
        retrieved_at=timezone.now(),
        locator={"field": field_name},
        identity_claims=identity_claims or {},
        confidence_factors={"fixture": True},
        content_type="application/json",
        extraction_method=method,
    )


class FakeStructuredAdapter:
    def __init__(self, observations, errors=None):
        self.observations = list(observations)
        self.errors = list(errors or [])
        self.calls = 0

    def collect(self, **kwargs):
        self.calls += 1
        return list(self.observations), list(self.errors)


class FakeSearchAdapter:
    name = "fake-search"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def search(self, query, *, limit):
        self.calls += 1
        return self.results[:limit], None


class FakeFetcher:
    def __init__(self, documents):
        self.documents = {row.source_url: row for row in documents}
        self.calls = 0

    def fetch(self, url):
        self.calls += 1
        return self.documents[url]


def _request(target_type, target_id, fields, *, mode="structured", form_context=None):
    return FieldEnrichmentRequest(
        target_type=target_type,
        target_id=target_id,
        field_names=tuple(fields),
        form_context=form_context or {},
        requested_mode=mode,
        visibility="admin",
    )


def test_field_policy_registry_is_field_specific():
    affiliation = FIELD_POLICIES.get("person", "affiliation")
    relation = FIELD_POLICIES.get("knowledge_node", "relation")
    path = FIELD_POLICIES.get("reading_path", "item")

    assert affiliation.priority_for(EnrichmentSourceClass.UNIVERSITY) > affiliation.priority_for(EnrichmentSourceClass.GENERAL_WEB)
    assert EnrichmentSourceClass.GENERAL_WEB not in relation.allowed_source_classes
    assert relation.evidence_min_count == relation.independent_source_min == 2
    assert path.candidate_kind == EnrichmentCandidate.CandidateKind.INTERPRETIVE
    assert EnrichmentSourceClass.SYLLABUS in path.required_source_classes


def test_person_identity_gate_rejects_same_name_without_corroboration(admin_user):
    person = _person("John Smith", birth_year=None)
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="external_identifier",
                value={"scheme": "orcid", "value": "0000-0001-0002-0003"},
                identity_claims={"name": "John Smith", "external_ids": {"orcid": "0000-0001-0002-0003"}},
            )
        ]
    )
    result = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("person", person.id, ["external_identifier"]),
        actor=admin_user,
    )

    assert result.candidates == []
    assert any(row.code == "identity_ambiguous" for row in result.errors)
    assert EnrichmentCandidate.objects.count() == 0


@override_settings(AI_AUTHORITY_RERANK_ENABLED=False)
def test_authority_structured_adapter_normalizes_person_fields_without_ai(monkeypatch, admin_user):
    person = _person("费孝通", birth_year=1910)
    rows = [
        {
            "id": "wikidata:Q123",
            "label": "费孝通",
            "original_name": "Fei Xiaotong",
            "aliases": [{"name": "Xiaotong Fei", "language": "en"}],
            "birth_year": 1910,
            "death_year": 2005,
            "external_ids": {"wikidata": "Q123", "viaf": "123456"},
            "source": "Wikidata",
            "provider": "wikidata",
            "source_url": "https://www.wikidata.org/wiki/Q123",
            "source_record_id": "",
        }
    ]
    monkeypatch.setattr(
        "catalog.services.field_enrichment.structured._authority_rows",
        lambda entity_type, query: (rows, []),
    )
    result = FieldEnrichmentService().enrich(
        _request("person", person.id, ["external_identifier", "name_variant"]),
        actor=admin_user,
    )

    assert {row.field_name for row in result.candidates} == {"external_identifier", "name_variant"}
    assert all(row.evidence_records.get().extraction_method == "structured_provider" for row in result.candidates)
    assert all(row.identity_status == EnrichmentCandidate.IdentityStatus.CONFIRMED for row in result.candidates)


@override_settings(AI_AUTHORITY_RERANK_ENABLED=False)
def test_authority_adapter_uses_verified_original_name_after_empty_chinese_lookup(monkeypatch, admin_user):
    person = _person("埃米尔·杜尔凯姆", birth_year=1858)
    person.original_name = "Émile Durkheim"
    person.save(update_fields=["original_name", "updated_at"])
    queries = []

    def authority_rows(entity_type, query):
        queries.append(query)
        if query == "埃米尔·杜尔凯姆":
            return [], []
        return [{
            "id": "viaf:100189183",
            "label": "Émile Durkheim",
            "original_name": "Émile Durkheim",
            "aliases": [],
            "birth_year": 1858,
            "death_year": 1917,
            "external_ids": {"viaf": "100189183"},
            "source": "VIAF",
            "provider": "viaf",
            "source_url": "https://viaf.org/viaf/100189183/",
            "source_record_id": "",
        }], []

    monkeypatch.setattr(
        "catalog.services.field_enrichment.structured._authority_rows",
        authority_rows,
    )
    result = FieldEnrichmentService().enrich(
        _request("person", person.id, ["external_identifier"]),
        actor=admin_user,
    )

    assert queries == ["埃米尔·杜尔凯姆", "Émile Durkheim"]
    assert len(result.candidates) == 1
    assert result.candidates[0].proposed_value == {"scheme": "viaf", "value": "100189183"}
    assert result.candidates[0].status == EnrichmentCandidate.Status.PENDING


def test_search_snippet_can_never_become_final_evidence(admin_user):
    person = _person()
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="external_identifier",
                value={"scheme": "orcid", "value": "0000-0001-0002-0003"},
                identity_claims={"name": person.preferred_name, "birth_year": 1930},
                method="search_snippet",
            )
        ]
    )
    result = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("person", person.id, ["external_identifier"]),
        actor=admin_user,
    )

    assert result.candidates == []
    assert result.stats["snippet_rejected"] == 1
    assert EnrichmentEvidence.objects.count() == 0


class FakeResponse:
    def __init__(self, status_code, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            request = pytest.importorskip("httpx").Request("GET", "https://example.com")
            response = pytest.importorskip("httpx").Response(self.status_code, request=request)
            raise pytest.importorskip("httpx").HTTPStatusError("failed", request=request, response=response)

    def iter_bytes(self):
        yield self._body


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        return next(self.responses)


def test_safe_fetch_stores_actual_page_and_extractor_uses_page_text(monkeypatch):
    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        lambda hostname, port: {"93.184.216.34"},
    )
    html = b"""<html><head><title>Official profile</title><link rel='canonical' href='https://example.com/profile'></head><body><main><h1>Pierre Bourdieu</h1><p>Pierre Bourdieu born 1930. ORCID 0000-0001-0002-0003.</p></main><script>ignore()</script></body></html>"""
    client = FakeClient([FakeResponse(200, html, {"content-type": "text/html; charset=utf-8"})])
    fetcher = SafeWebFetcher(client_factory=lambda **kwargs: client)

    document = fetcher.fetch("https://example.com/profile")
    policy = FIELD_POLICIES.get("person", "external_identifier")
    observations = extract_web_observations(
        document=document,
        policy=policy,
        context={"canonical_terms": ["Pierre Bourdieu"], "birth_year": 1930},
        form_context={},
    )

    assert document.title == "Official profile"
    assert "ignore" not in document.text
    assert observations[0].value["scheme"] == "orcid"
    assert "0000-0001-0002-0003" in observations[0].supporting_text
    record = SourceRecord.objects.get(provider="field_enrichment:web_fetch")
    assert record.raw_response["stored_text_is_bounded_extraction"] is True


def test_ssrf_blocks_private_initial_and_redirect_targets(monkeypatch):
    with pytest.raises(WebFetchError, match="私网"):
        validate_public_url("http://127.0.0.1/latest/meta-data")

    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        lambda hostname, port: {"93.184.216.34"},
    )
    client = FakeClient([FakeResponse(302, headers={"location": "http://169.254.169.254/latest/meta-data"})])
    fetcher = SafeWebFetcher(client_factory=lambda **kwargs: client)
    with pytest.raises(WebFetchError, match="私网"):
        fetcher.fetch("https://example.com/start")


def test_conflicting_structured_sources_remain_separate_candidates(admin_user):
    edition = _edition(year=None, publisher="Known Press")
    claims = {"title": edition.work.title, "publisher": edition.publisher}
    adapter = FakeStructuredAdapter(
        [
            _observation(field_name="publication_year", value=2000, url="https://registry.example/a", identity_claims=claims),
            _observation(field_name="publication_year", value=2001, url="https://registry.example/b", identity_claims=claims),
        ]
    )
    result = FieldEnrichmentService(structured_adapters={"bibliographic": adapter}).enrich(
        _request("edition", edition.id, ["publication_year"]),
        actor=admin_user,
    )

    assert len(result.candidates) == 2
    assert all(row.conflicts for row in result.candidates)
    assert {row.proposed_value for row in result.candidates} == {2000, 2001}


def test_candidate_and_evidence_deduplicate_across_repeated_page_request(admin_user):
    edition = _edition(year=None, publisher="Known Press")
    observation = _observation(
        field_name="publication_year",
        value=2000,
        identity_claims={"title": edition.work.title, "publisher": edition.publisher},
    )
    adapter = FakeStructuredAdapter([observation, observation])
    service = FieldEnrichmentService(structured_adapters={"bibliographic": adapter})

    first = service.enrich(_request("edition", edition.id, ["publication_year"]), actor=admin_user)
    second = service.enrich(_request("edition", edition.id, ["publication_year"]), actor=admin_user)

    assert first.candidates[0].id == second.candidates[0].id
    assert EnrichmentCandidate.objects.count() == 1
    assert EnrichmentEvidence.objects.count() == 1


def test_accept_person_name_variant_writes_authority_then_outbox(admin_user):
    person = _person()
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="name_variant",
                value={"name": "皮埃尔·布迪厄", "language": "zh", "variant_type": "transliteration"},
                identity_claims={"name": person.preferred_name, "birth_year": person.birth_year},
            )
        ]
    )
    candidate = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("person", person.id, ["name_variant"]), actor=admin_user
    ).candidates[0]
    before_entries = QueryLexiconEntry.objects.count()

    result = accept_enrichment_candidate(candidate, actor=admin_user, reason="人工核对来源")

    variant = PersonNameVariant.objects.get(person=person, name="皮埃尔·布迪厄")
    candidate.refresh_from_db()
    assert result.authority_model == "catalog.PersonNameVariant"
    assert variant.is_verified is True and variant.displayable is False
    assert candidate.status == EnrichmentCandidate.Status.ACCEPTED
    assert QueryLexiconChangeEvent.objects.filter(source_object_id=variant.id).exists()
    assert QueryLexiconEntry.objects.count() == before_entries


def test_accept_edition_candidate_respects_manual_field_lock(admin_user):
    edition = _edition(year=None, publisher="Known Press")
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="publication_year",
                value=2000,
                identity_claims={"title": edition.work.title, "publisher": edition.publisher},
            )
        ]
    )
    candidate = FieldEnrichmentService(structured_adapters={"bibliographic": adapter}).enrich(
        _request("edition", edition.id, ["publication_year"]), actor=admin_user
    ).candidates[0]
    FieldLock.objects.create(
        edition=edition,
        field_name="publication_year",
        locked_by=admin_user,
        locked_value=1999,
    )

    with pytest.raises(ValueError, match="人工锁定"):
        accept_enrichment_candidate(candidate, actor=admin_user)
    edition.refresh_from_db()
    candidate.refresh_from_db()
    assert edition.publication_year is None
    assert candidate.status == EnrichmentCandidate.Status.PENDING


def test_accept_edition_candidate_writes_edition_source_of_truth(admin_user):
    edition = _edition(year=None, publisher="Known Press")
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="publication_year",
                value=2000,
                identity_claims={"title": edition.work.title, "publisher": edition.publisher},
            )
        ]
    )
    candidate = FieldEnrichmentService(structured_adapters={"bibliographic": adapter}).enrich(
        _request("edition", edition.id, ["publication_year"]), actor=admin_user
    ).candidates[0]

    result = accept_enrichment_candidate(candidate, actor=admin_user, reason="书目来源已人工核对")

    edition.refresh_from_db()
    candidate.refresh_from_db()
    assert result.authority_model == "catalog.Edition"
    assert edition.publication_year == 2000
    assert candidate.status == EnrichmentCandidate.Status.ACCEPTED


def test_accept_knowledge_alias_writes_alias_and_query_lexicon_event(admin_user):
    node = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="Habitus",
        slug="habitus-task5-alias",
        status="draft",
    )
    adapter = FakeStructuredAdapter(
        [
            _observation(
                field_name="alias",
                value={"alias": "惯习", "language": "zh", "alias_type": "translation"},
                source_class=EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA,
                identity_claims={"name": "Habitus"},
            )
        ]
    )
    candidate = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("knowledge_node", node.id, ["alias"]), actor=admin_user
    ).candidates[0]
    before_entries = QueryLexiconEntry.objects.count()

    accept_enrichment_candidate(candidate, actor=admin_user, reason="术语来源已人工核对")

    alias = KnowledgeNodeAlias.objects.get(node=node, alias="惯习")
    assert QueryLexiconChangeEvent.objects.filter(source_object_id=alias.id).exists()
    assert QueryLexiconEntry.objects.count() == before_entries


def test_rejected_candidate_is_not_reopened_by_same_source(admin_user):
    edition = _edition(year=None, publisher="Known Press")
    observation = _observation(
        field_name="publication_year",
        value=2000,
        identity_claims={"title": edition.work.title, "publisher": edition.publisher},
    )
    adapter = FakeStructuredAdapter([observation])
    service = FieldEnrichmentService(structured_adapters={"bibliographic": adapter})
    candidate = service.enrich(
        _request("edition", edition.id, ["publication_year"]), actor=admin_user
    ).candidates[0]
    evidence_id = candidate.evidence_records.get().id
    reject_enrichment_candidate(candidate, actor=admin_user, reason="来源不足")

    repeated = service.enrich(
        _request("edition", edition.id, ["publication_year"]), actor=admin_user
    ).candidates[0]

    assert repeated.id == candidate.id
    assert repeated.status == EnrichmentCandidate.Status.REJECTED
    assert list(repeated.evidence_records.values_list("id", flat=True)) == [evidence_id]


def _document(url, text, *, source_class=EnrichmentSourceClass.ACADEMIC_JOURNAL):
    return FetchedDocument(
        source_url=url,
        canonical_url=url,
        title="Scholarly source",
        domain=url.split("/")[2],
        text=text,
        retrieved_at=timezone.now(),
        content_checksum=uuid4().hex * 2,
        http_status=200,
        content_type="text/html",
        source_class=source_class,
    )


def test_interpretive_relation_requires_review_and_two_real_sources(admin_user):
    source = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="Field theory",
        slug="field-theory-task5",
        status="draft",
    )
    target = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="Practice theory",
        slug="practice-theory-task5",
        status="draft",
    )
    documents = [
        _document("https://journal.example/article-a", "Field theory explicitly extends Practice theory by redefining social positions."),
        _document("https://university.example/paper-b", "Field theory extends Practice theory through a relational account of action.", source_class=EnrichmentSourceClass.UNIVERSITY),
    ]
    search = FakeSearchAdapter([SearchResult(url=row.source_url, title=row.title, provider="fake") for row in documents])
    fetcher = FakeFetcher(documents)
    service = FieldEnrichmentService(search_adapter=search, fetcher=fetcher)
    result = service.enrich(
        _request(
            "knowledge_node",
            source.id,
            ["relation"],
            mode="web",
            form_context={
                "target_node_id": str(target.id),
                "relation_type": "extends",
            },
        ),
        actor=admin_user,
    )

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.candidate_kind == EnrichmentCandidate.CandidateKind.INTERPRETIVE
    assert candidate.status == EnrichmentCandidate.Status.PENDING
    assert candidate.evidence_records.count() == 2
    assert KnowledgeRelation.objects.count() == 0

    accepted = accept_enrichment_candidate(candidate, actor=admin_user, reason="两份学术来源已人工核对")
    relation = KnowledgeRelation.objects.get(pk=accepted.authority_id)
    assert relation.status == "pending"
    assert relation.relation_type == "extends"


def test_theory_relation_cooccurrence_without_relation_phrase_is_not_evidence(admin_user):
    source = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="Recognition theory",
        slug="recognition-theory-task5",
        status="draft",
    )
    target = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.THEORY_TRADITION,
        canonical_name_zh="Practice theory",
        slug="practice-theory-cooccurrence-task5",
        status="draft",
    )
    document = _document(
        "https://journal.example/cooccurrence",
        "Recognition theory and Practice theory are both discussed in this literature review.",
    )
    result = FieldEnrichmentService(
        search_adapter=FakeSearchAdapter([SearchResult(url=document.source_url, title=document.title, provider="fake")]),
        fetcher=FakeFetcher([document]),
    ).enrich(
        _request(
            "knowledge_node",
            source.id,
            ["relation"],
            mode="web",
            form_context={
                "target_node_id": str(target.id),
                "relation_type": "extends",
            },
        ),
        actor=admin_user,
    )

    assert result.candidates == []
    assert EnrichmentEvidence.objects.count() == 0


def test_provider_partial_failure_keeps_other_candidates(admin_user):
    person = _person()
    observation = _observation(
        field_name="external_identifier",
        value={"scheme": "orcid", "value": "0000-0001-0002-0003"},
        identity_claims={"name": person.preferred_name, "birth_year": person.birth_year},
    )
    adapter = FakeStructuredAdapter(
        [observation],
        [EnrichmentError(code="timeout", provider="secondary", detail="timed out")],
    )
    result = FieldEnrichmentService(structured_adapters={"authority": adapter}).enrich(
        _request("person", person.id, ["external_identifier"]), actor=admin_user
    )

    assert len(result.candidates) == 1
    assert any(row.code == "timeout" for row in result.errors)


def test_page_level_web_request_fetches_each_source_once(admin_user):
    person = _person()
    document = _document(
        "https://university.example/profile",
        "Pierre Bourdieu born 1930. 皮埃尔·布迪厄（Pierre Bourdieu）。ORCID 0000-0001-0002-0003.",
        source_class=EnrichmentSourceClass.UNIVERSITY,
    )
    search = FakeSearchAdapter([SearchResult(url=document.source_url, title=document.title, provider="fake")])
    fetcher = FakeFetcher([document])
    result = FieldEnrichmentService(search_adapter=search, fetcher=fetcher).enrich(
        _request("person", person.id, ["external_identifier", "name_variant"], mode="web"),
        actor=admin_user,
    )

    assert fetcher.calls == 1
    assert {row.field_name for row in result.candidates} == {"external_identifier", "name_variant"}


def test_field_enrichment_api_is_admin_only_and_reports_errors(api_client, admin_user, reader_user):
    person = _person()
    payload = {
        "target_type": "person",
        "target_id": str(person.id),
        "fields": ["external_identifier"],
        "requested_mode": "web",
        "visibility": "admin",
    }
    api_client.force_authenticate(reader_user)
    forbidden = api_client.post("/api/catalog/admin/field-enrichment/", payload, format="json")
    assert forbidden.status_code == 403

    api_client.force_authenticate(admin_user)
    with override_settings(FIELD_ENRICHMENT_SEARXNG_URL=""):
        response = api_client.post("/api/catalog/admin/field-enrichment/", payload, format="json")
    assert response.status_code == 200
    assert response.data["results"] == []
    assert response.data["errors"][0]["code"] == "provider_unavailable"


def test_shared_candidate_review_envelope_is_staff_only(api_client, admin_user, reader_user):
    api_client.force_authenticate(reader_user)
    forbidden = api_client.get("/api/catalog/admin/candidate-review/")
    assert forbidden.status_code == 403

    api_client.force_authenticate(admin_user)
    response = api_client.get(
        "/api/catalog/admin/candidate-review/",
        {"status": "pending", "kind": "all"},
    )
    assert response.status_code == 200
    assert response.data["counts"]["total"] == 0
    assert response.data["results"] == []
