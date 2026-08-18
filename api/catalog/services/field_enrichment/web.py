from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import timedelta
from hashlib import sha256
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
import time
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from catalog.models import EnrichmentSourceClass
from ingestion.models import SourceRecord

from .policies import FieldPolicy
from .types import EnrichmentError, FetchedDocument, SearchResult
from .values import stable_json


class WebSearchError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


class WebFetchError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


class WebSearchAdapter(Protocol):
    name: str

    def search(self, query: str, *, limit: int) -> tuple[list[SearchResult], SourceRecord | None]: ...


def _configured_hosts(name: str) -> set[str]:
    value = getattr(settings, name, "")
    values = value.split(",") if isinstance(value, str) else value
    return {str(item).strip().casefold() for item in values if str(item).strip()}


def canonicalize_url(value: str) -> str:
    parsed = urlsplit(str(value or "").strip())
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
        raise WebFetchError("invalid_source", "来源 URL 必须是完整 HTTP 或 HTTPS 地址。")
    if parsed.username or parsed.password:
        raise WebFetchError("invalid_source", "来源 URL 不允许包含用户凭据。")
    scheme = parsed.scheme.casefold()
    host = parsed.hostname.casefold().rstrip(".")
    port = parsed.port
    netloc = host
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        netloc = f"{host}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    return urlunsplit((scheme, netloc, path, parsed.query, ""))


def _resolve_addresses(hostname: str, port: int) -> set[str]:
    try:
        return {
            row[4][0]
            for row in socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as exc:
        raise WebFetchError("fetch_blocked", "来源主机无法解析。") from exc


def validate_public_url(value: str) -> str:
    normalized = canonicalize_url(value)
    parsed = urlsplit(normalized)
    host = parsed.hostname or ""
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise WebFetchError("fetch_blocked", "来源地址指向本机或私有网络。")
    try:
        literal = ipaddress.ip_address(host)
        addresses = {str(literal)}
    except ValueError:
        addresses = _resolve_addresses(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    if not addresses:
        raise WebFetchError("fetch_blocked", "来源主机没有可用地址。")
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise WebFetchError("fetch_blocked", "来源地址解析到私网、回环或链路本地地址。")
    return normalized


def classify_source(url: str, title: str = "") -> str:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").casefold()
    combined = f"{host} {parsed.path} {title}".casefold()
    if any(token in combined for token in ("syllabus", "course-outline", "课程大纲", "教学大纲")):
        return EnrichmentSourceClass.SYLLABUS
    if host == "plato.stanford.edu" or "encyclopedia" in combined:
        return EnrichmentSourceClass.SCHOLARLY_ENCYCLOPEDIA
    if host.endswith(".edu") or ".edu." in host or host.endswith(".ac.uk") or host.endswith(".edu.cn"):
        return EnrichmentSourceClass.UNIVERSITY
    if any(token in combined for token in ("institute", "research-cent", "研究所", "研究院")):
        return EnrichmentSourceClass.RESEARCH_INSTITUTE
    if any(token in combined for token in ("association", "society", "学会", "协会")):
        return EnrichmentSourceClass.PROFESSIONAL_ASSOCIATION
    if any(token in combined for token in ("journal", "doi.org", "期刊")):
        return EnrichmentSourceClass.ACADEMIC_JOURNAL
    if any(token in combined for token in ("publisher", "press", "出版社")):
        return EnrichmentSourceClass.PUBLISHER
    if any(token in combined for token in ("library", "catalog", "图书馆")):
        return EnrichmentSourceClass.LIBRARY_CATALOG
    if any(token in combined for token in ("profile", "people/", "faculty/", "~")):
        return EnrichmentSourceClass.SCHOLAR_HOMEPAGE
    return EnrichmentSourceClass.GENERAL_WEB


class SearXNGSearchAdapter:
    name = "searxng"

    def __init__(self, requester: Callable | None = None):
        self.requester = requester or httpx.get

    def _base_url(self) -> str:
        value = str(getattr(settings, "FIELD_ENRICHMENT_SEARXNG_URL", "") or "").strip()
        if not value:
            raise WebSearchError("provider_unavailable", "SearXNG 尚未配置。")
        parsed = urlsplit(value)
        allowed = _configured_hosts("FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise WebSearchError("invalid_source", "SearXNG URL 无效。")
        if parsed.hostname.casefold() not in allowed:
            raise WebSearchError("fetch_blocked", "SearXNG 主机不在配置允许列表中。")
        return value.rstrip("/")

    def search(self, query: str, *, limit: int) -> tuple[list[SearchResult], SourceRecord | None]:
        query = " ".join(str(query or "").split())[:500]
        if not query:
            return [], None
        base_url = self._base_url()
        fingerprint = sha256(f"searxng:{query.casefold()}:{limit}".encode("utf-8")).hexdigest()
        now = timezone.now()
        cached = SourceRecord.objects.filter(
            upload_item__isnull=True,
            provider="field_enrichment:searxng",
            operation="search",
            request_fingerprint=fingerprint,
            status=SourceRecord.Status.SUCCEEDED,
            expires_at__gt=now,
        ).order_by("-retrieved_at").first()
        if cached:
            values = cached.raw_response.get("results") or []
            return [SearchResult(**row) for row in values if isinstance(row, dict)], cached
        host = urlsplit(base_url).hostname or "searxng"
        minimum = max(
            0,
            min(int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_MIN_INTERVAL_MS", 200)), 5000),
        ) / 1000
        rate_key = f"field-enrichment:search:last:{host}"
        previous = cache.get(rate_key)
        if previous is not None:
            remaining = minimum - (time.time() - float(previous))
            if remaining > 0:
                time.sleep(min(remaining, 1))
        cache.set(rate_key, time.time(), timeout=60)
        timeout = max(2, min(int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_TIMEOUT_SECONDS", 8)), 30))
        try:
            response = self.requester(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
                headers={"Accept": "application/json", "User-Agent": "SocialTheoryLibrary/2.7 field-enrichment"},
                timeout=timeout,
                follow_redirects=False,
            )
            if 300 <= response.status_code < 400:
                raise WebSearchError("invalid_source", "SearXNG 返回了未授权的重定向。")
            response.raise_for_status()
            max_bytes = max(16_384, min(int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_MAX_BYTES", 524_288)), 2_097_152))
            if len(response.content) > max_bytes:
                raise WebSearchError("invalid_source", "SearXNG 响应超过大小限制。")
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise WebSearchError("timeout", "SearXNG 搜索超时。") from exc
        except httpx.HTTPStatusError as exc:
            code = "rate_limited" if exc.response.status_code == 429 else "provider_unavailable"
            raise WebSearchError(code, f"SearXNG 返回 HTTP {exc.response.status_code}。") from exc
        except (httpx.RequestError, ValueError, json.JSONDecodeError) as exc:
            raise WebSearchError("provider_unavailable", "SearXNG 响应不可用。") from exc
        results = []
        for row in payload.get("results", []) if isinstance(payload, dict) else []:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            title = " ".join(str(row.get("title") or url).split())[:1000]
            if not url:
                continue
            results.append(
                SearchResult(
                    url=url,
                    title=title,
                    snippet=" ".join(str(row.get("content") or "").split())[:2000],
                    provider=self.name,
                    source_class=classify_source(url, title),
                )
            )
            if len(results) >= limit:
                break
        record = SourceRecord.objects.create(
            provider="field_enrichment:searxng",
            operation="search",
            query={"query": query, "limit": limit},
            request_fingerprint=fingerprint,
            raw_response={
                "results": [row.__dict__ for row in results],
                "snippet_is_discovery_only": True,
            },
            provider_version="searxng-json-v1",
            retrieved_at=now,
            expires_at=now + timedelta(seconds=int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_CACHE_SECONDS", 86400))),
            status=SourceRecord.Status.SUCCEEDED,
        )
        return results, record


class _PageParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self.canonical_href = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "link":
            values = {str(key).casefold(): str(value or "") for key, value in attrs}
            if "canonical" in values.get("rel", "").casefold() and values.get("href"):
                self.canonical_href = values["href"]
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3", "h4", "tr"}:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if tag == "title":
            self.in_title = False
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag in {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self.in_title:
            self.title_parts.append(data)
        if self.skip_depth == 0:
            self.text_parts.append(data)


def _clean_extracted_text(values: Iterable[str], limit: int) -> str:
    text = "".join(values).replace("\x00", "")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line)[:limit]


class SafeWebFetcher:
    def __init__(self, client_factory: Callable | None = None):
        self.client_factory = client_factory or httpx.Client

    @staticmethod
    def _rate_limit(domain: str) -> None:
        minimum = max(0, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_MIN_INTERVAL_MS", 250)), 5000)) / 1000
        key = f"field-enrichment:fetch:last:{domain}"
        previous = cache.get(key)
        if previous is not None:
            remaining = minimum - (time.time() - float(previous))
            if remaining > 0:
                time.sleep(min(remaining, 1))
        cache.set(key, time.time(), timeout=60)

    def _cached(self, normalized_url: str) -> FetchedDocument | None:
        fingerprint = sha256(normalized_url.encode("utf-8")).hexdigest()
        record = SourceRecord.objects.filter(
            upload_item__isnull=True,
            provider="field_enrichment:web_fetch",
            operation="fetch_page",
            request_fingerprint=fingerprint,
            status=SourceRecord.Status.SUCCEEDED,
            expires_at__gt=timezone.now(),
        ).order_by("-retrieved_at").first()
        payload = record.raw_response.get("document") if record else None
        if not isinstance(payload, dict) or not payload.get("text"):
            return None
        try:
            return FetchedDocument(
                source_url=payload["source_url"],
                canonical_url=payload["canonical_url"],
                title=payload["title"],
                domain=payload["domain"],
                text=payload["text"],
                retrieved_at=record.retrieved_at,
                content_checksum=payload["content_checksum"],
                http_status=int(payload["http_status"]),
                content_type=payload["content_type"],
                source_record_id=record.id,
                source_class=payload.get("source_class") or EnrichmentSourceClass.UNKNOWN,
            )
        except (KeyError, TypeError, ValueError):
            return None

    def fetch(self, url: str) -> FetchedDocument:
        original_url = validate_public_url(url)
        cached = self._cached(original_url)
        if cached:
            return cached
        timeout = max(2, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_TIMEOUT_SECONDS", 10)), 30))
        max_bytes = max(16_384, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_MAX_BYTES", 1_048_576)), 5_242_880))
        max_text_chars = max(4_000, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_TEXT_CHARS", 120_000)), 500_000))
        redirects = max(0, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_REDIRECT_LIMIT", 3)), 5))
        current_url = original_url
        response_bytes = b""
        status_code = 0
        content_type = ""
        try:
            with self.client_factory(timeout=timeout, follow_redirects=False) as client:
                for redirect_count in range(redirects + 1):
                    current_url = validate_public_url(current_url)
                    domain = urlsplit(current_url).hostname or ""
                    self._rate_limit(domain)
                    with client.stream(
                        "GET",
                        current_url,
                        headers={
                            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8",
                            "User-Agent": "SocialTheoryLibrary/2.7 field-enrichment",
                        },
                    ) as response:
                        status_code = response.status_code
                        if 300 <= status_code < 400:
                            location = response.headers.get("location", "")
                            if not location or redirect_count >= redirects:
                                raise WebFetchError("invalid_source", "来源重定向超过限制。")
                            current_url = validate_public_url(urljoin(current_url, location))
                            continue
                        if status_code == 429:
                            raise WebFetchError("rate_limited", "来源页面请求频率受限。")
                        response.raise_for_status()
                        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                        if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                            raise WebFetchError("invalid_source", "来源页面内容类型不支持。")
                        chunks = []
                        size = 0
                        for chunk in response.iter_bytes():
                            size += len(chunk)
                            if size > max_bytes:
                                raise WebFetchError("invalid_source", "来源页面超过大小限制。")
                            chunks.append(chunk)
                        response_bytes = b"".join(chunks)
                        break
        except httpx.TimeoutException as exc:
            raise WebFetchError("timeout", "来源页面请求超时。") from exc
        except httpx.HTTPStatusError as exc:
            raise WebFetchError("provider_unavailable", f"来源页面返回 HTTP {exc.response.status_code}。") from exc
        except httpx.RequestError as exc:
            raise WebFetchError("provider_unavailable", "来源页面当前不可访问。") from exc
        text_value = response_bytes.decode("utf-8", errors="replace")
        title = urlsplit(current_url).hostname or "来源页面"
        canonical_url = current_url
        if content_type in {"text/html", "application/xhtml+xml"}:
            parser = _PageParser()
            parser.feed(text_value)
            extracted = _clean_extracted_text(parser.text_parts, max_text_chars)
            parsed_title = " ".join("".join(parser.title_parts).split())
            if parsed_title:
                title = parsed_title[:1000]
            if parser.canonical_href:
                try:
                    canonical_url = validate_public_url(urljoin(current_url, parser.canonical_href))
                except WebFetchError:
                    canonical_url = current_url
        else:
            extracted = _clean_extracted_text([text_value], max_text_chars)
        if len(extracted) < 40:
            raise WebFetchError("parse_failed", "来源页面没有足够可审核正文。")
        checksum = sha256(response_bytes).hexdigest()
        retrieved_at = timezone.now()
        source_class = classify_source(canonical_url, title)
        record = SourceRecord.objects.create(
            provider="field_enrichment:web_fetch",
            operation="fetch_page",
            query={"url": original_url},
            request_fingerprint=sha256(original_url.encode("utf-8")).hexdigest(),
            external_id=canonical_url[:255],
            raw_response={
                "document": {
                    "source_url": original_url,
                    "canonical_url": canonical_url,
                    "title": title,
                    "domain": urlsplit(canonical_url).hostname or "",
                    "text": extracted,
                    "content_checksum": checksum,
                    "http_status": status_code,
                    "content_type": content_type,
                    "source_class": source_class,
                },
                "stored_text_is_bounded_extraction": True,
                "response_size_bytes": len(response_bytes),
            },
            provider_version="safe-web-fetch-v1",
            retrieved_at=retrieved_at,
            expires_at=retrieved_at + timedelta(seconds=int(getattr(settings, "FIELD_ENRICHMENT_FETCH_CACHE_SECONDS", 86400))),
            status=SourceRecord.Status.SUCCEEDED,
        )
        return FetchedDocument(
            source_url=original_url,
            canonical_url=canonical_url,
            title=title,
            domain=urlsplit(canonical_url).hostname or "",
            text=extracted,
            retrieved_at=retrieved_at,
            content_checksum=checksum,
            http_status=status_code,
            content_type=content_type,
            source_record_id=record.id,
            source_class=source_class,
        )


def configured_web_search_adapter() -> WebSearchAdapter:
    name = str(getattr(settings, "FIELD_ENRICHMENT_WEB_SEARCH_ADAPTER", "searxng") or "").strip().casefold()
    if name == "searxng":
        return SearXNGSearchAdapter()
    raise WebSearchError("provider_unavailable", f"未配置可用的 WebSearchAdapter：{name or 'none'}")


def plan_queries(*, context: dict, policies: tuple[FieldPolicy, ...], form_context: dict) -> list[dict]:
    canonical = next(iter(context.get("canonical_terms") or []), "").strip()
    if not canonical:
        return []
    related_name = str(form_context.get("related_entity_name") or "").strip()
    values = []
    for policy in policies:
        suffix = {
            "external_identifier": "ORCID VIAF authority identifier",
            "affiliation": "university affiliation official profile",
            "name_variant": "alternate name translated name",
            "publication_year": "publication year",
            "publisher": "publisher",
            "isbn": "ISBN",
            "first_publication_date": "first published",
            "foreign_name": "English name",
            "alias": "also known as translation",
            "discipline": "academic discipline classification",
            "subdiscipline": "subdiscipline classification",
            "relation": f"{related_name} {form_context.get('relation_type', '')}",
            "timeline_fact": "publication history chronology",
            "timeline_interpretation": "intellectual development scholarly interpretation",
            "item": "syllabus reading list",
        }.get(policy.field_name, policy.field_name)
        query = " ".join(f'"{canonical}" {suffix}'.split())[:500]
        if query:
            values.append(
                {
                    "query": query,
                    "field_name": policy.field_name,
                    "preferred_source_classes": list(policy.source_priority.keys()),
                }
            )
    output = []
    seen = set()
    for row in values:
        key = row["query"].casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    max_queries = max(1, min(int(getattr(settings, "FIELD_ENRICHMENT_MAX_SEARCH_QUERIES", 8)), 16))
    return output[:max_queries]


def search_and_fetch(
    *,
    context: dict,
    policies: tuple[FieldPolicy, ...],
    form_context: dict,
    search_adapter: WebSearchAdapter | None = None,
    fetcher: SafeWebFetcher | None = None,
) -> tuple[list[FetchedDocument], list[EnrichmentError], dict]:
    search_adapter = search_adapter or configured_web_search_adapter()
    fetcher = fetcher or SafeWebFetcher()
    queries = plan_queries(context=context, policies=policies, form_context=form_context)
    result_limit = max(1, min(int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_RESULTS_PER_QUERY", 5)), 10))
    results: list[SearchResult] = []
    errors: list[EnrichmentError] = []
    for row in queries:
        retries = max(0, min(int(getattr(settings, "FIELD_ENRICHMENT_SEARCH_RETRIES", 1)), 2))
        for attempt in range(retries + 1):
            try:
                values, _record = search_adapter.search(row["query"], limit=result_limit)
                results.extend(values)
                break
            except WebSearchError as exc:
                retryable = exc.code in {"timeout", "provider_unavailable", "rate_limited"}
                if retryable and attempt < retries:
                    time.sleep(min(0.25 * (2**attempt), 1))
                    continue
                errors.append(
                    EnrichmentError(
                        code=exc.code,
                        provider=getattr(search_adapter, "name", "web_search"),
                        field_name=row["field_name"],
                        detail=str(exc),
                    )
                )
                break
    documents = []
    seen_urls = set()
    max_documents = max(1, min(int(getattr(settings, "FIELD_ENRICHMENT_MAX_FETCHED_DOCUMENTS", 12)), 24))
    for result in results:
        try:
            key = canonicalize_url(result.url)
        except WebFetchError as exc:
            errors.append(EnrichmentError(code=exc.code, provider=result.provider, detail=str(exc)))
            continue
        if key in seen_urls:
            continue
        seen_urls.add(key)
        retries = max(0, min(int(getattr(settings, "FIELD_ENRICHMENT_FETCH_RETRIES", 1)), 2))
        for attempt in range(retries + 1):
            try:
                documents.append(fetcher.fetch(key))
                break
            except WebFetchError as exc:
                retryable = exc.code in {"timeout", "provider_unavailable", "rate_limited"}
                if retryable and attempt < retries:
                    time.sleep(min(0.25 * (2**attempt), 1))
                    continue
                errors.append(EnrichmentError(code=exc.code, provider=result.provider, detail=str(exc)))
                break
        if len(documents) >= max_documents:
            break
    return documents, errors, {
        "query_count": len(queries),
        "search_result_count": len(results),
        "unique_source_url_count": len(seen_urls),
        "fetched_document_count": len(documents),
    }
