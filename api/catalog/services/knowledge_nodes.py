from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from catalog.models import (
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeMergeRecord,
    KnowledgeNodeVersion,
    KnowledgeRelation,
    KnowledgeRelationVersion,
    LegacyKnowledgeMapping,
    PersonNodeRelation,
    ReadingPathItem,
    TheoryReviewTask,
    TimelineEventRelation,
    WorkNodeRelation,
)


def _user_id(user):
    return user.pk if user and getattr(user, "is_authenticated", False) else None


def node_snapshot(node: KnowledgeNode) -> dict:
    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "canonical_name_zh": node.canonical_name_zh,
        "canonical_name_en": node.canonical_name_en,
        "slug": node.slug,
        "summary": node.summary,
        "definition": node.definition,
        "core_questions": node.core_questions,
        "basic_propositions": node.basic_propositions,
        "theoretical_boundary": node.theoretical_boundary,
        "start_year": node.start_year,
        "end_year": node.end_year,
        "period_label": node.period_label,
        "primary_discipline_id": str(node.primary_discipline_id) if node.primary_discipline_id else None,
        "status": node.status,
        "sort_order": node.sort_order,
        "published_at": node.published_at.isoformat() if node.published_at else None,
        "aliases": list(
            node.aliases.order_by("alias").values(
                "alias", "language", "alias_type", "normalized_alias"
            )
        ),
        "discipline_links": [
            {
                "discipline_id": str(row["discipline_id"]),
                "relation_type": row["relation_type"],
                "discipline_specific_summary": row["discipline_specific_summary"],
                "sort_order": row["sort_order"],
                "status": row["status"],
            }
            for row in node.discipline_links.order_by("sort_order").values(
                "discipline_id",
                "relation_type",
                "discipline_specific_summary",
                "sort_order",
                "status",
            )
        ],
    }


def relation_snapshot(relation: KnowledgeRelation) -> dict:
    return {
        "id": str(relation.id),
        "source_node_id": str(relation.source_node_id),
        "target_node_id": str(relation.target_node_id),
        "relation_type": relation.relation_type,
        "direction": relation.direction,
        "description": relation.description,
        "evidence_source": relation.evidence_source,
        "confidence": relation.confidence,
        "status": relation.status,
        "published_at": relation.published_at.isoformat() if relation.published_at else None,
    }


def record_node_version(node: KnowledgeNode, actor=None, change_note="") -> KnowledgeNodeVersion:
    latest = (
        KnowledgeNodeVersion.objects.filter(node=node).aggregate(value=Max("version_number"))["value"]
        or 0
    )
    return KnowledgeNodeVersion.objects.create(
        node=node,
        version_number=latest + 1,
        snapshot=node_snapshot(node),
        change_note=change_note,
        created_by_id=_user_id(actor),
    )


def record_relation_version(
    relation: KnowledgeRelation,
    actor=None,
    change_note="",
) -> KnowledgeRelationVersion:
    latest = (
        KnowledgeRelationVersion.objects.filter(relation=relation).aggregate(
            value=Max("version_number")
        )["value"]
        or 0
    )
    return KnowledgeRelationVersion.objects.create(
        relation=relation,
        version_number=latest + 1,
        snapshot=relation_snapshot(relation),
        change_note=change_note,
        created_by_id=_user_id(actor),
    )


def merge_preview(source: KnowledgeNode) -> dict:
    return {
        "aliases": source.aliases.count(),
        "discipline_links": source.discipline_links.count(),
        "work_relations": source.work_relations.count(),
        "person_relations": source.person_relations.count(),
        "knowledge_relations": KnowledgeRelation.objects.filter(
            Q(source_node=source) | Q(target_node=source)
        ).count(),
        "evidence": source.evidence.count(),
        "timeline_events": source.timeline_links.count(),
        "reading_path_items": source.reading_path_items.count(),
        "review_tasks": source.review_tasks.count(),
        "legacy_mappings": source.legacy_mappings.count(),
        "public_url": f"/theories/nodes/{source.slug}",
    }


def _copy_evidence(evidence, *, node, work_relation=None, knowledge_relation=None):
    lookup = {
        "work": evidence.work,
        "file": evidence.file,
        "node": node,
        "page_number": evidence.page_number,
        "quote": evidence.quote,
    }
    defaults = {
        "work_node_relation": work_relation,
        "knowledge_relation": knowledge_relation,
        "page_end": evidence.page_end,
        "printed_page_label": evidence.printed_page_label,
        "bounding_box": evidence.bounding_box,
        "extraction_method": evidence.extraction_method,
        "ocr_confidence": evidence.ocr_confidence,
        "semantic_confidence": evidence.semantic_confidence,
        "review_status": evidence.review_status,
        "reviewed_by": evidence.reviewed_by,
        "reviewed_at": evidence.reviewed_at,
    }
    copied, created = EvidenceSnippet.objects.get_or_create(**lookup, defaults=defaults)
    return copied, created


@transaction.atomic
def merge_nodes(source_id, target_id, *, actor, change_note="") -> KnowledgeNodeMergeRecord:
    if str(source_id) == str(target_id):
        raise ValueError("不能将节点合并到自身。")
    source = KnowledgeNode.objects.select_for_update().get(pk=source_id)
    target = KnowledgeNode.objects.select_for_update().get(pk=target_id)
    if source.status == "archived":
        raise ValueError("来源节点已经归档。")

    before_source = node_snapshot(source)
    before_target = node_snapshot(target)
    affected = merge_preview(source)
    created_ids = defaultdict(list)
    moved_ids = defaultdict(list)

    for alias in source.aliases.all():
        copied, created = KnowledgeNodeAlias.objects.get_or_create(
            node=target,
            normalized_alias=alias.normalized_alias,
            defaults={
                "alias": alias.alias,
                "language": alias.language,
                "alias_type": alias.alias_type,
                "created_by_id": _user_id(actor),
            },
        )
        if created:
            created_ids["KnowledgeNodeAlias"].append(str(copied.id))

    for link in source.discipline_links.all():
        copied, created = KnowledgeNodeDiscipline.objects.get_or_create(
            node=target,
            discipline=link.discipline,
            defaults={
                "relation_type": link.relation_type,
                "discipline_specific_summary": link.discipline_specific_summary,
                "sort_order": link.sort_order,
                "status": link.status,
                "reviewed_by": link.reviewed_by,
                "reviewed_at": link.reviewed_at,
            },
        )
        if created:
            created_ids["KnowledgeNodeDiscipline"].append(str(copied.id))

    work_relation_map = {}
    for relation in source.work_relations.select_related("work"):
        copied, created = WorkNodeRelation.objects.get_or_create(
            work=relation.work,
            node=target,
            role=relation.role,
            defaults={
                "is_primary": relation.is_primary,
                "strength": relation.strength,
                "confidence": relation.confidence,
                "status": relation.status,
                "source": relation.source,
                "created_by_id": _user_id(actor),
                "reviewed_by": relation.reviewed_by,
                "reviewed_at": relation.reviewed_at,
            },
        )
        work_relation_map[relation.id] = copied
        if created:
            created_ids["WorkNodeRelation"].append(str(copied.id))
        for evidence in relation.evidence.all():
            evidence_copy, evidence_created = _copy_evidence(
                evidence,
                node=target,
                work_relation=copied,
            )
            if evidence_created:
                created_ids["EvidenceSnippet"].append(str(evidence_copy.id))

    for relation in source.person_relations.select_related("person"):
        copied, created = PersonNodeRelation.objects.get_or_create(
            person=relation.person,
            node=target,
            defaults={
                "relation_label": relation.relation_label,
                "is_representative": relation.is_representative,
                "sort_order": relation.sort_order,
                "confidence": relation.confidence,
                "status": relation.status,
                "source": relation.source,
                "reviewed_by": relation.reviewed_by,
                "reviewed_at": relation.reviewed_at,
            },
        )
        if created:
            created_ids["PersonNodeRelation"].append(str(copied.id))

    source_relations = KnowledgeRelation.objects.filter(
        Q(source_node=source) | Q(target_node=source)
    ).select_related("source_node", "target_node")
    for relation in source_relations:
        new_source = target if relation.source_node_id == source.id else relation.source_node
        new_target = target if relation.target_node_id == source.id else relation.target_node
        if new_source.id == new_target.id:
            continue
        copied, created = KnowledgeRelation.objects.get_or_create(
            source_node=new_source,
            target_node=new_target,
            relation_type=relation.relation_type,
            defaults={
                "direction": relation.direction,
                "description": relation.description,
                "evidence_source": relation.evidence_source,
                "confidence": relation.confidence,
                "status": relation.status,
                "created_by_id": _user_id(actor),
                "reviewed_by": relation.reviewed_by,
                "published_at": relation.published_at,
            },
        )
        if created:
            created_ids["KnowledgeRelation"].append(str(copied.id))
        for evidence in relation.evidence.all():
            evidence_copy, evidence_created = _copy_evidence(
                evidence,
                node=target,
                knowledge_relation=copied,
            )
            if evidence_created:
                created_ids["EvidenceSnippet"].append(str(evidence_copy.id))

    relation_bound_evidence = source.evidence.filter(
        work_node_relation__isnull=True,
        knowledge_relation__isnull=True,
    )
    for evidence in relation_bound_evidence:
        evidence_copy, evidence_created = _copy_evidence(evidence, node=target)
        if evidence_created:
            created_ids["EvidenceSnippet"].append(str(evidence_copy.id))

    for link in source.timeline_links.all():
        copied, created = TimelineEventRelation.objects.get_or_create(
            event=link.event,
            relation_type=link.relation_type,
            node=target,
            discipline=link.discipline,
            scholar=link.scholar,
            work=link.work,
            defaults={
                "evidence": link.evidence,
                "description": link.description,
                "sort_order": link.sort_order,
            },
        )
        if created:
            created_ids["TimelineEventRelation"].append(str(copied.id))

    for item in source.reading_path_items.all():
        moved_ids["ReadingPathItem"].append(str(item.id))
    source.reading_path_items.update(node=target)

    for task in source.review_tasks.all():
        moved_ids["TheoryReviewTask"].append(str(task.id))
    source.review_tasks.update(candidate_node=target)

    for mapping in source.legacy_mappings.all():
        moved_ids["LegacyKnowledgeMapping"].append(str(mapping.id))
    source.legacy_mappings.update(node=target)

    source.status = "archived"
    source.published_at = None
    source.save(update_fields=["status", "published_at", "updated_at"])
    record_node_version(target, actor, change_note or f"合并节点 {source.canonical_name_zh}")
    record_node_version(source, actor, f"已合并到 {target.canonical_name_zh}")

    record = KnowledgeNodeMergeRecord.objects.create(
        source_node=source,
        target_node=target,
        source_snapshot=before_source,
        target_snapshot=before_target,
        affected_counts=affected,
        rollback_payload={
            "created_ids": dict(created_ids),
            "moved_ids": dict(moved_ids),
        },
        merged_by_id=_user_id(actor),
    )
    return record


@transaction.atomic
def rollback_merge(record_id, *, actor) -> KnowledgeNodeMergeRecord:
    record = KnowledgeNodeMergeRecord.objects.select_for_update().get(pk=record_id)
    if record.rolled_back_at:
        raise ValueError("该合并记录已经回滚。")
    source = KnowledgeNode.objects.select_for_update().get(pk=record.source_node_id)
    target = KnowledgeNode.objects.select_for_update().get(pk=record.target_node_id)
    payload = record.rollback_payload or {}
    created_ids = payload.get("created_ids", {})
    model_map = {
        "EvidenceSnippet": EvidenceSnippet,
        "TimelineEventRelation": TimelineEventRelation,
        "KnowledgeRelation": KnowledgeRelation,
        "WorkNodeRelation": WorkNodeRelation,
        "PersonNodeRelation": PersonNodeRelation,
        "KnowledgeNodeDiscipline": KnowledgeNodeDiscipline,
        "KnowledgeNodeAlias": KnowledgeNodeAlias,
    }
    for model_name in (
        "EvidenceSnippet",
        "TimelineEventRelation",
        "KnowledgeRelation",
        "WorkNodeRelation",
        "PersonNodeRelation",
        "KnowledgeNodeDiscipline",
        "KnowledgeNodeAlias",
    ):
        ids = created_ids.get(model_name, [])
        if ids:
            model_map[model_name].objects.filter(pk__in=ids).delete()

    moved = payload.get("moved_ids", {})
    ReadingPathItem.objects.filter(pk__in=moved.get("ReadingPathItem", [])).update(node=source)
    TheoryReviewTask.objects.filter(pk__in=moved.get("TheoryReviewTask", [])).update(
        candidate_node=source
    )
    LegacyKnowledgeMapping.objects.filter(
        pk__in=moved.get("LegacyKnowledgeMapping", [])
    ).update(node=source)

    source.status = record.source_snapshot.get("status", "draft")
    source.published_at = None
    source.save(update_fields=["status", "published_at", "updated_at"])
    record_node_version(source, actor, f"回滚与 {target.canonical_name_zh} 的合并")
    record_node_version(target, actor, f"回滚来源节点 {source.canonical_name_zh}")
    record.rolled_back_at = timezone.now()
    record.rolled_back_by_id = _user_id(actor)
    record.save(update_fields=["rolled_back_at", "rolled_back_by", "updated_at"])
    return record
