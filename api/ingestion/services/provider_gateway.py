from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import timedelta
from hashlib import sha256
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from xml.etree.ElementTree import ParseError

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from catalog.models import DocumentType
from ingestion.models import SourceRecord, UploadItem

from .metadata import (
    Candidate,
    resolve_doi,
    resolve_google_books_isbn,
    resolve_grobid,
    resolve_isbn,
    resolve_openalex_doi,
    search_crossref_title,
    search_google_books_title,
    search_openalex_title,
    search_openlibrary_title,
)


Resolver = Callable[[], list[Candidate]]


def _stable_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(provider: str, operation: str, query: dict) -> str:
    payload = _stable_json({"provider": provider, "operation": operation, "query": query})
    return sha256(payload.encode("utf-8")).hexdigest()


def _enabled(provider: str) -> bool:
    configured = getattr(
        settings,
        "METADATA_PROVIDER_ENABLED",
        "crossref,openlibrary,google_books",
    )
    values = configured.split(",") if isinstance(configured, str) else configured
    enabled = {
        value.strip().casefold()
        for value in values
        if value.strip()
    }
    return provider.casefold() in enabled


def _allowed_host(url: str) -> bool:
    host = (urlparse(url).hostname or "").casefold()
    configured = getattr(
        settings,
        "METADATA_PROVIDER_ALLOWED_HOSTS",
        "api.crossref.org,openlibrary.org,www.googleapis.com",
    )
    values = configured.split(",") if isinstance(configured, str) else configured
    allowed = {
        value.strip().casefold()
        for value in values
        if value.strip()
    }
    return bool(host and host in allowed)


def _provider_url(provider: str) -> str:
    urls = {
        "crossref": "https://api.crossref.org",
        "openlibrary": "https://openlibrary.org",
        "google_books": "https://www.googleapis.com",
        "openalex": "https://api.openalex.org",
        "grobid": getattr(settings, "GROBID_SERVICE_URL", ""),
    }
    return urls.get(provider, "")


def _serialize_candidates(candidates: list[Candidate]) -> list[dict]:
    return [asdict(candidate) for candidate in candidates]


def _deserialize_candidates(values: list[dict]) -> list[Candidate]:
    candidates = []
    for value in values:
        if not isinstance(value, dict):
            continue
        try:
            candidates.append(
                Candidate(
                    field_name=str(value["field_name"]),
                    value=value.get("value"),
                    source=str(value["source"]),
                    confidence=float(value.get("confidence", 0)),
                    evidence=dict(value.get("evidence") or {}),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return candidates


def _bounded_raw_response(raw_response) -> dict:
    """Keep an auditable snapshot without allowing an unbounded provider payload."""

    max_bytes = max(
        16_384,
        min(int(getattr(settings, "METADATA_PROVIDER_MAX_RESPONSE_BYTES", 1_048_576)), 5_242_880),
    )
    serialized = _stable_json(raw_response)
    encoded = serialized.encode("utf-8")
    if len(encoded) <= max_bytes:
        return {"payload": json.loads(serialized), "truncated": False}
    preview = encoded[:max_bytes].decode("utf-8", errors="replace")
    return {
        "payload_preview": preview,
        "truncated": True,
        "original_size_bytes": len(encoded),
        "sha256": sha256(encoded).hexdigest(),
    }


def _error_details(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "元数据来源响应超时"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}", f"元数据来源返回 HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.RequestError):
        return "network_error", f"无法连接元数据来源：{str(exc)[:240]}"
    if isinstance(exc, (ParseError, KeyError, TypeError, ValueError)):
        return "invalid_response", f"元数据来源响应无法解析：{str(exc)[:240]}"
    if isinstance(exc, OSError):
        return "local_io_error", f"元数据来源所需文件无法读取：{str(exc)[:240]}"
    return "provider_error", f"元数据来源执行失败：{str(exc)[:240]}"


def _cache_key(provider: str, suffix: str) -> str:
    return f"metadata-provider:{provider}:{suffix}"


def _circuit_is_open(provider: str) -> bool:
    return bool(cache.get(_cache_key(provider, "circuit-open")))


def _record_failure(provider: str) -> None:
    failures_key = _cache_key(provider, "failures")
    failures = int(cache.get(failures_key, 0)) + 1
    circuit_seconds = int(getattr(settings, "METADATA_PROVIDER_CIRCUIT_SECONDS", 300))
    cache.set(failures_key, failures, timeout=circuit_seconds)
    threshold = int(getattr(settings, "METADATA_PROVIDER_CIRCUIT_FAILURES", 3))
    if failures >= threshold:
        cache.set(_cache_key(provider, "circuit-open"), True, timeout=circuit_seconds)


def _record_success(provider: str) -> None:
    cache.delete_many(
        [
            _cache_key(provider, "failures"),
            _cache_key(provider, "circuit-open"),
        ]
    )


def _respect_rate_limit(provider: str) -> None:
    minimum = max(0, int(getattr(settings, "METADATA_PROVIDER_MIN_INTERVAL_MS", 150))) / 1000
    key = _cache_key(provider, "last-request")
    last_request = cache.get(key)
    if last_request is not None:
        remaining = minimum - (time.time() - float(last_request))
        if remaining > 0:
            time.sleep(min(remaining, 1))
    cache.set(key, time.time(), timeout=60)


def _attach_source_record(candidates: list[Candidate], source_record: SourceRecord) -> list[Candidate]:
    values = []
    for candidate in candidates:
        evidence = dict(candidate.evidence or {})
        evidence["source_record_id"] = str(source_record.id)
        values.append(
            Candidate(
                field_name=candidate.field_name,
                value=candidate.value,
                source=candidate.source,
                confidence=candidate.confidence,
                evidence=evidence,
            )
        )
    return values


def invoke_provider(
    *,
    provider: str,
    operation: str,
    query: dict,
    resolver: Resolver,
    upload_item: UploadItem | None = None,
) -> tuple[list[Candidate], list[str]]:
    """Run one configured provider with cache, provenance and a small circuit breaker."""

    provider = provider.casefold()
    if not _enabled(provider):
        return [], [f"{provider} 元数据来源已禁用"]
    provider_url = _provider_url(provider)
    if provider == "openalex" and not getattr(settings, "OPENALEX_API_KEY", ""):
        return [], ["openalex 元数据来源尚未配置 API Key"]
    if not provider_url:
        return [], [f"{provider} 元数据来源尚未配置"]
    if not _allowed_host(provider_url):
        return [], [f"{provider} 元数据来源主机不在允许列表中"]
    if _circuit_is_open(provider):
        return [], [f"{provider} 元数据来源暂时停止请求，稍后可重试"]

    request_fingerprint = _fingerprint(provider, operation, query)
    now = timezone.now()
    cached = (
        SourceRecord.objects.filter(
            upload_item=upload_item,
            provider=provider,
            operation=operation,
            request_fingerprint=request_fingerprint,
            status=SourceRecord.Status.SUCCEEDED,
            expires_at__gt=now,
        )
        .order_by("-retrieved_at")
        .first()
    )
    if cached:
        snapshot = cached.raw_response.get("candidate_snapshot", [])
        return _attach_source_record(_deserialize_candidates(snapshot), cached), []

    attempts = int(getattr(settings, "METADATA_PROVIDER_RETRIES", 1)) + 1
    last_error: Exception | None = None
    for attempt_number in range(1, attempts + 1):
        _respect_rate_limit(provider)
        try:
            result = resolver()
            candidates = list(result)
            raw_response = getattr(result, "raw_response", {})
            external_id = str(getattr(result, "external_id", "") or "")
            provider_version = str(getattr(result, "provider_version", "v1") or "v1")
            record = SourceRecord.objects.create(
                upload_item=upload_item,
                provider=provider,
                operation=operation,
                query=query,
                request_fingerprint=request_fingerprint,
                external_id=external_id,
                raw_response={
                    **_bounded_raw_response(raw_response),
                    "candidate_snapshot": _serialize_candidates(candidates),
                    "attempt": attempt_number,
                },
                provider_version=provider_version,
                expires_at=now
                + timedelta(
                    seconds=int(getattr(settings, "METADATA_PROVIDER_CACHE_SECONDS", 86_400))
                ),
                status=SourceRecord.Status.SUCCEEDED,
            )
            _record_success(provider)
            return _attach_source_record(candidates, record), []
        except (httpx.HTTPError, ParseError, KeyError, TypeError, ValueError, OSError) as exc:
            last_error = exc
            if attempt_number < attempts:
                continue

    assert last_error is not None
    error_code, error_message = _error_details(last_error)
    SourceRecord.objects.create(
        upload_item=upload_item,
        provider=provider,
        operation=operation,
        query=query,
        request_fingerprint=request_fingerprint,
        status=SourceRecord.Status.FAILED,
        error_code=error_code,
        error_message=error_message,
    )
    _record_failure(provider)
    return [], [f"{provider} {operation} 失败：{error_message}"]


def enrich_candidates_with_gateway(
    candidates: list[Candidate],
    path: str | Path | None = None,
    *,
    upload_item: UploadItem | None = None,
) -> tuple[list[Candidate], list[str]]:
    enriched = list(candidates)
    warnings: list[str] = []
    doi = next((candidate.value for candidate in candidates if candidate.field_name == "doi"), None)
    isbn = next((candidate.value for candidate in candidates if candidate.field_name == "isbn"), None)
    language = next((candidate.value for candidate in candidates if candidate.field_name == "language"), "")

    calls: list[tuple[str, str, dict, Resolver]] = []
    if doi:
        calls.append(("crossref", "lookup_doi", {"doi": str(doi)}, lambda: resolve_doi(str(doi))))
        if _enabled("openalex"):
            calls.append(
                ("openalex", "lookup_doi", {"doi": str(doi)}, lambda: resolve_openalex_doi(str(doi)))
            )
    elif isbn:
        calls.extend(
            [
                ("openlibrary", "lookup_isbn", {"isbn": str(isbn)}, lambda: resolve_isbn(str(isbn))),
                (
                    "google_books",
                    "lookup_isbn",
                    {"isbn": str(isbn), "language": str(language)},
                    lambda: resolve_google_books_isbn(str(isbn), language=str(language)),
                ),
            ]
        )
    document_type = next(
        (
            candidate.value
            for candidate in sorted(candidates, key=lambda row: row.confidence, reverse=True)
            if candidate.field_name == "document_type"
        ),
        None,
    )
    if path and document_type == DocumentType.JOURNAL_ARTICLE:
        path_value = str(path)
        calls.append(("grobid", "parse_header", {"filename": Path(path).name}, lambda: resolve_grobid(path_value)))

    for provider, operation, query, resolver in calls:
        values, provider_warnings = invoke_provider(
            provider=provider,
            operation=operation,
            query=query,
            resolver=resolver,
            upload_item=upload_item,
        )
        enriched.extend(values)
        warnings.extend(provider_warnings)
    return enriched, warnings


def refresh_remote_candidates(
    edition,
    *,
    upload_item: UploadItem | None = None,
    should_continue: Callable[[], bool] | None = None,
) -> tuple[list[Candidate], list[str]]:
    candidates: list[Candidate] = []
    warnings: list[str] = []
    calls: list[tuple[str, str, dict, Resolver]] = []
    if edition.doi:
        calls.append(("crossref", "lookup_doi", {"doi": edition.doi}, lambda: resolve_doi(edition.doi)))
        if _enabled("openalex"):
            calls.append(
                ("openalex", "lookup_doi", {"doi": edition.doi}, lambda: resolve_openalex_doi(edition.doi))
            )
    elif edition.isbn:
        calls.extend(
            [
                ("openlibrary", "lookup_isbn", {"isbn": edition.isbn}, lambda: resolve_isbn(edition.isbn)),
                (
                    "google_books",
                    "lookup_isbn",
                    {"isbn": edition.isbn, "language": edition.work.language},
                    lambda: resolve_google_books_isbn(edition.isbn, language=edition.work.language),
                ),
            ]
        )

    title = edition.work.title.strip()
    if title and not calls:
        if edition.work.document_type == DocumentType.JOURNAL_ARTICLE:
            calls.append(("crossref", "search_book", {"title": title}, lambda: search_crossref_title(title)))
            if _enabled("openalex"):
                calls.append(
                    ("openalex", "search_work", {"title": title}, lambda: search_openalex_title(title))
                )
        else:
            calls.extend(
                [
                    (
                        "openlibrary",
                        "search_book",
                        {"title": title, "language": edition.work.language},
                        lambda: search_openlibrary_title(title, language=edition.work.language),
                    ),
                    (
                        "google_books",
                        "search_book",
                        {"title": title, "language": edition.work.language},
                        lambda: search_google_books_title(title, language=edition.work.language),
                    ),
                ]
            )

    for provider, operation, query, resolver in calls:
        if should_continue is not None and not should_continue():
            warnings.append("联网补充已在下一来源请求前暂停。")
            break
        values, provider_warnings = invoke_provider(
            provider=provider,
            operation=operation,
            query=query,
            resolver=resolver,
            upload_item=upload_item,
        )
        candidates.extend(values)
        warnings.extend(provider_warnings)
    return candidates, warnings


def provider_configuration_health() -> list[dict]:
    """Cheap configuration health. This deliberately performs no network request."""

    values = []
    for provider in ("crossref", "openlibrary", "google_books", "openalex", "grobid"):
        url = _provider_url(provider)
        configured = bool(url) and (
            provider != "openalex" or bool(getattr(settings, "OPENALEX_API_KEY", ""))
        )
        enabled = _enabled(provider)
        values.append(
            {
                "provider": provider,
                "enabled": enabled,
                "configured": configured,
                "allowed_host": configured and _allowed_host(url),
                "status": (
                    "disabled"
                    if not enabled
                    else "not_configured"
                    if not configured
                    else "configured"
                    if _allowed_host(url)
                    else "blocked"
                ),
            }
        )
    return values
