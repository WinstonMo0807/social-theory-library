from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from billiard.exceptions import SoftTimeLimitExceeded
from django.db.models import Count, Q

from catalog.models import (
    Discipline,
    Edition,
    KnowledgeNode,
    OrganizationAuthority,
    Person,
    PublisherAuthority,
    ReadingPath,
    Subdiscipline,
    TheorySchool,
    Topic,
    Work,
)
from catalog.services.authority_suggestions import authority_suggestions
from catalog.services.field_enrichment.web import WebSearchError, configured_web_search_adapter

from .context import ResearchContext
from .ranking import score_candidate


ENTITY_DISCOVERY_VERSION = "universal-entity-discovery-v1"
SUPPORTED_ENTITY_TYPES = (
    "person",
    "work",
    "theory",
    "topic",
    "knowledge_node",
    "discipline",
    "subdiscipline",
    "organization",
    "institution",
    "publisher",
    "journal",
    "reading_path",
)

DRAFT_CREATABLE_ENTITY_TYPES = {
    "person",
    "work",
    "knowledge_node",
    "organization",
}


def _external_actions(entity_type: str) -> list[str]:
    actions = ["inspect"]
    if entity_type in DRAFT_CREATABLE_ENTITY_TYPES:
        actions.append("create_draft")
    actions.extend(["keep_unresolved", "reject"])
    return actions


@dataclass(frozen=True)
class EntityDiscoveryRequest:
    entity_type: str
    field: str
    query: str
    context: ResearchContext | None
    include_external: bool = True
    include_web: bool = True
    limit: int = 12


def _status(row: Any) -> str:
    return str(
        getattr(row, "authority_status", "")
        or getattr(row, "editorial_status", "")
        or getattr(row, "status", "")
        or "unknown"
    )


def _formal(status: str) -> bool:
    return status in {"published", "verified", "approved", "active"}


def _candidate(
    *,
    identifier: str,
    entity_type: str,
    label: str,
    secondary: str = "",
    entity_id: str | None = None,
    status: str = "unknown",
    group: str,
    source: str,
    provider: str = "",
    reasons: list[str] | None = None,
    conflicts: list[str] | None = None,
    external_ids: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    source_url: str = "",
    source_record_id: str = "",
    actions: list[str] | None = None,
    evidence_status: str = "evidence",
) -> dict[str, Any]:
    return {
        "id": identifier,
        "kind": "entity_discovery",
        "entity_type": entity_type,
        "entity_id": entity_id,
        "label": label,
        "primary_name": label,
        "secondary_identity": secondary,
        "entity_status": status,
        "candidate_group": group,
        "source": source,
        "provider": provider or source,
        "match_reasons": list(reasons or []),
        "conflicts": list(conflicts or []),
        "external_ids": dict(external_ids or {}),
        "metadata": metadata or {},
        "evidence": list(evidence or []),
        "evidence_count": len(evidence or []),
        "evidence_status": evidence_status,
        "source_url": source_url,
        "source_record_id": source_record_id,
        "available_actions": list(actions or ["inspect"]),
        "human_confirmation_required": True,
    }


def _local_people(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Person.objects.filter(
        Q(preferred_name__icontains=query)
        | Q(original_name__icontains=query)
        | Q(aliases__icontains=query)
    ).annotate(collection_count=Count("contributions__edition__work", distinct=True))[:limit]
    output = []
    for row in rows:
        status = _status(row)
        secondary = row.original_name
        years = "–".join(str(value) for value in (row.birth_year, row.death_year) if value)
        if years:
            secondary = " · ".join(value for value in (secondary, years) if value)
        output.append(_candidate(
            identifier=f"local:person:{row.id}",
            entity_type="person",
            entity_id=str(row.id),
            label=row.preferred_name,
            secondary=secondary,
            status=status,
            group="local" if _formal(status) else "local_draft",
            source="library",
            reasons=["馆内 Person 名称或别名匹配"],
            conflicts=["同名不能自动证明为同一人物"],
            external_ids=row.external_ids,
            metadata={
                "original_name": row.original_name,
                "aliases": list(row.aliases or []),
                "birth_year": row.birth_year,
                "death_year": row.death_year,
                "collection_count": row.collection_count,
            },
            actions=["inspect", "link_existing"],
        ))
    return output


def _local_works(query: str, limit: int) -> list[dict[str, Any]]:
    rows = Work.objects.filter(
        Q(title__icontains=query)
        | Q(original_title__icontains=query)
        | Q(uniform_title__icontains=query)
        | Q(search_aliases__icontains=query)
    ).annotate(edition_count=Count("editions", distinct=True))[:limit]
    output = []
    for row in rows:
        published = row.editions.filter(state="published").exists()
        output.append(_candidate(
            identifier=f"local:work:{row.id}",
            entity_type="work",
            entity_id=str(row.id),
            label=row.title,
            secondary=row.original_title or row.subtitle,
            status="published" if published else "draft",
            group="local" if published else "local_draft",
            source="library",
            reasons=["馆内 Work 题名或别名匹配"],
            conflicts=["同题名仍可能是不同作品、译作或版本"],
            metadata={"document_type": row.document_type, "edition_count": row.edition_count},
            actions=["inspect", "link_existing"],
        ))
    return output


def _named_rows(model, query: str, *, name_fields: tuple[str, ...], entity_type: str, limit: int):
    condition = Q()
    for field_name in name_fields:
        condition |= Q(**{f"{field_name}__icontains": query})
    rows = model.objects.filter(condition)[:limit]
    output = []
    for row in rows:
        label = str(
            getattr(row, "name", "")
            or getattr(row, "canonical_name_zh", "")
            or getattr(row, "preferred_name", "")
            or getattr(row, "canonical_name", "")
            or getattr(row, "title", "")
        )
        secondary = str(
            getattr(row, "foreign_name", "")
            or getattr(row, "canonical_name_en", "")
            or getattr(row, "original_name", "")
            or ""
        )
        status = _status(row)
        output.append(_candidate(
            identifier=f"local:{entity_type}:{row.pk}",
            entity_type=entity_type,
            entity_id=str(row.pk),
            label=label,
            secondary=secondary,
            status=status,
            group="local" if _formal(status) else "local_draft",
            source="library",
            reasons=[f"馆内 {entity_type} 名称匹配"],
            metadata={
                "slug": str(getattr(row, "slug", "") or ""),
                "description": str(getattr(row, "description", "") or getattr(row, "summary", "") or "")[:500],
            },
            actions=["inspect", "link_existing"],
        ))
    return output


def _local_journals(query: str, limit: int) -> list[dict[str, Any]]:
    rows = (
        Edition.objects.exclude(journal_title="")
        .filter(journal_title__icontains=query)
        .values("journal_title")
        .annotate(collection_count=Count("id"))
        .order_by("journal_title")[:limit]
    )
    return [
        _candidate(
            identifier=f"local:journal:{sha256(row['journal_title'].casefold().encode()).hexdigest()[:20]}",
            entity_type="journal",
            entity_id=None,
            label=row["journal_title"],
            status="catalogued",
            group="local",
            source="library",
            reasons=["馆内 Edition 期刊名匹配"],
            metadata={"collection_count": row["collection_count"]},
            actions=["inspect", "use_value"],
        )
        for row in rows
    ]


def _local_candidates(entity_type: str, query: str, limit: int) -> list[dict[str, Any]]:
    if entity_type == "person":
        return _local_people(query, limit)
    if entity_type == "work":
        return _local_works(query, limit)
    if entity_type == "theory":
        return _named_rows(TheorySchool, query, name_fields=("name", "foreign_name"), entity_type="theory", limit=limit)
    if entity_type == "topic":
        return _named_rows(Topic, query, name_fields=("name",), entity_type="topic", limit=limit)
    if entity_type == "knowledge_node":
        return _named_rows(KnowledgeNode, query, name_fields=("canonical_name_zh", "canonical_name_en"), entity_type="knowledge_node", limit=limit)
    if entity_type == "discipline":
        return _named_rows(Discipline, query, name_fields=("name", "foreign_name"), entity_type="discipline", limit=limit)
    if entity_type == "subdiscipline":
        return _named_rows(Subdiscipline, query, name_fields=("name", "foreign_name"), entity_type="subdiscipline", limit=limit)
    if entity_type in {"organization", "institution"}:
        return _named_rows(OrganizationAuthority, query, name_fields=("preferred_name", "original_name"), entity_type="organization", limit=limit)
    if entity_type == "publisher":
        return _named_rows(PublisherAuthority, query, name_fields=("canonical_name",), entity_type="publisher", limit=limit)
    if entity_type == "journal":
        return _local_journals(query, limit)
    if entity_type == "reading_path":
        return _named_rows(ReadingPath, query, name_fields=("title",), entity_type="reading_path", limit=limit)
    return []


AUTHORITY_TYPE_MAP = {
    "person": "person",
    "theory": "theory_tradition",
    "topic": "topic",
    "knowledge_node": "concept",
    "discipline": "discipline",
    "subdiscipline": "subdiscipline",
}


def _candidate_deduplication_key(row: dict[str, Any]) -> tuple[str, str, str]:
    group = str(row.get("candidate_group") or "")
    if group not in {"authority", "external_web"}:
        return (
            group,
            str(row.get("entity_id") or ""),
            str(row.get("label") or "").casefold(),
        )

    provider = str(row.get("provider") or row.get("source") or "").strip().casefold()
    external_ids = tuple(
        sorted(
            (
                str(key).strip().casefold(),
                str(value).strip().casefold(),
            )
            for key, value in dict(row.get("external_ids") or {}).items()
            if str(key).strip() and str(value).strip()
        )
    )
    if external_ids:
        stable_identity = f"external_ids:{external_ids!r}"
    elif str(row.get("source_url") or "").strip():
        stable_identity = f"source_url:{str(row['source_url']).strip()}"
    elif str(row.get("source_record_id") or "").strip():
        stable_identity = f"source_record_id:{str(row['source_record_id']).strip()}"
    else:
        stable_identity = f"candidate_id:{str(row.get('id') or '').strip()}"
    return group, provider, stable_identity


class UniversalEntityDiscovery:
    def discover(self, request: EntityDiscoveryRequest) -> dict[str, Any]:
        entity_type = str(request.entity_type or "").strip().casefold()
        if entity_type == "institution":
            entity_type = "organization"
        if entity_type not in SUPPORTED_ENTITY_TYPES:
            raise ValueError("不支持的 Entity Discovery 类型。")
        query = " ".join(str(request.query or "").split()).strip()[:240]
        if len(query) < 2:
            raise ValueError("Entity Discovery 至少需要 2 个字符。")
        limit = max(2, min(int(request.limit), 24))
        candidates = _local_candidates(entity_type, query, limit)
        warnings: list[dict[str, str]] = []
        providers_attempted = ["local"]

        authority_type = AUTHORITY_TYPE_MAP.get(entity_type)
        if request.include_external and authority_type:
            providers_attempted.append("authority")
            try:
                payload = authority_suggestions(authority_type, query)
                warnings.extend({"code": "authority_partial", "detail": str(value)[:500]} for value in payload.get("warnings") or [])
                for row in payload.get("results") or []:
                    source = str(row.get("provider") or row.get("source") or "authority").casefold()
                    if source in {"library", "local", "馆内"} or str(row.get("id") or "").startswith("local:"):
                        continue
                    external_type = entity_type
                    evidence = [{
                        "source_record_id": row.get("source_record_id"),
                        "source_url": row.get("source_url"),
                        "source": row.get("source") or row.get("provider"),
                        "supporting_text": row.get("description") or row.get("label"),
                    }]
                    candidates.append(_candidate(
                        identifier=f"authority:{source}:{row.get('id')}",
                        entity_type=external_type,
                        entity_id=None,
                        label=str(row.get("label") or ""),
                        secondary=str(row.get("original_name") or row.get("description") or "")[:300],
                        status="external_candidate",
                        group="authority",
                        source=str(row.get("source") or source),
                        provider=source,
                        reasons=list(row.get("match_reasons") or []),
                        conflicts=list(row.get("conflicts") or []),
                        external_ids=dict(row.get("external_ids") or {}),
                        metadata={
                            "aliases": list(row.get("aliases") or []),
                            "birth_year": row.get("birth_year"),
                            "death_year": row.get("death_year"),
                            "source_entity_type": authority_type,
                        },
                        evidence=evidence,
                        source_url=str(row.get("source_url") or ""),
                        source_record_id=str(row.get("source_record_id") or ""),
                        actions=_external_actions(entity_type),
                        evidence_status="structured_evidence",
                    ))
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                warnings.append({"code": "authority_unavailable", "detail": str(exc)[:500]})

        if request.include_external and request.include_web:
            providers_attempted.append("searxng")
            try:
                results, _record = configured_web_search_adapter().search(query, limit=min(limit, 8))
                if not results:
                    warnings.append({"code": "web_search_zero_results", "detail": "一般 Web 没有返回结果。"})
                for index, result in enumerate(results):
                    candidates.append(_candidate(
                        identifier=f"web:{sha256(f'{entity_type}:{result.url}'.encode()).hexdigest()[:24]}:{index}",
                        entity_type=entity_type,
                        entity_id=None,
                        label=result.title or result.url,
                        secondary=result.snippet[:300],
                        status="research_lead",
                        group="external_web",
                        source=result.source_class,
                        provider="searxng",
                        reasons=["SearXNG 发现公开来源", "搜索摘要仅为发现线索"],
                        conflicts=[],
                        metadata={"query": query, "url": result.url},
                        source_url=result.url,
                        actions=_external_actions(entity_type),
                        evidence_status="lead_only",
                    ))
            except WebSearchError as exc:
                warnings.append({"code": getattr(exc, "code", "web_search_failed"), "detail": str(exc)[:500]})
            except SoftTimeLimitExceeded:
                raise
            except Exception as exc:
                warnings.append({"code": "web_search_failed", "detail": str(exc)[:500]})

        candidates.append(_candidate(
            identifier=f"unresolved:{entity_type}:{sha256(query.casefold().encode()).hexdigest()[:24]}",
            entity_type=entity_type,
            entity_id=None,
            label=query,
            secondary="保留当前文本，不创建或替换正式实体。",
            status="unresolved",
            group="unresolved",
            source="unresolved",
            reasons=["管理员可以保持未解析，后续继续核对"],
            actions=["inspect", "keep_unresolved"],
            evidence_status="none",
        ))

        deduplicated: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in candidates:
            if not row.get("label"):
                continue
            score = score_candidate(row, query=query, expected_entity_types=(entity_type,))
            if score.field_fit_score <= 0:
                continue
            row["score_components"] = score.payload()
            row["confidence"] = score.total
            key = _candidate_deduplication_key(row)
            previous = deduplicated.get(key)
            if previous is None or row["confidence"] > previous["confidence"]:
                deduplicated[key] = row
        ordered = sorted(
            deduplicated.values(),
            key=lambda row: (
                {"local": 0, "local_draft": 1, "authority": 2, "external_web": 3, "unresolved": 4}.get(str(row.get("candidate_group")), 9),
                -float(row.get("confidence") or 0),
                str(row.get("label")),
            ),
        )[: max(limit * 4, 12)]
        groups = []
        labels = {
            "local": "馆内已有",
            "local_draft": "馆内草稿 / 待审核",
            "authority": "权威来源候选",
            "external_web": "一般网络候选",
            "unresolved": "未解析",
        }
        for key in labels:
            count = sum(1 for row in ordered if row.get("candidate_group") == key)
            if count:
                groups.append({"key": key, "label": labels[key], "count": count})
        external_failed = bool(warnings) and any(row["code"] not in {"web_search_zero_results"} for row in warnings)
        context_fingerprint = (
            request.context.fingerprint
            if request.context is not None
            else sha256(
                f"{ENTITY_DISCOVERY_VERSION}:{entity_type}:{request.field}:{query}".encode()
            ).hexdigest()
        )
        return {
            "version": ENTITY_DISCOVERY_VERSION,
            "entity_type": entity_type,
            "field": request.field,
            "query": query,
            "context_fingerprint": context_fingerprint,
            "groups": groups,
            "results": ordered,
            "warnings": warnings,
            "status": "degraded" if external_failed and any(row.get("candidate_group") in {"local", "local_draft"} for row in ordered) else "failed" if external_failed and len(ordered) == 1 else "healthy",
            "providers_attempted": providers_attempted,
            "multiple_candidates": len(ordered) > 1,
        }
