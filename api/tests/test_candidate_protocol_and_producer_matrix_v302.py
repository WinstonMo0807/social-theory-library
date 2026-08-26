from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace

import pytest
from django.utils import timezone

from catalog.models import (
    DebateCandidate,
    DocumentType,
    Edition,
    EnrichmentCandidate,
    EnrichmentSourceClass,
    EvidencePack,
    Work,
)
from catalog.services.candidate_decision_protocol import (
    CANDIDATE_DECISION_PROTOCOL_VERSION,
    describe_candidate_actions,
)
from catalog.services.field_enrichment.types import FetchedDocument
from catalog.services.research.contracts import RESEARCH_CONTRACTS
from catalog.services.research.orchestrator import ResearchOrchestrator
from catalog.services.research.producer_capabilities import (
    ProducerState,
    capability_for_contract,
    producer_capability_coverage,
)
from catalog.services.workflow_suggestions import WorkflowSuggestionAggregator
from ingestion.models import (
    EntityResolutionCandidate,
    SourceRecord,
    UploadBatch,
    UploadItem,
)


def test_candidate_action_descriptor_preserves_verify_endpoint_and_evidence_gate():
    descriptors = describe_candidate_actions(
        ["inspect", "verify", "reject"],
        decision_url="/candidate/decision/",
        verify_url="/candidate/verify/",
        evidence_count=0,
        evidence_status="lead_only",
    )

    assert [row["key"] for row in descriptors] == ["inspect", "verify", "reject"]
    assert descriptors[1] == {
        "key": "verify",
        "label": "核实此结果",
        "endpoint": "/candidate/verify/",
        "method": "POST",
        "payload": {},
        "availability": {"available": True, "reason": ""},
        "evidence_requirement": {
            "mode": "source_document",
            "minimum_count": 0,
            "satisfied": True,
        },
    }


@pytest.mark.django_db
def test_direct_entity_picker_verifies_searching_lead_into_evidenced_adoptable_candidate(
    api_client,
    admin_user,
    monkeypatch,
):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="中国社会学研究",
        language="zh-CN",
    )
    edition = Edition.objects.create(work=work, publication_year=2026)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="china-sociology.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )
    source_record = SourceRecord.objects.create(
        provider="field_enrichment:web_fetch",
        operation="fetch_page",
        status=SourceRecord.Status.SUCCEEDED,
    )
    candidate_id = "web:person:searching:chen-da"
    query = "陈达"
    source_url = "https://example.org/scholars/chen-da"
    discovery = {
        "version": "universal-entity-discovery-v1",
        "entity_type": "person",
        "field": "contributors.contributors",
        "query": query,
        "context_fingerprint": "direct-picker-test",
        "groups": [
            {"key": "external_web", "label": "Web 线索", "count": 1}
        ],
        "results": [
            {
                "id": candidate_id,
                "kind": "entity_discovery",
                "entity_type": "person",
                "entity_id": None,
                "label": query,
                "primary_name": query,
                "secondary_identity": "待核实网页线索",
                "entity_status": "external_candidate",
                "candidate_group": "external_web",
                "source": "general_web",
                "provider": "searching",
                "match_reasons": ["搜索结果名称匹配"],
                "conflicts": [],
                "external_ids": {},
                "metadata": {"aliases": ["Chen Da"]},
                "evidence": [],
                "evidence_count": 0,
                "evidence_status": "lead_only",
                "source_url": source_url,
                "source_record_id": "",
                "available_actions": ["inspect", "verify", "reject"],
                "human_confirmation_required": True,
                "confidence": 0.78,
            }
        ],
        "warnings": [],
        "status": "healthy",
        "providers_attempted": ["searching"],
        "multiple_candidates": False,
    }

    class RecordingFetcher:
        def __init__(self):
            self.urls = []

        def fetch(self, url):
            self.urls.append(url)
            return FetchedDocument(
                source_url=source_url,
                canonical_url=source_url,
                title="陈达学者资料",
                domain="example.org",
                text=(
                    "陈达是中国早期社会学研究者。本页提供其学术经历、"
                    "著作目录和可供馆员核对的责任者身份资料。"
                ),
                retrieved_at=timezone.now(),
                content_checksum="c" * 64,
                http_status=200,
                content_type="text/html; charset=utf-8",
                source_record_id=source_record.id,
                source_class=EnrichmentSourceClass.SCHOLAR_HOMEPAGE,
            )

    fetcher = RecordingFetcher()
    monkeypatch.setattr(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        lambda _discovery, _request: discovery,
    )
    monkeypatch.setattr(
        "catalog.services.candidate_verification.SafeWebFetcher",
        lambda: fetcher,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/catalog/admin/research/entity-decisions/",
        {
            "item_id": str(item.id),
            "work_id": str(work.id),
            "edition_id": str(edition.id),
            "step": "contributors",
            "field": "contributors.contributors",
            "entity_type": "person",
            "query": query,
            "candidate_id": candidate_id,
            "action": "verify",
            "draft": {
                "contributors": {"items": [{"display_name": query}]}
            },
            "changed_fields": ["contributors.items.0.display_name"],
        },
        format="json",
        HTTP_X_REQUEST_ID="v302-direct-picker-verify",
    )

    assert response.status_code == 200, response.data
    assert response.data["status"] == "verified"
    assert response.data["code"] == "candidate_verified"
    assert fetcher.urls == [source_url]

    persisted = EntityResolutionCandidate.objects.get(upload_item=item)
    assert persisted.source_record_id == source_record.id
    assert persisted.supporting_properties["candidate_group"] == "external_evidence"
    assert persisted.supporting_properties["evidence_status"] == "verified_text"
    assert persisted.preview_data["evidence"][0]["text"].startswith("陈达")

    candidate = response.data["candidate"]
    assert candidate["id"] == str(persisted.id)
    assert candidate["source_tier"] == "web_evidence"
    assert candidate["evidence_status"] == "verified_text"
    assert candidate["evidence_count"] == 1
    assert candidate["action_protocol_version"] == CANDIDATE_DECISION_PROTOCOL_VERSION
    assert candidate["available_actions"] == [
        "inspect",
        "create_draft",
        "keep_unresolved",
        "reject",
    ]
    descriptors = {row["key"]: row for row in candidate["action_descriptors"]}
    assert descriptors["create_draft"]["availability"]["available"] is True
    assert descriptors["create_draft"]["endpoint"] == candidate["decision_url"]
    assert descriptors["create_draft"]["evidence_requirement"]["satisfied"] is True
    assert "verify" not in descriptors


def test_client_draft_action_is_available_without_server_endpoint():
    descriptor = describe_candidate_actions(
        ["apply_to_draft"],
        evidence_count=0,
    )[0]

    assert descriptor["method"] == "CLIENT"
    assert descriptor["endpoint"] is None
    assert descriptor["availability"] == {"available": True, "reason": ""}


def test_field_producer_matrix_distinguishes_productive_degraded_and_disabled():
    title = capability_for_contract(RESEARCH_CONTRACTS.get("work", "title"))
    claims = capability_for_contract(RESEARCH_CONTRACTS.get("curation", "core_viewpoints"))
    reader = capability_for_contract(RESEARCH_CONTRACTS.get("reader", "reader_rendition_policy"))

    assert title.state == ProducerState.PRODUCTIVE
    assert title.persistence_models == ("EnrichmentCandidate", "EnrichmentEvidence")
    assert title.decision_adapter == "field_enrichment_candidate"
    assert title.required_capability == "entity_reasoning"
    assert title.channels["pdf_native"]["state"] == ProducerState.PRODUCTIVE
    assert title.channels["ocr"]["state"] == ProducerState.PRODUCTIVE
    assert title.channels["local_catalog"]["state"] == ProducerState.PRODUCTIVE
    assert title.channels["verified_web"]["state"] == ProducerState.DEGRADED
    assert title.channels["ai_synthesis"]["state"] == ProducerState.UNAVAILABLE
    assert claims.state == ProducerState.DEGRADED
    assert claims.producer.endswith("high_value_claim_candidates")
    assert claims.decision_adapter == "derived_claim_curation"
    assert claims.channels["ai_synthesis"]["state"] == ProducerState.DEGRADED
    assert reader.state == ProducerState.UNAVAILABLE
    assert "禁用自动研究" in reader.reason

    coverage = producer_capability_coverage()
    assert coverage["healthy"] is True
    assert coverage["unavailable_enabled_fields"] == []


def test_field_outcome_never_reports_no_candidate_as_completed_without_producer(monkeypatch):
    monkeypatch.setattr(
        "catalog.services.research.orchestrator.capability_for_contract",
        lambda _contract: SimpleNamespace(
            state=ProducerState.UNAVAILABLE,
            reason="测试 producer 未注册。",
        ),
    )

    outcomes = ResearchOrchestrator._field_outcomes(
        [
            {
                "step": "work",
                "field": "abstract",
                "context_fingerprint": "draft-context",
                "no_reliable_candidate_reason": "PDF 中没有可定位摘要。",
            }
        ],
        {"enrichment": [], "entities": [], "editorial_evidence": []},
    )

    assert outcomes == [
        {
            "field": "work.abstract",
            "status": "producer_unavailable",
            "reason": "测试 producer 未注册。",
            "context_fingerprint": "draft-context",
            "producer_capability": {
                "state": ProducerState.UNAVAILABLE,
                "reason": "测试 producer 未注册。",
            },
        }
    ]


@pytest.mark.django_db
def test_workflow_and_candidate_review_expose_same_action_descriptor_contract(
    api_client,
    admin_user,
):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="Candidate Protocol",
        language="en",
    )
    edition = Edition.objects.create(work=work, publication_year=2026)
    candidate = EnrichmentCandidate.objects.create(
        target_type=EnrichmentCandidate.TargetType.WORK,
        target_id=work.id,
        field_name="title",
        candidate_kind=EnrichmentCandidate.CandidateKind.FACTUAL,
        proposed_value="Candidate Protocol Revised",
        normalized_value={"value": "Candidate Protocol Revised"},
        source_class=EnrichmentSourceClass.NATIONAL_LIBRARY,
        confidence=0.91,
        conflict_group="work-title",
        policy_version="test-policy-v1",
        extraction_version="test-extraction-v1",
        fingerprint=sha256(b"candidate-protocol-v302").hexdigest(),
    )

    suggestion = next(
        row
        for row in WorkflowSuggestionAggregator(edition).aggregate(step="work")["suggestions"]
        if row["id"] == str(candidate.id)
    )
    assert suggestion["available_actions"] == ["inspect", "accept", "reject"]
    assert suggestion["action_protocol_version"] == CANDIDATE_DECISION_PROTOCOL_VERSION
    assert suggestion["action_descriptors"][1]["endpoint"] == suggestion["decision_url"]
    assert suggestion["action_descriptors"][1]["key"] == "accept"

    api_client.force_authenticate(admin_user)
    review = api_client.get(
        "/api/catalog/admin/candidate-review/",
        {"kind": "field_enrichment", "status": "pending"},
    )
    assert review.status_code == 200
    row = review.data["results"][0]
    assert row["id"] == str(candidate.id)
    assert row["available_actions"] == ["inspect", "accept", "reject"]
    assert row["action_protocol_version"] == CANDIDATE_DECISION_PROTOCOL_VERSION
    assert row["action_descriptors"][1]["endpoint"] == row["decision_url"]


@pytest.mark.django_db
def test_research_contract_api_exposes_producer_matrix(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    response = api_client.get("/api/catalog/admin/research/contracts/", {"step": "curation"})

    assert response.status_code == 200
    assert response.data["producer_coverage"]["healthy"] is True
    assert response.data["producer_matrix"]
    by_field = {row["field"]: row for row in response.data["producer_matrix"]}
    assert by_field["core_viewpoints"]["state"] == "degraded"
    contract = next(row for row in response.data["contracts"] if row["field"] == "core_viewpoints")
    assert contract["producer_capability"] == by_field["core_viewpoints"]


@pytest.mark.django_db
def test_knowledge_studio_uses_protocol_for_evidenced_debate_decision(
    api_client,
    admin_user,
):
    pack = EvidencePack.objects.create(
        task_profile_key="debate_discovery",
        task_profile_version=1,
        retrieval_profile="curation",
        envelope_snapshot=[
            {
                "kind": "collection_text",
                "text": "国家能力的效果受到制度条件限制。",
                "locator": {"page": 12},
                "reader_url": "/reader/test?page=12",
            }
        ],
        fingerprint=sha256(b"studio-debate-protocol-v302").hexdigest(),
    )
    candidate = DebateCandidate.objects.create(
        title="国家能力与发展",
        canonical_question="国家能力是否必然促进发展？",
        summary="一个有条件的理论争论。",
        evidence_pack=pack,
        quality_score=0.9,
        importance_score=0.8,
    )
    api_client.force_authenticate(admin_user)

    workspace = api_client.get("/api/catalog/admin/knowledge-workspace/")

    assert workspace.status_code == 200
    row = next(
        value
        for value in workspace.data["studio"]["generated_candidates"]
        if value["id"] == str(candidate.id)
    )
    assert row["available_actions"] == [
        "inspect",
        "accept",
        "accept_with_edit",
        "defer",
        "reject",
    ]
    assert row["action_descriptors"][1]["availability"]["available"] is True
    assert row["action_descriptors"][2]["value_field"] == "canonical_question"

    decided = api_client.post(
        f"/api{row['decision_url']}",
        row["action_descriptors"][1]["payload"] | {"action": "accept"},
        format="json",
    )

    assert decided.status_code == 200
    assert decided.data["status"] == "adopted"
    assert decided.data["draft_node_id"]
