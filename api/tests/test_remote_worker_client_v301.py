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


def test_remote_worker_environment_can_opt_into_library_synthesis(monkeypatch):
    monkeypatch.setenv("STL_WORKER_SERVER_URL", "https://books.example/api/capability-worker")
    monkeypatch.setenv("STL_WORKER_TOKEN", "w" * 40)
    monkeypatch.setenv("STL_WORKER_MODEL", "qwen-library:14b")
    monkeypatch.setenv("STL_WORKER_MODEL_REVISION", "sha256-library-model")
    monkeypatch.setenv("STL_WORKER_CAPABILITIES", "llm_large")
    monkeypatch.setenv("STL_WORKER_TASK_KINDS", "library_synthesis")

    config = RemoteWorkerClientConfig.from_environment()

    assert config.capabilities == ("llm_large",)
    assert config.task_kinds == ("library_synthesis",)


def test_remote_worker_heartbeats_pulls_runs_ollama_and_completes_claim():
    server = _ServerClient(_claim_payload())
    model = _ModelClient(
        {
            "message": {
                "content": json.dumps(
                    {
                        "claims": [
                            {
                                "proposition": "制度保障薄弱时，失业可能加剧贫困。",
                                "subject": "失业",
                                "predicate": "加剧",
                                "object": "贫困",
                                "polarity": "positive",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        }
    )
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=server,
        model_client=model,
        sleep=lambda _seconds: None,
    )

    result = worker.run_once()

    assert result == "completed"
    heartbeat = next(payload for url, payload in server.calls if url.endswith("heartbeat/"))
    assert heartbeat["capabilities"] == ["llm_small"]
    assert heartbeat["model_revisions"]["llm_small"] == {
        "provider": "ollama",
        "model": "qwen-claim:8b",
        "revision": "sha256-model-revision",
    }
    complete = next(payload for url, payload in server.calls if url.endswith("complete/"))
    assert complete["result"]["claims"][0]["polarity"] == "positive"
    assert complete["result"]["provider"] == "ollama"
    assert model.calls[0][0].endswith("/api/chat")
    assert model.calls[0][1]["json"]["format"] == _claim_payload()["job"]["output_schema"]
    assert "w" * 40 not in str(server.calls)


def test_remote_worker_declares_and_executes_structured_library_synthesis():
    claimed = _library_synthesis_payload()
    evidence_ids = [row["id"] for row in claimed["job"]["input"]["evidence"]]
    server = _ServerClient(claimed)
    model = _ModelClient(
        {
            "message": {
                "content": json.dumps(
                    {
                        "candidate": {
                            "value": "馆藏原文把失业加剧贫困限定在制度保障薄弱的情境。",
                            "evidence_span_ids": evidence_ids,
                            "rationale": "导论和结论共同支持。",
                        }
                    },
                    ensure_ascii=False,
                )
            }
        }
    )
    worker = RemoteAIWorkerClient(
        _config(
            capabilities=("llm_large",),
            task_kinds=("library_synthesis",),
        ),
        server_client=server,
        model_client=model,
        sleep=lambda _seconds: None,
    )

    assert worker.run_once() == "completed"
    heartbeat = next(payload for url, payload in server.calls if url.endswith("heartbeat/"))
    assert heartbeat["capabilities"] == ["llm_large"]
    assert heartbeat["metadata"]["task_kinds"] == ["library_synthesis"]
    assert heartbeat["metadata"]["task_profiles"] == {
        "library_synthesis": ["library_synthesis"]
    }
    completed = next(payload for url, payload in server.calls if url.endswith("complete/"))
    assert completed["result"]["candidate"]["evidence_span_ids"] == evidence_ids
    assert completed["result"]["provider"] == "ollama"
    model_prompt = model.calls[0][1]["json"]["messages"][1]["content"]
    assert claimed["job"]["input"]["evidence_pack_id"] in model_prompt
    assert all(evidence_id in model_prompt for evidence_id in evidence_ids)


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


def test_remote_worker_releases_retryable_model_schema_failure():
    server = _ServerClient(_claim_payload())
    model = _ModelClient({"message": {"content": "not json"}})
    worker = RemoteAIWorkerClient(
        _config(),
        server_client=server,
        model_client=model,
        sleep=lambda _seconds: None,
    )

    with pytest.raises(RemoteWorkerClientError) as raised:
        worker.run_once()

    assert raised.value.code == "model_invalid_json"
    release = next(payload for url, payload in server.calls if url.endswith("release/"))
    assert release["retry"] is True
    assert release["error_code"] == "model_invalid_json"


def test_remote_worker_keeps_heartbeat_and_lease_alive_during_inference():
    server = _ServerClient(_claim_payload())
    model = _SlowModelClient({"message": {"content": '{"claims": []}'}})
    worker = RemoteAIWorkerClient(
        _config(keepalive_seconds=1),
        server_client=server,
        model_client=model,
        sleep=lambda _seconds: None,
    )

    assert worker.run_once() == "completed"
    assert sum(url.endswith("heartbeat/") for url, _payload in server.calls) >= 2
    assert sum(url.endswith("renew/") for url, _payload in server.calls) >= 2


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
