"""Runnable pull worker for bounded, evidence-only local GPU tasks.

The default remains claim extraction with ``llm_small``.  An operator may
explicitly declare the ``llm_large`` and ``library_synthesis`` protocol through
environment configuration.  The worker never connects directly to PostgreSQL.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
import re
import socket
import sys
import threading
import time
from typing import Any, Callable
from urllib.parse import urlsplit
import uuid

import httpx


WORKER_VERSION = "3.0.2"
SUPPORTED_PROVIDERS = {"ollama", "openai_compatible", "vllm"}
SUPPORTED_CAPABILITIES = {"llm_small", "llm_large"}
SUPPORTED_TASK_KINDS = {"claim_extraction", "library_synthesis"}
TASK_CAPABILITY = {
    "claim_extraction": "llm_small",
    "library_synthesis": "llm_large",
}


def _environment_list(name: str, default: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip().casefold()
            for value in os.getenv(name, default).split(",")
            if value.strip()
        )
    )


class RemoteWorkerClientError(RuntimeError):
    def __init__(
        self,
        code: str,
        detail: str,
        *,
        retryable: bool = True,
        retry_after_seconds: int = 0,
    ):
        super().__init__(detail)
        self.code = str(code or "worker_error")[:120]
        self.retryable = retryable
        self.retry_after_seconds = max(0, int(retry_after_seconds or 0))


@dataclass(frozen=True, slots=True)
class RemoteWorkerClientConfig:
    server_url: str
    worker_token: str
    executor_id: str
    provider: str
    model_url: str
    model: str
    model_revision: str
    capabilities: tuple[str, ...] = ("llm_small",)
    task_kinds: tuple[str, ...] = ("claim_extraction",)
    model_api_key: str = ""
    display_name: str = "RTX 4070 worker"
    gpu_name: str = "RTX 4070"
    concurrency: int = 1
    request_timeout_seconds: int = 180
    poll_seconds: int = 10
    keepalive_seconds: int = 30
    allow_insecure_server_http: bool = False

    @classmethod
    def from_environment(cls) -> "RemoteWorkerClientConfig":
        return cls(
            server_url=os.getenv("STL_WORKER_SERVER_URL", ""),
            worker_token=os.getenv("STL_WORKER_TOKEN", ""),
            executor_id=os.getenv("STL_WORKER_EXECUTOR_ID", f"remote-gpu:{socket.gethostname()}"),
            provider=os.getenv("STL_WORKER_PROVIDER", "ollama"),
            model_url=os.getenv("STL_WORKER_MODEL_URL", "http://127.0.0.1:11434"),
            model=os.getenv("STL_WORKER_MODEL", ""),
            model_revision=os.getenv("STL_WORKER_MODEL_REVISION", ""),
            capabilities=_environment_list("STL_WORKER_CAPABILITIES", "llm_small"),
            task_kinds=_environment_list("STL_WORKER_TASK_KINDS", "claim_extraction"),
            model_api_key=os.getenv("STL_WORKER_MODEL_API_KEY", ""),
            display_name=os.getenv("STL_WORKER_DISPLAY_NAME", "RTX 4070 worker"),
            gpu_name=os.getenv("STL_WORKER_GPU_NAME", "RTX 4070"),
            concurrency=int(os.getenv("STL_WORKER_CONCURRENCY", "1")),
            request_timeout_seconds=int(os.getenv("STL_WORKER_MODEL_TIMEOUT_SECONDS", "180")),
            poll_seconds=int(os.getenv("STL_WORKER_POLL_SECONDS", "10")),
            keepalive_seconds=int(os.getenv("STL_WORKER_KEEPALIVE_SECONDS", "30")),
            allow_insecure_server_http=os.getenv("STL_WORKER_ALLOW_HTTP", "false").strip().casefold() == "true",
        ).validated()

    def validated(self) -> "RemoteWorkerClientConfig":
        server_url = str(self.server_url or "").strip().rstrip("/")
        parsed = urlsplit(server_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise RemoteWorkerClientError("invalid_server_url", "STL_WORKER_SERVER_URL 必须是完整 URL。", retryable=False)
        if parsed.scheme != "https" and not (
            self.allow_insecure_server_http
            and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        ):
            raise RemoteWorkerClientError("https_required", "远程 Worker 服务端必须使用 HTTPS。", retryable=False)
        if len(str(self.worker_token or "")) < 32:
            raise RemoteWorkerClientError("worker_token_missing", "STL_WORKER_TOKEN 至少需要 32 个字符。", retryable=False)
        executor_id = str(self.executor_id or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", executor_id):
            raise RemoteWorkerClientError("executor_id_invalid", "STL_WORKER_EXECUTOR_ID 格式无效。", retryable=False)
        provider = str(self.provider or "").strip().casefold()
        if provider not in SUPPORTED_PROVIDERS:
            raise RemoteWorkerClientError("provider_unsupported", "本地模型 Provider 不受支持。", retryable=False)
        model_url = str(self.model_url or "").strip().rstrip("/")
        model_parsed = urlsplit(model_url)
        if model_parsed.scheme not in {"http", "https"} or not model_parsed.hostname:
            raise RemoteWorkerClientError("invalid_model_url", "STL_WORKER_MODEL_URL 必须是完整 URL。", retryable=False)
        if not str(self.model or "").strip() or not str(self.model_revision or "").strip():
            raise RemoteWorkerClientError("model_identity_missing", "模型名称与不可变 revision 都必须配置。", retryable=False)
        capabilities = tuple(dict.fromkeys(str(value or "").strip().casefold() for value in self.capabilities))
        task_kinds = tuple(dict.fromkeys(str(value or "").strip().casefold() for value in self.task_kinds))
        if not capabilities or any(value not in SUPPORTED_CAPABILITIES for value in capabilities):
            raise RemoteWorkerClientError("capability_unsupported", "Worker capability 配置无效。", retryable=False)
        if not task_kinds or any(value not in SUPPORTED_TASK_KINDS for value in task_kinds):
            raise RemoteWorkerClientError("task_kind_unsupported", "Worker task kind 配置无效。", retryable=False)
        for task_kind in task_kinds:
            if TASK_CAPABILITY[task_kind] not in capabilities:
                raise RemoteWorkerClientError(
                    "task_capability_mismatch",
                    f"{task_kind} 需要 {TASK_CAPABILITY[task_kind]} capability。",
                    retryable=False,
                )
        if not 1 <= int(self.concurrency) <= 16:
            raise RemoteWorkerClientError("invalid_concurrency", "Worker concurrency 必须在 1 到 16 之间。", retryable=False)
        return RemoteWorkerClientConfig(
            server_url=server_url,
            worker_token=str(self.worker_token),
            executor_id=executor_id,
            provider=provider,
            model_url=model_url,
            model=str(self.model).strip()[:240],
            model_revision=str(self.model_revision).strip()[:160],
            capabilities=capabilities,
            task_kinds=task_kinds,
            model_api_key=str(self.model_api_key or ""),
            display_name=str(self.display_name or "")[:240],
            gpu_name=str(self.gpu_name or "")[:160],
            concurrency=int(self.concurrency),
            request_timeout_seconds=max(10, min(int(self.request_timeout_seconds), 600)),
            poll_seconds=max(10, min(int(self.poll_seconds), 60)),
            keepalive_seconds=max(1, min(int(self.keepalive_seconds), 60)),
            allow_insecure_server_http=bool(self.allow_insecure_server_http),
        )


def _response_json(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RemoteWorkerClientError("invalid_response", "服务响应不是 JSON。") from exc
    if not isinstance(payload, dict):
        raise RemoteWorkerClientError("invalid_response", "服务响应必须是 JSON 对象。")
    return payload


def _json_content(value: object) -> dict[str, Any]:
    text = str(value or "").strip()
    if text.startswith("```"):
        text = re_sub_code_fence(text)
    try:
        payload = json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RemoteWorkerClientError("model_invalid_json", "模型没有返回有效 JSON。") from exc
    if not isinstance(payload, dict):
        raise RemoteWorkerClientError("model_invalid_json", "模型结果必须是 JSON 对象。")
    return payload


def re_sub_code_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


class RemoteAIWorkerClient:
    def __init__(
        self,
        config: RemoteWorkerClientConfig,
        *,
        server_client: httpx.Client | None = None,
        model_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config.validated()
        self.server_client = server_client or httpx.Client(
            timeout=30,
            headers={"X-Library-Worker-Token": self.config.worker_token},
            trust_env=False,
        )
        self.model_client = model_client or httpx.Client(
            timeout=self.config.request_timeout_seconds,
            trust_env=False,
        )
        self.sleep = sleep
        self._owns_server_client = server_client is None
        self._owns_model_client = model_client is None
        self._last_heartbeat_at = 0.0
        self._poll_after_seconds = max(10, self.config.poll_seconds)

    def close(self) -> None:
        if self._owns_server_client:
            self.server_client.close()
        if self._owns_model_client:
            self.model_client.close()

    def _server_post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            response = self.server_client.post(
                f"{self.config.server_url}/{path.lstrip('/')}",
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise RemoteWorkerClientError(
                "server_timeout",
                "Worker 服务端响应超时，将保留任务并稍后重试。",
            ) from exc
        except httpx.RequestError as exc:
            raise RemoteWorkerClientError(
                "server_unavailable",
                "Worker 服务端暂时不可连接，将保持运行并稍后重试。",
            ) from exc
        if response.status_code >= 400:
            detail = ""
            response_code = ""
            try:
                response_payload = response.json()
                detail = str(response_payload.get("detail") or "")
                response_code = str(response_payload.get("code") or "")
            except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
                detail = ""
            retry_after = 0
            try:
                retry_after = int(response.headers.get("Retry-After") or 0)
            except (AttributeError, TypeError, ValueError):
                retry_after = 0
            raise RemoteWorkerClientError(
                response_code or f"server_http_{response.status_code}",
                detail or f"Worker 服务端返回 HTTP {response.status_code}。",
                retryable=response.status_code >= 500 or response.status_code in {408, 409, 429},
                retry_after_seconds=retry_after,
            )
        return response

    def heartbeat(self) -> dict[str, Any]:
        model_revision = {
            "provider": self.config.provider,
            "model": self.config.model,
            "revision": self.config.model_revision,
        }
        response = self._server_post(
            "heartbeat/",
            {
                "executor_id": self.config.executor_id,
                "display_name": self.config.display_name,
                "capabilities": list(self.config.capabilities),
                "model_revisions": {
                    capability: dict(model_revision)
                    for capability in self.config.capabilities
                },
                "concurrency": self.config.concurrency,
                "metadata": {
                    "worker_version": WORKER_VERSION,
                    "runtime": self.config.provider,
                    "gpu_name": self.config.gpu_name,
                    "host_label": socket.gethostname(),
                    "task_kinds": list(self.config.task_kinds),
                    "task_profiles": {
                        task_kind: [task_kind]
                        for task_kind in self.config.task_kinds
                    },
                },
            },
        )
        payload = _response_json(response)
        self._last_heartbeat_at = time.monotonic()
        try:
            server_poll = int(payload.get("poll_after_seconds") or 0)
        except (TypeError, ValueError):
            server_poll = 0
        self._poll_after_seconds = max(10, self.config.poll_seconds, server_poll)
        return payload

    def claim(self) -> dict[str, Any] | None:
        response = self._server_post(
            "claim/",
            {"executor_id": self.config.executor_id},
        )
        if response.status_code == 204:
            return None
        return _response_json(response)

    def renew(self, lease: dict[str, Any]) -> None:
        self._server_post(
            f"demands/{lease['demand_id']}/renew/",
            {
                "executor_id": self.config.executor_id,
                "lease_token": lease["lease_token"],
            },
        )

    def complete(self, lease: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        completion_id = "worker-" + str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                ":".join(
                    (
                        self.config.executor_id,
                        str(lease["demand_id"]),
                        str(lease["lease_token"]),
                    )
                ),
            )
        )
        response = self._server_post(
            f"demands/{lease['demand_id']}/complete/",
            {
                "executor_id": self.config.executor_id,
                "lease_token": lease["lease_token"],
                "completion_id": completion_id,
                "result": result,
            },
        )
        return _response_json(response)

    def release(self, lease: dict[str, Any], error: RemoteWorkerClientError) -> None:
        self._server_post(
            f"demands/{lease['demand_id']}/release/",
            {
                "executor_id": self.config.executor_id,
                "lease_token": lease["lease_token"],
                "error_code": error.code,
                "error_message": str(error)[:1000],
                "retry": error.retryable,
                "retry_after_seconds": 60 if error.retryable else 0,
            },
        )

    def _model_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.config.model_api_key:
            headers["Authorization"] = f"Bearer {self.config.model_api_key}"
        return headers

    def _model_post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        try:
            return self.model_client.post(
                f"{self.config.model_url}/{path.lstrip('/')}",
                headers=self._model_headers(),
                json=payload,
            )
        except httpx.TimeoutException as exc:
            raise RemoteWorkerClientError("model_timeout", "本地模型响应超时。") from exc
        except httpx.RequestError as exc:
            raise RemoteWorkerClientError("model_unavailable", "本地模型当前不可连接。") from exc

    def run_model(self, job: dict[str, Any]) -> dict[str, Any]:
        task_kind = str(job.get("task_kind") or "").strip()
        if task_kind not in self.config.task_kinds:
            raise RemoteWorkerClientError("unsupported_task_kind", "Worker 未声明该 task kind。", retryable=False)
        prompt = dict(job.get("prompt") or {})
        source = dict(job.get("input") or {})
        schema = dict(job.get("output_schema") or {})
        system_prompt = str(prompt.get("content") or "")
        if not system_prompt or not schema:
            raise RemoteWorkerClientError("job_payload_invalid", "任务缺少 Prompt 或输出 schema。", retryable=False)
        if task_kind == "claim_extraction":
            document_text = str(source.get("text") or "")
            if not document_text:
                raise RemoteWorkerClientError("job_payload_invalid", "任务缺少 EvidenceSpan。", retryable=False)
            user_prompt = (
                "只分析以下馆藏原文。严格按给定 JSON schema 返回，不使用外部常识。\n\n"
                f"{document_text}"
            )
        else:
            evidence = source.get("evidence")
            if not isinstance(evidence, list) or not 2 <= len(evidence) <= 12:
                raise RemoteWorkerClientError("job_payload_invalid", "Library Synthesis 缺少有界的 EvidencePack。", retryable=False)
            evidence_ids = {
                str(row.get("id") or "")
                for row in evidence
                if isinstance(row, dict) and str(row.get("id") or "") and str(row.get("text") or "").strip()
            }
            if len(evidence_ids) != len(evidence) or not str(source.get("evidence_pack_id") or ""):
                raise RemoteWorkerClientError("job_payload_invalid", "EvidencePack 缺少原文或稳定标识。", retryable=False)
            user_prompt = (
                "只使用下列 EvidencePack 馆藏原文生成候选。"
                "evidence_span_ids 只能引用列出的 id，不得使用外部常识。"
                "严格按给定 JSON schema 返回。\n\n"
                + json.dumps(
                    {
                        "evidence_pack_id": source["evidence_pack_id"],
                        "requested_field": source.get("requested_field"),
                        "evidence": evidence,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        if self.config.provider == "ollama":
            response = self._model_post(
                "api/chat",
                {
                    "model": self.config.model,
                    "stream": False,
                    "format": schema,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {"temperature": 0},
                },
            )
            if response.status_code >= 400:
                raise RemoteWorkerClientError("model_http_error", f"本地模型返回 HTTP {response.status_code}。")
            payload = _response_json(response)
            result = _json_content((payload.get("message") or {}).get("content"))
        else:
            response = self._model_post(
                "v1/chat/completions",
                {
                    "model": self.config.model,
                    "temperature": 0,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            if response.status_code >= 400:
                raise RemoteWorkerClientError("model_http_error", f"本地模型返回 HTTP {response.status_code}。")
            payload = _response_json(response)
            choices = payload.get("choices") or []
            content = ((choices[0].get("message") or {}).get("content") if choices and isinstance(choices[0], dict) else "")
            result = _json_content(content)
        identity = {
            "provider": self.config.provider,
            "model": self.config.model,
            "model_revision": self.config.model_revision,
        }
        if task_kind == "claim_extraction":
            claims = result.get("claims")
            if not isinstance(claims, list):
                raise RemoteWorkerClientError("model_schema_invalid", "模型结果缺少 claims 数组。")
            max_claims = max(1, min(int((job.get("limits") or {}).get("max_claims") or 24), 24))
            if len(claims) > max_claims:
                raise RemoteWorkerClientError("model_schema_invalid", "模型返回的 Claim 数量超过任务上限。")
            return {**identity, "claims": claims}
        candidate = result.get("candidate")
        if not isinstance(candidate, dict):
            raise RemoteWorkerClientError("model_schema_invalid", "模型结果缺少 candidate 对象。")
        value = " ".join(str(candidate.get("value") or "").split())
        rationale = " ".join(str(candidate.get("rationale") or "").split())
        selected_ids = [str(value) for value in candidate.get("evidence_span_ids") or [] if str(value)]
        allowed_ids = {str(row["id"]) for row in source["evidence"]}
        max_output_chars = max(1, min(int((job.get("limits") or {}).get("max_output_chars") or 12_000), 12_000))
        if (
            not value
            or len(value) > max_output_chars
            or not selected_ids
            or len(selected_ids) > 12
            or any(value not in allowed_ids for value in selected_ids)
        ):
            raise RemoteWorkerClientError("model_schema_invalid", "Library Synthesis 结果未受 EvidencePack 约束。")
        return {
            **identity,
            "candidate": {
                "value": value,
                "evidence_span_ids": selected_ids,
                "rationale": rationale,
            },
        }

    def run_once(self) -> str:
        if (
            self._last_heartbeat_at <= 0
            or time.monotonic() - self._last_heartbeat_at >= 30
        ):
            self.heartbeat()
        claimed = self.claim()
        if claimed is None:
            return "idle"
        lease = claimed.get("lease") if isinstance(claimed, dict) else None
        job = claimed.get("job") if isinstance(claimed, dict) else None
        if not isinstance(lease, dict) or not isinstance(job, dict):
            raise RemoteWorkerClientError("claim_response_invalid", "领取响应缺少 lease 或 job。")
        keepalive_stop = threading.Event()
        keepalive_errors: list[RemoteWorkerClientError] = []
        keepalive_thread: threading.Thread | None = None

        def keepalive() -> None:
            while not keepalive_stop.wait(self.config.keepalive_seconds):
                try:
                    # Heartbeat TTL is shorter than the maximum model timeout.
                    # Refresh both executor liveness and the demand lease while
                    # the separate model HTTP client is blocked on inference.
                    self.heartbeat()
                    self.renew(lease)
                except RemoteWorkerClientError as exc:
                    keepalive_errors.append(exc)
                    return

        try:
            self.renew(lease)
            keepalive_thread = threading.Thread(
                target=keepalive,
                name="stl-worker-lease-keepalive",
                daemon=True,
            )
            keepalive_thread.start()
            result = self.run_model(job)
            keepalive_stop.set()
            keepalive_thread.join(timeout=5)
            if keepalive_errors:
                raise RemoteWorkerClientError(
                    "keepalive_failed",
                    "模型执行期间未能续期 Worker heartbeat 或任务租约。",
                ) from keepalive_errors[0]
            self.complete(lease, result)
        except RemoteWorkerClientError as exc:
            keepalive_stop.set()
            if keepalive_thread is not None:
                keepalive_thread.join(timeout=5)
            try:
                self.release(lease, exc)
            except RemoteWorkerClientError:
                pass
            raise
        return "completed"

    def run_forever(self) -> None:
        while True:
            try:
                state = self.run_once()
                if state == "completed":
                    print("remote evidence task completed", flush=True)
                    continue
            except RemoteWorkerClientError as exc:
                print(f"worker degraded: {exc.code}", file=sys.stderr, flush=True)
                if exc.retry_after_seconds:
                    self._poll_after_seconds = max(
                        self._poll_after_seconds,
                        min(exc.retry_after_seconds, 300),
                    )
            self.sleep(self._poll_after_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Social Theory Library remote AI pull worker")
    parser.add_argument("--once", action="store_true", help="Heartbeat and process at most one demand")
    args = parser.parse_args(argv)
    try:
        config = RemoteWorkerClientConfig.from_environment()
        worker = RemoteAIWorkerClient(config)
    except RemoteWorkerClientError as exc:
        print(f"worker configuration error: {exc.code}", file=sys.stderr)
        return 2
    try:
        if args.once:
            print(worker.run_once(), flush=True)
        else:
            worker.run_forever()
    except KeyboardInterrupt:
        return 0
    except RemoteWorkerClientError as exc:
        print(f"worker failed: {exc.code}", file=sys.stderr)
        return 1
    finally:
        worker.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
