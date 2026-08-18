from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from django.conf import settings


class SemanticRerankerError(RuntimeError):
    """A bounded, recoverable failure from the optional reranker service."""


@dataclass(frozen=True, slots=True)
class RerankerConfig:
    provider: str
    url: str
    model: str
    api_key: str
    allowed_hosts: tuple[str, ...]
    timeout_seconds: int
    max_text_chars: int


def current_reranker_config() -> RerankerConfig:
    raw_hosts = getattr(
        settings,
        "SEMANTIC_SEARCH_V2_RERANK_ALLOWED_HOSTS",
        "reranker,localhost,127.0.0.1",
    )
    values = raw_hosts.split(",") if isinstance(raw_hosts, str) else raw_hosts
    return RerankerConfig(
        provider=str(
            getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_PROVIDER", "rules")
        ).strip().casefold(),
        url=str(getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_URL", "")).strip(),
        model=str(
            getattr(
                settings,
                "SEMANTIC_SEARCH_V2_RERANK_MODEL",
                "Qwen/Qwen3-Reranker-0.6B",
            )
        ).strip(),
        api_key=str(
            getattr(settings, "SEMANTIC_SEARCH_V2_RERANK_API_KEY", "")
        ),
        allowed_hosts=tuple(
            str(value).strip().casefold()
            for value in values
            if str(value).strip()
        ),
        timeout_seconds=max(
            2,
            min(
                int(
                    getattr(
                        settings,
                        "SEMANTIC_SEARCH_V2_RERANK_TIMEOUT_SECONDS",
                        15,
                    )
                ),
                60,
            ),
        ),
        max_text_chars=max(
            500,
            min(
                int(
                    getattr(
                        settings,
                        "SEMANTIC_SEARCH_V2_RERANK_MAX_TEXT_CHARS",
                        4000,
                    )
                ),
                8000,
            ),
        ),
    )


def _validate_endpoint(config: RerankerConfig) -> None:
    parsed = urlparse(config.url)
    hostname = (parsed.hostname or "").casefold()
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise SemanticRerankerError("重排服务地址必须是明确的 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SemanticRerankerError("重排服务地址不能包含凭据、查询参数或片段。")
    if hostname not in config.allowed_hosts:
        raise SemanticRerankerError("重排服务主机不在允许列表中。")


def _document_text(row: dict, max_chars: int, *, include_context: bool) -> str:
    chunk = row["chunk"]
    heading = "\n".join(
        value
        for value in (
            str(getattr(chunk.asset.edition.work, "title", "") or ""),
            str(getattr(chunk, "chapter_title", "") or ""),
            str(getattr(chunk, "section_title", "") or ""),
        )
        if value
    )
    body_parts = [str(getattr(chunk, "original_text", "") or "")]
    if include_context:
        body_parts = [
            str(getattr(chunk, "context_before", "") or ""),
            *body_parts,
            str(getattr(chunk, "context_after", "") or ""),
        ]
    body = "\n".join(value for value in body_parts if value)
    return f"{heading}\n{body}".strip()[:max_chars]


def rerank_candidates(
    query: str,
    rows: list[dict],
    *,
    top_k: int,
    config: RerankerConfig | None = None,
    include_context: bool = True,
) -> dict:
    """Rerank a small candidate set through a persistent local HTTP service.

    The service uses the common ``/rerank`` contract accepted by several local
    model servers.  This process never loads model weights and never sends a
    full PDF.  Callers must catch ``SemanticRerankerError`` and keep the RRF
    order so search remains usable when the optional service is unavailable.
    """

    config = config or current_reranker_config()
    if config.provider != "local_http":
        raise SemanticRerankerError("当前没有启用本地 HTTP 重排服务。")
    if not config.url or not config.model:
        raise SemanticRerankerError("本地重排服务尚未完整配置。")
    _validate_endpoint(config)
    bounded_count = min(max(0, int(top_k)), 64, len(rows))
    if not bounded_count:
        return {
            "rows": rows,
            "applied": False,
            "provider": config.provider,
            "model": config.model,
        }

    candidates = rows[:bounded_count]
    documents: list[str] = []
    remaining_chars = 96_000
    for row in candidates:
        value = _document_text(
            row,
            min(config.max_text_chars, remaining_chars),
            include_context=include_context,
        )
        documents.append(value)
        remaining_chars = max(0, remaining_chars - len(value))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "SocialTheoryLibrary/2.7 viewpoint-reranker",
    }
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    try:
        response = httpx.post(
            config.url,
            headers=headers,
            json={
                "model": config.model,
                "query": str(query)[:1200],
                "documents": documents,
                "top_n": bounded_count,
                "return_documents": False,
            },
            timeout=config.timeout_seconds,
            follow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            raise SemanticRerankerError("重排服务返回了未授权的重定向。")
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise SemanticRerankerError("重排服务响应超过安全大小限制。")
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        raise SemanticRerankerError("本地重排服务暂时不可用。") from exc

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise SemanticRerankerError("重排服务返回格式不符合约定。")
    ordered: list[dict] = []
    used: set[int] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("index"))
            score = float(item.get("relevance_score"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= bounded_count or index in used:
            continue
        row = candidates[index]
        row["model_rerank_score"] = score
        row["reranker_score"] = score
        row["model_rerank_rank"] = len(ordered) + 1
        ordered.append(row)
        used.add(index)
    if not ordered:
        raise SemanticRerankerError("重排服务没有返回可用的候选次序。")
    ordered.extend(candidates[index] for index in range(bounded_count) if index not in used)
    ordered.extend(rows[bounded_count:])
    return {
        "rows": ordered,
        "applied": True,
        "provider": config.provider,
        "model": config.model,
    }
