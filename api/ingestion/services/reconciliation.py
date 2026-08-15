from __future__ import annotations

from difflib import SequenceMatcher
import unicodedata

from django.db import transaction
from django.db.models import Q

from catalog.models import KnowledgeNode, OrganizationAuthority, Person, PublisherAuthority, Work
from ingestion.models import EntityResolutionCandidate, ReviewTask, UploadItem


def normalized_label(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold().strip()
    return "".join(character for character in value if character.isalnum())


def _score_label(source_name: str, candidate_name: str) -> tuple[float, list[str]]:
    source = normalized_label(source_name)
    candidate = normalized_label(candidate_name)
    if not source or not candidate:
        return 0, []
    if source == candidate:
        return 0.82, ["规范化名称完全一致", "仅名称一致，仍需人工确认身份"]
    ratio = SequenceMatcher(None, source, candidate).ratio()
    if ratio >= 0.9:
        return round(0.64 + (ratio - 0.9), 4), ["名称高度相似", "缺少强标识符"]
    if ratio >= 0.72:
        return round(0.4 + (ratio - 0.72), 4), ["名称可能相关", "需要更多身份属性"]
    return 0, []


def _person_matches(source_name: str) -> list[dict]:
    source = normalized_label(source_name)
    query = Person.objects.filter(
        Q(preferred_name__iexact=source_name.strip())
        | Q(original_name__iexact=source_name.strip())
        | Q(preferred_name__icontains=source_name.strip())
    ).order_by("preferred_name")[:20]
    matches = []
    for person in query:
        labels = [person.preferred_name, person.original_name, *list(person.aliases or [])]
        scores = [_score_label(source_name, value) for value in labels if value]
        if not scores:
            continue
        score, reasons = max(scores, key=lambda value: value[0])
        if score <= 0:
            continue
        strong_ids = {
            key: value
            for key, value in dict(person.external_ids or {}).items()
            if value and key.casefold() in {"orcid", "viaf", "isni", "wikidata", "openalex", "loc"}
        }
        if strong_ids:
            reasons = [*reasons, "候选实体已有权威标识符"]
        matches.append(
            {
                "entity_type": "person",
                "entity_id": str(person.id),
                "label": person.preferred_name,
                "aliases": person.aliases,
                "external_ids": person.external_ids,
                "supporting_properties": {
                    "original_name": person.original_name,
                    "birth_year": person.birth_year,
                    "death_year": person.death_year,
                    "authority_status": person.authority_status,
                },
                "score": score,
                "reasons": reasons,
                "conflicts": ["同名不能自动证明为同一人物"],
                "preview_data": {"biography": person.biography[:500]},
            }
        )
    return sorted(matches, key=lambda value: value["score"], reverse=True)[:8]


def _work_matches(source_name: str) -> list[dict]:
    rows = Work.objects.filter(
        Q(title__icontains=source_name.strip())
        | Q(original_title__icontains=source_name.strip())
        | Q(uniform_title__icontains=source_name.strip())
    ).prefetch_related("editions")[:20]
    values = []
    for work in rows:
        score, reasons = _score_label(source_name, work.uniform_title or work.title)
        if score <= 0:
            continue
        values.append(
            {
                "entity_type": "work",
                "entity_id": str(work.id),
                "label": work.title,
                "aliases": work.search_aliases,
                "external_ids": {},
                "supporting_properties": {
                    "document_type": work.document_type,
                    "language": work.language,
                    "edition_count": work.editions.count(),
                },
                "score": score,
                "reasons": reasons,
                "conflicts": ["题名相同仍可能是不同作品或不同译作"],
                "preview_data": {"subtitle": work.subtitle, "original_title": work.original_title},
            }
        )
    return sorted(values, key=lambda value: value["score"], reverse=True)[:8]


def _publisher_matches(source_name: str) -> list[dict]:
    rows = PublisherAuthority.objects.filter(canonical_name__icontains=source_name.strip())[:20]
    values = []
    for publisher in rows:
        labels = [publisher.canonical_name, *list(publisher.aliases or [])]
        score, reasons = max((_score_label(source_name, value) for value in labels if value), default=(0, []))
        if score <= 0:
            continue
        values.append(
            {
                "entity_type": "publisher_authority",
                "entity_id": str(publisher.id),
                "label": publisher.canonical_name,
                "aliases": publisher.aliases,
                "external_ids": {},
                "supporting_properties": {
                    "country": publisher.country,
                    "valid_from": publisher.valid_from,
                    "valid_to": publisher.valid_to,
                    "possible_places": publisher.possible_places,
                },
                "score": score,
                "reasons": reasons,
                "conflicts": ["权威出版社不能替代版本中原样出版项"],
                "preview_data": {"notes": publisher.notes[:500]},
            }
        )
    return sorted(values, key=lambda value: value["score"], reverse=True)[:8]


def _organization_matches(source_name: str) -> list[dict]:
    rows = OrganizationAuthority.objects.filter(
        Q(preferred_name__icontains=source_name.strip())
        | Q(original_name__icontains=source_name.strip())
    )[:20]
    values = []
    for organization in rows:
        labels = [organization.preferred_name, organization.original_name, *list(organization.aliases or [])]
        score, reasons = max((_score_label(source_name, value) for value in labels if value), default=(0, []))
        if score <= 0:
            continue
        values.append(
            {
                "entity_type": "organization_authority",
                "entity_id": str(organization.id),
                "label": organization.preferred_name,
                "aliases": organization.aliases,
                "external_ids": organization.external_ids,
                "supporting_properties": {
                    "organization_type": organization.organization_type,
                    "country": organization.country,
                    "authority_status": organization.authority_status,
                },
                "score": score,
                "reasons": reasons,
                "conflicts": ["机构名称相似不能自动证明为同一法人或同一历史时期机构"],
                "preview_data": {"description": organization.description[:500]},
            }
        )
    return sorted(values, key=lambda value: value["score"], reverse=True)[:8]


def _knowledge_matches(source_name: str, node_types: set[str] | None) -> list[dict]:
    rows = KnowledgeNode.objects.filter(canonical_name_zh__icontains=source_name.strip())
    if node_types:
        rows = rows.filter(node_type__in=node_types)
    values = []
    for node in rows[:20]:
        labels = [node.canonical_name_zh, node.canonical_name_en]
        score, reasons = max((_score_label(source_name, value) for value in labels if value), default=(0, []))
        if score <= 0:
            continue
        values.append(
            {
                "entity_type": "knowledge_node",
                "entity_id": str(node.id),
                "label": node.canonical_name_zh,
                "aliases": list(node.aliases.values_list("alias", flat=True)),
                "external_ids": {},
                "supporting_properties": {
                    "node_type": node.node_type,
                    "status": node.status,
                },
                "score": score,
                "reasons": reasons,
                "conflicts": ["术语相似不能自动证明概念等同"],
                "preview_data": {"definition": node.definition[:500]},
            }
        )
    return sorted(values, key=lambda value: value["score"], reverse=True)[:8]


def find_entity_matches(
    *,
    target_type: str,
    source_name: str,
    node_types: set[str] | None = None,
) -> list[dict]:
    if target_type == "person":
        return _person_matches(source_name)
    if target_type == "work":
        return _work_matches(source_name)
    if target_type == "publisher":
        return _publisher_matches(source_name)
    if target_type == "organization":
        return _organization_matches(source_name)
    if target_type == "knowledge_node":
        return _knowledge_matches(source_name, node_types)
    raise ValueError(f"不支持的消歧对象类型：{target_type}")


@transaction.atomic
def persist_resolution_candidates(
    item: UploadItem,
    *,
    target_type: str,
    source_name: str,
    node_types: set[str] | None = None,
    supporting_properties: dict | None = None,
    source_record=None,
) -> list[EntityResolutionCandidate]:
    source_name = " ".join(str(source_name).split()).strip()
    if not source_name:
        return []
    matches = find_entity_matches(
        target_type=target_type,
        source_name=source_name,
        node_types=node_types,
    )
    rows = []
    for match in matches:
        row, _ = EntityResolutionCandidate.objects.update_or_create(
            upload_item=item,
            target_type=target_type,
            source_name=source_name,
            candidate_entity_type=match["entity_type"],
            candidate_entity_id=match["entity_id"],
            defaults={
                "source_record": source_record,
                "label": match["label"],
                "aliases": match["aliases"],
                "external_ids": match["external_ids"],
                "supporting_properties": {
                    **match["supporting_properties"],
                    **(supporting_properties or {}),
                },
                "match_score": match["score"],
                "match_reasons": match["reasons"],
                "conflicts": match["conflicts"],
                "preview_data": match["preview_data"],
            },
        )
        rows.append(row)

    draft_type = f"{target_type}_draft"
    draft_properties = {"requires_human_review": True}
    draft_properties.update(supporting_properties or {})
    if target_type == "knowledge_node" and node_types and len(node_types) == 1:
        draft_properties["node_type"] = next(iter(node_types))
    draft, _ = EntityResolutionCandidate.objects.update_or_create(
        upload_item=item,
        target_type=target_type,
        source_name=source_name,
        candidate_entity_type=draft_type,
        candidate_entity_id="",
        defaults={
            "source_record": source_record,
            "label": f"新建草稿：{source_name}",
            "aliases": [],
            "external_ids": {},
            "supporting_properties": draft_properties,
            "match_score": 0.35,
            "match_reasons": ["馆内没有能够自动确认的强标识符匹配"],
            "conflicts": ["创建后仍需完善权威信息"],
            "preview_data": {},
        },
    )
    rows.append(draft)
    target_id = normalized_label(source_name)[:128]
    task = ReviewTask.objects.filter(
        upload_item=item,
        task_type="entity_resolution",
        target_type=target_type,
        target_id=target_id,
        status__in=[ReviewTask.Status.PENDING, ReviewTask.Status.IN_PROGRESS],
    ).first()
    if task is None:
        ReviewTask.objects.create(
            upload_item=item,
            task_type="entity_resolution",
            target_type=target_type,
            target_id=target_id,
            title=f"确认{source_name}对应的馆内实体",
            details={
                "source_name": source_name,
                "candidate_count": len(rows),
                "automatic_merge_allowed": False,
            },
            priority=item.priority,
        )
    return rows


def propose_author_reconciliation(item: UploadItem, authors: list[str]) -> int:
    count = 0
    for author in authors:
        count += len(
            persist_resolution_candidates(
                item,
                target_type="person",
                source_name=str(author),
            )
        )
    return count
