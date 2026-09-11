"""Explicit, non-destructive Person merges with conflict-checked reversal.

The first executor only moves non-colliding references. It never chooses
between two profiles or conflicting relationships, and never deletes rows.
"""
from collections import Counter
from hashlib import sha256
import json
import re
from uuid import uuid4

from django.apps import apps
from django.db import transaction
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from common.capabilities import Capability, has_capability
from catalog import models
from catalog.services.field_decisions import dependency_fingerprint
from catalog.services.knowledge_publication import create_catalog_publication_event, create_entity_publication_event
from catalog.services.person_resolution import (
    PERSON_REFERENCES, PROFILE_REFERENCES, REFERENCE_LIMIT, _json, _record, person_merge_preview,
)
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock
from catalog.services.topics import _has_identifier, _replace_identifier
from ingestion.models import AuditEvent, EntityResolutionCandidate, FieldLock


MERGE_VERSION = "person-merge-noncolliding-v1"
PERSON_FIELDS = {"authors", "translators"}


def _owner(actor):
    if not has_capability(actor, Capability.MERGE_AUTHORITY):
        raise PermissionDenied("只有 System Owner 可以执行人物合并或回滚。")


def _digest(value):
    return sha256(json.dumps(_json(value), sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def _canonical_record(row):
    # Only model-maintained row timestamps are incidental. A similarly named
    # key inside a user's JSON is business data and must protect rollback.
    return {key: value for key, value in _record(row).items() if key not in {"created_at", "updated_at"}}


def _mentions(value, people):
    return any(_has_identifier(value, identifier) for identifier in people)


def _json_scope(queryset, fields, people, direct=Q(pk__in=[])):
    condition = direct
    for index, field in enumerate(fields):
        alias = f"person_merge_json_{index}"
        queryset = queryset.annotate(**{alias: Cast(field, TextField())})
        for identifier in people:
            condition |= Q(**{f"{alias}__icontains": str(identifier)})
    return queryset.filter(condition)


def _limited(queryset, *, lock=False):
    if lock:
        queryset = queryset.select_for_update()
    rows = list(queryset.order_by("pk")[:REFERENCE_LIMIT + 1])
    if len(rows) > REFERENCE_LIMIT:
        raise ValueError("人物合并影响范围超过事务处理上限，请先缩小或核对范围。")
    return rows


def _editing_context(source, target, edition_ids, work_ids, *, lock=False):
    people = {source.pk, target.pk}
    profile_ids = list(models.ScholarProfile.objects.filter(person_id__in=people).values_list("pk", flat=True))
    drafts = _json_scope(
        models.EditorialRevision.objects.filter(status="draft"), ["patch"], people,
        direct=(Q(target_type="scholar_profile", target_id__in=profile_ids)
                | Q(target_type="work", target_id__in=work_ids)
                | Q(target_type="edition", target_id__in=edition_ids)),
    )
    bundles = models.PublicationBundleItem.objects.filter(
        object_type="person", object_id__in=people,
        bundle__status__in=["draft", "publishing", "failed"],
    )
    candidates = (
        (models.EnrichmentCandidate, _json_scope(
            models.EnrichmentCandidate.objects.filter(status="pending"),
            ["proposed_value", "current_value", "request_context"], people,
            direct=Q(target_type="person", target_id__in=people),
        )),
        (models.QueryLexiconCandidate, _json_scope(
            models.QueryLexiconCandidate.objects.filter(status="pending"), ["possible_targets"], people,
            direct=Q(target_entity_type="person", target_entity_id__in=people),
        )),
        (EntityResolutionCandidate, _json_scope(
            EntityResolutionCandidate.objects.filter(status="proposed"), ["preview_data", "supporting_properties"], people,
            direct=Q(candidate_entity_id__in=[str(value) for value in people]),
        )),
    )
    pending = {"editorial_drafts": _limited(drafts, lock=lock), "open_bundles": _limited(bundles, lock=lock)}
    for model, queryset in candidates:
        pending[model._meta.label] = _limited(queryset, lock=lock)
    pending["cataloging_sessions"] = _limited(models.CatalogingSession.objects.filter(
        edition_id__in=edition_ids, status__in=["open", "publishing"],
    ), lock=lock)
    pending["research_runs"] = _limited(_json_scope(
        models.ResearchRun.objects.filter(status__in=[models.ResearchRun.Status.QUEUED, models.ResearchRun.Status.RUNNING]), ["context_snapshot"], people,
        direct=Q(edition_id__in=edition_ids),
    ), lock=lock)
    decisions = _limited(_json_scope(
        models.CatalogFieldDecision.objects.all(), ["value"], people,
        direct=Q(edition_id__in=edition_ids) | Q(target_type="person", target_id__in=people),
    ), lock=lock)
    locks = _limited(_json_scope(FieldLock.objects.all(), ["locked_value"], people, direct=Q(edition_id__in=edition_ids)), lock=lock)
    return pending, decisions, locks


def _state(source, target, edition_ids, *, lock=False):
    """Canonical state only: asynchronous projection status is not an edit."""
    people = {source.pk, target.pk}
    profile_ids = list(models.ScholarProfile.objects.filter(person_id__in=people).values_list("pk", flat=True))
    references = []
    for model, field, _label in PERSON_REFERENCES:
        rows = _limited(model.objects.filter(**{f"{field}_id__in": people}), lock=lock)
        references.append((model._meta.label, field, [_canonical_record(row) for row in rows]))
    for model, field, _label in PROFILE_REFERENCES:
        rows = _limited(model.objects.filter(**{f"{field}_id__in": profile_ids}), lock=lock)
        references.append((model._meta.label, field, [_canonical_record(row) for row in rows]))
    editions = _limited(models.Edition.objects.filter(pk__in=edition_ids), lock=lock)
    work_ids = {row.work_id for row in editions}
    works = _limited(models.Work.objects.filter(pk__in=work_ids), lock=lock)
    pending, decisions, locks = _editing_context(source, target, edition_ids, work_ids, lock=lock)
    canonical_ids = people | set(profile_ids) | set(work_ids) | {row.pk for row in editions}
    canonical = list(models.CanonicalObjectRevision.objects.filter(object_id__in=canonical_ids).order_by("object_type", "object_id").values("object_type", "object_id", "current_revision"))
    payload = {
        "source": _canonical_record(source), "target": _canonical_record(target), "references": references,
        "works": [_canonical_record(row) for row in works],
        # Serving pointers/processing timestamps legitimately change after
        # publication. Editorial fields and canonical revisions may not.
        "editions": [{key: value for key, value in _canonical_record(row).items() if key not in {
            "active_catalog_revision_id", "metadata_ready_at", "fulltext_ready_at", "intelligence_status",
            "published_at", "first_published_at", "last_published_at", "semantic_index_status", "updated_at",
        }} for row in editions],
        "decisions": [_canonical_record(row) for row in decisions], "locks": [_canonical_record(row) for row in locks],
        "pending": {kind: [{"id": str(row.pk), "updated_at": row.updated_at} for row in rows] for kind, rows in pending.items()},
        "canonical": canonical,
    }
    return payload, pending, decisions, locks


def prepare_person_merge(source, target):
    preview = person_merge_preview(source, target)
    edition_ids = [row["id"] for row in preview["affected_editions"]]
    state, pending, decisions, locks = _state(source, target, edition_ids)
    blockers = list(preview["review_issues"])
    if source.authority_status != "verified":
        blockers.append({"code": "source_not_verified", "detail": "请先核验来源人物，未经确认的身份不能经合并成为正式别名。"})
    if preview["identity_conflicts"]:
        blockers.append({"code": "identity_conflict", "detail": "人物身份字段存在冲突，请先核对。"})
    if any(group["collisions"] for group in preview["references"]):
        blockers.append({"code": "reference_collision", "detail": "双方有重复唯一关系，本执行器不会删除或选择其中一条。"})
    for kind, rows in pending.items():
        if rows:
            blockers.append({"code": "pending_context", "detail": f"{kind}仍有待处理内容，请先完成或放弃。"})
    supported_editions = {str(value) for value in edition_ids}
    for row, value in [*((row, row.value) for row in decisions), *((row, row.locked_value) for row in locks)]:
        if _has_identifier(value, source.pk) and (row.field_name not in PERSON_FIELDS or str(row.edition_id) not in supported_editions):
            blockers.append({"code": "unsupported_field_reference", "detail": "其他人工字段仍引用来源人物，需要先核对其含义。"})
    preview["execution_policy"] = MERGE_VERSION
    preview["execution_guidance"] = [
        "保留人物的姓名、生卒年、简介、图片和外部标识符保持现值；来源基础资料仍保留在来源人物及操作快照中。",
        "仅迁移无唯一约束冲突的引用，保留原记录ID、审核状态和来源；未核验名称不会被提升为已核验。",
        "唯一学者档案保留原ID与网址；双方都有学者档案时暂不执行，不自动取舍内容。",
        "公开书目通过现有发布处理更新，处理完成前继续读取上一正式版本；回滚会拒绝后续人工修改。",
    ]
    preview["review_issues"] = blockers
    preview["merge_execution_available"] = not blockers and preview["complete_reference_listing"]
    preview["context_impact"] = {
        "field_decisions": len(decisions), "field_locks": len(locks),
        "pending": {kind: len(rows) for kind, rows in pending.items()},
        "historical_candidates": "preserved_without_retargeting",
    }
    preview["fingerprint"] = _digest({"preview": preview, "state": state})
    return preview


def _locked_people(source_id, target_id):
    if str(source_id) == str(target_id):
        raise ValueError("人物不能合并到自身。")
    acquire_generation_lock(shared=True)
    rows = list(models.Person.objects.select_for_update().filter(pk__in=[source_id, target_id]).order_by("pk"))
    by_id = {str(row.pk): row for row in rows}
    if len(rows) != 2:
        raise ValueError("来源人物或保留人物已不存在。")
    return by_id[str(source_id)], by_id[str(target_id)]


def _change(row, updates, changes):
    before = {name: _json(getattr(row, name)) for name in updates}
    for name, value in updates.items():
        setattr(row, name, value)
    row.save(update_fields=[*updates, "updated_at"])
    changes.append({"model": row._meta.label, "id": str(row.pk), "before": before, "after": _json(updates)})


def _publish(source, target, edition_ids, actor, operation_id, *, rollback=False):
    provenance = {"source": "person_merge_rollback" if rollback else "person_merge", "person_merge_id": str(operation_id)}
    events = []
    for person in (source, target):
        withdrawing = person.authority_status == "merged"
        event = create_entity_publication_event(
            object_type="person", object_id=person.pk,
            event_type="entity_updated" if withdrawing else "entity_published" if rollback and person.pk == source.pk else "entity_merged",
            changed_fields=["authority_status", "merged_into", "name_variants", "relations"], actor=actor,
            idempotency_key=f"{provenance['source']}:{operation_id}:person:{person.pk}",
            provenance={**provenance, "withdrawal": withdrawing},
        )
        events.append(str(event.pk))
    for profile in models.ScholarProfile.objects.filter(person_id__in=[source.pk, target.pk], editorial_status="published"):
        event = create_entity_publication_event(
            object_type="scholar_profile", object_id=profile.pk, event_type="entity_updated",
            changed_fields=["person", "relations"], actor=actor,
            idempotency_key=f"{provenance['source']}:{operation_id}:scholar:{profile.pk}", provenance=provenance,
        )
        events.append(str(event.pk))
    for edition in models.Edition.objects.filter(pk__in=edition_ids, state="published").order_by("pk"):
        event = create_catalog_publication_event(
            edition, event_type="catalog_updated", changed_fields=["contributors"], actor=actor,
            idempotency_key=f"{provenance['source']}:{operation_id}:edition:{edition.pk}", provenance=provenance,
        )
        events.append(str(event.pk))
    return events


@transaction.atomic
def merge_people(source_id, target_id, *, actor, expected_fingerprint, idempotency_key, confirmed=False, change_note=""):
    _owner(actor)
    if confirmed is not True:
        raise ValueError("请先预览并人工确认人物合并。")
    idempotency_key = str(idempotency_key or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,160}", idempotency_key):
        raise ValueError("请提供有效幂等标识。")
    # Serialize the request key even when retries name different people.
    acquire_entity_lock("person_merge_request", idempotency_key)
    source, target = _locked_people(source_id, target_id)
    existing = models.PersonMergeRecord.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if str(existing.source_person_id) != str(source_id) or str(existing.target_person_id) != str(target_id) or existing.preview_fingerprint != expected_fingerprint:
            raise ValueError("幂等标识已用于不同的人物合并。")
        return existing
    preview = prepare_person_merge(source, target)
    if preview["fingerprint"] != expected_fingerprint:
        raise ValueError("人物或引用已变化，请重新预览后确认。")
    if not preview["merge_execution_available"]:
        raise ValueError("当前人物合并存在未解决的冲突或不完整范围。")
    edition_ids = [row["id"] for row in preview["affected_editions"]]
    _state(source, target, edition_ids, lock=True)
    # Re-read after all concrete relationship locks, not just the two people.
    if prepare_person_merge(source, target)["fingerprint"] != expected_fingerprint:
        raise ValueError("加锁期间引用已变化，请重新预览。")
    source_snapshot, target_snapshot = _record(source), _record(target)
    operation_id = uuid4()
    changes = []
    for model, field, _label in PERSON_REFERENCES:
        for row in _limited(model.objects.filter(**{f"{field}_id": source.pk}), lock=True):
            _change(row, {f"{field}_id": target.pk}, changes)
    _, _, decisions, locks = _state(source, target, edition_ids, lock=True)
    for decision in decisions:
        if decision.field_name not in PERSON_FIELDS or not _has_identifier(decision.value, source.pk):
            continue
        before = decision.value
        _change(decision, {
            "value": _replace_identifier(decision.value, source.pk, target.pk),
            "dependency_fingerprint": dependency_fingerprint(decision.edition, decision.field_name),
        }, changes)
        models.CatalogFieldDecisionLog.objects.create(
            decision=decision, action="person_merge", old_value=before, new_value=decision.value,
            actor=actor, reason=f"人物身份合并 {operation_id}，保留原审核状态。",
        )
    for lock in locks:
        if lock.field_name in PERSON_FIELDS and _has_identifier(lock.locked_value, source.pk):
            _change(lock, {"locked_value": _replace_identifier(lock.locked_value, source.pk, target.pk)}, changes)
    source.authority_status = "merged"
    source.merged_into = target
    source.save(update_fields=["authority_status", "merged_into", "updated_at"])
    events = _publish(source, target, edition_ids, actor, operation_id)
    source.refresh_from_db()
    target.refresh_from_db()
    state, _, _, _ = _state(source, target, edition_ids)
    record = models.PersonMergeRecord.objects.create(
        pk=operation_id, source_person=source, target_person=target, created_by=actor,
        idempotency_key=idempotency_key, preview_fingerprint=expected_fingerprint,
        source_snapshot=source_snapshot, target_snapshot=target_snapshot, changes=changes,
        affected_edition_ids=edition_ids, event_ids=events, rollback_fingerprint=_digest(state),
    )
    AuditEvent.objects.create(
        actor=actor, action="person_merge", object_type="catalog.PersonMergeRecord", object_id=str(record.pk),
        before={"source": source_snapshot, "target": target_snapshot},
        after={"source_id": str(source.pk), "target_id": str(target.pk), "change_note": str(change_note)[:500], "moved_counts": dict(Counter(row["model"] for row in changes)), "event_ids": events},
    )
    return record


def rollback_preview(record):
    source, target = record.source_person, record.target_person
    state, pending, _, _ = _state(source, target, record.affected_edition_ids)
    fingerprint = _digest(state)
    blockers = []
    if record.rolled_back_at:
        blockers.append("该合并已经回滚。")
    if fingerprint != record.rollback_fingerprint:
        blockers.append("合并后人物、关联或编辑状态已变化，不能覆盖后续修改。")
    if any(pending.values()):
        blockers.append("相关对象有新的待处理编辑内容。")
    newer = models.KnowledgePublicationEvent.objects.filter(
        catalog_revision__edition_id__in=record.affected_edition_ids,
        catalog_revision__status="preparing",
    ).exclude(pk__in=record.event_ids)
    if newer.exists():
        blockers.append("相关书目有后续发布仍在处理。")
    return {"can_rollback": not blockers, "fingerprint": fingerprint, "blockers": blockers}


@transaction.atomic
def rollback_person_merge(record_id, *, actor, expected_fingerprint, confirmed=False):
    _owner(actor)
    if confirmed is not True:
        raise ValueError("请先预览并人工确认人物合并回滚。")
    record = models.PersonMergeRecord.objects.select_for_update().get(pk=record_id)
    source, target = _locked_people(record.source_person_id, record.target_person_id)
    if record.rolled_back_at:
        return record
    record.source_person, record.target_person = source, target
    _state(source, target, record.affected_edition_ids, lock=True)
    preview = rollback_preview(record)
    if not preview["can_rollback"] or preview["fingerprint"] != expected_fingerprint:
        raise ValueError("合并后内容已变化或尚有新编辑，不能直接回滚。")
    # Restore the source identity before moving verified name variants back.
    source.authority_status = record.source_snapshot["authority_status"]
    source.merged_into_id = record.source_snapshot["merged_into_id"]
    source.save(update_fields=["authority_status", "merged_into", "updated_at"])
    for change in reversed(record.changes):
        model = apps.get_model(change["model"])
        row = model.objects.select_for_update().get(pk=change["id"])
        updates = change["before"]
        for name, value in updates.items():
            field = model._meta.get_field(name.removesuffix("_id") if name.endswith("_id") else name)
            setattr(row, name, field.target_field.to_python(value) if field.is_relation else field.to_python(value))
        row.save(update_fields=[*updates, "updated_at"])
        if model is models.CatalogFieldDecision:
            models.CatalogFieldDecisionLog.objects.create(
                decision=row, action="person_merge_rollback", old_value=change["after"].get("value"), new_value=row.value,
                actor=actor, reason=f"回滚人物合并 {record.pk}，保留原审核状态。",
            )
    models.CatalogPublicationRevision.objects.filter(
        knowledge_events__id__in=record.event_ids, status="preparing",
    ).update(status="superseded", superseded_at=timezone.now())
    events = _publish(source, target, record.affected_edition_ids, actor, record.pk, rollback=True)
    record.rolled_back_at = timezone.now()
    record.rolled_back_by = actor
    record.save(update_fields=["rolled_back_at", "rolled_back_by", "updated_at"])
    AuditEvent.objects.create(
        actor=actor, action="person_merge_rollback", object_type="catalog.PersonMergeRecord", object_id=str(record.pk),
        before={"source_id": str(source.pk), "target_id": str(target.pk)}, after={"event_ids": events},
    )
    return record
