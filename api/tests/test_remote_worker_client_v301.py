from __future__ import annotations

import json
import time

import httpx
import pytest

from common.remote_worker_client import (
    RemoteAIWorkerClient,
    RemoteWorkerClientConfig,
    RemoteWorkerClientError,
)


class _Response:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _ServerClient:
    def __init__(self, claim_payload=None):
        self.claim_payload = claim_payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs.get("json")))
        if url.endswith("heartbeat/"):
            return _Response(200, {"status": "online", "poll_after_seconds": 5})
        if url.endswith("claim/"):
            return _Response(200, self.claim_payload) if self.claim_payload else _Response(204)
        if url.endswith("renew/"):
            return _Response(200, {"lease_expires_at": "2026-08-25T12:00:00Z"})
        if url.endswith("model/"):
            return _Response(200, {"data": {"summary": "fixture"}, "output_hash": "fixture-output-hash"})
        if url.endswith("complete/"):
            return _Response(200, {"status": "completed", "created": 1})
        if url.endswith("release/"):
            return _Response(200, {"state": "ready"})
        raise AssertionError(url)


class _ModelClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response(200, self.payload)


class _SlowModelClient(_ModelClient):
    def post(self, url, **kwargs):
        time.sleep(1.1)
        return super().post(url, **kwargs)


class _UnavailableServerClient:
    def post(self, url, **kwargs):
        request = httpx.Request("POST", url)
        raise httpx.ConnectError("temporary WAN failure", request=request)


def _config(**overrides):
    values = {
        "server_url": "https://books.example/api/capability-worker",
        "worker_token": "w" * 40,
        "executor_id": "remote-gpu:4070-test",
        "provider": "ollama",
        "model_url": "http://127.0.0.1:11434",
        "model": "qwen-claim:8b",
        "model_revision": "sha256-model-revision",
    }
    values.update(overrides)
    return RemoteWorkerClientConfig(**values)


def _claim_payload():
    return {
        "lease": {
            "demand_id": "1bc3765a-749a-4dff-92f9-ac252ddfbe91",
            "lease_token": "8a7f082d-ea06-48b0-becb-949f08f32f20",
        },
        "job": {
            "task_kind": "claim_extraction",
            "input": {"text": "制度保障薄弱时，失业可能加剧贫困。"},
            "prompt": {"content": "抽取原子社会科学命题。"},
            "output_schema": {
                "type": "object",
                "properties": {"claims": {"type": "array"}},
                "required": ["claims"],
            },
            "limits": {"max_claims": 24},
        },
    }


def _library_synthesis_payload():
    evidence = [
        {
            "id": "7a1f65d7-5066-45ab-a83e-5e4fb65b0270",
            "kind": "collection_text",
            "source": {"document_revision_id": "revision-1"},
            "text": "导论讨论制度保障、失业与贫困之间的条件性关系。",
            "locator": {"page": 1},
            "quality": {"score": 0.9},
            "provenance": {"extraction_method": "embedded"},
        },
        {
            "id": "c785e8ca-4354-478f-a2d7-2dbfece2ab61",
            "kind": "collection_text",
            "source": {"document_revision_id": "revision-1"},
            "text": "结论限定这一解释仅适用于制度保障薄弱的情境。",
            "locator": {"page": 2},
            "quality": {"score": 0.92},
            "provenance": {"extraction_method": "embedded"},
        },
    ]
    return {
        "lease": {
            "demand_id": "9726d707-99bb-4b22-87a9-27f5da291a21",
            "lease_token": "5f39ea5b-6739-42c1-8193-f5f5ea2f6ed3",
        },
        "job": {
            "task_kind": "library_synthesis",
            "task_profile_key": "library_synthesis",
            "input": {
                "evidence_pack_id": "dd3abf64-0b61-4604-86bf-edfb17333afb",
                "requested_field": "abstract",
                "evidence": evidence,
            },
            "prompt": {"content": "只根据 EvidencePack 生成馆藏综合候选。"},
            "output_schema": {
                "type": "object",
                "required": ["candidate"],
                "properties": {"candidate": {"type": "object"}},
            },
            "limits": {"max_evidence": 12, "max_output_chars": 12_000},
        },
    }


def test_remote_worker_requires_https_for_non_local_server():
    with pytest.raises(RemoteWorkerClientError) as raised:
        _config(server_url="http://books.example/api/capability-worker").validated()

    assert raised.value.code == "https_required"


def test_remote_worker_enforces_rate_safe_poll_floor():
    assert _config(poll_seconds=1).validated().poll_seconds == 10


def test_remote_worker_environment_uses_managed_curation_and_rejects_old_kind(monkeypatch):
    monkeypatch.setenv("STL_WORKER_SERVER_URL","https://books.example/api/capability-worker")
    monkeypatch.setenv("STL_WORKER_TOKEN","w"*40)
    monkeypatch.setenv("STL_WORKER_CAPABILITIES","llm_large")
    monkeypatch.setenv("STL_WORKER_TASK_KINDS","curation_stage")
    config=RemoteWorkerClientConfig.from_environment()
    assert config.capabilities==("llm_large",) and config.task_kinds==("curation_stage",)
    monkeypatch.setenv("STL_WORKER_TASK_KINDS","library_synthesis")
    with pytest.raises(RemoteWorkerClientError): RemoteWorkerClientConfig.from_environment()


def test_remote_worker_curation_uses_server_transport_and_bound_receipt(monkeypatch):
    claimed=_curation_payload()
    server=_ServerClient(claimed)
    model=_ModelClient({})
    worker=RemoteAIWorkerClient(_config(capabilities=("llm_large",)),server_client=server,model_client=model,sleep=lambda seconds:None)
    monkeypatch.setattr("common.docetl_map.run_map",_map_fixture)
    assert worker.run_once()=="completed"
    heartbeat=next(payload for url,payload in server.calls if url.endswith("heartbeat/"))
    assert heartbeat["metadata"]["task_kinds"]==["curation_stage"]
    assert heartbeat["model_revisions"]["llm_large"]["provider"]=="stl-managed"
    invocation=next(payload for url,payload in server.calls if url.endswith("model/"))
    assert invocation["lease_token"]==claimed["lease"]["lease_token"]
    assert len(invocation["input_hash"])==64
    completion=next(payload for url,payload in server.calls if url.endswith("complete/"))
    assert completion["result"]["artifact_id"]==claimed["job"]["artifact_id"]
    assert completion["result"]["output_hash"]=="fixture-output-hash"
    assert model.calls==[] and "w"*40 not in str(server.calls)


def test_remote_worker_rejects_legacy_producers_without_any_model_call():
    for claimed in (_claim_payload(),_library_synthesis_payload()):
        server=_ServerClient(claimed);model=_ModelClient({})
        worker=RemoteAIWorkerClient(_config(),server_client=server,model_client=model,sleep=lambda seconds:None)
        with pytest.raises(RemoteWorkerClientError) as raised: worker.run_once()
        assert raised.value.code=="knowledge_producer_retired" and not raised.value.retryable
        assert not model.calls
        release=next(payload for url,payload in server.calls if url.endswith("release/"))
        assert release["retry"] is False
        assert not any(url.endswith("complete/") for url,_ in server.calls)


def test_remote_worker_offline_poll_is_idle_and_does_not_call_model():
    server = _ServerClient()
    model = _ModelClient({})
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=server,
        model_client=model,
        sleep=lambda _seconds: None,
    )

    assert worker.run_once() == "idle"
    assert model.calls == []


def test_remote_worker_does_not_repeat_idle_heartbeat_on_every_claim_poll():
    server = _ServerClient()
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=server,
        model_client=_ModelClient({}),
        sleep=lambda _seconds: None,
    )

    assert worker.run_once() == "idle"
    assert worker.run_once() == "idle"
    assert sum(url.endswith("heartbeat/") for url, _payload in server.calls) == 1
    assert sum(url.endswith("claim/") for url, _payload in server.calls) == 2


def test_remote_worker_wan_failure_is_bounded_and_run_forever_keeps_polling():
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=_UnavailableServerClient(),
        model_client=_ModelClient({}),
        sleep=lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt()),
    )

    with pytest.raises(RemoteWorkerClientError) as raised:
        worker.run_once()
    assert raised.value.code == "server_unavailable"

    with pytest.raises(KeyboardInterrupt):
        worker.run_forever()


def test_remote_worker_preserves_transient_transport_failure_retry(monkeypatch):
    server=_ServerClient(_curation_payload())
    worker=RemoteAIWorkerClient(_config(),server_client=server,model_client=_ModelClient({}),sleep=lambda seconds:None)
    def unavailable(*args,**kwargs):
        raise RemoteWorkerClientError("server_unavailable","fixture transport failure",retryable=True)
    monkeypatch.setattr("common.docetl_map.run_map",unavailable)
    with pytest.raises(RemoteWorkerClientError) as raised: worker.run_once()
    assert raised.value.code=="server_unavailable"
    release=next(payload for url,payload in server.calls if url.endswith("release/"))
    assert release["retry"] is True and release["error_code"]=="server_unavailable"
    assert not any(url.endswith("complete/") for url,_ in server.calls)


def test_remote_worker_keeps_heartbeat_and_lease_alive_during_managed_stage(monkeypatch):
    server=_ServerClient(_curation_payload())
    model=_ModelClient({})
    worker=RemoteAIWorkerClient(_config(keepalive_seconds=1),server_client=server,model_client=model,sleep=lambda seconds:None)
    def delayed(*args):
        time.sleep(1.1)
        return _map_fixture(*args)
    monkeypatch.setattr("common.docetl_map.run_map",delayed)
    assert worker.run_once()=="completed"
    assert sum(url.endswith("heartbeat/") for url,_ in server.calls)>=2
    assert sum(url.endswith("renew/") for url,_ in server.calls)>=2
    assert model.calls==[]


def test_remote_worker_completion_id_is_stable_for_lease_replay():
    server = _ServerClient()
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=server,
        model_client=_ModelClient({}),
        sleep=lambda _seconds: None,
    )
    lease = _claim_payload()["lease"]
    result = {"claims": []}

    worker.complete(lease, result)
    worker.complete(lease, result)

    completion_ids = [
        payload["completion_id"]
        for url, payload in server.calls
        if url.endswith("complete/")
    ]
    assert len(completion_ids) == 2
    assert completion_ids[0] == completion_ids[1]


def _curation_payload():
    value=_claim_payload()
    value["job"]={"task_kind":"curation_stage","transport":"stl-managed","artifact_id":"fixture-artifact",
        "runtime":{"provider":"openai_compatible","model":"fixture","model_revision":"fixture-v1"},
        "prompt":"按原文范围分析","input":"隔离测试原文","output_schema":{"type":"object","properties":{"summary":{"type":"string"}}}}
    return value

def _map_fixture(model,prompt,text,schema,invoke):
    assert model=="fixture" and schema["type"]=="object"
    return invoke(prompt+"\n<source_data>"+text+"</source_data>")
