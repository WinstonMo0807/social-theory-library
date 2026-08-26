from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json

import pytest
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from catalog.models import (
    Asset,
    CapabilityDemand,
    CapabilityExecutor,
    ClaimEvidence,
    DerivedClaim,
    DocumentRevision,
    Edition,
    EvidencePack,
    EvidenceSpan,
    Page,
    PublicationState,
    Work,
)
from catalog.services.claims.pipeline import schedule_document_claim_extraction
from catalog.services.evidence_envelope import evidence_span_envelope
from catalog.services.research.evidence_pack import create_evidence_pack
from catalog.services.research.library_synthesis import schedule_library_synthesis
from catalog.services.research.task_profiles import resolve_task_profile
from common.task_runtime import queue_or_wait
from ingestion.models import MetadataCandidate, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db
WORKER_SECRET = "remote-worker-test-secret-" + "x" * 32
WORKER_HEADERS = {"HTTP_X_LIBRARY_WORKER_TOKEN": WORKER_SECRET}


def _post(client, url, payload, *, headers=None):
    request_headers = WORKER_HEADERS if headers is None else headers
    return client.post(
        url,
        data=json.dumps(payload),
        content_type="application/json",
        **request_headers,
    )


def _source(*, title="Remote claim", pages=1):
    work = Work.objects.create(document_type="book", title=title, language="zh-CN")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug=f"remote-{sha256(title.encode()).hexdigest()[:12]}",
        publication_year=2024,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=f"public/{title}.pdf",
        sha256=sha256(title.encode()).hexdigest(),
        byte_size=4096,
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
        parser_version="test",
        extraction_method="embedded",
        extraction_version="test",
        source_checksum=asset.sha256,
        text_checksum=sha256(f"text-{title}".encode()).hexdigest(),
        is_active=True,
    )
    spans = []
    for index in range(1, pages + 1):
        text = f"失业在制度保障薄弱时可能加剧贫困。第 {index} 页。"
        page = Page.objects.create(
            asset=asset,
            index=index,
            printed_label=str(index),
            text=text,
            normalized_text=text,
            text_source=Page.TextSource.EMBEDDED,
            confidence=0.98,
        )
        spans.append(
            EvidenceSpan.objects.create(
                document_revision=revision,
                page=page,
                page_number=index,
                printed_page_label=str(index),
                start_offset=0,
                end_offset=len(text),
                original_text=text,
                normalized_text=text,
                language="zh-CN",
                content_hash=sha256(text.encode()).hexdigest(),
                quality=0.96,
                extraction_method="embedded",
            )
        )
    return revision, spans


def _heartbeat_payload(*, concurrency=1, capabilities=None, task_kinds=None):
    capabilities = list(capabilities or ["llm_small"])
    payload = {
        "executor_id": "remote-gpu:4070-test",
        "display_name": "RTX 4070 test worker",
        "capabilities": capabilities,
        "model_revisions": {
            capability: {
                "provider": "ollama",
                "model": "qwen-claim-8b",
                "revision": "model-sha-4070-test",
            }
            for capability in capabilities
        },
        "concurrency": concurrency,
        "metadata": {
            "worker_version": "3.0.0-test",
            "gpu_name": "RTX 4070",
            "secret": "must-not-be-stored",
        },
    }
    if task_kinds is not None:
        payload["metadata"]["task_kinds"] = list(task_kinds)
        payload["metadata"]["task_profiles"] = {
            task_kind: [task_kind]
            for task_kind in task_kinds
        }
    return payload


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_worker_token_required_and_ai_model_revision_must_be_declared(client):
    url = reverse("remote-worker-heartbeat")
    no_token = _post(client, url, _heartbeat_payload(), headers={})
    wrong_token = _post(
        client,
        url,
        _heartbeat_payload(),
        headers={"HTTP_X_LIBRARY_WORKER_TOKEN": "z" * 48},
    )
    missing_revision = _heartbeat_payload()
    missing_revision["model_revisions"] = {}
    invalid_model = _post(client, url, missing_revision)

    assert no_token.status_code == 403
    assert wrong_token.status_code == 403
    assert invalid_model.status_code == 400
    assert CapabilityExecutor.objects.exists() is False


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_heartbeat_makes_waiting_non_blocking_claim_demand_ready(client):
    revision, _spans = _source(title="offline then online")
    scheduled = schedule_document_claim_extraction(revision)
    demand = CapabilityDemand.objects.get(pk=scheduled["demand_ids"][0])

    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert demand.publication_blocking is False

    response = _post(client, reverse("remote-worker-heartbeat"), _heartbeat_payload())
    demand.refresh_from_db()
    executor = CapabilityExecutor.objects.get(executor_id="remote-gpu:4070-test")

    assert response.status_code == 200
    assert executor.kind == CapabilityExecutor.Kind.REMOTE_GPU
    assert executor.metadata["transport"] == "https_pull"
    assert "secret" not in executor.metadata
    assert demand.state == CapabilityDemand.State.READY


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_claim_respects_concurrency_and_release_is_retryable(client):
    revision, _spans = _source(title="remote concurrency", pages=2)
    schedule_document_claim_extraction(revision)
    _post(client, reverse("remote-worker-heartbeat"), _heartbeat_payload(concurrency=1))

    first = _post(client, reverse("remote-worker-claim"), {"executor_id": "remote-gpu:4070-test"})
    second = _post(client, reverse("remote-worker-claim"), {"executor_id": "remote-gpu:4070-test"})
    lease = first.json()["lease"]
    renew = _post(
        client,
        reverse("remote-worker-renew", kwargs={"demand_id": lease["demand_id"]}),
        {
            "executor_id": "remote-gpu:4070-test",
            "lease_token": lease["lease_token"],
        },
    )
    release = _post(
        client,
        reverse("remote-worker-release", kwargs={"demand_id": lease["demand_id"]}),
        {
            "executor_id": "remote-gpu:4070-test",
            "lease_token": lease["lease_token"],
            "error_code": "local_model_busy",
            "error_message": "retry after local model unload",
            "retry": True,
            "retry_after_seconds": 0,
        },
    )

    assert first.status_code == 200
    assert first.json()["job"]["task_kind"] == "claim_extraction"
    assert first.json()["job"]["input"]["text"]
    assert first.json()["job"]["prompt"]["content"]
    assert second.status_code == 204
    assert renew.status_code == 200
    assert renew.json()["lease_expires_at"] >= lease["lease_expires_at"]
    assert release.status_code == 200
    assert release.json()["state"] == CapabilityDemand.State.READY
    assert release.json()["publication_blocking"] is False


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_remote_completion_persists_claim_evidence_before_idempotent_completion(client):
    revision, spans = _source(title="remote completion")
    schedule_document_claim_extraction(revision)
    _post(client, reverse("remote-worker-heartbeat"), _heartbeat_payload())
    claim_response = _post(
        client,
        reverse("remote-worker-claim"),
        {"executor_id": "remote-gpu:4070-test"},
    )
    lease = claim_response.json()["lease"]
    result = {
        "provider": "ollama",
        "model": "qwen-claim-8b",
        "model_revision": "model-sha-4070-test",
        "claims": [
            {
                "proposition": "制度保障薄弱时，失业可能加剧贫困。",
                "subject": "失业",
                "predicate": "加剧",
                "object": "贫困",
                "polarity": "positive",
                "modality": "可能",
                "qualifiers": ["制度保障薄弱时"],
                "attribution": "author_claim",
                "claim_type": "causal",
                "quality_score": 0.91,
                "importance_score": 0.84,
            }
        ],
    }
    payload = {
        "executor_id": "remote-gpu:4070-test",
        "lease_token": lease["lease_token"],
        "completion_id": "completion-4070-1",
        "result": result,
    }
    url = reverse("remote-worker-complete", kwargs={"demand_id": lease["demand_id"]})
    completed = _post(client, url, payload)
    replay = _post(client, url, payload)

    demand = CapabilityDemand.objects.get(pk=lease["demand_id"])
    claim = DerivedClaim.objects.get(document_revision=revision)
    assert completed.status_code == 200
    assert completed.json()["created"] == 1
    assert completed.json()["idempotent_replay"] is False
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert demand.state == CapabilityDemand.State.COMPLETED
    assert demand.publication_blocking is False
    assert claim.shadow is True
    assert claim.model_provider == "ollama"
    assert claim.model_name == "qwen-claim-8b"
    assert claim.model_revision == "model-sha-4070-test"
    assert ClaimEvidence.objects.filter(
        derived_claim=claim,
        evidence_span=spans[0],
    ).exists()

    changed = dict(payload)
    changed["result"] = {**result, "claims": []}
    conflict = _post(client, url, changed)
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "completion_conflict"


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_remote_library_synthesis_protocol_persists_evidence_candidate_only(
    client,
    admin_user,
):
    revision, spans = _source(title="remote library synthesis", pages=2)
    pack = create_evidence_pack(
        task_profile=resolve_task_profile("library_synthesis"),
        envelopes=[evidence_span_envelope(span).as_dict() for span in spans],
        retrieval_snapshot={
            "profile": "library_synthesis",
            "field_name": "abstract",
            "evidence_span_ids": [str(span.id) for span in spans],
            "collection_only": True,
        },
        subject_type="work",
        subject_id=str(revision.asset.edition.work_id),
        actor=admin_user,
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="library-synthesis.pdf",
        edition=revision.asset.edition,
    )
    scheduled = schedule_library_synthesis(
        pack,
        upload_item=item,
        field_name="abstract",
    )
    demand = CapabilityDemand.objects.get(pk=scheduled["demand_id"])
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY

    heartbeat = _heartbeat_payload(
        capabilities=["llm_large"],
        task_kinds=["library_synthesis"],
    )
    online = _post(client, reverse("remote-worker-heartbeat"), heartbeat)
    claimed = _post(
        client,
        reverse("remote-worker-claim"),
        {"executor_id": "remote-gpu:4070-test"},
    )

    assert online.status_code == 200
    assert claimed.status_code == 200
    lease = claimed.json()["lease"]
    job = claimed.json()["job"]
    assert job["task_kind"] == "library_synthesis"
    assert job["task_profile_key"] == "library_synthesis"
    assert job["input"]["evidence_pack_id"] == str(pack.id)
    assert job["input"]["evidence_pack_fingerprint"] == pack.fingerprint
    assert {row["id"] for row in job["input"]["evidence"]} == {
        str(span.id) for span in spans
    }

    result = {
        "provider": "ollama",
        "model": "qwen-claim-8b",
        "model_revision": "model-sha-4070-test",
        "candidate": {
            "value": "馆藏综合候选仅概括两页原文中的制度保障、失业与贫困关系。",
            "evidence_span_ids": [str(span.id) for span in spans],
            "rationale": "两处馆藏原文共同支持这一概括。",
        },
    }
    completion_payload = {
        "executor_id": "remote-gpu:4070-test",
        "lease_token": lease["lease_token"],
        "completion_id": "library-synthesis-completion-1",
        "result": result,
    }
    completion_url = reverse(
        "remote-worker-complete",
        kwargs={"demand_id": lease["demand_id"]},
    )
    completed = _post(client, completion_url, completion_payload)
    replay = _post(client, completion_url, completion_payload)

    assert completed.status_code == 200
    assert completed.json()["created"] == 1
    assert completed.json()["claim_ids"] == []
    assert len(completed.json()["candidate_ids"]) == 1
    assert replay.status_code == 200
    assert replay.json()["candidate_ids"] == completed.json()["candidate_ids"]
    assert replay.json()["idempotent_replay"] is True
    candidate = MetadataCandidate.objects.get(pk=completed.json()["candidate_ids"][0])
    assert candidate.upload_item == item
    assert candidate.field_name == "abstract"
    assert candidate.source == "ai_library_synthesis_v1"
    assert candidate.evidence["evidence_pack_id"] == str(pack.id)
    assert set(candidate.evidence["evidence_span_ids"]) == {
        str(span.id) for span in spans
    }
    assert candidate.evidence_records.count() == 2
    revision.asset.edition.work.refresh_from_db()
    assert revision.asset.edition.work.abstract == ""
    demand.refresh_from_db()
    assert demand.state == CapabilityDemand.State.COMPLETED
    assert demand.publication_blocking is False


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_expired_lease_cannot_persist_remote_result(client):
    revision, _spans = _source(title="expired remote lease")
    schedule_document_claim_extraction(revision)
    _post(client, reverse("remote-worker-heartbeat"), _heartbeat_payload())
    claim_response = _post(
        client,
        reverse("remote-worker-claim"),
        {"executor_id": "remote-gpu:4070-test"},
    )
    lease = claim_response.json()["lease"]
    CapabilityDemand.objects.filter(pk=lease["demand_id"]).update(
        lease_expires_at=timezone.now() - timedelta(seconds=1)
    )

    response = _post(
        client,
        reverse("remote-worker-complete", kwargs={"demand_id": lease["demand_id"]}),
        {
            "executor_id": "remote-gpu:4070-test",
            "lease_token": lease["lease_token"],
            "completion_id": "expired-completion",
            "result": {
                "provider": "ollama",
                "model": "qwen-claim-8b",
                "model_revision": "model-sha-4070-test",
                "claims": [],
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "lease_expired"
    assert DerivedClaim.objects.exists() is False


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
    CAPABILITY_REMOTE_WORKER_MAX_REQUEST_BYTES=256,
)
def test_worker_request_payload_is_bounded(client):
    payload = _heartbeat_payload()
    payload["metadata"]["runtime"] = "x" * 1000
    response = _post(client, reverse("remote-worker-heartbeat"), payload)

    assert response.status_code == 413


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_pull_worker_leaves_unhandled_task_kind_waiting(client):
    _post(client, reverse("remote-worker-heartbeat"), _heartbeat_payload())
    demand = queue_or_wait(
        owner_type="research_run",
        owner_key="unsupported-test",
        capability="llm_small",
        idempotency_key="remote-unsupported-kind",
        payload={"task_kind": "unhandled_reasoning"},
        publication_blocking=False,
    ).demand

    response = _post(
        client,
        reverse("remote-worker-claim"),
        {"executor_id": "remote-gpu:4070-test"},
    )
    demand.refresh_from_db()

    assert response.status_code == 204
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
