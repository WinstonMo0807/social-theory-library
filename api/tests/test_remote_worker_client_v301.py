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


def test_remote_worker_requires_https_for_non_local_server():
    with pytest.raises(RemoteWorkerClientError) as raised:
        _config(server_url="http://books.example/api/capability-worker").validated()

    assert raised.value.code == "https_required"


def test_remote_worker_enforces_rate_safe_poll_floor():
    assert _config(poll_seconds=1).validated().poll_seconds == 10


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
