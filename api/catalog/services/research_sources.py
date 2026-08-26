"""Research source registry used by research, diagnostics and administration.

The registry is a thin coordination layer above the existing authority,
bibliographic, SearXNG and SafeWebFetcher implementations.  It stores only
safe adapter switches and environment aliases in ``SiteSetting``.  Provider
credentials remain process secrets and are never serialized to clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import json
import os
import re
from typing import Any
from urllib.parse import parse_qs
from xml.etree import ElementTree

from django.conf import settings
from django.db import DatabaseError, transaction
from django.utils import timezone

from catalog.models import ProviderCredentialSecret, SiteSetting
from ingestion.models import AuditEvent, SourceRecord


REGISTRY_SETTING_KEY = "research_source_registry"
REGISTRY_VERSION = "research-source-registry-v1"
ALIAS_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ResearchSourceError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, slots=True)
class ResearchSourceSpec:
    key: str
    label: str
    category: str
    purpose: str
    affected_features: tuple[str, ...]
    metadata_formats: tuple[str, ...]
    source_record_providers: tuple[str, ...]
    environment_group: str = ""
    environment_setting: str = ""
    endpoint_setting: str = ""
    credential_setting: str = ""
    endpoint_required: bool = False
    credential_required: bool = False
    fixed_endpoint: bool = False
    default_enabled: bool = False
    execution_mode: str = "structured"
    usage_policy: str = "public_metadata"
    test_probe: str = ""
    configuration_requirements: tuple[str, ...] = ()


STANDARD_BIBLIOGRAPHIC_FORMATS = (
    "json_ld",
    "highwire_citation_meta",
    "coins",
    "rdf",
    "ris",
    "bibtex",
    "marc_xml",
)


SOURCE_SPECS = (
    ResearchSourceSpec(
        "wikidata",
        "Wikidata",
        "authority",
        "人物与知识对象的结构化身份线索",
        ("人物身份候选", "理论与概念消歧"),
        ("json",),
        ("authority:wikidata",),
        environment_group="AUTHORITY_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="authority.wikidata",
        configuration_requirements=("公开结构化接口",),
    ),
    ResearchSourceSpec(
        "viaf",
        "VIAF",
        "authority",
        "人物规范名、译名和馆藏身份核对",
        ("作者与责任者", "学者主页"),
        ("json",),
        ("authority:viaf",),
        environment_group="AUTHORITY_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="authority.viaf",
        configuration_requirements=("公开结构化接口",),
    ),
    ResearchSourceSpec(
        "loc",
        "Library of Congress",
        "authority",
        "英文人物与主题规范记录",
        ("作者与责任者", "主题候选"),
        ("json",),
        ("authority:loc",),
        environment_group="AUTHORITY_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="authority.loc",
        configuration_requirements=("公开结构化接口",),
    ),
    ResearchSourceSpec(
        "openalex",
        "OpenAlex",
        "authority",
        "学者身份、作品和引文元数据",
        ("作者身份候选", "书目核对", "Research Evidence"),
        ("json",),
        ("authority:openalex", "openalex"),
        environment_group="AUTHORITY_PROVIDER_ENABLED",
        credential_setting="OPENALEX_API_KEY",
        credential_required=True,
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="authority.openalex",
        configuration_requirements=("API credential alias",),
    ),
    ResearchSourceSpec(
        "crossref",
        "Crossref",
        "bibliographic",
        "DOI、期刊和出版信息核对",
        ("图书与版本", "期刊书目候选"),
        ("json",),
        ("crossref",),
        environment_group="METADATA_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="metadata.crossref",
        configuration_requirements=("公开结构化接口", "建议配置联系邮箱"),
    ),
    ResearchSourceSpec(
        "openlibrary",
        "OpenLibrary",
        "bibliographic",
        "ISBN、版本与出版社信息核对",
        ("图书与版本", "书目候选"),
        ("json",),
        ("openlibrary",),
        environment_group="METADATA_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="metadata.openlibrary",
        configuration_requirements=("公开结构化接口",),
    ),
    ResearchSourceSpec(
        "google_books",
        "Google Books",
        "bibliographic",
        "ISBN、题名与版本信息交叉核对",
        ("图书与版本", "书目候选"),
        ("json",),
        ("google_books",),
        environment_group="METADATA_PROVIDER_ENABLED",
        fixed_endpoint=True,
        default_enabled=True,
        test_probe="metadata.google_books",
        configuration_requirements=("公开 Books API",),
    ),
    ResearchSourceSpec(
        "searxng",
        "SearXNG",
        "discovery",
        "发现可能包含权威信息或正文证据的公开页面",
        ("Web discovery lead", "实体发现"),
        ("json",),
        ("field_enrichment:searxng",),
        endpoint_setting="FIELD_ENRICHMENT_SEARXNG_URL",
        endpoint_required=True,
        default_enabled=True,
        execution_mode="discovery_only",
        usage_policy="snippet_is_lead_only",
        test_probe="searxng",
        configuration_requirements=("内网 SearXNG endpoint", "允许主机清单"),
    ),
    ResearchSourceSpec(
        "safe_web_fetcher",
        "SafeWebFetcher",
        "evidence",
        "把 Web discovery lead 转换为可审核正文 Evidence",
        ("网页证据", "Candidate 核实"),
        ("html", "text"),
        ("field_enrichment:web_fetch",),
        default_enabled=True,
        execution_mode="verified_fetch",
        usage_policy="page_directives_ssrf_and_size_bounded",
        test_probe="safe_web_fetcher",
        configuration_requirements=("可用 discovery 来源", "公开 HTTP 或 HTTPS 页面"),
    ),
    ResearchSourceSpec(
        "grobid",
        "GROBID",
        "document",
        "期刊题录、作者和结构化页头解析",
        ("期刊书目候选", "Document Intelligence"),
        ("tei_xml",),
        ("grobid",),
        environment_group="METADATA_PROVIDER_ENABLED",
        endpoint_setting="GROBID_SERVICE_URL",
        endpoint_required=True,
        default_enabled=False,
        execution_mode="optional_document_provider",
        configuration_requirements=("NAS GROBID endpoint",),
    ),
    ResearchSourceSpec(
        "ncp_ssd",
        "国家哲学社会科学文献中心 NCPSSD",
        "chinese_bibliographic",
        "中文社会科学文献 discovery 与公开 metadata 扩展位置",
        ("中文期刊书目候选", "Research discovery"),
        STANDARD_BIBLIOGRAPHIC_FORMATS,
        ("ncp_ssd",),
        endpoint_required=True,
        default_enabled=False,
        execution_mode="public_metadata_extension",
        usage_policy="public_metadata_only_after_usage_review",
        configuration_requirements=("经过使用规则核对的 endpoint alias", "仅公开 metadata"),
    ),
    ResearchSourceSpec(
        "nlb_singapore",
        "新加坡国家图书馆中文馆藏 API",
        "chinese_bibliographic",
        "通过国家图书馆正式 Catalogue API 核对中文图书题名、责任者与版本信息",
        ("中文图书版本候选", "作者与责任者", "Research Evidence"),
        ("json",),
        ("nlb_singapore",),
        credential_required=True,
        fixed_endpoint=True,
        default_enabled=False,
        execution_mode="credentialed_official_api",
        usage_policy="official_catalogue_api_only",
        test_probe="metadata.nlb_singapore",
        configuration_requirements=(
            "NLB Open Web Service API Key",
            "NLB App Code",
            "加密凭据格式为包含 api_key 与 app_code 的 JSON",
        ),
    ),
    ResearchSourceSpec(
        "union_catalog_z3950",
        "全国联合编目 Z39.50",
        "chinese_bibliographic",
        "可授权的全国联合编目书目查询",
        ("中文图书版本候选", "ISBN 与出版信息核对"),
        ("marc_xml", "marc21"),
        ("union_catalog_z3950",),
        endpoint_required=True,
        credential_required=True,
        default_enabled=False,
        execution_mode="configured_z3950",
        usage_policy="configured_authorized_access_only",
        configuration_requirements=("Z39.50 endpoint alias", "credential alias", "可选 Z39.50 runtime"),
    ),
    ResearchSourceSpec(
        "cnki",
        "CNKI",
        "licensed_chinese",
        "合法授权环境中的元数据或人工 Evidence 导入",
        ("中文期刊候选", "人工 Evidence import"),
        ("ris", "bibtex", "manual_evidence"),
        ("cnki",),
        endpoint_required=True,
        credential_required=True,
        default_enabled=False,
        execution_mode="licensed_or_manual",
        usage_policy="no_login_bypass_no_crawler",
        configuration_requirements=("合法 provider endpoint", "credential alias", "或人工 Evidence 导入"),
    ),
    ResearchSourceSpec(
        "vip",
        "维普 VIP",
        "licensed_chinese",
        "合法授权环境中的元数据或人工 Evidence 导入",
        ("中文期刊候选", "人工 Evidence import"),
        ("ris", "manual_evidence"),
        ("vip",),
        endpoint_required=True,
        credential_required=True,
        default_enabled=False,
        execution_mode="licensed_or_manual",
        usage_policy="no_login_bypass_no_crawler",
        configuration_requirements=("合法 provider endpoint", "credential alias", "或人工 Evidence 导入"),
    ),
    ResearchSourceSpec(
        "wanfang",
        "万方 Wanfang",
        "licensed_chinese",
        "合法授权环境中的元数据或人工 Evidence 导入",
        ("中文期刊候选", "人工 Evidence import"),
        ("ris", "manual_evidence"),
        ("wanfang",),
        endpoint_required=True,
        credential_required=True,
        default_enabled=False,
        execution_mode="licensed_or_manual",
        usage_policy="no_login_bypass_no_crawler",
        configuration_requirements=("合法 provider endpoint", "credential alias", "或人工 Evidence 导入"),
    ),
)

SOURCE_SPEC_BY_KEY = {row.key: row for row in SOURCE_SPECS}


def _setting_values(name: str) -> set[str]:
    value = getattr(settings, name, "")
    values = value.split(",") if isinstance(value, str) else value
    return {
        str(item).strip().casefold()
        for item in values or ()
        if str(item).strip()
    }


def _stored_document() -> dict:
    try:
        value = SiteSetting.objects.filter(key=REGISTRY_SETTING_KEY).values_list("value", flat=True).first()
    except (DatabaseError, RuntimeError):
        value = None
    if not isinstance(value, dict):
        return {"version": REGISTRY_VERSION, "adapters": {}}
    adapters = value.get("adapters")
    return {
        "version": REGISTRY_VERSION,
        "adapters": dict(adapters) if isinstance(adapters, dict) else {},
    }


def _default_enabled(spec: ResearchSourceSpec) -> bool:
    if spec.environment_group:
        return spec.key in _setting_values(spec.environment_group)
    if spec.key == "searxng":
        return bool(str(getattr(settings, "FIELD_ENRICHMENT_SEARXNG_URL", "") or "").strip())
    if spec.endpoint_setting:
        return bool(str(getattr(settings, spec.endpoint_setting, "") or "").strip())
    return spec.default_enabled


def source_configuration(source_key: str) -> dict[str, Any]:
    key = str(source_key or "").strip().casefold()
    spec = SOURCE_SPEC_BY_KEY.get(key)
    if spec is None:
        raise ResearchSourceError("source_unknown", "Research Source Adapter 不存在。")
    stored = _stored_document().get("adapters", {}).get(key)
    stored = dict(stored) if isinstance(stored, dict) else {}
    return {
        "enabled": bool(stored.get("enabled", _default_enabled(spec))),
        "endpoint_alias": str(stored.get("endpoint_alias") or "").strip().casefold(),
        "credential_alias": str(stored.get("credential_alias") or "").strip().casefold(),
        "configured_by": "database" if stored else "environment",
    }


def research_source_enabled(source_key: str, *, environment_default: bool | None = None) -> bool:
    key = str(source_key or "").strip().casefold()
    spec = SOURCE_SPEC_BY_KEY.get(key)
    if spec is None:
        return bool(environment_default)
    stored = _stored_document().get("adapters", {}).get(key)
    if isinstance(stored, dict) and "enabled" in stored:
        return bool(stored["enabled"])
    return _default_enabled(spec) if environment_default is None else bool(environment_default)


def _alias_environment(prefix: str, alias: str) -> str:
    if not alias:
        return ""
    key = prefix + alias.upper().replace("-", "_")
    return str(os.getenv(key, "") or "").strip()


def resolve_source_endpoint(source_key: str) -> str:
    spec = SOURCE_SPEC_BY_KEY[source_key]
    config = source_configuration(source_key)
    alias_value = _alias_environment("RESEARCH_SOURCE_ENDPOINT_", config["endpoint_alias"])
    if alias_value:
        return alias_value.rstrip("/")
    if spec.endpoint_setting:
        return str(getattr(settings, spec.endpoint_setting, "") or "").strip().rstrip("/")
    return "fixed-public-endpoint" if spec.fixed_endpoint else ""


def resolve_source_credential(source_key: str) -> str:
    spec = SOURCE_SPEC_BY_KEY[source_key]
    config = source_configuration(source_key)
    alias_value = _alias_environment("RESEARCH_SOURCE_CREDENTIAL_", config["credential_alias"])
    if alias_value:
        return alias_value
    if config["credential_alias"]:
        from catalog.services.provider_secrets import resolve_provider_secret

        stored_value = resolve_provider_secret(
            config["credential_alias"],
            purpose="research_source",
        )
        if stored_value:
            return stored_value
    if spec.credential_setting:
        return str(getattr(settings, spec.credential_setting, "") or "")
    return ""


class _StandardMetadataHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, list[str]] = {}
        self.coins: list[str] = []
        self.in_json_ld = False
        self.json_ld_parts: list[str] = []
        self.json_ld: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = {str(key).casefold(): str(value or "") for key, value in attrs}
        if tag.casefold() == "meta":
            name = (values.get("name") or values.get("property") or "").strip().casefold()
            content = values.get("content", "").strip()
            if name and content:
                self.meta.setdefault(name, []).append(content)
        elif tag.casefold() == "span" and "z3988" in values.get("class", "").casefold():
            if values.get("title"):
                self.coins.append(values["title"])
        elif tag.casefold() == "script" and values.get("type", "").casefold() == "application/ld+json":
            self.in_json_ld = True
            self.json_ld_parts = []

    def handle_endtag(self, tag):
        if tag.casefold() == "script" and self.in_json_ld:
            self.in_json_ld = False
            self.json_ld.append("".join(self.json_ld_parts))

    def handle_data(self, data):
        if self.in_json_ld:
            self.json_ld_parts.append(data)


def _first(value):
    if isinstance(value, list):
        return value[0] if value else ""
    return value


def _normalize_json_ld(value: object) -> dict[str, Any]:
    if isinstance(value, list):
        rows = [row for row in value if isinstance(row, dict)]
        value = rows[0] if rows else {}
    if not isinstance(value, dict):
        return {}
    if isinstance(value.get("@graph"), list):
        graph = [row for row in value["@graph"] if isinstance(row, dict)]
        value = next((row for row in graph if row.get("headline") or row.get("name")), value)
    authors = value.get("author") or value.get("creator") or []
    authors = authors if isinstance(authors, list) else [authors]
    author_names = [
        str(row.get("name") if isinstance(row, dict) else row).strip()
        for row in authors
        if str(row.get("name") if isinstance(row, dict) else row).strip()
    ]
    identifiers = value.get("identifier") or []
    identifiers = identifiers if isinstance(identifiers, list) else [identifiers]
    return {
        "title": str(value.get("headline") or value.get("name") or "").strip(),
        "authors": author_names,
        "abstract": str(value.get("abstract") or value.get("description") or "").strip(),
        "publication_date": str(value.get("datePublished") or "").strip(),
        "publisher": str(
            (value.get("publisher") or {}).get("name")
            if isinstance(value.get("publisher"), dict)
            else value.get("publisher") or ""
        ).strip(),
        "identifiers": [str(row).strip() for row in identifiers if str(row).strip()],
        "source_format": "json_ld",
    }


def _extract_html_metadata(text: str) -> dict[str, Any]:
    parser = _StandardMetadataHTMLParser()
    parser.feed(text)
    parser.close()
    meta = parser.meta
    output = {
        "title": _first(meta.get("citation_title") or meta.get("dc.title") or meta.get("og:title") or ""),
        "authors": list(meta.get("citation_author") or meta.get("dc.creator") or []),
        "abstract": _first(meta.get("citation_abstract") or meta.get("dc.description") or meta.get("description") or ""),
        "publication_date": _first(meta.get("citation_publication_date") or meta.get("citation_date") or meta.get("dc.date") or ""),
        "publisher": _first(meta.get("citation_publisher") or meta.get("dc.publisher") or ""),
        "doi": _first(meta.get("citation_doi") or meta.get("dc.identifier") or ""),
        "isbn": _first(meta.get("citation_isbn") or ""),
        "source_format": "highwire_citation_meta",
    }
    for raw in parser.coins:
        values = parse_qs(raw, keep_blank_values=False)
        output["title"] = output["title"] or _first(values.get("rft.atitle") or values.get("rft.btitle") or values.get("rft.title") or "")
        output["authors"] = output["authors"] or list(values.get("rft.au") or [])
        output["publication_date"] = output["publication_date"] or _first(values.get("rft.date") or "")
        output["source_format"] = "coins"
    for raw in parser.json_ld:
        try:
            normalized = _normalize_json_ld(json.loads(raw))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        for key, value in normalized.items():
            if value not in (None, "", []):
                output[key] = value
        break
    return {key: value for key, value in output.items() if value not in (None, "", [])}


def _extract_ris(text: str) -> dict[str, Any]:
    values: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = re.match(r"^([A-Z0-9]{2})\s*-\s*(.*)$", line.strip())
        if match:
            values.setdefault(match.group(1), []).append(match.group(2).strip())
    return {
        "title": _first(values.get("TI") or values.get("T1") or ""),
        "authors": list(values.get("AU") or values.get("A1") or []),
        "abstract": _first(values.get("AB") or ""),
        "publication_date": _first(values.get("PY") or values.get("Y1") or ""),
        "publisher": _first(values.get("PB") or ""),
        "doi": _first(values.get("DO") or ""),
        "isbn": _first(values.get("SN") or ""),
        "source_format": "ris",
    }


def _extract_bibtex(text: str) -> dict[str, Any]:
    fields = {
        match.group(1).casefold(): match.group(2).strip().strip("{}\"")
        for match in re.finditer(
            r"(?i)([a-z][a-z0-9_-]*)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)",
            text,
        )
    }
    return {
        "title": fields.get("title", ""),
        "authors": [value.strip() for value in fields.get("author", "").split(" and ") if value.strip()],
        "abstract": fields.get("abstract", ""),
        "publication_date": fields.get("date") or fields.get("year", ""),
        "publisher": fields.get("publisher", ""),
        "doi": fields.get("doi", ""),
        "isbn": fields.get("isbn", ""),
        "source_format": "bibtex",
    }


def _extract_marc_xml(text: str) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ResearchSourceError("invalid_metadata", "MARC/XML 无法解析。") from exc
    datafields: dict[str, list[dict[str, str]]] = {}
    for field in root.iter():
        if field.tag.rsplit("}", 1)[-1] != "datafield":
            continue
        tag = str(field.attrib.get("tag") or "")
        row = {}
        for child in field:
            if child.tag.rsplit("}", 1)[-1] == "subfield":
                row[str(child.attrib.get("code") or "")] = str(child.text or "").strip()
        datafields.setdefault(tag, []).append(row)
    title_row = _first(datafields.get("245") or [{}]) or {}
    author_rows = (datafields.get("100") or []) + (datafields.get("700") or [])
    publication_row = _first(datafields.get("264") or datafields.get("260") or [{}]) or {}
    isbn_rows = datafields.get("020") or []
    return {
        "title": " ".join(value for value in (title_row.get("a"), title_row.get("b")) if value).rstrip(" /:"),
        "authors": [row.get("a", "").rstrip(" ,") for row in author_rows if row.get("a")],
        "publication_place": publication_row.get("a", "").rstrip(" :"),
        "publisher": publication_row.get("b", "").rstrip(" ,"),
        "publication_date": publication_row.get("c", "").rstrip(" ."),
        "isbn": _first([row.get("a", "") for row in isbn_rows if row.get("a")]),
        "source_format": "marc_xml",
    }


def _extract_rdf_xml(text: str) -> dict[str, Any]:
    """Extract the Dublin Core subset commonly exposed by library RDF feeds."""

    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ResearchSourceError("invalid_metadata", "RDF/XML 无法解析。") from exc
    values: dict[str, list[str]] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1].casefold()
        value = " ".join(str(element.text or "").split()).strip()
        if value and name in {
            "title",
            "creator",
            "contributor",
            "description",
            "date",
            "issued",
            "publisher",
            "identifier",
            "language",
        }:
            values.setdefault(name, []).append(value)
    identifiers = values.get("identifier") or []
    doi = next(
        (
            match.group(1)
            for value in identifiers
            if (match := re.search(r"(?i)(?:doi:\s*|https?://doi\.org/)?(10\.\d{4,9}/\S+)", value))
        ),
        "",
    )
    isbn = next(
        (
            re.sub(r"[^0-9Xx]", "", match.group(1))
            for value in identifiers
            if (match := re.search(r"(?i)(?:isbn(?:-1[03])?:?\s*)?([0-9X][0-9X\s-]{8,20}[0-9X])", value))
        ),
        "",
    )
    return {
        "title": _first(values.get("title") or ""),
        "authors": list(values.get("creator") or values.get("contributor") or []),
        "abstract": _first(values.get("description") or ""),
        "publication_date": _first(values.get("issued") or values.get("date") or ""),
        "publisher": _first(values.get("publisher") or ""),
        "language": _first(values.get("language") or ""),
        "doi": doi.rstrip(".,;"),
        "isbn": isbn,
        "source_format": "rdf",
    }


def extract_standard_metadata(payload: object, content_type: str = "") -> dict[str, Any]:
    """Extract common publisher/library metadata without source-specific scraping."""

    if isinstance(payload, (dict, list)):
        return _normalize_json_ld(payload)
    text = str(payload or "").strip()
    kind = str(content_type or "").casefold()
    if not text:
        return {}
    if "html" in kind or "<html" in text[:500].casefold():
        return _extract_html_metadata(text)
    if "ris" in kind or re.search(r"(?m)^TY\s+-\s+", text):
        return {key: value for key, value in _extract_ris(text).items() if value not in (None, "", [])}
    if "bibtex" in kind or re.search(r"(?i)@(?:book|article|incollection|misc)\s*\{", text):
        return {key: value for key, value in _extract_bibtex(text).items() if value not in (None, "", [])}
    if "rdf" in kind or "<rdf:rdf" in text[:500].casefold():
        return {key: value for key, value in _extract_rdf_xml(text).items() if value not in (None, "", [])}
    if "xml" in kind or text.startswith("<?xml") or "<record" in text[:500]:
        return {key: value for key, value in _extract_marc_xml(text).items() if value not in (None, "", [])}
    try:
        return _normalize_json_ld(json.loads(text))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


class ResearchSourceAdapter:
    """Standard adapter surface modelled after translator-style source adapters."""

    def __init__(self, spec: ResearchSourceSpec):
        self.spec = spec
        self.key = spec.key

    def detect(self, payload: object, *, content_type: str = "") -> bool:
        return bool(extract_standard_metadata(payload, content_type))

    def search(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        if not research_source_enabled(self.key):
            raise ResearchSourceError("source_disabled", f"{self.spec.label} 已禁用。")
        query = " ".join(str(query or "").split())[:500]
        limit = max(1, min(int(limit), 20))
        if self.key in {"wikidata", "viaf", "loc"}:
            from catalog.services.authority_suggestions import _fetch_provider_with_policy

            return list(_fetch_provider_with_policy(self.key, "person", query))[:limit]
        if self.key == "openalex":
            from ingestion.services.metadata import search_openalex_title

            return [row.__dict__ for row in search_openalex_title(query, limit=limit)]
        if self.key in {"crossref", "openlibrary", "google_books", "nlb_singapore"}:
            from ingestion.services.metadata import (
                search_crossref_title,
                search_google_books_title,
                search_nlb_singapore_title,
                search_openlibrary_title,
            )

            resolver = {
                "crossref": lambda: search_crossref_title(query, limit=limit),
                "openlibrary": lambda: search_openlibrary_title(query, limit=limit),
                "google_books": lambda: search_google_books_title(query, language="", limit=limit),
                "nlb_singapore": lambda: search_nlb_singapore_title(query, limit=limit),
            }[self.key]
            return [row.__dict__ for row in resolver()]
        if self.key == "searxng":
            from catalog.services.field_enrichment.web import configured_web_search_adapter

            values, _record = configured_web_search_adapter().search(query, limit=limit)
            return [row.__dict__ for row in values]
        raise ResearchSourceError(
            "search_not_available",
            f"{self.spec.label} 当前只提供受控扩展位置或人工 Evidence 导入。",
        )

    def fetch(self, identifier: str) -> object:
        if not research_source_enabled(self.key):
            raise ResearchSourceError("source_disabled", f"{self.spec.label} 已禁用。")
        if self.key == "safe_web_fetcher":
            from catalog.services.field_enrichment.web import SafeWebFetcher

            return SafeWebFetcher().fetch(identifier)
        if self.key == "nlb_singapore":
            from ingestion.services.metadata import fetch_nlb_singapore_title

            return fetch_nlb_singapore_title(identifier)
        raise ResearchSourceError("fetch_not_available", f"{self.spec.label} 没有通用匿名 fetch。")

    def extract_metadata(self, payload: object, *, content_type: str = "") -> dict[str, Any]:
        if self.key == "nlb_singapore":
            from ingestion.services.metadata import normalize_nlb_singapore_record

            return normalize_nlb_singapore_record(payload)
        return extract_standard_metadata(payload, content_type)

    def normalize(self, metadata: dict[str, Any]) -> dict[str, Any]:
        output = {}
        for key, value in dict(metadata or {}).items():
            if isinstance(value, str):
                value = " ".join(value.split()).strip()
            elif isinstance(value, list):
                value = [" ".join(str(item).split()).strip() for item in value if str(item).strip()]
            if value not in (None, "", []):
                output[str(key)] = value
        return output

    def evidence(self, metadata: dict[str, Any], *, source_url: str = "") -> dict[str, Any]:
        normalized = self.normalize(metadata)
        return {
            "kind": "external_metadata",
            "source": self.key,
            "text": json.dumps(normalized, ensure_ascii=False, sort_keys=True)[:8000],
            "locator": {"url": str(source_url or "")[:2000], "format": normalized.get("source_format", "structured")},
            "quality": {"structured": True, "lead_only": self.spec.execution_mode == "discovery_only"},
            "provenance": {
                "adapter": self.key,
                "registry_version": REGISTRY_VERSION,
                "content_hash": sha256(json.dumps(normalized, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
            },
        }

    def health(self) -> dict[str, Any]:
        return source_registry_row(self.spec)

    def test_fixture(self) -> dict[str, Any]:
        if self.key == "nlb_singapore":
            return {
                "query": "乡土中国",
                "content_type": "application/json",
                "metadata": {
                    "brn": 200001,
                    "nativeTitle": "乡土中国",
                    "nativeAuthor": "费孝通",
                    "isbns": ["9787108062156"],
                    "nativePublisher": ["北京 : 商务印书馆"],
                    "publishDate": "2018",
                },
            }
        return {
            "query": "Mind Self and Society" if self.spec.category != "authority" else "George Herbert Mead",
            "content_type": "text/html",
            "metadata": '<meta name="citation_title" content="Mind, Self, and Society">',
        }


RESEARCH_SOURCE_ADAPTERS = {
    spec.key: ResearchSourceAdapter(spec)
    for spec in SOURCE_SPECS
}


def source_adapter(source_key: str) -> ResearchSourceAdapter:
    adapter = RESEARCH_SOURCE_ADAPTERS.get(str(source_key or "").strip().casefold())
    if adapter is None:
        raise ResearchSourceError("source_unknown", "Research Source Adapter 不存在。")
    return adapter


def _latest_record(spec: ResearchSourceSpec, status_value: str):
    return (
        SourceRecord.objects.filter(
            provider__in=spec.source_record_providers,
            status=status_value,
        )
        .order_by("-retrieved_at")
        .first()
    )


def source_registry_row(spec: ResearchSourceSpec) -> dict[str, Any]:
    config = source_configuration(spec.key)
    endpoint_configured = bool(resolve_source_endpoint(spec.key))
    credential_configured = bool(resolve_source_credential(spec.key))
    credential_status = None
    if config["credential_alias"]:
        try:
            credential_status = (
                ProviderCredentialSecret.objects.filter(
                    alias=config["credential_alias"],
                    purpose=ProviderCredentialSecret.Purpose.RESEARCH_SOURCE,
                )
                .only(
                    "updated_at",
                    "last_tested_at",
                    "last_test_status",
                    "last_test_message",
                )
                .first()
            )
        except (DatabaseError, RuntimeError):
            credential_status = None
    latest_success = _latest_record(spec, SourceRecord.Status.SUCCEEDED)
    latest_failure = _latest_record(spec, SourceRecord.Status.FAILED)
    requirements_met = (
        (not spec.endpoint_required or endpoint_configured)
        and (not spec.credential_required or credential_configured)
    )
    if not config["enabled"]:
        status_value = "disabled"
    elif not requirements_met:
        status_value = "not_configured"
    elif latest_failure and (
        latest_success is None or latest_failure.retrieved_at > latest_success.retrieved_at
    ):
        status_value = "degraded"
    else:
        status_value = "configured"
    return {
        "key": spec.key,
        "label": spec.label,
        "category": spec.category,
        "purpose": spec.purpose,
        "affected_features": list(spec.affected_features),
        "metadata_formats": list(spec.metadata_formats),
        "execution_mode": spec.execution_mode,
        "usage_policy": spec.usage_policy,
        "configuration_requirements": list(spec.configuration_requirements),
        "enabled": config["enabled"],
        "status": status_value,
        "configured_by": config["configured_by"],
        "endpoint_configured": endpoint_configured,
        "credential_configured": credential_configured,
        "endpoint_alias_set": bool(config["endpoint_alias"]),
        "credential_alias_set": bool(config["credential_alias"]),
        "endpoint_alias_supported": bool(not spec.fixed_endpoint and (spec.endpoint_required or spec.endpoint_setting)),
        "credential_alias_supported": bool(spec.credential_required or spec.credential_setting),
        "credential_updated_at": credential_status.updated_at if credential_status else None,
        "credential_last_tested_at": credential_status.last_tested_at if credential_status else None,
        "credential_last_test_status": credential_status.last_test_status if credential_status else "",
        "credential_last_test_message": credential_status.last_test_message if credential_status else "",
        "last_success_at": latest_success.retrieved_at if latest_success else None,
        "last_failure_at": latest_failure.retrieved_at if latest_failure else None,
        "last_error_code": latest_failure.error_code if latest_failure else "",
        "last_error_category": latest_failure.error_code if latest_failure else "",
        "secret_values_exposed": False,
    }


def research_source_registry_payload(*, user=None) -> dict[str, Any]:
    from accounts.ownership import is_library_owner
    from common.capabilities import Capability, has_capability

    rows = [source_registry_row(spec) for spec in SOURCE_SPECS]
    return {
        "version": REGISTRY_VERSION,
        "generated_at": timezone.now(),
        "adapters": rows,
        "summary": {
            "total": len(rows),
            "enabled": sum(row["enabled"] for row in rows),
            "configured": sum(row["status"] == "configured" for row in rows),
            "degraded": sum(row["enabled"] and row["status"] in {"degraded", "not_configured"} for row in rows),
            "chinese_extensions": sum(row["category"] in {"chinese_bibliographic", "licensed_chinese"} for row in rows),
        },
        "permissions": {
            "can_edit": bool(user and has_capability(user, Capability.CONFIGURE_PROVIDERS)),
            "can_test": bool(user and has_capability(user, Capability.CONFIGURE_PROVIDERS)),
            "can_edit_sensitive_aliases": bool(user and is_library_owner(user)),
        },
        "secret_values_exposed": False,
    }


def _validated_alias(value: object, *, field_name: str) -> str:
    normalized = str(value or "").strip().casefold()
    if normalized and not ALIAS_RE.fullmatch(normalized):
        raise ResearchSourceError("invalid_alias", f"{field_name} 格式无效。")
    return normalized


@transaction.atomic
def update_research_source_registry(
    updates: object,
    *,
    actor,
    allow_sensitive_aliases: bool,
    request_id: str = "",
) -> dict[str, Any]:
    if not isinstance(updates, list) or not 1 <= len(updates) <= len(SOURCE_SPECS):
        raise ResearchSourceError("invalid_document", "adapters 必须是有界配置列表。")
    before_document = _stored_document()
    adapters = dict(before_document.get("adapters") or {})
    for value in updates:
        if not isinstance(value, dict):
            raise ResearchSourceError("invalid_document", "每个 adapter 配置必须是对象。")
        forbidden = {"secret", "api_key", "token", "password"}.intersection(value)
        if forbidden:
            raise ResearchSourceError("secret_rejected", "Research Source Registry 不接收明文凭据。")
        key = str(value.get("key") or "").strip().casefold()
        if key not in SOURCE_SPEC_BY_KEY:
            raise ResearchSourceError("source_unknown", "Research Source Adapter 不存在。")
        current = dict(adapters.get(key) or {})
        if "enabled" in value:
            current["enabled"] = bool(value["enabled"])
        alias_fields = {"endpoint_alias", "credential_alias"}.intersection(value)
        if alias_fields and not allow_sensitive_aliases:
            raise ResearchSourceError("owner_required", "只有 System Owner 可以修改 Provider alias。")
        spec = SOURCE_SPEC_BY_KEY[key]
        if "endpoint_alias" in alias_fields and not (
            not spec.fixed_endpoint and (spec.endpoint_required or spec.endpoint_setting)
        ):
            raise ResearchSourceError("alias_not_supported", "该 Research Source 不支持 endpoint alias。")
        if "credential_alias" in alias_fields and not (
            spec.credential_required or spec.credential_setting
        ):
            raise ResearchSourceError("alias_not_supported", "该 Research Source 不支持 credential alias。")
        for field_name in alias_fields:
            current[field_name] = _validated_alias(value.get(field_name), field_name=field_name)
        adapters[key] = current
    document = {
        "version": REGISTRY_VERSION,
        "adapters": adapters,
    }
    SiteSetting.objects.update_or_create(
        key=REGISTRY_SETTING_KEY,
        defaults={"value": document, "public": False, "updated_by": actor},
    )
    before_safe = {
        key: {
            "enabled": value.get("enabled"),
            "endpoint_alias_set": bool(value.get("endpoint_alias")),
            "credential_alias_set": bool(value.get("credential_alias")),
        }
        for key, value in (before_document.get("adapters") or {}).items()
        if isinstance(value, dict)
    }
    after_safe = {
        key: {
            "enabled": value.get("enabled"),
            "endpoint_alias_set": bool(value.get("endpoint_alias")),
            "credential_alias_set": bool(value.get("credential_alias")),
        }
        for key, value in adapters.items()
        if isinstance(value, dict)
    }
    AuditEvent.objects.create(
        actor=actor,
        action="research_source_registry_update",
        object_type="SiteSetting",
        object_id=REGISTRY_SETTING_KEY,
        before=before_safe,
        after=after_safe,
        request_id=str(request_id or "")[:120],
    )
    return document


def _record_research_source_credential_test(
    adapter: ResearchSourceAdapter,
    result: dict[str, Any],
) -> dict[str, Any]:
    alias = source_configuration(adapter.key)["credential_alias"]
    if alias:
        from catalog.services.provider_secrets import record_provider_secret_test

        record_provider_secret_test(
            alias=alias,
            status=str(result.get("status") or "unknown"),
            message=str(result.get("detail") or result.get("error_code") or ""),
        )
    return result


def test_research_source(source_key: str, *, actor=None) -> dict[str, Any]:
    adapter = source_adapter(source_key)
    row = adapter.health()
    if not row["enabled"]:
        return _record_research_source_credential_test(
            adapter,
            {"key": adapter.key, "status": "disabled", "functional": False, "productive": False, "error_code": "source_disabled"},
        )
    if row["status"] == "not_configured":
        return _record_research_source_credential_test(
            adapter,
            {"key": adapter.key, "status": "not_configured", "functional": False, "productive": False, "error_code": "source_not_configured"},
        )
    if adapter.spec.test_probe:
        from catalog.services.system_health import run_health_probe

        run = run_health_probe(adapter.spec.test_probe, source="manual", actor=actor)
        return _record_research_source_credential_test(
            adapter,
            {
                "key": adapter.key,
                "status": run.status,
                "functional": run.functional,
                "productive": run.productive,
                "error_code": run.error_code,
                "checked_at": run.finished_at or run.created_at,
                "details": dict(run.details or {}),
            },
        )
    if adapter.spec.execution_mode in {"licensed_or_manual", "configured_z3950"}:
        return _record_research_source_credential_test(
            adapter,
            {
                "key": adapter.key,
                "status": "degraded",
                "functional": False,
                "productive": False,
                "error_code": "adapter_runtime_not_installed",
                "detail": "配置位置已建立，当前部署未启用授权 connector。人工 Evidence 导入仍可使用。",
            },
        )
    return _record_research_source_credential_test(
        adapter,
        {
            "key": adapter.key,
            "status": "configured",
            "functional": True,
            "productive": None,
            "error_code": "live_test_not_defined",
            "detail": "来源配置有效，但尚无获准的匿名 live fixture。",
        },
    )
