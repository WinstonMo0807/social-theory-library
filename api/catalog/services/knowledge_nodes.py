from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from catalog.models import (
    EvidenceSnippet,
    CatalogPublicationRevision,
    Edition,
    EditorialRevision,
    KnowledgePublicationEvent,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
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
from catalog.services.canonical_mutations import record_admin_canonical_change


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
        "subdiscipline_links": [
            {
                "subdiscipline_id": str(row["subdiscipline_id"]),
                "is_primary": row["is_primary"],
                "relation_role": row["relation_role"],
                "source": row["source"],
                "confidence": row["confidence"],
                "sort_order": row["sort_order"],
                "status": row["status"],
            }
            for row in node.subdiscipline_links.order_by("sort_order").values(
                "subdiscipline_id",
                "is_primary",
                "relation_role",
                "source",
                "confidence",
                "sort_order",
                "status",
            )
        ],
        "topic_links": [
            {
                "topic_id": str(row["topic_id"]),
                "relation_label": row["relation_label"],
                "source": row["source"],
                "confidence": row["confidence"],
                "sort_order": row["sort_order"],
                "status": row["status"],
            }
            for row in node.topic_links.order_by("sort_order").values(
                "topic_id",
                "relation_label",
                "source",
                "confidence",
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
        "subdiscipline_links": source.subdiscipline_links.count(),
        "topic_links": source.topic_links.count(),
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


def _publish_merged_work_metadata(work_ids, *, actor, operation_id):
    from catalog.services.knowledge_publication import create_catalog_publication_event

    for edition in Edition.objects.select_for_update().filter(work_id__in=work_ids, state="published").order_by("pk"):
        create_catalog_publication_event(
            edition, event_type=KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
            changed_fields=["theories"], actor=actor,
            idempotency_key=f"node-merge-metadata:{operation_id}:{edition.pk}",
            provenance={"source": "node_merge", "merge_operation_id": str(operation_id)},
        )


def _check_merged_relation_decisions(source, target, *, created):
    if created or getattr(source, "status", "") != "published":
        return
    if getattr(target, "status", "") != "published":
        raise ValueError("合并双方存在已确认与未确认或已拒绝的关系冲突，请先处理关系。")
    strengths = {"weak": 1, "medium": 2, "strong": 3}
    if strengths.get(getattr(source, "strength", ""), 0) > strengths.get(getattr(target, "strength", ""), 0):
        raise ValueError("来源关系具有更高的人工确认强度，请先核对目标关系，避免合并时丢失决定。")
    if getattr(source, "is_primary", False) and not getattr(target, "is_primary", False):
        raise ValueError("来源包含主要关系而目标不是主要关系，请先明确保留哪项决定。")


@transaction.atomic
def merge_nodes(source_id, target_id, *, actor, change_note="") -> KnowledgeNodeMergeRecord:
    if str(source_id) == str(target_id):
        raise ValueError("不能将节点合并到自身。")
    source = KnowledgeNode.objects.select_for_update().get(pk=source_id)
    target = KnowledgeNode.objects.select_for_update().get(pk=target_id)
    if source.status == "archived":
        raise ValueError("来源节点已经归档。")
    if target.status != "published":
        raise ValueError("请选择已发布的目标理论节点。")
    work_ids = set(source.work_relations.values_list("work_id", flat=True))
    if EditorialRevision.objects.filter(target_type="knowledge_node", target_id__in=[source.pk, target.pk], status="draft").exists():
        raise ValueError("相关理论节点有未发布的编辑草稿，请先完成或放弃草稿。")
    if EditorialRevision.objects.filter(target_type="work", target_id__in=work_ids, status="draft").exists():
        raise ValueError("相关作品有未发布的编辑草稿，请先完成或放弃草稿。")
    if CatalogPublicationRevision.objects.filter(edition__work_id__in=work_ids, status="preparing").exists():
        raise ValueError("相关作品正在更新智能内容，请处理完成后再合并。")

    before_source = node_snapshot(source)
    before_target = node_snapshot(target)
    affected = merge_preview(source)
    created_ids = defaultdict(list)
    moved_ids = defaultdict(list)
    retired_rows = defaultdict(dict)

    from catalog.services.query_lexicon.registry import FORMAL_KNOWLEDGE_ALIAS_SOURCES

    for alias in source.aliases.filter(is_verified=True, source_kind__in=FORMAL_KNOWLEDGE_ALIAS_SOURCES):
        copied, created = KnowledgeNodeAlias.objects.get_or_create(
            node=target,
            normalized_alias=alias.normalized_alias,
            defaults={
                "alias": alias.alias,
                "language": alias.language,
                "alias_type": alias.alias_type,
                "source_kind": alias.source_kind,
                "is_verified": alias.is_verified,
                "created_by_id": _user_id(actor),
            },
        )
        if created:
            created_ids["KnowledgeNodeAlias"].append(str(copied.id))
    for name, language in ((source.canonical_name_zh, "zh-CN"), (source.canonical_name_en, "en")):
        normalized = " ".join(str(name or "").casefold().split())
        if not normalized or normalized in {" ".join(target.canonical_name_zh.casefold().split()), " ".join(target.canonical_name_en.casefold().split())}:
            continue
        alias, created = KnowledgeNodeAlias.objects.get_or_create(
            node=target, normalized_alias=normalized,
            defaults={"alias": name, "language": language, "source_kind": KnowledgeNodeAlias.SourceKind.EDITORIAL, "is_verified": True, "created_by_id": _user_id(actor)},
        )
        if created:
            created_ids["KnowledgeNodeAlias"].append(str(alias.pk))

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
        _check_merged_relation_decisions(link, copied, created=created)
        if created:
            created_ids["KnowledgeNodeDiscipline"].append(str(copied.id))

    for link in source.subdiscipline_links.all():
        copied, created = KnowledgeNodeSubdiscipline.objects.get_or_create(
            node=target,
            subdiscipline=link.subdiscipline,
            defaults={
                "is_primary": link.is_primary,
                "relation_role": link.relation_role,
                "source": link.source,
                "confidence": link.confidence,
                "sort_order": link.sort_order,
                "status": link.status,
                "reviewed_by": link.reviewed_by,
                "reviewed_at": link.reviewed_at,
            },
        )
        _check_merged_relation_decisions(link, copied, created=created)
        if created:
            created_ids["KnowledgeNodeSubdiscipline"].append(str(copied.id))

    for link in source.topic_links.all():
        copied, created = KnowledgeNodeTopic.objects.get_or_create(
            node=target,
            topic=link.topic,
            defaults={
                "relation_label": link.relation_label,
                "source": link.source,
                "confidence": link.confidence,
                "sort_order": link.sort_order,
                "status": link.status,
                "reviewed_by": link.reviewed_by,
                "reviewed_at": link.reviewed_at,
            },
        )
        _check_merged_relation_decisions(link, copied, created=created)
        if created:
            created_ids["KnowledgeNodeTopic"].append(str(copied.id))

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
        _check_merged_relation_decisions(relation, copied, created=created)
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
        _check_merged_relation_decisions(relation, copied, created=created)
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
        _check_merged_relation_decisions(relation, copied, created=created)
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
    # Keep the source relation rows for rollback, but never snapshot them as
    # still-public relations alongside their newly copied survivor relations.
    for model, query in (
        (WorkNodeRelation, Q(node=source)),
        (PersonNodeRelation, Q(node=source)),
        (KnowledgeRelation, Q(source_node=source) | Q(target_node=source)),
    ):
        rows = model.objects.filter(query, status="published")
        retired_rows[model.__name__] = {str(row.pk): row.status for row in rows}
        rows.update(status="archived", updated_at=timezone.now())
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
            "retired_rows": dict(retired_rows),
            "affected_work_ids": [str(identifier) for identifier in work_ids],
        },
        merged_by_id=_user_id(actor),
    )
    record_admin_canonical_change(
        object_type="knowledge_node",
        target=source,
        change_kind="withdraw",
        changed_fields=["status", "published_at", "merged_into"],
        actor=actor,
        request_idempotency_key=f"knowledge-node-merge:{record.id}:source",
    )
    record_admin_canonical_change(
        object_type="knowledge_node",
        target=target,
        change_kind="merge",
        changed_fields=[
            "aliases",
            "discipline_links",
            "subdiscipline_links",
            "topic_links",
            "work_relations",
            "person_relations",
            "knowledge_relations",
            "evidence",
            "timeline_events",
            "reading_path_items",
            "legacy_mappings",
        ],
        actor=actor,
        request_idempotency_key=f"knowledge-node-merge:{record.id}:target",
    )
    _publish_merged_work_metadata(work_ids, actor=actor, operation_id=record.pk)
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
        "KnowledgeNodeSubdiscipline": KnowledgeNodeSubdiscipline,
        "KnowledgeNodeTopic": KnowledgeNodeTopic,
        "KnowledgeNodeAlias": KnowledgeNodeAlias,
    }
    for model_name, rows in payload.get("retired_rows", {}).items():
        model = model_map.get(model_name)
        if model is not None:
            for identifier, previous_status in rows.items():
                model.objects.filter(pk=identifier).update(status=previous_status, updated_at=timezone.now())
    for model_name in (
        "EvidenceSnippet",
        "TimelineEventRelation",
        "KnowledgeRelation",
        "WorkNodeRelation",
        "PersonNodeRelation",
        "KnowledgeNodeDiscipline",
        "KnowledgeNodeSubdiscipline",
        "KnowledgeNodeTopic",
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
    record_admin_canonical_change(
        object_type="knowledge_node",
        target=source,
        change_kind=(
            "publish"
            if record.source_snapshot.get("status") == "published"
            else "update"
        ),
        changed_fields=["status", "published_at", "merge_rollback"],
        actor=actor,
        request_idempotency_key=f"knowledge-node-merge-rollback:{record.id}:source",
    )
    record_admin_canonical_change(
        object_type="knowledge_node",
        target=target,
        change_kind="update",
        changed_fields=[
            "aliases",
            "discipline_links",
            "subdiscipline_links",
            "topic_links",
            "work_relations",
            "person_relations",
            "knowledge_relations",
            "evidence",
            "timeline_events",
            "reading_path_items",
            "legacy_mappings",
            "merge_rollback",
        ],
        actor=actor,
        request_idempotency_key=f"knowledge-node-merge-rollback:{record.id}:target",
    )
    _publish_merged_work_metadata(payload.get("affected_work_ids", []), actor=actor, operation_id=f"rollback:{record.pk}")
    return record
