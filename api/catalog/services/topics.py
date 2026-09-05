"""Explicit, audited Topic identity merges over existing canonical relations."""

from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import uuid

from django.db import transaction
from django.utils import timezone

from catalog import models
from catalog.services.field_decisions import (
    dependency_fingerprint,
    invalidate_dependent_fields,
    record_field_decision,
)
from ingestion.models import AuditEvent
from reading.models import SavedTopic


# Every concrete Topic FK is covered. New Topic relations must be added here
# before merges are enabled for them; silently leaving an unknown FK behind
# would split one identity across two records.
RELATIONS = (
    (models.TopicDisciplineRelation, ("discipline_id",), "学科关系"),
    (models.TopicTheoryRelation, ("theory_school_id",), "理论关系"),
    (models.TopicSubdisciplineRelation, ("subdiscipline_id",), "子学科关系"),
    (models.WorkTopicRelation, ("work_id",), "作品关系"),
    (models.PersonTopicRelation, ("person_id",), "学者关系"),
    (models.KnowledgeNodeTopic, ("node_id",), "理论节点关系"),
    (SavedTopic, ("user_id",), "读者收藏"),
    (models.WorkKnowledgeRelation, ("work_id", "kind", "theory_school_id", "concept_id", "role"), "旧作品关系"),
    (models.PersonKnowledgeRelation, ("person_id", "theory_school_id", "concept_id"), "旧学者关系"),
    (models.CuratedClaim, (), "已整理观点"),
    (models.RecommendationItem, ("snapshot_id",), "推荐展示"),
    (models.RecommendationOverride, ("policy_id", "action", "active"), "推荐设置"),
)


def _json(value):
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _snapshot(row):
    return _json({field.attname: getattr(row, field.attname) for field in row._meta.concrete_fields})


def _has_identifier(value, identifier):
    if isinstance(value, dict):
        return any(_has_identifier(item, identifier) for item in value.values())
    if isinstance(value, list):
        return any(_has_identifier(item, identifier) for item in value)
    return str(value) == str(identifier)


def _replace_identifier(value, source_id, target_id):
    if isinstance(value, list):
        values = [_replace_identifier(item, source_id, target_id) for item in value]
        # Field decisions use scalar id lists. Preserve structured rows in order.
        return list(dict.fromkeys(values)) if all(isinstance(item, str) for item in values) else values
    if isinstance(value, dict):
        return {key: _replace_identifier(item, source_id, target_id) for key, item in value.items()}
    return str(target_id) if str(value) == str(source_id) else value


def _assert_relation_inventory():
    expected = {model._meta.label_lower for model, _keys, _label in RELATIONS}
    actual = {
        relation.related_model._meta.label_lower
        for relation in models.Topic._meta.related_objects
        if relation.field.name == "topic"
    }
    if actual != expected:
        raise ValueError("主题关联结构已经变化，请先更新主题合并支持。")


def _review_status(row):
    status = getattr(row, "review_status", getattr(row, "status", ""))
    if getattr(row, "approved", False) and status != "rejected":
        status = "approved"
    return status


def _conflict(left, right):
    statuses = {_review_status(left), _review_status(right)}
    return "rejected" in statuses and bool(statuses.intersection({"approved", "published"}))


def _strength(row):
    status = _review_status(row)
    return (
        2 if status in {"approved", "published", "rejected"} else 0,
        1 if getattr(row, "reviewed_by_id", None) else 0,
        {"high": 3, "medium": 2, "low": 1}.get(getattr(row, "strength", ""), 0),
        1 if getattr(row, "is_primary", False) else 0,
    )


def _affected_work_ids(source):
    return set(models.WorkTopicRelation.objects.filter(topic=source).values_list("work_id", flat=True)) | set(
        models.WorkKnowledgeRelation.objects.filter(topic=source).values_list("work_id", flat=True)
    )


def _draft_blockers(source, target, work_ids):
    blockers = []
    for revision in models.EditorialRevision.objects.filter(status=models.EditorialRevision.Status.DRAFT).iterator():
        directly_editing = revision.target_type == "topic" and revision.target_id in {source.pk, target.pk}
        edits_work_topics = revision.target_type == "work" and revision.target_id in work_ids and "knowledge" in (revision.patch or {})
        if directly_editing or edits_work_topics or _has_identifier(revision.patch, source.pk):
            blockers.append({"code": "open_editorial_draft", "label": "相关对象有未发布的编辑草稿，请先完成或放弃该草稿。", "object_type": revision.target_type, "object_id": str(revision.target_id)})
    if models.CatalogPublicationRevision.objects.filter(edition__work_id__in=work_ids, status=models.CatalogPublicationRevision.Status.PREPARING).exists():
        blockers.append({"code": "catalog_publication_in_progress", "label": "相关作品正在发布或更新智能内容，请处理完成后再合并。"})
    return blockers


def topic_merge_preview(source, target=None):
    _assert_relation_inventory()
    work_ids = _affected_work_ids(source)
    impact = []
    conflicts = []
    fingerprint_rows = []
    for model, keys, label in RELATIONS:
        rows = list(model.objects.filter(topic=source).order_by("pk"))
        impact.append({"label": label, "count": len(rows)})
        fingerprint_rows.extend(_snapshot(row) for row in rows)
        if target is None or not keys:
            continue
        for row in rows:
            duplicates = model.objects.filter(topic=target, **{key: getattr(row, key) for key in keys}).order_by("pk")
            for duplicate in duplicates:
                fingerprint_rows.append(_snapshot(duplicate))
                if _conflict(row, duplicate):
                    conflicts.append({"code": "review_conflict", "label": f"{label}存在人工确认与人工拒绝冲突，请先处理。"})
    blockers = []
    if target is not None:
        if source.pk == target.pk:
            blockers.append({"code": "same_topic", "label": "不能将主题合并到自身。"})
        if source.editorial_status == "archived":
            blockers.append({"code": "source_archived", "label": "来源主题已经下线。"})
        if target.editorial_status != "published":
            blockers.append({"code": "target_unpublished", "label": "请选择已发布的目标主题。"})
        blockers.extend(_draft_blockers(source, target, work_ids))
        for legacy in models.WorkKnowledgeRelation.objects.filter(topic_id__in=[source.pk, target.pk], approved=True).exclude(review_status="rejected"):
            if models.WorkTopicRelation.objects.filter(work_id=legacy.work_id, topic_id__in=[source.pk, target.pk], review_status="rejected").exists():
                conflicts.append({"code": "legacy_review_conflict", "label": "作品的旧主题关系与当前人工拒绝记录冲突，请先处理。"})
        # A pin and an exclusion are two incompatible administrator decisions.
        for override in models.RecommendationOverride.objects.filter(topic=source, active=True):
            if models.RecommendationOverride.objects.filter(topic=target, policy_id=override.policy_id, active=True).exclude(action=override.action).exists():
                conflicts.append({"code": "recommendation_conflict", "label": "两个主题的推荐设置存在固定展示与排除展示冲突。"})
    blockers.extend(conflicts)
    fingerprint = sha256(json.dumps(_json({
        "source": _snapshot(source), "target": _snapshot(target) if target else None,
        "relations": fingerprint_rows, "blockers": blockers,
    }), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
    return {
        "source": {"id": str(source.pk), "name": source.name},
        "target": {"id": str(target.pk), "name": target.name} if target else None,
        "impact": impact,
        "published_editions": models.Edition.objects.filter(work_id__in=work_ids, state=models.PublicationState.PUBLISHED).count(),
        "blockers": blockers,
        "can_merge": target is not None and not blockers,
        "fingerprint": fingerprint,
        "guidance": "正式关系和读者收藏会迁至目标主题。重复关系保留人工审核结果，来源主题下线并保留审计记录。",
    }


def _merge_relation(row, duplicate, *, changes):
    if _conflict(row, duplicate):
        raise ValueError("发现相互冲突的人工关系，未执行合并。")
    before = [_snapshot(row), _snapshot(duplicate)]
    if _strength(row) > _strength(duplicate):
        excluded = {"id", "created_at", "updated_at", "topic", "topic_id"}
        fields = []
        for field in row._meta.concrete_fields:
            if field.name not in excluded and field.attname not in excluded:
                setattr(duplicate, field.attname, getattr(row, field.attname))
                fields.append(field.name)
        duplicate.save(update_fields=[*fields, "updated_at"])
    # Relation rows are replaced only after their complete before values have
    # been captured for the same transaction's AuditEvent.
    row.delete()
    changes.append({"model": duplicate._meta.label, "before": before, "after": _snapshot(duplicate), "deduplicated": True})


@transaction.atomic
def merge_topics(source_id, target_id, *, actor, change_note="", expected_fingerprint=""):
    source_id, target_id = uuid.UUID(str(source_id)), uuid.UUID(str(target_id))
    if source_id == target_id:
        raise ValueError("不能将主题合并到自身。")
    topics = {row.pk: row for row in models.Topic.objects.select_for_update().filter(pk__in=[source_id, target_id]).order_by("pk")}
    source, target = topics.get(source_id), topics.get(target_id)
    if source is None or target is None:
        raise ValueError("来源或目标主题已不存在。")
    prior_merge = (source.curation or {}).get("topic_merge", {})
    if prior_merge.get("target_id") == str(target_id):
        return prior_merge["result"]
    work_ids = _affected_work_ids(source)
    # Lock canonical Works/Editions before capturing new published metadata.
    list(models.Work.objects.select_for_update().filter(pk__in=work_ids).order_by("pk"))
    editions = list(models.Edition.objects.select_for_update().filter(work_id__in=work_ids).order_by("pk"))
    for model, _keys, _label in RELATIONS:
        list(model.objects.select_for_update().filter(topic_id__in=[source_id, target_id]).order_by("pk"))
    preview = topic_merge_preview(source, target)
    if not preview["can_merge"]:
        raise ValueError(" ".join(dict.fromkeys(item["label"] for item in preview["blockers"])))
    if expected_fingerprint and expected_fingerprint != preview["fingerprint"]:
        raise ValueError("主题或关联已经变化，请重新查看合并影响后确认。")
    before = {"source": _snapshot(source), "target": _snapshot(target)}
    changes = []
    for model, keys, _label in RELATIONS:
        for row in list(model.objects.filter(topic=source).order_by("pk")):
            duplicate = model.objects.filter(topic=target, **{key: getattr(row, key) for key in keys}).order_by("pk").first() if keys else None
            if duplicate is not None:
                _merge_relation(row, duplicate, changes=changes)
            else:
                prior = _snapshot(row)
                row.topic = target
                row.save(update_fields=["topic", "updated_at"])
                changes.append({"model": model._meta.label, "before": [prior], "after": _snapshot(row), "deduplicated": False})

    now = timezone.now()
    # Explicitly preserve previously approved compatibility relations in the
    # canonical relation set captured by publication snapshots.
    for legacy in models.WorkKnowledgeRelation.objects.filter(topic=target, work_id__in=work_ids, approved=True).exclude(review_status="rejected"):
        canonical = models.WorkTopicRelation.objects.filter(topic=target, work_id=legacy.work_id).first()
        if canonical is None:
            canonical = models.WorkTopicRelation.objects.create(
                topic=target, work_id=legacy.work_id, review_status=models.RelationReviewStatus.APPROVED,
                reviewed_by=legacy.reviewed_by or actor, reviewed_at=legacy.reviewed_at or now,
                is_primary=legacy.is_primary, strength=legacy.strength, source=legacy.source,
                confidence=legacy.confidence, evidence_asset_id=legacy.evidence_asset_id,
                evidence_page=legacy.evidence_page, evidence_printed_label=legacy.evidence_printed_label,
                evidence_text=legacy.evidence_text,
            )
            changes.append({"model": canonical._meta.label, "before": [], "after": _snapshot(canonical), "deduplicated": False, "legacy_relation_id": str(legacy.pk)})
        elif canonical.review_status != models.RelationReviewStatus.APPROVED:
            prior = _snapshot(canonical)
            canonical.review_status = models.RelationReviewStatus.APPROVED
            canonical.reviewed_by = legacy.reviewed_by or actor
            canonical.reviewed_at = legacy.reviewed_at or now
            for field_name in ("is_primary", "strength", "source", "confidence", "evidence_asset_id", "evidence_page", "evidence_printed_label", "evidence_text"):
                setattr(canonical, field_name, getattr(legacy, field_name))
            canonical.save()
            changes.append({"model": canonical._meta.label, "before": [prior], "after": _snapshot(canonical), "deduplicated": False, "legacy_relation_id": str(legacy.pk)})
    raw_aliases = (target.curation or {}).get("confirmed_aliases", [])
    aliases = list(raw_aliases) if isinstance(raw_aliases, list) else []
    alias_names = {
        str(item.get("name", "")).casefold() for item in aliases
        if isinstance(item, dict) and item.get("source") == "editorial"
        and item.get("confirmed_by") and item.get("confirmed_at")
    }
    source_aliases = (source.curation or {}).get("confirmed_aliases", [])
    source_aliases = source_aliases if isinstance(source_aliases, list) else []
    confirmed_names = [
        item.get("name", "") for item in source_aliases
        if isinstance(item, dict) and item.get("source") == "editorial"
        and item.get("confirmed_by") and item.get("confirmed_at")
    ]
    for name in [source.name, *confirmed_names]:
        name = str(name).strip()
        if name and name.casefold() not in alias_names and name.casefold() != target.name.casefold():
            aliases.append({"name": name, "source": "editorial", "confirmed_by": str(actor.pk), "confirmed_at": now.isoformat(), "source_topic_id": str(source.pk)})
            alias_names.add(name.casefold())
    target.curation = {**(target.curation or {}), "confirmed_aliases": aliases}
    target.save(update_fields=["curation", "updated_at"])
    source.editorial_status = "archived"
    source.save(update_fields=["editorial_status", "updated_at"])

    for edition in editions:
        for decision in edition.field_decisions.filter(field_name="topics"):
            if not _has_identifier(decision.value, source.pk):
                continue
            record_field_decision(
                context_type=decision.context_type, context_id=decision.context_id,
                target_type=decision.target_type, target_id=decision.target_id,
                field_name="topics", status=decision.status,
                value=_replace_identifier(decision.value, source.pk, target.pk),
                actor=actor, edition=edition, bundle=decision.bundle,
                provenance={**(decision.provenance or {}), "topic_merge": {"source": str(source.pk), "target": str(target.pk)}},
                evidence_summary=decision.evidence_summary, dependency_fields=decision.dependency_fields,
                dependency_hash=dependency_fingerprint(edition, "topics"),
                confirmation_method=decision.confirmation_method, reason="管理员合并重复主题，保留原审核状态。",
                stale_reason=decision.stale_reason,
            )
        invalidate_dependent_fields(edition, ["topics"], actor=actor)

    # Open publication bundles are current editing state, not historical facts.
    # References become links to the published survivor, never new entities.
    for item in models.PublicationBundleItem.objects.select_for_update().filter(
        object_type="topic", object_id=source.pk, bundle__status=models.PublicationBundle.Status.DRAFT,
    ):
        prior = _snapshot(item)
        existing = models.PublicationBundleItem.objects.filter(bundle=item.bundle, object_type="topic", object_id=target.pk).first()
        if existing:
            item.delete()
            changes.append({"model": item._meta.label, "before": [prior], "after": _snapshot(existing), "deduplicated": True})
        else:
            item.object_id = target.pk
            item.action = models.PublicationBundleItem.Action.LINK
            item.label = target.name
            item.snapshot = {"editorial_status": "published", "merged_from": str(source.pk)}
            item.minimum_complete = True
            item.blockers = []
            item.save()
            changes.append({"model": item._meta.label, "before": [prior], "after": _snapshot(item), "deduplicated": False})

    audit = AuditEvent.objects.create(
        actor=actor, action="topic_merge", object_type="catalog.Topic", object_id=str(source.pk),
        before=before, after={"target": _snapshot(target), "relations": changes, "change_note": str(change_note)[:500]},
    )
    from catalog.services.knowledge_publication import create_catalog_publication_event, create_entity_publication_event

    related_keys = {("topic", str(row.pk)) for row in (source, target)}
    for change in changes:
        for key, object_type in (("work_id", "work"), ("person_id", "person"), ("node_id", "knowledge_node")):
            identifier = change["after"].get(key)
            if identifier:
                related_keys.add((object_type, str(identifier)))
    related = [{"object_type": kind, "object_id": identifier} for kind, identifier in sorted(related_keys)]
    provenance = {"merge_source_id": str(source.pk), "merge_target_id": str(target.pk), "audit_event_id": str(audit.pk)}
    events = []
    for topic in (source, target):
        withdrawing = topic.pk == source.pk
        event = create_entity_publication_event(
            object_type="topic", object_id=topic.pk,
            event_type=models.KnowledgePublicationEvent.EventType.ENTITY_UPDATED if withdrawing else models.KnowledgePublicationEvent.EventType.ENTITY_MERGED,
            changed_fields=["editorial_status", "curation", "relations", "search_aliases"],
            related_entities=related, actor=actor,
            idempotency_key=f"topic-merge:{source.pk}:{target.pk}:{topic.pk}", provenance={**provenance, "withdrawal": withdrawing},
        )
        events.append(str(event.pk))
    revisions = []
    for edition in editions:
        if edition.state != models.PublicationState.PUBLISHED:
            continue
        event = create_catalog_publication_event(
            edition, event_type=models.KnowledgePublicationEvent.EventType.CATALOG_UPDATED,
            changed_fields=["topics"], actor=actor,
            idempotency_key=f"topic-merge:{source.pk}:{target.pk}:edition:{edition.pk}", provenance=provenance,
        )
        revisions.append(str(event.catalog_revision_id))
    result = {
        "source_id": str(source.pk), "target_id": str(target.pk), "target_name": target.name,
        "audit_event_id": str(audit.pk), "event_ids": events, "catalog_revision_ids": revisions,
        "moved_counts": dict(Counter(item["model"] for item in changes)),
        "detail": "主题已合并。正式关系与收藏已经迁移，相关智能内容正在更新。",
    }
    source.curation = {**(source.curation or {}), "topic_merge": {"target_id": str(target.pk), "merged_at": now.isoformat(), "result": result}}
    source.save(update_fields=["curation", "updated_at"])
    return result
