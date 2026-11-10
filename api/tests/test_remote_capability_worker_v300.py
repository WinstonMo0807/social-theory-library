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
from common.task_runtime import queue_or_wait, register_executor_heartbeat, claim_specific_demand
from tests.test_knowledge_core import source
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
def test_heartbeat_cannot_reactivate_retired_document_producer(client):
    revision,_=_source(title="retired remote schedule")
    assert schedule_document_claim_extraction(revision)["status"]=="retired"
    response=_post(client,reverse("remote-worker-heartbeat"),_heartbeat_payload())
    assert response.status_code==200
    executor=CapabilityExecutor.objects.get(executor_id="remote-gpu:4070-test")
    assert "secret" not in executor.metadata
    assert not CapabilityDemand.objects.exists()
    assert _post(client,reverse("remote-worker-claim"),{"executor_id":executor.executor_id}).status_code==204


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_curation_http_claim_respects_concurrency_renewal_and_release(client,source,admin_user,monkeypatch,settings):
    from tests.test_intelligence_remote import stage
    run,artifact,lease,job,config,scheduled=stage(source,admin_user,monkeypatch,settings)
    payload={"executor_id":"curation-test","lease_token":str(lease.lease_token),"error_code":"busy","error_message":"fixture resource wait","retry":True,"retry_after_seconds":0}
    release=_post(client,reverse("remote-worker-release",kwargs={"demand_id":lease.demand_id}),payload)
    assert release.status_code==200 and release.json()["state"]==CapabilityDemand.State.READY
    claimed=_post(client,reverse("remote-worker-claim"),{"executor_id":"curation-test"})
    assert claimed.status_code==200 and claimed.json()["job"]["task_kind"]=="curation_stage"
    current=claimed.json()["lease"]
    assert _post(client,reverse("remote-worker-claim"),{"executor_id":"curation-test"}).status_code==204
    renew=_post(client,reverse("remote-worker-renew",kwargs={"demand_id":current["demand_id"]}),
        {"executor_id":"curation-test","lease_token":current["lease_token"]})
    assert renew.status_code==200 and renew.json()["lease_expires_at"]>=current["lease_expires_at"]


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_old_remote_completion_cannot_write_claims_after_retirement(client):
    demand,lease=_legacy_lease()
    payload={"executor_id":"legacy-fixture","lease_token":str(lease.lease_token),"completion_id":"legacy-complete","result":{"claims":[{"proposition":"必须拒绝"}]}}
    endpoint=reverse("remote-worker-complete",kwargs={"demand_id":demand.pk})
    for _ in range(2):
        response=_post(client,endpoint,payload)
        assert response.status_code==409 and response.json()["code"]=="knowledge_producer_retired"
    assert not DerivedClaim.objects.exists() and not ClaimEvidence.objects.exists()
    demand.refresh_from_db()
    assert demand.state==CapabilityDemand.State.CLAIMED


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_library_synthesis_retirement_keeps_source_pack_without_candidate(client,admin_user):
    revision,spans=_source(title="retired library synthesis", pages=2)
    pack=create_evidence_pack(task_profile=resolve_task_profile("library_synthesis"),
        envelopes=[evidence_span_envelope(span).as_dict() for span in spans],retrieval_snapshot={"collection_only":True},
        subject_type="work",subject_id=str(revision.asset.edition.work_id),actor=admin_user)
    batch=UploadBatch.objects.create(created_by=admin_user,expected_count=1)
    item=UploadItem.objects.create(batch=batch,source_filename="fixture.pdf",edition=revision.asset.edition)
    result=schedule_library_synthesis(pack,upload_item=item,field_name="abstract")
    assert result["status"]=="retired" and not result["publication_blocking"]
    assert not MetadataCandidate.objects.exists() and not CapabilityDemand.objects.exists()
    assert EvidencePack.objects.filter(pk=pack.pk).exists()


@override_settings(
    CAPABILITY_REMOTE_WORKER_ENABLED=True,
    CAPABILITY_REMOTE_WORKER_SHARED_SECRET=WORKER_SECRET,
)
def test_expired_lease_cannot_persist_remote_result(client):
    demand,lease=_legacy_lease()
    CapabilityDemand.objects.filter(pk=demand.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
    response=_post(client,reverse("remote-worker-complete",kwargs={"demand_id":demand.pk}),
        {"executor_id":"legacy-fixture","lease_token":str(lease.lease_token),"completion_id":"expired","result":{"claims":[]}})
    assert response.status_code==409 and response.json()["code"]=="lease_expired"
    assert not DerivedClaim.objects.exists()


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


def _legacy_lease():
    revision,spans=_source(title="legacy in-flight fixture")
    register_executor_heartbeat(executor_id="legacy-fixture",capabilities=["llm_small"],kind="remote_gpu",concurrency=1)
    demand=queue_or_wait(owner_type="evidence_span",owner_key=str(spans[0].pk),capability="llm_small",idempotency_key="old-in-flight",
        payload={"task_kind":"claim_extraction","document_revision_id":str(revision.pk),"evidence_span_id":str(spans[0].pk)},publication_blocking=False).demand
    lease=claim_specific_demand(demand.pk,executor_id="legacy-fixture")
    assert lease
    return demand,lease
