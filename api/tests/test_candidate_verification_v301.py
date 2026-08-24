from __future__ import annotations

import socket
from uuid import uuid4

import httpx
import pytest
from django.urls import reverse
from django.utils import timezone

from catalog.models import DocumentType, Edition, EnrichmentSourceClass, KnowledgeNode, Work
from catalog.services.candidate_verification import (
    CandidateVerificationError,
    verify_research_candidate,
)
from catalog.services.field_enrichment.types import FetchedDocument
from catalog.services.field_enrichment.web import SafeWebFetcher, WebFetchError, validate_public_url
from catalog.services.research.entity_discovery import EntityDiscoveryRequest, UniversalEntityDiscovery
from catalog.services.research.orchestrator import ResearchOrchestrator
from catalog.services.workflow_suggestions import WorkflowSuggestionAggregator
from ingestion.models import EntityResolutionCandidate, MetadataCandidate, SourceRecord, UploadBatch, UploadItem
from ingestion.services.entity_resolution_decisions import available_resolution_actions


pytestmark = pytest.mark.django_db


def _workspace(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="社会理论的结构")
    edition = Edition.objects.create(work=work, publication_year=2024)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="theory.pdf",
        edition=edition,
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )
    return work, edition, item


def _web_lead(item, *, label="Pierre Bourdieu profile"):
    return EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name=label,
        candidate_entity_type="person_draft",
        label=label,
        match_score=0.99,
        match_reasons=["搜索摘要名称匹配"],
        supporting_properties={
            "research_field": "contributors.contributors",
            "candidate_group": "external_web",
            "provider": "searxng",
            "source_url": "https://example.org/bourdieu",
            "evidence_status": "lead_only",
            "research_allowed_resolution_actions": [
                "create_draft",
                "keep_unresolved",
                "reject",
            ],
        },
        preview_data={"source_url": "https://example.org/bourdieu", "evidence": []},
    )


class _Fetcher:
    def __init__(self, document):
        self.document = document
        self.calls = 0

    def fetch(self, url):
        self.calls += 1
        return self.document


def _document(source_record, text="Pierre Bourdieu profile presents verified biographical information for library review."):
    return FetchedDocument(
        source_url="https://example.org/bourdieu",
        canonical_url="https://example.org/bourdieu",
        title="Pierre Bourdieu profile",
        domain="example.org",
        text=text,
        retrieved_at=timezone.now(),
        content_checksum="a" * 64,
        http_status=200,
        content_type="text/html",
        source_record_id=source_record.id,
        source_class=EnrichmentSourceClass.SCHOLAR_HOMEPAGE,
    )


def test_workflow_candidates_are_sorted_by_provenance_tier_before_confidence(admin_user):
    _work, edition, item = _workspace(admin_user)
    EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="Pierre Bourdieu",
        candidate_entity_type="person",
        candidate_entity_id=str(uuid4()),
        label="馆内 Pierre Bourdieu",
        match_score=0.12,
    )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="authors",
        value=["Crossref Author"],
        source="crossref",
        confidence=0.99,
    )
    lead = _web_lead(item)

    rows = WorkflowSuggestionAggregator(edition, item=item).aggregate(
        step="contributors"
    )["suggestions"]
    candidate_ids = {
        str(value)
        for value in [
            lead.id,
            *EntityResolutionCandidate.objects.exclude(pk=lead.pk).values_list("id", flat=True),
            *MetadataCandidate.objects.values_list("id", flat=True),
        ]
    }
    matching = [row for row in rows if row["id"] in candidate_ids]
    tiers = [row["source_tier"] for row in matching]

    assert tiers == ["in_library", "structured_source", "research_lead"]
    assert matching[-1]["available_actions"] == ["inspect", "verify", "reject"]
    assert matching[-1]["verify_url"].endswith(f"/{lead.id}/verify/")


def test_verify_web_lead_persists_evidence_and_unlocks_human_actions(admin_user, api_client, monkeypatch):
    _work, _edition, item = _workspace(admin_user)
    lead = _web_lead(item)
    source_record = SourceRecord.objects.create(
        provider="field_enrichment:web_fetch",
        operation="fetch_page",
        status=SourceRecord.Status.SUCCEEDED,
    )
    fetcher = _Fetcher(_document(source_record))
    monkeypatch.setattr(
        "catalog.services.candidate_verification.SafeWebFetcher",
        lambda: fetcher,
    )
    assert available_resolution_actions(lead) == ["reject"]

    api_client.force_authenticate(admin_user)
    response = api_client.post(
        reverse("admin-research-candidate-verify", kwargs={"candidate_id": lead.id}),
        {},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["status"] == "verified"
    assert response.data["code"] == "candidate_verified"
    assert response.data["candidate"]["source_tier"] == "web_evidence"
    assert response.data["candidate"]["evidence_count"] == 1
    lead.refresh_from_db()
    assert lead.source_record_id == source_record.id
    assert lead.supporting_properties["evidence_status"] == "verified_text"
    assert lead.preview_data["evidence"][0]["provenance"]["content_checksum"] == "a" * 64
    assert "create_draft" in available_resolution_actions(lead)
    assert fetcher.calls == 1


def test_verify_web_lead_reports_no_reliable_candidate_without_mutating_lead(admin_user):
    _work, _edition, item = _workspace(admin_user)
    lead = _web_lead(item)
    source_record = SourceRecord.objects.create(
        provider="field_enrichment:web_fetch",
        operation="fetch_page",
        status=SourceRecord.Status.SUCCEEDED,
    )

    with pytest.raises(CandidateVerificationError) as raised:
        verify_research_candidate(
            lead,
            fetcher=_Fetcher(_document(source_record, text="An unrelated page with enough readable body text for parsing.")),
        )

    assert raised.value.code == "no_reliable_candidate"
    lead.refresh_from_db()
    assert lead.supporting_properties["evidence_status"] == "lead_only"
    assert available_resolution_actions(lead) == ["reject"]


def test_later_discovery_does_not_erase_verified_web_evidence(admin_user):
    _work, _edition, item = _workspace(admin_user)
    group = {
        "entity_type": "person",
        "field": "contributors.contributors",
        "results": [
            {
                "id": "web:person:0",
                "entity_type": "person",
                "label": "Pierre Bourdieu profile",
                "candidate_group": "external_web",
                "provider": "searxng",
                "source_url": "https://example.org/bourdieu",
                "evidence_status": "lead_only",
                "confidence": 0.62,
                "match_reasons": ["搜索摘要名称匹配"],
                "available_actions": ["inspect", "verify", "reject"],
            }
        ],
    }
    ResearchOrchestrator._persist_intake_entity_candidates(item=item, groups=[group])
    lead = EntityResolutionCandidate.objects.get(pk=group["results"][0]["review_candidate_id"])
    source_record = SourceRecord.objects.create(
        provider="field_enrichment:web_fetch",
        operation="fetch_page",
        status=SourceRecord.Status.SUCCEEDED,
    )
    verified = verify_research_candidate(
        lead,
        fetcher=_Fetcher(_document(source_record)),
    ).candidate
    verified_evidence = verified.preview_data["evidence"]
    verified_reason = list(verified.match_reasons)

    ResearchOrchestrator._persist_intake_entity_candidates(item=item, groups=[group])

    verified.refresh_from_db()
    assert verified.supporting_properties["evidence_status"] == "verified_text"
    assert verified.supporting_properties["evidence_provider"] == "safe_web_fetch"
    assert verified.preview_data["evidence"] == verified_evidence
    assert set(verified_reason).issubset(set(verified.match_reasons))
    assert "create_draft" in available_resolution_actions(verified)


def test_verify_ephemeral_lead_creates_field_candidate_with_evidence(admin_user, api_client, monkeypatch):
    work, edition, _item = _workspace(admin_user)
    edition.publisher = ""
    edition.save(update_fields=["publisher", "updated_at"])
    source_record = SourceRecord.objects.create(
        provider="field_enrichment:web_fetch",
        operation="fetch_page",
        status=SourceRecord.Status.SUCCEEDED,
    )
    document = FetchedDocument(
        source_url="https://example.org/book",
        canonical_url="https://example.org/book",
        title=work.title,
        domain="example.org",
        text=f"{work.title} bibliographic record published 2024. Publisher: Evidence Press；this record identifies the exact work title.",
        retrieved_at=timezone.now(),
        content_checksum="b" * 64,
        http_status=200,
        content_type="text/html",
        source_record_id=source_record.id,
        source_class=EnrichmentSourceClass.GENERAL_WEB,
    )
    monkeypatch.setattr(
        "catalog.services.field_enrichment.service.SafeWebFetcher",
        lambda: _Fetcher(document),
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        reverse("admin-research-lead-verify"),
        {
            "source_url": document.source_url,
            "target_type": "edition",
            "target_id": str(edition.id),
            "field_name": "publisher",
            "form_context": {"submitted_form": {"title": work.title}},
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["status"] == "verified"
    assert response.data["candidate"]["proposed_value"] == "Evidence Press"
    assert response.data["candidate"]["evidence_count"] == 1
    assert response.data["candidate"]["evidence_records"][0]["source_record"] == source_record.id


def test_concept_and_debate_discovery_use_canonical_knowledge_nodes(monkeypatch):
    concept = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.CONCEPT,
        canonical_name_zh="惯习",
        canonical_name_en="Habitus",
        slug="habitus-v301-candidate",
        status="published",
    )
    debate = KnowledgeNode.objects.create(
        node_type=KnowledgeNode.NodeType.DEBATE,
        canonical_name_zh="结构与能动性之争",
        slug="structure-agency-v301-candidate",
        status="draft",
    )
    discovery = UniversalEntityDiscovery()
    concept_payload = discovery.discover(
        EntityDiscoveryRequest("concept", "knowledge.concepts", "惯习", None, include_external=False)
    )
    debate_payload = discovery.discover(
        EntityDiscoveryRequest("debate", "knowledge.debates", "能动性", None, include_external=False)
    )

    assert concept_payload["results"][0]["entity_id"] == str(concept.id)
    assert concept_payload["results"][0]["candidate_group"] == "local"
    assert debate_payload["results"][0]["entity_id"] == str(debate.id)
    assert debate_payload["results"][0]["candidate_group"] == "local_draft"


class _Response:
    def __init__(self, status_code=200, body=b"", headers=None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.org/page")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("failed", request=request, response=response)

    def iter_bytes(self):
        yield self._body


class _Client:
    def __init__(self, responses=None, error=None):
        self.responses = iter(responses or [])
        self.error = error
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def stream(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self.error:
            raise self.error
        return next(self.responses)


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (_Response(302), "redirect"),
        (_Response(403), "robots"),
        (_Response(200, b"image", {"content-type": "image/png"}), "content_type"),
        (_Response(200, b"tiny", {"content-type": "text/html"}), "html"),
        (_Response(200, b"<html><body>readable body text that is longer than forty characters.</body></html>", {"content-type": "text/html; charset=not-a-real-encoding"}), "encoding"),
    ],
)
def test_safe_web_fetcher_reports_actionable_response_categories(monkeypatch, response, expected):
    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        lambda hostname, port: {"93.184.216.34"},
    )
    fetcher = SafeWebFetcher(client_factory=lambda **kwargs: _Client([response]))
    with pytest.raises(WebFetchError) as raised:
        fetcher.fetch(f"https://example.org/{expected}-{uuid4()}")
    assert raised.value.code == expected


def test_safe_web_fetcher_reports_dns_tls_timeout_and_size(monkeypatch, settings):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: (_ for _ in ()).throw(socket.gaierror()))
    with pytest.raises(WebFetchError) as raised:
        validate_public_url("https://unresolvable.example/page")
    assert raised.value.code == "dns"

    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        lambda hostname, port: {"93.184.216.34"},
    )
    for error, expected in (
        (httpx.ConnectError("certificate verify failed"), "tls"),
        (httpx.ReadTimeout("read timeout"), "timeout"),
    ):
        fetcher = SafeWebFetcher(client_factory=lambda **kwargs: _Client(error=error))
        with pytest.raises(WebFetchError) as raised:
            fetcher.fetch(f"https://example.org/{expected}-{uuid4()}")
        assert raised.value.code == expected

    settings.FIELD_ENRICHMENT_FETCH_MAX_BYTES = 16_384
    response = _Response(
        200,
        b"unused",
        {"content-type": "text/html", "content-length": "20000"},
    )
    fetcher = SafeWebFetcher(client_factory=lambda **kwargs: _Client([response]))
    with pytest.raises(WebFetchError) as raised:
        fetcher.fetch(f"https://example.org/size-{uuid4()}")
    assert raised.value.code == "size"


def test_safe_web_fetcher_pins_validated_ip_instead_of_re_resolving_hostname(monkeypatch):
    resolve_calls = []

    def rebinding_resolver(hostname, port):
        resolve_calls.append((hostname, port))
        return {"93.184.216.34"} if len(resolve_calls) <= 2 else {"127.0.0.1"}

    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        rebinding_resolver,
    )
    response = _Response(
        200,
        b"Verified public evidence text that is deliberately longer than forty characters.",
        {"content-type": "text/plain; charset=utf-8"},
    )
    client = _Client([response])
    factory_kwargs = []

    def client_factory(**kwargs):
        factory_kwargs.append(kwargs)
        return client

    fetcher = SafeWebFetcher(client_factory=client_factory)
    fetcher.fetch(f"https://rebind.example/evidence-{uuid4()}")

    assert resolve_calls == [("rebind.example", 443)]
    request_args, request_kwargs = client.calls[0]
    assert request_args[1].startswith("https://93.184.216.34/")
    assert request_kwargs["headers"]["Host"] == "rebind.example"
    assert request_kwargs["extensions"]["sni_hostname"] == "rebind.example"
    assert factory_kwargs[0]["trust_env"] is False


def test_safe_web_fetcher_disables_environment_proxy_and_repins_each_redirect(monkeypatch):
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:65530")
    addresses = {
        "first.example": {"93.184.216.34"},
        "second.example": {"151.101.1.69"},
    }
    monkeypatch.setattr(
        "catalog.services.field_enrichment.web._resolve_addresses",
        lambda hostname, port: addresses[hostname],
    )
    client = _Client(
        [
            _Response(302, headers={"location": "https://second.example/final"}),
            _Response(
                200,
                b"Redirected public evidence text that is deliberately longer than forty characters.",
                {"content-type": "text/plain; charset=utf-8"},
            ),
        ]
    )
    factory_kwargs = []

    def client_factory(**kwargs):
        factory_kwargs.append(kwargs)
        return client

    monkeypatch.setattr(
        "catalog.services.field_enrichment.web.httpx.Client",
        client_factory,
    )
    fetcher = SafeWebFetcher()
    document = fetcher.fetch(f"https://first.example/start-{uuid4()}")

    assert document.canonical_url == "https://second.example/final"
    assert [kwargs["trust_env"] for kwargs in factory_kwargs] == [False, False]
    first_args, first_kwargs = client.calls[0]
    second_args, second_kwargs = client.calls[1]
    assert first_args[1].startswith("https://93.184.216.34/")
    assert first_kwargs["headers"]["Host"] == "first.example"
    assert first_kwargs["extensions"]["sni_hostname"] == "first.example"
    assert second_args[1] == "https://151.101.1.69/final"
    assert second_kwargs["headers"]["Host"] == "second.example"
    assert second_kwargs["extensions"]["sni_hostname"] == "second.example"
