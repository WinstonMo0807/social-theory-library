from __future__ import annotations

from datetime import date, datetime
import json
import re
import unicodedata
from uuid import UUID

from catalog.models import (
    KnowledgeNodeAlias,
    KnowledgeRelation,
    PersonNameVariant,
    TheoryTimelineEvent,
)


IDENTIFIER_SCHEMES = {
    "doi",
    "isbn",
    "isni",
    "loc",
    "openalex",
    "orcid",
    "viaf",
    "wikidata",
}


def normalize_text(value) -> str:
    return unicodedata.normalize("NFKC", " ".join(str(value or "").split())).strip()


def normalize_json(value):
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, str):
        return normalize_text(value)
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): normalize_json(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    return value


def stable_json(value) -> str:
    return json.dumps(
        normalize_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _mapping(value) -> dict:
    if not isinstance(value, dict):
        raise ValueError("候选值必须是结构化对象。")
    return dict(value)


def _uuid(value, field_name: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} 不是有效 UUID。") from exc


def _short_text(value, label: str, limit: int) -> str:
    text = normalize_text(value)
    if not text:
        raise ValueError(f"{label}不能为空。")
    if len(text) > limit:
        raise ValueError(f"{label}超过 {limit} 字符。")
    return text


def _identifier(value):
    row = _mapping(value)
    scheme = normalize_text(row.get("scheme")).casefold()
    identifier = _short_text(row.get("value"), "标识符", 500)
    if scheme not in IDENTIFIER_SCHEMES:
        raise ValueError("不支持的标识符类型。")
    return {"scheme": scheme, "value": identifier}


def _affiliation(value):
    row = _mapping(value)
    return {
        "name": _short_text(row.get("name"), "机构名称", 500),
        "role": normalize_text(row.get("role"))[:240],
        "start_year": row.get("start_year") or None,
        "end_year": row.get("end_year") or None,
    }


def _name_variant(value):
    row = _mapping(value)
    variant_type = normalize_text(row.get("variant_type")).casefold() or "alias"
    if variant_type not in PersonNameVariant.VariantType.values:
        raise ValueError("人物名称变体类型无效。")
    return {
        "name": _short_text(row.get("name"), "人物名称", 240),
        "language": normalize_text(row.get("language"))[:24] or "und",
        "variant_type": variant_type,
    }


def _publication_year(value):
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("出版年份必须是整数。") from exc
    if year < 1000 or year > 2100:
        raise ValueError("出版年份超出允许范围。")
    return year


def _isbn(value):
    text = re.sub(r"[^0-9Xx]", "", normalize_text(value))
    if len(text) not in {10, 13}:
        raise ValueError("ISBN 必须是 10 或 13 位。")
    return text.upper()


def _doi(value):
    text = normalize_text(value).removeprefix("https://doi.org/").removeprefix("http://doi.org/")
    if not re.fullmatch(r"10\.\d{4,9}/\S+", text, re.I):
        raise ValueError("DOI 格式无效。")
    return text


def _date(value):
    try:
        parsed = date.fromisoformat(normalize_text(value))
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD。") from exc
    return parsed.isoformat()


def _alias(value):
    row = _mapping(value)
    alias_type = normalize_text(row.get("alias_type")).casefold() or "alias"
    if alias_type not in KnowledgeNodeAlias.AliasType.values:
        raise ValueError("知识节点 alias type 无效。")
    return {
        "alias": _short_text(row.get("alias"), "别名", 240),
        "language": normalize_text(row.get("language"))[:16] or "und",
        "alias_type": alias_type,
    }


def _discipline(value):
    row = _mapping(value)
    relation_type = normalize_text(row.get("relation_type")).casefold() or "related"
    if relation_type not in {"primary", "related", "transferred"}:
        raise ValueError("知识节点学科关系类型无效。")
    return {
        "discipline_id": _uuid(row.get("discipline_id"), "discipline_id"),
        "relation_type": relation_type,
    }


def _subdiscipline(value):
    row = _mapping(value)
    return {
        "subdiscipline_node_id": _uuid(
            row.get("subdiscipline_node_id"), "subdiscipline_node_id"
        )
    }


def _relation(value):
    row = _mapping(value)
    relation_type = normalize_text(row.get("relation_type")).casefold()
    if relation_type not in KnowledgeRelation.RelationType.values:
        raise ValueError("理论关系类型无效。")
    return {
        "target_node_id": _uuid(row.get("target_node_id"), "target_node_id"),
        "relation_type": relation_type,
        "description": normalize_text(row.get("description"))[:4000],
    }


def _timeline(value, *, interpretive: bool):
    row = _mapping(value)
    event_type = normalize_text(row.get("event_type")).casefold()
    if event_type and event_type not in TheoryTimelineEvent.EventType.values:
        raise ValueError("时间线事件类型无效。")
    start_year = row.get("start_year")
    if start_year not in (None, ""):
        start_year = int(start_year)
    if not interpretive and start_year is None:
        raise ValueError("事实型时间线候选必须有开始年份。")
    return {
        "title": _short_text(row.get("title"), "事件标题", 300),
        "description": normalize_text(row.get("description"))[:5000],
        "event_type": event_type or (
            TheoryTimelineEvent.EventType.DEVELOPMENT
            if interpretive
            else TheoryTimelineEvent.EventType.PUBLICATION
        ),
        "start_year": start_year,
        "end_year": int(row["end_year"]) if row.get("end_year") not in (None, "") else None,
        "date_label": normalize_text(row.get("date_label"))[:120],
    }


def _topic_discipline(value):
    row = _mapping(value)
    return {"discipline_id": _uuid(row.get("discipline_id"), "discipline_id")}


def _reading_path_item(value):
    row = _mapping(value)
    node_id = row.get("node_id")
    work_id = row.get("work_id")
    if not node_id and not work_id:
        raise ValueError("阅读路径候选必须指向馆内 Work 或 KnowledgeNode。")
    return {
        "stage_name": _short_text(row.get("stage_name"), "阅读阶段", 160),
        "stage_description": normalize_text(row.get("stage_description"))[:4000],
        "node_id": _uuid(node_id, "node_id") if node_id else "",
        "work_id": _uuid(work_id, "work_id") if work_id else "",
        "recommendation_reason": normalize_text(row.get("recommendation_reason"))[:4000],
        "is_required": bool(row.get("is_required", False)),
    }


VALUE_NORMALIZERS = {
    "person_external_identifier": _identifier,
    "person_affiliation": _affiliation,
    "person_name_variant": _name_variant,
    "edition_publication_year": _publication_year,
    "edition_publisher": lambda value: _short_text(value, "出版社", 300),
    "edition_isbn": _isbn,
    "edition_isbn10": _isbn,
    "edition_isbn13": _isbn,
    "edition_doi": _doi,
    "edition_version_label": lambda value: _short_text(value, "版本说明", 120),
    "edition_publication_place": lambda value: _short_text(value, "出版地", 200),
    "edition_journal_title": lambda value: _short_text(value, "期刊名", 300),
    "edition_volume": lambda value: _short_text(value, "卷", 40),
    "edition_issue": lambda value: _short_text(value, "期", 40),
    "edition_page_range": lambda value: _short_text(value, "页码范围", 80),
    "edition_series": lambda value: _short_text(value, "丛书", 300),
    "edition_extent": lambda value: _short_text(value, "载体范围", 160),
    "edition_responsibility_statement": lambda value: _short_text(value, "责任说明", 4000),
    "edition_degree_institution": lambda value: _short_text(value, "学位授予单位", 300),
    "edition_degree_type": lambda value: _short_text(value, "学位类型", 120),
    "edition_report_institution": lambda value: _short_text(value, "报告责任机构", 300),
    "work_title": lambda value: _short_text(value, "作品题名", 600),
    "work_subtitle": lambda value: _short_text(value, "副题名", 600),
    "work_original_title": lambda value: _short_text(value, "原题名", 600),
    "work_uniform_title": lambda value: _short_text(value, "规范题名", 600),
    "work_language": lambda value: _short_text(value, "作品语言", 32),
    "work_original_language": lambda value: _short_text(value, "原作语言", 32),
    "work_abstract": lambda value: _short_text(value, "作品摘要", 20000),
    "work_discipline": _discipline,
    "work_subdiscipline": _subdiscipline,
    "work_first_publication_date": _date,
    "discipline_foreign_name": lambda value: _short_text(value, "外文名称", 240),
    "subdiscipline_foreign_name": lambda value: _short_text(value, "外文名称", 240),
    "knowledge_node_alias": _alias,
    "knowledge_node_discipline": _discipline,
    "knowledge_node_subdiscipline": _subdiscipline,
    "knowledge_relation": _relation,
    "knowledge_node_timeline_fact": lambda value: _timeline(value, interpretive=False),
    "knowledge_node_timeline_interpretation": lambda value: _timeline(value, interpretive=True),
    "topic_discipline": _topic_discipline,
    "reading_path_item": _reading_path_item,
}


def normalize_candidate_value(mutation_adapter: str, value):
    try:
        normalizer = VALUE_NORMALIZERS[mutation_adapter]
    except KeyError as exc:
        raise ValueError("该字段尚未配置候选值校验器。") from exc
    return normalize_json(normalizer(value))


def candidate_identity_value(mutation_adapter: str, value):
    """Return the source-independent value used for candidate deduplication."""

    value = normalize_json(value)
    if mutation_adapter == "knowledge_relation":
        return {
            "target_node_id": value.get("target_node_id"),
            "relation_type": value.get("relation_type"),
        }
    if mutation_adapter in {
        "knowledge_node_timeline_fact",
        "knowledge_node_timeline_interpretation",
    }:
        return {
            key: value.get(key)
            for key in ("title", "event_type", "start_year", "end_year", "date_label")
        }
    return value
