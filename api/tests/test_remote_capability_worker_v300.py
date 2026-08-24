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
    EvidenceSpan,
    Page,
    PublicationState,
    Work,
)
from catalog.services.claims.pipeline import schedule_document_claim_extraction
from common.task_runtime import queue_or_wait


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


def _heartbeat_payload(*, concurrency=1):
    return {
        "executor_id": "remote-gpu:4070-test",
        "display_name": "RTX 4070 test worker",
        "capabilities": ["llm_small"],
        "model_revisions": {
            "llm_small": {
                "provider": "ollama",
                "model": "qwen-claim-8b",
                "revision": "model-sha-4070-test",
            }
        },
        "concurrency": concurrency,
        "metadata": {
            "worker_version": "3.0.0-test",
            "gpu_name": "RTX 4070",
            "secret": "must-not-be-stored",
        },
    }


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
