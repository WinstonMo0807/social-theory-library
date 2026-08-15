from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

import yaml


MAX_METADATA_IMPORT_BYTES = 512 * 1024

SUPPORTED_IMPORT_FORMATS = {
    "ris",
    "bibtex",
    "csl_json",
    "sidecar_json",
    "sidecar_yaml",
}

FIELD_LIMITS = {
    "title": 600,
    "subtitle": 600,
    "document_type": 32,
    "language": 16,
    "version_label": 120,
    "publication_year": None,
    "publisher": 300,
    "publication_place": 200,
    "journal_title": 300,
    "volume": 40,
    "issue": 40,
    "page_range": 80,
    "degree_institution": 300,
    "degree_type": 120,
    "report_institution": 300,
    "isbn": 32,
    "doi": 255,
    "abstract": 20_000,
    "authors": None,
}

SIDECAR_CONTROL_FIELDS = {"schema_version"}

DOCUMENT_TYPE_ALIASES = {
    "book": "book",
    "book-chapter": "book",
    "chapter": "book",
    "inbook": "book",
    "incollection": "book",
    "article": "journal_article",
    "article-journal": "journal_article",
    "journal": "journal_article",
    "journal_article": "journal_article",
    "jour": "journal_article",
    "thes": "thesis",
    "thesis": "thesis",
    "phdthesis": "thesis",
    "mastersthesis": "thesis",
    "report": "report",
    "rprt": "report",
    "techreport": "report",
}

LANGUAGE_ALIASES = {
    "zh": "zh-CN",
    "zh-cn": "zh-CN",
    "zh-hans": "zh-CN",
    "chi": "zh-CN",
    "zho": "zh-CN",
    "中文": "zh-CN",
    "简体中文": "zh-CN",
    "zh-tw": "zh-TW",
    "zh-hant": "zh-TW",
    "繁体中文": "zh-TW",
    "繁體中文": "zh-TW",
    "en": "en",
    "eng": "en",
    "english": "en",
    "英文": "en",
}


class MetadataImportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ParsedMetadataImport:
    format: str
    fields: dict[str, Any]
    field_sources: dict[str, str]
    raw_record: dict[str, Any]
    record_key: str = ""


def normalize_import_format(format_hint: str = "", filename: str = "", data: bytes = b"") -> str:
    value = str(format_hint or "").strip().casefold().replace("-", "_")
    aliases = {
        "bib": "bibtex",
        "csl": "csl_json",
        "csljson": "csl_json",
        "json_csl": "csl_json",
        "sidecar": "sidecar_json",
        "yaml": "sidecar_yaml",
        "yml": "sidecar_yaml",
        "sidecar_yaml": "sidecar_yaml",
        "json": "sidecar_json",
    }
    value = aliases.get(value, value)
    if value:
        if value not in SUPPORTED_IMPORT_FORMATS:
            raise MetadataImportError("unsupported_format", "仅支持 RIS、BibTeX、CSL-JSON、sidecar JSON 和 YAML。")
        return value

    suffix = str(filename or "").strip().casefold().rsplit(".", 1)[-1]
    if suffix == "ris":
        return "ris"
    if suffix in {"bib", "bibtex"}:
        return "bibtex"
    if suffix in {"yaml", "yml"}:
        return "sidecar_yaml"
    if suffix == "json":
        try:
            payload = json.loads(_decode_text(data))
        except (MetadataImportError, json.JSONDecodeError) as exc:
            raise MetadataImportError("invalid_json", "JSON 文件无法解析。") from exc
        if isinstance(payload, list):
            return "csl_json"
        if isinstance(payload, dict) and (
            "issued" in payload
            or "container-title" in payload
            or isinstance(payload.get("author"), list)
            or str(payload.get("type") or "").casefold() in DOCUMENT_TYPE_ALIASES
        ):
            return "csl_json"
        return "sidecar_json"
    raise MetadataImportError("format_required", "无法从文件名判断格式，请明确提交 format。")


def parse_metadata_import(data: bytes, *, format_hint: str = "", filename: str = "") -> ParsedMetadataImport:
    if not data:
        raise MetadataImportError("empty_file", "元数据文件为空。")
    if len(data) > MAX_METADATA_IMPORT_BYTES:
        raise MetadataImportError(
            "file_too_large",
            f"元数据文件不能超过 {MAX_METADATA_IMPORT_BYTES // 1024} KiB。",
        )
    import_format = normalize_import_format(format_hint, filename, data)
    text = _decode_text(data)
    if import_format == "ris":
        parsed = _parse_ris(text)
    elif import_format == "bibtex":
        parsed = _parse_bibtex(text)
    elif import_format == "csl_json":
        parsed = _parse_csl_json(text)
    elif import_format == "sidecar_json":
        parsed = _parse_sidecar_json(text)
    else:
        parsed = _parse_sidecar_yaml(text)
    fields = _normalize_fields(parsed.fields)
    if not fields:
        raise MetadataImportError("no_supported_fields", "文件中没有可导入的受支持字段。")
    return ParsedMetadataImport(
        format=parsed.format,
        fields=fields,
        field_sources={key: parsed.field_sources[key] for key in fields},
        raw_record=parsed.raw_record,
        record_key=parsed.record_key,
    )


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MetadataImportError("invalid_encoding", "元数据文件必须使用 UTF-8 编码。") from exc


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    if value is None:
        return ""
    return " ".join(str(value).replace("\x00", "").split()).strip()


def _normalize_fields(values: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field_name, value in values.items():
        if field_name not in FIELD_LIMITS:
            continue
        if field_name == "authors":
            if isinstance(value, str):
                value = [part.strip() for part in re.split(r"\s+and\s+|[;；]", value) if part.strip()]
            if not isinstance(value, list):
                raise MetadataImportError("invalid_authors", "authors 必须是姓名字符串数组。")
            authors = []
            for author in value:
                name = _clean_text(author)
                if name and name not in authors:
                    if len(name) > 240:
                        raise MetadataImportError("field_too_long", "作者名称不能超过 240 个字符。")
                    authors.append(name)
            if len(authors) > 100:
                raise MetadataImportError("too_many_authors", "单条记录最多导入 100 位责任者。")
            if authors:
                normalized[field_name] = authors
            continue
        if field_name == "publication_year":
            match = re.search(r"(?<!\d)(\d{4})(?!\d)", _clean_text(value))
            if not match:
                continue
            year = int(match.group(1))
            if not 1400 <= year <= 2100:
                raise MetadataImportError("invalid_publication_year", "出版年份必须在 1400 至 2100 之间。")
            normalized[field_name] = year
            continue
        text = _clean_text(value)
        if not text:
            continue
        if field_name == "document_type":
            mapped = DOCUMENT_TYPE_ALIASES.get(text.casefold())
            if not mapped:
                raise MetadataImportError("invalid_document_type", f"不支持的文献类型：{text}")
            text = mapped
        elif field_name == "language":
            text = LANGUAGE_ALIASES.get(text.casefold(), text)
            if text not in {"zh-CN", "zh-TW", "en"}:
                raise MetadataImportError("invalid_language", f"不支持的正文语言：{text}")
        elif field_name == "doi":
            text = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", text, flags=re.IGNORECASE).strip()
        limit = FIELD_LIMITS[field_name]
        if limit is not None and len(text) > limit:
            raise MetadataImportError("field_too_long", f"字段 {field_name} 超过 {limit} 个字符。")
        normalized[field_name] = text
    return normalized


def _require_single_record(records: list[Any], import_format: str) -> Any:
    if not records:
        raise MetadataImportError("no_record", f"{import_format} 文件中没有书目记录。")
    if len(records) != 1:
        raise MetadataImportError(
            "multiple_records",
            "单个元数据文件只能关联一个馆藏项，请拆分后分别导入。",
        )
    return records[0]


def _parse_ris(text: str) -> ParsedMetadataImport:
    records: list[dict[str, list[str]]] = []
    current: dict[str, list[str]] = {}
    last_tag = ""
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if not raw_line.strip():
            continue
        match = re.match(r"^([A-Z0-9]{2})\s*-\s?(.*)$", raw_line)
        if not match:
            if last_tag and raw_line[:1].isspace():
                current[last_tag][-1] = f"{current[last_tag][-1]} {_clean_text(raw_line)}".strip()
                continue
            raise MetadataImportError("invalid_ris", f"RIS 第 {line_number} 行格式无效。")
        tag, value = match.group(1), match.group(2).strip()
        if tag == "TY" and current:
            raise MetadataImportError("invalid_ris", "上一条 RIS 记录缺少 ER 结束标记。")
        current.setdefault(tag, []).append(value)
        last_tag = tag
        if tag == "ER":
            records.append(current)
            current = {}
            last_tag = ""
    if current:
        raise MetadataImportError("invalid_ris", "RIS 记录缺少 ER 结束标记。")
    record = _require_single_record(records, "RIS")

    fields: dict[str, Any] = {}
    sources: dict[str, str] = {}

    def assign(field_name: str, tags: tuple[str, ...], *, multiple: bool = False):
        for tag in tags:
            values = [_clean_text(value) for value in record.get(tag, []) if _clean_text(value)]
            if values:
                fields[field_name] = values if multiple else values[0]
                sources[field_name] = tag
                return

    assign("title", ("TI", "T1", "CT"))
    assign("subtitle", ("ST",))
    assign("authors", ("AU", "A1"), multiple=True)
    assign("publisher", ("PB",))
    assign("publication_place", ("CY", "PP"))
    assign("journal_title", ("JF", "JO", "T2"))
    assign("volume", ("VL",))
    assign("issue", ("IS",))
    assign("isbn", ("SN",))
    assign("doi", ("DO",))
    assign("abstract", ("AB", "N2"))
    assign("language", ("LA",))
    assign("version_label", ("ET",))
    assign("degree_institution", ("PB",)) if record.get("TY", [""])[0].casefold() == "thes" else None
    assign("publication_year", ("PY", "Y1", "DA"))
    start_page = _clean_text((record.get("SP") or [""])[0])
    end_page = _clean_text((record.get("EP") or [""])[0])
    if start_page:
        fields["page_range"] = f"{start_page}-{end_page}" if end_page and end_page != start_page else start_page
        sources["page_range"] = "SP/EP" if end_page else "SP"
    ris_type = _clean_text((record.get("TY") or [""])[0])
    if ris_type:
        fields["document_type"] = ris_type
        sources["document_type"] = "TY"
    return ParsedMetadataImport("ris", fields, sources, record)


def _scan_bibtex_entries(text: str) -> list[tuple[str, str, str]]:
    entries: list[tuple[str, str, str]] = []
    cursor = 0
    while True:
        match = re.search(r"@([A-Za-z]+)\s*([\{(])", text[cursor:])
        if not match:
            break
        entry_type = match.group(1).casefold()
        opener = match.group(2)
        closer = "}" if opener == "{" else ")"
        start = cursor + match.end()
        depth = 1
        quoted = False
        escaped = False
        index = start
        while index < len(text) and depth:
            character = text[index]
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = not quoted
            elif not quoted and character == opener:
                depth += 1
            elif not quoted and character == closer:
                depth -= 1
            index += 1
        if depth:
            raise MetadataImportError("invalid_bibtex", "BibTeX 记录括号没有闭合。")
        if entry_type not in {"comment", "preamble", "string"}:
            body = text[start : index - 1].strip()
            key, separator, fields_text = body.partition(",")
            if not separator or not key.strip():
                raise MetadataImportError("invalid_bibtex", "BibTeX 记录缺少 citation key 或字段。")
            entries.append((entry_type, key.strip(), fields_text))
        cursor = index
    return entries


def _bibtex_value(text: str, start: int) -> tuple[str, int]:
    parts: list[str] = []
    index = start
    while index < len(text):
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            break
        if text[index] == "{":
            depth = 1
            escaped = False
            value_start = index + 1
            index += 1
            while index < len(text) and depth:
                character = text[index]
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == "{":
                    depth += 1
                elif character == "}":
                    depth -= 1
                index += 1
            if depth:
                raise MetadataImportError("invalid_bibtex", "BibTeX 字段花括号没有闭合。")
            parts.append(text[value_start : index - 1])
        elif text[index] == '"':
            escaped = False
            value_start = index + 1
            index += 1
            while index < len(text):
                character = text[index]
                if escaped:
                    escaped = False
                elif character == "\\":
                    escaped = True
                elif character == '"':
                    break
                index += 1
            if index >= len(text):
                raise MetadataImportError("invalid_bibtex", "BibTeX 字段引号没有闭合。")
            parts.append(text[value_start:index])
            index += 1
        else:
            value_start = index
            while index < len(text) and text[index] not in {",", "#"}:
                index += 1
            parts.append(text[value_start:index].strip())
        while index < len(text) and text[index].isspace():
            index += 1
        if index < len(text) and text[index] == "#":
            index += 1
            continue
        break
    value = "".join(parts)
    value = value.replace("~", " ").replace(r"\&", "&").replace(r"\%", "%")
    value = value.replace("{", "").replace("}", "")
    return _clean_text(value), index


def _parse_bibtex_fields(fields_text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    index = 0
    while index < len(fields_text):
        while index < len(fields_text) and (fields_text[index].isspace() or fields_text[index] == ","):
            index += 1
        if index >= len(fields_text):
            break
        match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", fields_text[index:])
        if not match:
            raise MetadataImportError("invalid_bibtex", "BibTeX 字段名或等号格式无效。")
        name = match.group(1).casefold()
        index += match.end()
        value, index = _bibtex_value(fields_text, index)
        values[name] = value
        while index < len(fields_text) and fields_text[index].isspace():
            index += 1
        if index < len(fields_text) and fields_text[index] not in {","}:
            raise MetadataImportError("invalid_bibtex", "BibTeX 字段之间必须使用逗号分隔。")
    return values


def _parse_bibtex(text: str) -> ParsedMetadataImport:
    entry_type, record_key, fields_record = _require_single_record(_scan_bibtex_entries(text), "BibTeX")
    record = _parse_bibtex_fields(fields_record)
    mapping = {
        "title": "title",
        "subtitle": "subtitle",
        "author": "authors",
        "publisher": "publisher",
        "address": "publication_place",
        "location": "publication_place",
        "year": "publication_year",
        "isbn": "isbn",
        "doi": "doi",
        "journal": "journal_title",
        "journaltitle": "journal_title",
        "volume": "volume",
        "number": "issue",
        "issue": "issue",
        "pages": "page_range",
        "abstract": "abstract",
        "language": "language",
        "edition": "version_label",
        "school": "degree_institution",
        "institution": "report_institution",
    }
    fields: dict[str, Any] = {"document_type": entry_type}
    sources = {"document_type": f"@{entry_type}"}
    for source_name, field_name in mapping.items():
        value = record.get(source_name)
        if not value or field_name in fields:
            continue
        fields[field_name] = value
        sources[field_name] = source_name
    raw_record = {"entry_type": entry_type, "citation_key": record_key, "fields": record}
    return ParsedMetadataImport("bibtex", fields, sources, raw_record, record_key)


def _csl_author_name(value: Any) -> str:
    if not isinstance(value, dict):
        return _clean_text(value)
    if value.get("literal"):
        return _clean_text(value["literal"])
    family = _clean_text(value.get("family"))
    given = _clean_text(value.get("given"))
    if family and given:
        return f"{family}, {given}"
    return family or given


def _parse_csl_json(text: str) -> ParsedMetadataImport:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetadataImportError("invalid_json", "CSL-JSON 文件无法解析。") from exc
    record = _require_single_record(payload if isinstance(payload, list) else [payload], "CSL-JSON")
    if not isinstance(record, dict):
        raise MetadataImportError("invalid_csl_json", "CSL-JSON 记录必须是对象。")
    mapping = {
        "title": "title",
        "title-short": "subtitle",
        "publisher": "publisher",
        "publisher-place": "publication_place",
        "container-title": "journal_title",
        "volume": "volume",
        "issue": "issue",
        "page": "page_range",
        "ISBN": "isbn",
        "DOI": "doi",
        "abstract": "abstract",
        "language": "language",
        "edition": "version_label",
    }
    fields: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for source_name, field_name in mapping.items():
        if record.get(source_name) not in (None, "", []):
            fields[field_name] = record[source_name]
            sources[field_name] = source_name
    authors = [_csl_author_name(value) for value in record.get("author", [])]
    authors = [value for value in authors if value]
    if authors:
        fields["authors"] = authors
        sources["authors"] = "author"
    issued = record.get("issued")
    if isinstance(issued, dict):
        date_parts = issued.get("date-parts")
        if isinstance(date_parts, list) and date_parts and isinstance(date_parts[0], list) and date_parts[0]:
            fields["publication_year"] = date_parts[0][0]
            sources["publication_year"] = "issued.date-parts"
    if record.get("type"):
        fields["document_type"] = record["type"]
        sources["document_type"] = "type"
    record_key = _clean_text(record.get("id"))
    return ParsedMetadataImport("csl_json", fields, sources, record, record_key)


def _parse_sidecar_json(text: str) -> ParsedMetadataImport:
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MetadataImportError("invalid_json", "sidecar JSON 文件无法解析。") from exc
    if not isinstance(record, dict):
        raise MetadataImportError("invalid_sidecar_json", "sidecar JSON 必须是单个对象。")
    unknown = sorted(set(record) - set(FIELD_LIMITS) - SIDECAR_CONTROL_FIELDS)
    if unknown:
        raise MetadataImportError(
            "unsupported_fields",
            f"sidecar JSON 包含不受支持的字段：{', '.join(unknown[:10])}",
        )
    fields = {key: value for key, value in record.items() if key in FIELD_LIMITS}
    sources = {key: key for key in fields}
    return ParsedMetadataImport("sidecar_json", fields, sources, record)


def _json_safe_yaml_value(value: Any, *, depth: int = 0, counter: list[int] | None = None):
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > 2000:
        raise MetadataImportError("yaml_too_complex", "YAML 节点数量超过安全上限。")
    if depth > 8:
        raise MetadataImportError("yaml_too_deep", "YAML 嵌套层级超过安全上限。")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_yaml_value(item, depth=depth + 1, counter=counter) for item in value]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise MetadataImportError("invalid_yaml_key", "YAML 字段名必须是字符串。")
            result[key] = _json_safe_yaml_value(item, depth=depth + 1, counter=counter)
        return result
    return str(value)


def _parse_sidecar_yaml(text: str) -> ParsedMetadataImport:
    try:
        payload = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise MetadataImportError("invalid_yaml", "sidecar YAML 文件无法安全解析。") from exc
    record = _json_safe_yaml_value(payload)
    if not isinstance(record, dict):
        raise MetadataImportError("invalid_sidecar_yaml", "sidecar YAML 必须是单个对象。")
    unknown = sorted(set(record) - set(FIELD_LIMITS) - SIDECAR_CONTROL_FIELDS)
    if unknown:
        raise MetadataImportError(
            "unsupported_fields",
            f"sidecar YAML 包含不受支持的字段：{', '.join(unknown[:10])}",
        )
    fields = {key: value for key, value in record.items() if key in FIELD_LIMITS}
    sources = {key: key for key in fields}
    return ParsedMetadataImport("sidecar_yaml", fields, sources, record)
