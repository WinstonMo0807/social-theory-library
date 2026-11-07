"""Allowlisted client for the shared offline service; Django never loads weights."""
from __future__ import annotations

import math
from urllib.parse import urlsplit

import httpx
from django.conf import settings


class DiscoveryInferenceError(RuntimeError):
    def __init__(self, code: str, message: str = "本地检索模型暂不可用。"):
        self.code = code
        super().__init__(message)


def _call(path: str, payload: dict | None = None, *, timeout_seconds: int | None = None,
          max_response_bytes: int = 2_000_000, transport: httpx.BaseTransport | None = None,
          allow_unready_health: bool = False) -> dict:
    base = str(getattr(settings, "DISCOVERY_INFERENCE_URL", "http://discovery-inference:8091")).rstrip("/")
    allowed = str(getattr(settings, "DISCOVERY_INFERENCE_ALLOWED_HOSTS", "discovery-inference,127.0.0.1,localhost")).split(",")
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in {item.strip() for item in allowed}
            or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise DiscoveryInferenceError("invalid_endpoint", "本地检索模型地址不在允许范围内。")
    timeout = (timeout_seconds if timeout_seconds is not None else
               min(250, max(5, int(getattr(settings, "DISCOVERY_INFERENCE_TIMEOUT_SECONDS", 130)))))
    try:
        if transport is None and (path != "/health" or not allow_unready_health):
            from common.on_demand import ensure_service
            ensure_service("inference", url=base)
        # Never inherit a machine's outbound proxy for private library text.
        with httpx.Client(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(timeout, connect=3),
                          **({"transport": transport} if transport is not None else {})) as client:
            with client.stream("GET" if payload is None else "POST", base + path, json=payload) as response:
                body = bytearray()
                for part in response.iter_bytes():
                    body.extend(part)
                    if len(body) > max_response_bytes:
                        raise DiscoveryInferenceError("invalid_response", "本地模型响应超过大小限制。")
                import json
                result = json.loads(body)
                if response.status_code != 200:
                    # Only the maintenance screen may read an unready service's
                    # bounded health document. Indexing/inference remain fail-closed.
                    if (allow_unready_health and path == "/health" and payload is None
                            and response.status_code == 503 and isinstance(result, dict)
                            and result.get("manifest_ready") is False
                            and isinstance(result.get("models"), dict)):
                        return result
                    detail = result.get("detail", {}) if isinstance(result, dict) else {}
                    code = detail.get("code", "service_unavailable") if isinstance(detail, dict) else "invalid_request"
                    safe_codes = {"model_missing", "artifact_mismatch", "input_too_long", "inference_busy", "inference_timeout",
                                  "model_load_failed", "inference_failed", "model_mismatch", "generation_unavailable",
                                  "generation_mismatch", "deep_unavailable", "deep_pending", "context_unsupported",
                                  "token_budget", "too_many_chunks", "context_budget"}
                    raise DiscoveryInferenceError(code if code in safe_codes else "service_unavailable")
        if not isinstance(result, dict):
            raise DiscoveryInferenceError("invalid_response")
        return result
    except DiscoveryInferenceError:
        raise
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as exc:
        raise DiscoveryInferenceError("service_unavailable") from exc


def _identity(result: dict, expected: str = "") -> None:
    if not all(isinstance(result.get(key), str) and result[key] for key in ("model", "revision", "artifact_id")):
        raise DiscoveryInferenceError("invalid_response")
    if expected and result["artifact_id"] != expected:
        raise DiscoveryInferenceError("artifact_mismatch", "查询模型与索引模型不一致。")


def inference_health(*, allow_unready: bool = False) -> dict:
    return _call("/health", timeout_seconds=5, max_response_bytes=32_000,
                 allow_unready_health=allow_unready)


def normalize_texts(texts: list[str]) -> dict:
    result = _call("/normalize", {"texts": texts})
    if not isinstance(result.get("texts"), list) or len(result["texts"]) != len(texts) or not all(isinstance(item, str) for item in result["texts"]):
        raise DiscoveryInferenceError("invalid_response")
    return result


def chunk_text(text: str, title: str = "", max_tokens: int = 320, overlap_tokens: int = 40) -> dict:
    result = _call("/chunk", {"text": text, "title": title, "max_tokens": max_tokens, "overlap_tokens": overlap_tokens})
    _identity(result)
    chunks = result.get("chunks")
    if not isinstance(chunks, list) or len(chunks) > 512:
        raise DiscoveryInferenceError("invalid_response")
    covered = 0
    for chunk in chunks:
        try:
            start, end = chunk["start"], chunk["end"]
            valid = (isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text)
                     and start <= covered and end > covered and text[start:end] == chunk["text"]
                     and isinstance(chunk["normalized_text"], str) and isinstance(chunk["embedding_text"], str)
                     and 0 < chunk["token_count"] <= max_tokens and not chunk.get("truncated"))
        except (KeyError, TypeError):
            valid = False
        if not valid:
            raise DiscoveryInferenceError("invalid_response", "本地模型返回的原文分块定位不完整。")
        covered = end
    if text[covered:].strip():
        raise DiscoveryInferenceError("invalid_response", "本地模型遗漏了尾部文字。")
    return result


def embed_texts(texts: list[str], kind: str = "passage", expected_artifact: str = "", *,
                expected_dimensions: int | None = None,
                deep_generation: str = "", titles: list[str] | None = None,
                transport: httpx.BaseTransport | None = None) -> dict:
    if expected_dimensions is None:
        expected_dimensions = int(getattr(settings, "DISCOVERY_EMBEDDING_DIMENSIONS", 384))
    if not 1 <= expected_dimensions <= 4096:
        raise DiscoveryInferenceError("invalid_response", "向量维度配置不在允许范围内。")
    payload = {"texts": texts, "kind": kind, "expected_artifact": expected_artifact}
    if deep_generation:
        payload.update(generation=deep_generation, titles=titles)
    result = _call("/deep-embed" if deep_generation else "/embed", payload,
                   **({"transport": transport} if transport is not None else {}))
    _identity(result, expected_artifact)
    if deep_generation and (result.get("generation") != deep_generation or result.get("model") != "google/embeddinggemma-2"):
        raise DiscoveryInferenceError("artifact_mismatch", "深度向量响应不属于当前模型代次。")
    vectors = result.get("vectors")
    if (result.get("dimensions") != expected_dimensions or not isinstance(vectors, list) or len(vectors) != len(texts)
            or result.get("truncated") != [False] * len(texts)):
        raise DiscoveryInferenceError("invalid_response")
    for vector in vectors:
        if (not isinstance(vector, list) or len(vector) != expected_dimensions
                or any(not isinstance(number, (int, float)) or not math.isfinite(number) for number in vector)
                or not 0.995 < sum(number * number for number in vector) < 1.005):
            raise DiscoveryInferenceError("invalid_response", "本地模型返回的向量不符合约定。")
    return result


def rerank(query: str, documents: list[str], top_n: int = 20, expected_artifact: str = "", *, contexts=None) -> dict:
    payload = {"query": query, "documents": documents, "top_n": top_n, "expected_artifact": expected_artifact}
    if contexts is not None:
        payload["contexts"] = [{key: item[key] for key in ("before", "after")} for item in contexts]
    result = _call("/rerank", payload)
    if contexts is not None and result.get("context_policy") != "adjacent-evidence-v1":
        raise DiscoveryInferenceError("context_unsupported", "推理服务未执行指定上下文策略。")
    _identity(result, expected_artifact)
    values = result.get("results")
    if not isinstance(values, list) or len(values) != min(top_n, len(documents)):
        raise DiscoveryInferenceError("invalid_response")
    seen = set()
    for item in values:
        try:
            index, score = item["index"], item["relevance_score"]
            valid = (isinstance(index, int) and 0 <= index < len(documents) and index not in seen
                     and isinstance(score, (int, float)) and math.isfinite(score))
        except (TypeError, KeyError):
            valid = False
        if not valid:
            raise DiscoveryInferenceError("invalid_response")
        seen.add(index)
    return result
