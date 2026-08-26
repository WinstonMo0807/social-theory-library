from __future__ import annotations

from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings

from accounts.models import User
from catalog.models import (
    Asset,
    CapabilityDemand,
    CapabilityExecutor,
    ClaimEvidence,
    DerivedClaim,
    DocumentRevision,
    Edition,
    EvidenceSpan,
    Page,
    PromptRegistryEntry,
    ProjectionState,
    PublicationState,
    Work,
)
from catalog.services.claims.attribution import infer_attribution
from catalog.services.claim_benchmark import (
    activate_claim_viewpoint_ranking,
    record_claim_benchmark_report,
)
from catalog.services.claims.indexing import _sync_claim_documents, index_document_revision_claims
from catalog.services.claims.pipeline import extract_claims_shadow
from catalog.services.claims.pipeline import (
    CLAIM_EXTRACTION_SCHEMA,
    _scheduled_runtime_identity,
    resolve_claim_extraction_prompt,
    schedule_document_claim_extraction,
)
from catalog.tasks import execute_claim_extraction_demand
from catalog.services.viewpoint_search import query_claim, viewpoint_search
from ingestion.services.ai_client import AIServiceUnavailable
from common.task_runtime import (
    claim_demand,
    claim_specific_demand,
    queue_or_wait,
    register_executor_heartbeat,
)


pytestmark = pytest.mark.django_db


def _source(*, title: str = "Claim 测试", pages: int = 2):
    work = Work.objects.create(document_type="book", title=title, language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"claim-{sha256(title.encode()).hexdigest()[:12]}",
        publication_year=2024,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{title}.pdf",
        sha256=sha256(title.encode()).hexdigest(),
        byte_size=2048,
        page_count=pages,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status=Asset.AccessStatus.PUBLIC,
        is_current=True,
        extraction_method="embedded",
    )
    revision = DocumentRevision.objects.create(
        asset=asset,
        revision=1,
        parser_name="pymupdf",
        parser_version="test-parser-v1",
        extraction_method="embedded",
        extraction_version="test-extraction-v1",
        source_checksum=asset.sha256,
        text_checksum=sha256(f"text-{title}".encode()).hexdigest(),
        is_active=True,
    )
    output = []
    texts = ["贫困导致犯罪。", "贫困不导致犯罪。"]
    for index in range(1, pages + 1):
        text = texts[index - 1] if index <= len(texts) else f"命题证据第 {index} 页。"
        page = Page.objects.create(
            asset=asset,
            index=index,
            printed_label=str(index + 10),
            text=text,
            normalized_text=text,
            text_source=Page.TextSource.EMBEDDED,
            confidence=0.98,
        )
        span = EvidenceSpan.objects.create(
            document_revision=revision,
            page=page,
            page_number=index,
            printed_page_label=str(index + 10),
            start_offset=0,
            end_offset=len(text),
            original_text=text,
            normalized_text=text,
            language="zh-CN",
            content_hash=sha256(text.encode()).hexdigest(),
            quality=0.95,
            extraction_method="embedded",
        )
        output.append(span)
    return work, edition, asset, revision, output


class FakeClaimClient:
    def __init__(self, claims):
        self.claims = claims
        self.calls = 0
        self.last_kwargs = None
        self.config = SimpleNamespace(
            provider="openai_compatible",
            model="claim-model",
            metadata_model="",
            reasoning={"model_revision": "model-sha-1"},
            fallback_profile_key="",
        )

    def generate_json(self, **kwargs):
        self.calls += 1
        self.last_kwargs = kwargs
        return SimpleNamespace(
            data={"claims": self.claims},
            provider="openai_compatible",
            model="claim-model",
            prompt_version="claim-extraction-v1",
        )


def _claim(revision, span, *, proposition, polarity, fingerprint):
    return DerivedClaim.objects.create(
        document_revision=revision,
        primary_evidence=span,
        work=revision.asset.edition.work,
        edition=revision.asset.edition,
        proposition=proposition,
        subject="贫困",
        predicate="导致",
        object="犯罪",
        polarity=polarity,
        attribution=DerivedClaim.Attribution.AUTHOR_CLAIM,
        claim_type=DerivedClaim.ClaimType.CAUSAL,
        prompt_key="claim_extraction",
        prompt_version="test-v1",
        model_provider="test",
        model_name="test-model",
        model_revision="test-model-r1",
        quality_score=0.92,
        importance_score=0.88,
        fingerprint=fingerprint,
        status=DerivedClaim.Status.ACTIVE,
        shadow=True,
    )


def test_claim_extraction_is_shadow_idempotent_and_preserves_qualifiers():
    _work, _edition, _asset, revision, spans = _source(title="限定条件提取")
    client = FakeClaimClient(
        [
            {
                "proposition": "贫困可能导致犯罪，但仅在失业率高时如此。",
                "subject": "贫困",
                "predicate": "导致",
                "object": "犯罪",
                "polarity": "positive",
                "modality": "可能",
                "qualifiers": ["仅在失业率高时", "城市人口"],
                "population_scope": {"label": "城市人口"},
                "attribution": "author_claim",
                "claim_type": "causal",
                "quality_score": 0.9,
                "importance_score": 0.8,
            }
        ]
    )

    first = extract_claims_shadow(spans[0], client=client)
    repeated = extract_claims_shadow(spans[0], client=client)

    assert first["status"] == "completed"
    assert first["created"] == 1
    assert first["publication_blocking"] is False
    assert repeated["idempotent_replay"] is True
    assert repeated["reused"] == 1
    assert client.calls == 1
    claim = DerivedClaim.objects.get(document_revision=revision)
    assert claim.shadow is True
    assert claim.qualifiers == ["仅在失业率高时", "城市人口"]
    assert claim.population_scope == {"label": "城市人口"}
    assert claim.model_revision == "model-sha-1"
    assert claim.quality_factors["extraction_input_key"] == first["extraction_input_key"]
    assert ClaimEvidence.objects.filter(
        derived_claim=claim,
        evidence_span=spans[0],
        role=ClaimEvidence.Role.PRIMARY,
    ).exists()


def test_claim_extraction_failure_is_non_blocking():
    _work, _edition, _asset, _revision, spans = _source(title="Claim AI 降级")
    client = FakeClaimClient([])

    def unavailable(**_kwargs):
        raise AIServiceUnavailable("worker offline")

    client.generate_json = unavailable
    result = extract_claims_shadow(spans[0], client=client)

    assert result["status"] == "degraded"
    assert result["error_code"] == "ai_service_unavailable"
    assert result["publication_blocking"] is False
    assert DerivedClaim.objects.exists() is False


def test_active_prompt_registry_revision_controls_extraction_and_provenance():
    _work, _edition, _asset, _revision, spans = _source(title="Prompt Registry Claim")
    content = "只从原文提取命题，并保留所有限定条件。"
    content_hash = sha256(content.encode()).hexdigest()
    schema_hash = sha256(b"registered-schema").hexdigest()
    prompt = PromptRegistryEntry.objects.create(
        key="claim_extraction",
        version=7,
        capability="claim_extraction",
        content=content,
        output_schema=CLAIM_EXTRACTION_SCHEMA,
        content_hash=content_hash,
        schema_hash=schema_hash,
        status=PromptRegistryEntry.Status.ACTIVE,
    )
    client = FakeClaimClient(
        [
            {
                "proposition": "贫困导致犯罪",
                "claim_type": "causal",
                "attribution": "author_claim",
                "qualifiers": ["仅限当前证据"],
            }
        ]
    )

    result = extract_claims_shadow(spans[0], client=client)
    claim = DerivedClaim.objects.get()

    assert client.last_kwargs["system_prompt"] == content
    assert client.last_kwargs["schema"] == CLAIM_EXTRACTION_SCHEMA
    assert client.last_kwargs["prompt_version"] == "registry-7"
    assert claim.prompt_key == prompt.key
    assert claim.prompt_version == "registry-7"
    assert claim.quality_factors["prompt"] == {
        "key": prompt.key,
        "version": "registry-7",
        "registry_id": str(prompt.id),
        "registry_version": 7,
        "content_hash": content_hash,
        "schema_hash": schema_hash,
        "source": "prompt_registry",
    }
    assert result["prompt"]["registry_id"] == str(prompt.id)


def test_attribution_does_not_turn_quoted_or_criticized_claim_into_author_claim():
    quoted = infer_attribution("作者写道：“阶级会再生产不平等。”")
    criticized = infer_attribution("本章批评‘贫困必然导致犯罪’这一主张。")

    assert quoted.attribution == DerivedClaim.Attribution.QUOTED_CLAIM
    assert criticized.attribution == DerivedClaim.Attribution.CRITICIZED_CLAIM


def test_claim_index_updates_existing_meilisearch_projection_revisions():
    _work, _edition, _asset, revision, spans = _source(title="Claim Index 投影")
    claim = _claim(
        revision,
        spans[0],
        proposition="贫困导致犯罪",
        polarity=DerivedClaim.Polarity.POSITIVE,
        fingerprint="index-positive",
    )
    writes = []

    def writer(revision_id, documents):
        writes.append((revision_id, documents))
        return {"backend": "meilisearch", "documents": len(documents)}

    result = index_document_revision_claims(revision, writer=writer)

    assert result["status"] == "completed"
    assert result["backend"] == "meilisearch"
    assert writes[0][0] == str(revision.id)
    assert writes[0][1][0]["claim_id"] == str(claim.id)
    assert writes[0][1][0]["evidence_span_id"] == str(spans[0].id)
    states = ProjectionState.objects.filter(
        projection_type=ProjectionState.ProjectionType.CLAIM_INDEX,
    )
    assert set(states.values_list("object_type", flat=True)) == {
        "document_revision",
        "derived_claim",
    }
    assert set(states.values_list("status", flat=True)) == {
        ProjectionState.Status.CURRENT,
    }
    assert all(
        source == projected
        for source, projected in states.values_list("source_revision", "projected_revision")
    )


def test_active_claim_index_sync_tombstones_superseded_revision_documents():
    _work, _edition, asset, previous, _spans = _source(
        title="Claim Index revision cleanup"
    )
    previous.is_active = False
    previous.save(update_fields=["is_active", "updated_at"])
    current = DocumentRevision.objects.create(
        asset=asset,
        revision=2,
        source_checksum=previous.source_checksum,
        text_checksum="8" * 64,
        is_active=True,
    )
    indexed = {
        str(previous.id): {"old-claim"},
        str(current.id): {"current-claim", "stale-current-claim"},
    }
    requests = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"taskUid": 1}

    def post(url, **kwargs):
        requests.append((url, kwargs.get("json")))
        return Response()

    with (
        patch("catalog.services.claims.indexing.ensure_claim_index"),
        patch(
            "catalog.services.claims.indexing._fetch_revision_document_ids",
            side_effect=lambda revision_id: indexed[str(revision_id)],
        ),
        patch("catalog.services.claims.indexing.httpx.post", side_effect=post),
        patch("catalog.services.claims.indexing._wait_task", return_value={"status": "succeeded"}),
    ):
        result = _sync_claim_documents(
            str(current.id),
            [{"id": "current-claim"}],
        )

    assert result["removed_stale_documents"] == 2
    assert result["cleaned_revision_count"] == 2
    delete_payloads = [
        payload for url, payload in requests if url.endswith("/documents/delete-batch")
    ]
    assert delete_payloads == [["old-claim", "stale-current-claim"]]


def test_claim_index_failure_remains_visible_but_does_not_block_publication():
    _work, _edition, _asset, revision, spans = _source(title="Claim Index 降级")
    _claim(
        revision,
        spans[0],
        proposition="贫困导致犯罪",
        polarity=DerivedClaim.Polarity.POSITIVE,
        fingerprint="index-degraded",
    )

    def writer(_revision_id, _documents):
        raise RuntimeError("meilisearch unavailable")

    result = index_document_revision_claims(revision, writer=writer)

    assert result["status"] == "degraded"
    assert result["publication_blocking"] is False
    assert set(
        ProjectionState.objects.values_list("status", flat=True)
    ) == {ProjectionState.Status.FAILED}


def test_document_claim_schedule_waits_without_executor_and_is_idempotent():
    _work, _edition, _asset, revision, spans = _source(title="Claim capability waiting")

    first = schedule_document_claim_extraction(revision)
    repeated = schedule_document_claim_extraction(revision)

    assert first["scheduled"] == len(spans)
    assert first["states"] == {
        CapabilityDemand.State.WAITING_FOR_CAPABILITY: len(spans)
    }
    assert first["publication_blocking"] is False
    assert repeated["demand_ids"] == first["demand_ids"]
    assert CapabilityDemand.objects.count() == len(spans)
    assert CapabilityDemand.objects.filter(publication_blocking=True).exists() is False
    assert set(CapabilityDemand.objects.values_list("preferred_queue", flat=True)) == {"celery"}


def test_specific_demand_lease_prevents_celery_and_remote_double_claim():
    nas = register_executor_heartbeat(
        executor_id="nas-celery:test",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["llm_small"],
        concurrency=1,
    )
    register_executor_heartbeat(
        executor_id="remote-gpu:test",
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        capabilities=["llm_small"],
        concurrency=1,
    )
    demand = queue_or_wait(
        owner_type="evidence_span",
        owner_key="span-test",
        capability="llm_small",
        idempotency_key="specific-claim-demand-test",
        payload={"task_kind": "claim_extraction"},
        publication_blocking=False,
    ).demand

    celery_lease = claim_specific_demand(demand.id, executor_id=nas.executor_id)
    remote_lease = claim_demand(executor_id="remote-gpu:test")

    assert celery_lease is not None
    assert celery_lease.demand_id == demand.id
    assert remote_lease is None
    demand.refresh_from_db()
    assert demand.state == CapabilityDemand.State.CLAIMED
    assert demand.claimed_by_id == nas.id


def test_celery_claim_task_completes_leased_demand_and_indexes_final_revision():
    _work, _edition, _asset, revision, spans = _source(
        title="Claim celery execution",
        pages=1,
    )
    executor = register_executor_heartbeat(
        executor_id="nas-celery:execution-test",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["llm_small"],
        concurrency=1,
    )
    prompt = resolve_claim_extraction_prompt()
    runtime = _scheduled_runtime_identity()
    demand = queue_or_wait(
        owner_type="evidence_span",
        owner_key=str(spans[0].id),
        capability="llm_small",
        idempotency_key="claim-celery-execution-test",
        payload={
            "task_kind": "claim_extraction",
            "document_revision_id": str(revision.id),
            "evidence_span_id": str(spans[0].id),
            "prompt_key": prompt["key"],
            "prompt_version": prompt["version"],
            "prompt_content_hash": prompt["content_hash"],
            "prompt_schema_hash": prompt["schema_hash"],
            "profile_key": runtime["profile_key"],
            "provider": runtime["provider"],
            "model": runtime["model"],
            "model_revision": runtime["model_revision"],
        },
        publication_blocking=False,
    ).demand
    lease = claim_specific_demand(demand.id, executor_id=executor.executor_id)

    with (
        patch(
            "catalog.services.claims.pipeline.extract_claims_shadow",
            return_value={
                "status": "completed",
                "created": 1,
                "publication_blocking": False,
            },
        ),
        patch(
            "catalog.services.claims.indexing.index_document_revision_claims",
            return_value={"status": "completed", "backend": "meilisearch"},
        ) as index_revision,
        patch(
            "catalog.services.claims.pipeline.dispatch_ready_claim_extraction_demands",
            return_value={"candidates": 0, "dispatched": 0},
        ),
    ):
        result = execute_claim_extraction_demand.apply(
            args=[str(demand.id), str(lease.lease_token), executor.executor_id]
        ).result

    demand.refresh_from_db()
    assert result["status"] == "completed"
    assert result["claim_index"]["backend"] == "meilisearch"
    assert demand.state == CapabilityDemand.State.COMPLETED
    assert demand.publication_blocking is False
    index_revision.assert_called_once_with(revision)


def test_query_claim_preserves_causal_negation():
    statement = query_claim("X 不导致 Y")

    assert statement.subject == "X"
    assert statement.predicate == "不导致"
    assert statement.object == "Y"
    assert statement.polarity == DerivedClaim.Polarity.NEGATIVE
    assert statement.claim_type == DerivedClaim.ClaimType.CAUSAL


@override_settings(VIEWPOINT_CLAIM_BENCHMARK_GATE_PASSED=False)
def test_viewpoint_search_keeps_baseline_default_and_groups_validated_claim_shadow():
    work, _edition, asset, revision, spans = _source(title="观点检索 Shadow")
    positive = _claim(
        revision,
        spans[0],
        proposition="贫困导致犯罪",
        polarity=DerivedClaim.Polarity.POSITIVE,
        fingerprint="viewpoint-positive",
    )
    negative = _claim(
        revision,
        spans[1],
        proposition="贫困不导致犯罪",
        polarity=DerivedClaim.Polarity.NEGATIVE,
        fingerprint="viewpoint-negative",
    )

    def retrieve(_query, **_kwargs):
        return {
            "search_version": "v2",
            "engine": "v2_hybrid",
            "fallback_used": False,
            "fallback_reason": "",
            "results": [
                {
                    "id": "semantic-positive",
                    "asset_id": str(asset.id),
                    "work_id": str(work.id),
                    "title": work.title,
                    "authors": ["测试作者"],
                    "page_start": 1,
                    "page_index": 1,
                    "snippet": spans[0].original_text,
                },
                {
                    "id": "missing-evidence",
                    "asset_id": str(asset.id),
                    "work_id": str(work.id),
                    "title": work.title,
                    "authors": [],
                    "page_start": 99,
                    "page_index": 99,
                    "snippet": "无法验证的片段",
                },
            ],
        }

    def claim_search(_query, **_kwargs):
        return {
            "backend": "meilisearch",
            "index_uid": "derived_claims",
            "hits": [
                {"claim_id": str(positive.id), "_rankingScore": 0.9},
                {"claim_id": str(negative.id), "_rankingScore": 0.88},
            ],
        }

    result = viewpoint_search(
        "贫困导致犯罪",
        retrieval_backend=retrieve,
        claim_search_backend=claim_search,
    )

    assert result["default_mode"] == "baseline"
    assert result["metadata"]["claim_ranking_status"] == "shadow"
    assert result["metadata"]["cosine_similarity_used_for_stance"] is False
    assert result["metadata"]["unvalidated_baseline_results_excluded"] == 1
    assert len(result["baseline"]["results"]) == 1
    assert result["shadow"]["groups"]["direct"][0]["claim_id"] == str(positive.id)
    assert result["shadow"]["groups"]["oppose"][0]["claim_id"] == str(negative.id)
    assert all(
        row["evidence"]["kind"] == "collection_text"
        and row["reader_url"].endswith(f"?page={row['page']}")
        and row["pdf_url"].endswith("/file/")
        for row in result["shadow"]["results"]
    )
    assert result["facets"]["relations"][0]["id"] == "direct"
    assert {"id", "slug", "label", "count"}.issubset(
        result["facets"]["relations"][0]
    )

    relation_filtered = viewpoint_search(
        "贫困导致犯罪",
        filters={"relations": ["oppose"]},
        retrieval_backend=retrieve,
        claim_search_backend=claim_search,
    )

    assert relation_filtered["default_mode"] == "baseline"
    assert relation_filtered["results"] == []
    assert [
        row["claim_id"] for row in relation_filtered["shadow"]["results"]
    ] == [str(negative.id)]


@override_settings(VIEWPOINT_CLAIM_BENCHMARK_GATE_PASSED=True)
def test_viewpoint_claim_default_requires_explicit_benchmark_gate(settings):
    work, _edition, _asset, revision, spans = _source(title="观点检索 Gate", pages=1)
    claim = _claim(
        revision,
        spans[0],
        proposition="贫困导致犯罪",
        polarity=DerivedClaim.Polarity.POSITIVE,
        fingerprint="viewpoint-gate",
    )

    search_kwargs = {
        "retrieval_backend": lambda *_args, **_kwargs: {"results": []},
        "claim_search_backend": lambda *_args, **_kwargs: {
            "backend": "database-fallback",
            "index_uid": "derived_claims",
            "hits": [{"claim_id": str(claim.id), "_rankingScore": 0.9}],
        },
    }
    flag_only = viewpoint_search("贫困导致犯罪", **search_kwargs)
    assert flag_only["default_mode"] == "baseline"
    assert flag_only["metadata"]["benchmark_activation"]["reason"] == (
        "postgres_activation_missing"
    )

    report = {
        "gold_query_count": 10,
        "completed_query_count": 10,
        "errors": [],
        "baseline": {"recall_at_k": 0.7},
        "claim_shadow": {"recall_at_k": 0.8},
        "gate": {"passed": True, "default_ranking_change_allowed": True},
    }
    benchmark = record_claim_benchmark_report(report)
    superadmin = User.objects.create_superuser(
        username="benchmark-owner@example.org",
        email="benchmark-owner@example.org",
        password="Correct-Horse-Battery-2026",
    )
    settings.LIBRARY_OWNER_EMAIL = superadmin.email
    activate_claim_viewpoint_ranking(benchmark["report_hash"], actor=superadmin)

    result = viewpoint_search(
        "贫困导致犯罪",
        **search_kwargs,
    )

    assert result["default_mode"] == "claim"
    assert result["metadata"]["benchmark_gate_passed"] is True
    assert result["results"][0]["work"]["id"] == str(work.id)
