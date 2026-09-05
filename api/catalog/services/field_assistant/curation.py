"""Field-scoped curation suggestions over the existing evidence services.

This adapter only prepares evidence. Existing editorial mutations remain the
sole acceptance path; a lookup never changes canonical entities or indexes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import unicodedata

import httpx
from django.core.cache import cache
from django.db.models import Q
from django.utils import timezone

from catalog.models import (
    Discipline, EnrichmentCandidate, KnowledgeNode, Person, Subdiscipline, Topic,
)
from catalog.services.authority_suggestions import authority_suggestions
from catalog.services.field_enrichment import FieldEnrichmentRequest, FieldEnrichmentService
from catalog.services.field_enrichment.policies import FIELD_POLICIES
from catalog.services.field_enrichment.targets import get_target

logger = logging.getLogger(__name__)

AUTHORITY_TYPES = {"person", "concept", "discipline", "subdiscipline", "theory_tradition", "topic"}
TARGET_TYPES = {"person", "work", "edition", "discipline", "subdiscipline", "knowledge_node", "topic", "reading_path"}
WORK_CLAIM_FIELDS = {"core_viewpoint", "major_criticism", "major_response"}
SOURCE_LABELS = {
    "publisher": "出版社资料", "identifier_registry": "权威资料",
    "national_library": "权威资料", "library_catalog": "权威资料",
    "university": "权威资料", "research_institute": "权威资料",
    "academic_journal": "权威资料", "professional_association": "权威资料",
    "scholarly_encyclopedia": "权威资料", "scholar_homepage": "权威资料",
}


def _text(value):
    return str(value).strip() if isinstance(value, (str, int, float)) else ""


def _strings(value):
    if not isinstance(value, list):
        return []
    return [text for item in value if (text := _text(item) or (_text(item.get("detail") or item.get("message") or item.get("name") or item.get("alias")) if isinstance(item, dict) else ""))]


def _key(value):
    return " ".join(unicodedata.normalize("NFKC", _text(value)).casefold().split())


def _value_label(value):
    if isinstance(value, dict):
        return next((_text(value.get(name)) for name in ("label", "name", "alias", "foreign_name", "canonical_name_zh", "canonical_name_en", "title", "value", "stage_name") if _text(value.get(name))), "")
    return _text(value)


def _identity(row, *, local=False):
    label = _text(row.get("label") or row.get("preferred_name") or row.get("canonical_name_zh") or row.get("name"))
    if not label:
        return None
    original = _text(row.get("original_name") or row.get("canonical_name_en") or row.get("foreign_name"))
    conflicts = _strings(row.get("conflicts"))
    summary = _text(row.get("description")) or ("馆内已有正式记录，请核对是否为同一对象。" if local else "资料中的名称与当前字段相符，请核对身份。")
    return {
        "key": f"{_key(label)}:{row.get('birth_year') or ''}:{row.get('death_year') or ''}", "label": label, "secondary": original,
        "summary": summary, "statusLabel": "存在冲突" if conflicts else "需要确认",
        "conflicts": conflicts,
        "evidence": [{"category": "馆内已有记录" if local else "权威资料", "summary": summary, "url": _text(row.get("source_url"))}],
        "authority": {
            "label": label, "originalName": original, "aliases": _strings(row.get("aliases")),
            "description": _text(row.get("description")),
            "birthYear": row.get("birth_year") if isinstance(row.get("birth_year"), int) else None,
            "deathYear": row.get("death_year") if isinstance(row.get("death_year"), int) else None,
        },
    }


def _formal_identity_rows(kind, query):
    if not query:
        return []
    if kind == "person":
        return [{"label": row.preferred_name, "original_name": row.original_name,
                 "aliases": list(row.name_variants.filter(is_verified=True).values_list("name", flat=True)),
                 "birth_year": row.birth_year, "death_year": row.death_year}
                for row in Person.objects.filter(
                    Q(preferred_name__icontains=query) | Q(original_name__icontains=query),
                    authority_status="verified", scholar_profile__editorial_status="published",
                )[:12]]
    if kind in {"concept", "theory_tradition"}:
        return [{"label": row.canonical_name_zh, "canonical_name_en": row.canonical_name_en,
                 "description": row.summary,
                 "aliases": list(row.aliases.values_list("alias", flat=True))}
                for row in KnowledgeNode.objects.filter(
                    Q(canonical_name_zh__icontains=query) | Q(canonical_name_en__icontains=query),
                    status="published", node_type=kind,
                )[:12]]
    model = {"topic": Topic, "discipline": Discipline, "subdiscipline": Subdiscipline}.get(kind)
    if model is None:
        return []
    return [{"label": row.name, "foreign_name": getattr(row, "foreign_name", ""),
             "description": getattr(row, "description", "")}
            for row in model.objects.filter(name__icontains=query, editorial_status="published")[:12]]


def _enrichment(row):
    if row.status != EnrichmentCandidate.Status.PENDING:
        return None
    evidence = [{"category": SOURCE_LABELS.get(item.source_class, "其他外部资料"),
                 "summary": item.supporting_text or item.source_title or "请核对资料中的字段值。",
                 "url": item.canonical_url}
                for item in row.evidence_records.all() if item.is_current]
    conflicts = _strings(row.conflicts)
    label = _value_label(row.proposed_value) or {
        "discipline": "学科关联建议", "subdiscipline": "子学科关联建议",
        "relation": "关系建议", "timeline_fact": "时间信息建议",
        "timeline_interpretation": "时间说明建议", "item": "阅读内容建议",
    }.get(row.field_name, "字段建议")
    distinct_sources = len({item["url"] for item in evidence if item["url"]})
    return {
        "key": _key(label) if _value_label(row.proposed_value) else f"{row.field_name}:{row.pk}",
        "label": label, "secondary": "", "summary": "多项资料支持同一个字段值。" if distinct_sources > 1 else "请核对依据后决定是否采用。",
        "statusLabel": "存在冲突" if conflicts else "建议采用" if distinct_sources > 1 and row.identity_status == "confirmed" else "需要确认",
        "conflicts": conflicts, "evidence": evidence[:8],
        "enrichment": {"id": str(row.pk), "proposed_value": row.proposed_value},
    }


def _merge(rows):
    merged = {}
    for row in rows:
        if not row:
            continue
        current = merged.get(row["key"])
        if current is None:
            merged[row["key"]] = row
            continue
        known = {(item["category"], item["summary"], item.get("url", "")) for item in current["evidence"]}
        current["evidence"].extend(item for item in row["evidence"] if (item["category"], item["summary"], item.get("url", "")) not in known)
        current["conflicts"] = list(dict.fromkeys([*current["conflicts"], *row["conflicts"]]))
        if "enrichment" in row:
            current["enrichment"] = row["enrichment"]
        if "authority" in row and "authority" not in current:
            current["authority"] = row["authority"]
        if current["conflicts"]:
            current["statusLabel"] = "存在冲突"
        if len(current["evidence"]) > 1:
            current["summary"] = "多个资料来源支持同一个字段值。"
    return list(merged.values())


def _work_claim_field(target, field_name, *, context, actor):
    from catalog.services.claims.curation import high_value_claim_candidates

    edition_id = context.get("edition_id")
    if edition_id and not target.editions.filter(pk=edition_id).exists():
        raise ValueError("该版本不属于当前作品。")
    candidates = high_value_claim_candidates(
        target, reviewer=actor, kind=field_name, edition_id=edition_id, limit=5,
    )
    rows = []
    for candidate in candidates:
        conflicts = [value.replace("Editor", "管理员").replace("命题簇", "观点") for value in _strings(candidate.get("conflicts"))]
        rows.append({
            "key": str(candidate["id"]), "label": candidate["label"], "secondary": "",
            "summary": "来自当前作品原文，请核对语境后采用。",
            "statusLabel": "存在冲突" if conflicts else "需要确认", "conflicts": conflicts,
            "evidence": [{"category": "来自本书", "summary": entry.get("supporting_text", ""), "url": entry.get("url", "")}
                         for entry in candidate.get("evidence", [])],
            "claim": {"id": str(candidate["id"]), "kind": candidate["curated_kind"], "decision_url": candidate["decision_url"]},
        })
    return {"results": rows[:3], "more_results": rows[3:], "has_more": len(rows) > 3,
            "message": "" if rows else "目前没有依据充分的建议，可以稍后处理。",
            "field": {"name": field_name}, "scope": "curation"}


def lookup_curation_field(*, object_type, object_id=None, field_name="identity", query="", authority_type="", current_value=None, form_context=None, actor=None):
    """Aggregate first, then expose a small field-specific result to Admin."""
    if object_type not in TARGET_TYPES:
        raise ValueError("不支持的策展对象。")
    if authority_type and authority_type not in AUTHORITY_TYPES:
        raise ValueError("不支持的馆内对象类型。")
    target = get_target(object_type, object_id) if object_id else None
    query = " ".join(str(query or "").split())[:240]
    context = form_context if isinstance(form_context, dict) else {}
    if object_type == "work" and field_name in WORK_CLAIM_FIELDS:
        if target is None:
            raise ValueError("请先保存作品，再查找观点建议。")
        # Reuse the existing bounded, evidence-backed claim selector. Do not
        # cache reviewer decisions or introduce another interpretation pipeline.
        return _work_claim_field(target, field_name, context=context, actor=actor)
    digest = hashlib.sha256(json.dumps([object_type, str(object_id or ""), field_name, query, authority_type, current_value, context, str(getattr(target, "updated_at", ""))], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
    cache_key = f"curation-field-assistant:v304:{digest}"
    cached = cache.get(cache_key)
    if cached is not None:
        identifiers = [row["enrichment"]["id"] for row in [*cached["results"], *cached.get("more_results", [])] if row.get("enrichment")]
        if not identifiers or EnrichmentCandidate.objects.filter(pk__in=identifiers, status="pending").count() == len(set(identifiers)):
            return cached
        cache.delete(cache_key)
    rows = []
    notices = []
    local = _formal_identity_rows(authority_type, query) if authority_type else []
    rows.extend(_identity(row, local=True) for row in local)
    policy = next((row for row in FIELD_POLICIES.for_target(object_type) if row.field_name == field_name), None)
    if target is not None and policy is not None:
        candidates = list(EnrichmentCandidate.objects.filter(target_type=object_type, target_id=target.pk, field_name=field_name, status="pending", refresh_after__gte=timezone.now()).prefetch_related("evidence_records").order_by("-confidence")[:30])
        if not candidates:
            try:
                result = FieldEnrichmentService().enrich(FieldEnrichmentRequest(
                    target_type=object_type, target_id=target.pk, field_names=(field_name,),
                    current_value={field_name: current_value} if current_value is not None else None,
                    form_context=context, requested_mode="full", visibility="admin",
                ), actor=actor)
                candidates = list(result.candidates)
                if result.errors:
                    notices.append("部分资料暂时不可用，可以继续手工编辑。")
            except (httpx.HTTPError, OSError, TimeoutError) as exc:
                logger.warning("curation field evidence unavailable type=%s field=%s error=%s", object_type, field_name, type(exc).__name__)
                notices.append("资料查询暂时不可用，可以继续手工编辑。")
        rows.extend(_enrichment(row) for row in candidates)
    if authority_type and len(query) >= 2 and not local:
        try:
            # The provider's local entries may include editorial drafts. Only
            # this adapter's formal-query result can be labelled internal.
            result = authority_suggestions(authority_type, query)
            rows.extend(_identity(row) for row in result.get("results", []) if not str(row.get("id", "")).startswith("local:"))
            if result.get("warnings"):
                notices.append("部分资料暂时不可用，已保留其余依据。")
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            logger.warning("curation identity evidence unavailable type=%s error=%s", object_type, type(exc).__name__)
            notices.append("身份资料暂时不可用，可以继续手工编辑。")
    combined = _merge(rows)
    response = {"results": combined[:3], "more_results": combined[3:12], "has_more": len(combined) > 3, "message": " ".join(dict.fromkeys(notices)), "field": {"name": field_name}, "scope": "curation"}
    cache.set(cache_key, response, timeout=60)
    return response
