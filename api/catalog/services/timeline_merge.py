"""Explicit event merge on original revisions, with guarded, non-destructive reversal."""
from copy import copy, deepcopy
from hashlib import sha256
import json
from uuid import uuid4, uuid5

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, TextField
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from common.capabilities import Capability, has_capability
from catalog import models
from catalog.services import content_placements as placements
from catalog.services.editorial_drafts import save_object_editorial_patch
from catalog.services.editorial_revision import editorial_target_snapshot, publish_editorial_revision
from catalog.services.person_authority import AuthorityConflict
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock
from catalog.services.relation_editorial import _relation_key
from catalog.timeline_editor import validate_timeline_details
from ingestion.models import AuditEvent


def digest(value):
    return sha256(json.dumps(value, cls=DjangoJSONEncoder, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def scope_queries(source_id, target_id):
    ids = [source_id, target_id]
    revisions = models.EditorialRevision.objects.annotate(merge_text=Cast("materialized_preview", TextField()))
    return {
        "events": models.TheoryTimelineEvent.objects.filter(Q(pk__in=ids) | Q(merged_into_id__in=ids)),
        "relations": models.TimelineEventRelation.objects.filter(event_id__in=ids),
        "images": models.TimelineEvidenceImage.objects.filter(event_id__in=ids),
        "revisions": revisions.filter(Q(target_type="timeline_event", target_id__in=ids)
            | Q(target_type=placements.KIND, target_id__in=[placements.target_id("timeline_event", key) for key in ids])
            | Q(merge_text__icontains=str(source_id)) | Q(merge_text__icontains=str(target_id))),
        "canonical": models.CanonicalObjectRevision.objects.filter(object_type="timeline_event", object_id__in=ids),
        "bundles": models.PublicationBundleItem.objects.filter(object_type="timeline_event", object_id__in=ids, bundle__status__in=["draft", "publishing", "failed"]),
    }


def scope_state(source, target, *, lock=False):
    state = {}
    # ponytail: bound each original dependency collection; never truncate a rollback guard.
    for name, query in scope_queries(source.pk, target.pk).items():
        if lock:
            query = query.select_for_update()
        rows = list(query.order_by("pk").values()[:5001])
        if len(rows) > 5000:
            raise ValidationError("事件引用或历史超过本次归并上限，请先核对范围。")
        state[name] = rows
    return state


def _placement_snapshot(event):
    revision = placements.revisions("timeline_event", event.pk).first()
    return {"revision_id": str(revision.pk) if revision else None, "status": revision.status if revision else "",
            "items": deepcopy(revision.materialized_preview.get("items", [])) if revision else [],
            "groups": deepcopy(revision.materialized_preview.get("groups", [])) if revision else []}


def _snapshot(event):
    return editorial_target_snapshot(target_type="timeline_event", target=event)


def _summary(event):
    return {"id": str(event.pk), "title": event.title, "event_type": event.get_event_type_display(),
            "date_label": event.date_label, "start_year": event.start_year, "end_year": event.end_year,
            "start_date": event.start_date, "end_date": event.end_date, "date_precision": event.get_date_precision_display(),
            "review_status": event.review_status, "source": event.source, "description": event.description,
            "editor_url": f"/admin/theories/timeline?event={event.pk}"}


def _merged_page(source, source_page, target_page):
    items, groups = deepcopy(target_page["items"]), deepcopy(target_page["groups"])
    names = {(row["area"], row["name"]) for row in groups}
    names.update((row["area"], row["group"]) for row in items)
    mapping = {}
    incoming_groups = [*source_page["groups"], *({"area": row["area"], "name": row["group"]} for row in source_page["items"])]
    for group in incoming_groups:
        key = (group["area"], group["name"])
        if key in mapping:
            continue
        name, counter = key[1], 1
        while (key[0], name) in names:
            name = f"来源事件{' ' + str(counter) if counter > 1 else ''} · {key[1]}"
            counter += 1
        if len(name) > 240:
            raise ValidationError("来源编排分组名称过长，请先缩短原分组名称，避免归并时丢失说明。")
        mapping[key] = name
        names.add((key[0], name))
        groups.append({"area": key[0], "name": name})
    used = {row["id"] for row in items}
    for item in deepcopy(source_page["items"]):
        if item["id"] in used:
            item["id"] = str(uuid5(source.pk, item["id"]))
        used.add(item["id"])
        item["group"] = mapping[(item["area"], item["group"])]
        items.append(item)
    return {"items": placements._normalize(items, existing=target_page["items"], page_type="timeline_event"), "groups": placements._groups(groups, items)}


def _proposal(source, target):
    source_snapshot, target_snapshot = _snapshot(source), _snapshot(target)
    details = deepcopy(target.editorial_details or {})
    rows = details.setdefault("sources", [])
    known = {row["id"]: row for row in rows}
    candidates = deepcopy((source.editorial_details or {}).get("sources", []))
    if source.source or source.evidence_text or source.evidence_asset_id or (source.editorial_details or {}).get("primary_image_rendition_id"):
        candidates.insert(0, {"id": str(uuid5(source.pk, "merged-primary-evidence")), "kind": (source.editorial_details or {}).get("primary_kind", "other"),
            "citation": source.source or source.title, "locator": source.evidence_printed_label,
            "quote": source.evidence_text, "asset_id": str(source.evidence_asset_id) if source.evidence_asset_id else None,
            "page": source.evidence_page, "status": "related",
            "image_rendition_id": (source.editorial_details or {}).get("primary_image_rendition_id")})
    for row in candidates:
        if row["id"] in known:
            if known[row["id"]] == row:
                continue
            row["id"] = str(uuid5(source.pk, row["id"]))
        rows.append(row)
        known[row["id"]] = row
    for field in ("time_note", "conflict_note", "editor_note", "duplicate_reason"):
        value = (source.editorial_details or {}).get(field, "")
        if value and value != details.get(field):
            details[field] = "\n\n".join(filter(None, [details.get(field, ""), f"来源事件《{source.title}》：{value}"]))
    details["confirmed"] = True
    details = validate_timeline_details(details)
    relations = deepcopy(target_snapshot["timeline_relations"])
    known_relations = {_relation_key(row): row for row in relations}
    for row in source_snapshot["timeline_relations"]:
        key = _relation_key(row)
        old = known_relations.get(key)
        if old and any(old.get(field, "") != row.get(field, "") for field in ("participant_role", "description")):
            raise ValidationError("两条事件对同一关联的角色或说明不同，请先在原事件中核对，不能自动覆盖。")
        if old is None:
            relations.append(row)
            known_relations[key] = row
    for field in ("scholar", "work", "discipline"):
        identifier = source_snapshot.get(field)
        if identifier and identifier != target_snapshot.get(field) and not any(str(row.get(field) or "") == str(identifier) for row in relations):
            relations.append({"relation_type": "subject", field: identifier, "participant_role": "subject" if field == "scholar" else "", "description": "", "sort_order": len(relations)})
    patch = {"editorial_details": details, "timeline_relations": relations,
             "review_status": "approved" if "approved" in {source.review_status, target.review_status} else target.review_status}
    for field in ("subject_edition", "scholar", "work", "discipline", "subdiscipline", "theory_school"):
        if not target_snapshot.get(field) and source_snapshot.get(field):
            patch[field] = source_snapshot[field]
    from catalog.services.relation_editorial import validate_relation_patch
    from catalog.services.editorial_revision import EditorialRevisionError
    from catalog.timeline_editor import ensure_timeline_publication
    try:
        validate_relation_patch(target, patch)
        if patch["review_status"] == "approved":
            candidate = copy(target)
            for field, value in patch.items():
                if field != "timeline_relations":
                    model_field = target._meta.get_field(field)
                    setattr(candidate, model_field.attname, model_field.to_python(value))
            ensure_timeline_publication(candidate)
    except EditorialRevisionError as error:
        raise ValidationError(str(error)) from error
    return patch


def merge_preview(source, target):
    state = scope_state(source, target)
    blockers = []
    expected = {("catalog.TheoryTimelineEvent", "merged_into"), ("catalog.TimelineEventRelation", "event"),
                ("catalog.TimelineEvidenceImage", "event"), ("catalog.TimelineMergeRecord", "source"), ("catalog.TimelineMergeRecord", "target")}
    if any((row.related_model._meta.label, row.field.name) not in expected for row in models.TheoryTimelineEvent._meta.related_objects):
        blockers.append("出现尚未纳入预览的事件引用，需先完善归并范围。")
    from catalog.timeline_editor import ensure_timeline_publication
    for event in (source, target):
        if event.review_status == "approved":
            try:
                ensure_timeline_publication(event)
            except ValidationError:
                blockers.append(f"《{event.title}》的原公开资料未通过当前核对要求，须先修正以确保可回退。")
    if source.pk == target.pk:
        blockers.append("不能将事件合并到自身。")
    if source.merged_into_id or target.merged_into_id or source.merged_sources.exists() or target.merged_sources.exists():
        blockers.append("事件涉及尚未回退的归并，请先打开原归并记录核对。")
    if source.event_type != target.event_type:
        blockers.append("事件类型不同，不能把原著、译介、上架等混为一条。")
    if source.subject_edition_id and target.subject_edition_id and source.subject_edition_id != target.subject_edition_id:
        blockers.append("两个事件对应不同出版版本，请保留独立记录。")
    if source.work_id and target.work_id and source.work_id != target.work_id:
        blockers.append("两个事件对应不同作品，请先核对。")
    for field in ("subdiscipline", "theory_school"):
        if getattr(source, f"{field}_id") and getattr(target, f"{field}_id") and getattr(source, f"{field}_id") != getattr(target, f"{field}_id"):
            blockers.append("两个事件的主要领域归属不同，请先在原记录中核对。")
    if source.event_type in {"birth", "death"} and source.scholar_id != target.scholar_id:
        blockers.append("出生或去世事件的主要人物不同，不能直接归并。")
    if any(row["status"] == "draft" for row in state["revisions"] if row["target_type"] in {"timeline_event", placements.KIND}):
        blockers.append("相关事件或编排仍有待处理草稿，请先保存并处理原修订。")
    if state["bundles"]:
        blockers.append("相关事件正在发布队列中，请先处理原发布任务。")
    source_page, target_page = _placement_snapshot(source), _placement_snapshot(target)
    if len(source_page["items"]) + len(target_page["items"]) > 100:
        blockers.append("合并后页面引用超过100项，请先整理原编排。")
    proposal = None
    try:
        proposal = _proposal(source, target)
        _merged_page(source, source_page, target_page)
    except ValidationError as error:
        blockers.append(str(error.detail))
    if source.review_status == "rejected" or target.review_status == "rejected":
        blockers.append("已拒绝或下线的事件须先恢复核对，再归并。")
    return {"source": _summary(source), "target": _summary(target), "fingerprint": digest(state),
            "can_merge": not blockers, "blockers": blockers,
            "source_count": len(proposal["editorial_details"]["sources"]) if proposal else 0,
            "relation_count": len(proposal["timeline_relations"]) if proposal else 0,
            "placement_count": len(source_page["items"]) + len(target_page["items"]),
            "will_be_public": bool(proposal and proposal["review_status"] == "approved"),
            "rule": "保留右侧事件的标题、日期精度、主要出处及展示图片；汇入左侧出处、关联和页面编排，原事件与全部历史保留。"}


def _actor(actor):
    current = get_object_or_404(User.objects.select_for_update(), pk=actor.pk, is_active=True)
    if current.token_version != actor.token_version or not has_capability(current, Capability.MERGE_AUTHORITY):
        raise PermissionDenied("当前会话没有归并与回退权限，请由系统所有者核对。")
    return current


def _pair(source_id, target_id):
    rows = {row.pk: row for row in models.TheoryTimelineEvent.objects.select_for_update().filter(pk__in=[source_id, target_id]).order_by("pk")}
    if source_id not in rows or target_id not in rows:
        raise ValidationError("原事件已不存在，请重新读取。")
    return rows[source_id], rows[target_id]


def _apply(event, patch, actor, note):
    revision = save_object_editorial_patch("timeline_event", event.pk, patch, actor=actor, change_note=note)
    if revision:
        publish_editorial_revision(revision.pk, actor=actor)
    event.refresh_from_db()


def _page_command(event, actor, action, **data):
    latest = placements.revisions("timeline_event", event.pk).first()
    return placements.command("timeline_event", event.pk, {"action": action, "request_id": str(uuid4()), "expected_revision": placements.version(latest), **data}, actor)


def _save_page(event, actor, payload):
    _page_command(event, actor, "save", items=payload["items"], groups=payload["groups"])
    if event.review_status == "approved":
        _page_command(event, actor, "publish")


@transaction.atomic
def merge_events(source_id, target_id, *, actor, fingerprint, request_id, confirmed):
    actor = _actor(actor)
    if confirmed is not True:
        raise ValidationError("请先核对两条事件及完整影响范围。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock("timeline_merge_request", request_id)
    request_fingerprint = digest({"source": source_id, "target": target_id, "actor": actor.pk, "fingerprint": fingerprint})
    previous = models.TimelineMergeRecord.objects.filter(pk=request_id).first()
    if previous:
        if previous.request_fingerprint != request_fingerprint:
            raise AuthorityConflict("这个请求编号已用于另一项归并。")
        return previous
    if AuditEvent.objects.filter(pk=request_id).exists():
        raise AuthorityConflict("这个请求编号已被另一项操作使用。")
    source, target = _pair(source_id, target_id)
    scope_state(source, target, lock=True)
    preview = merge_preview(source, target)
    if preview["fingerprint"] != fingerprint or not preview["can_merge"]:
        raise AuthorityConflict({"detail": "事件或引用已变化，请重新预览。", "blockers": preview["blockers"]})
    before = {"source": _snapshot(source), "target": _snapshot(target), "source_page": _placement_snapshot(source), "target_page": _placement_snapshot(target)}
    proposal = _proposal(source, target)
    _apply(target, proposal, actor, "人工确认重复事件归并，保留来源与原事件历史")
    if before["source_page"]["items"] or before["source_page"]["groups"]:
        _save_page(target, actor, _merged_page(source, before["source_page"], before["target_page"]))
        _page_command(source, actor, "withdraw")
    _apply(source, {"review_status": "rejected"}, actor, "重复事件归并，原身份及历史保留")
    source.merged_into = target
    source.save(update_fields=["merged_into", "updated_at"])
    record = models.TimelineMergeRecord.objects.create(pk=request_id, source=source, target=target, created_by=actor,
        request_fingerprint=request_fingerprint, before=before, rollback_fingerprint=digest(scope_state(source, target)))
    AuditEvent.objects.create(pk=request_id, actor=actor, action="timeline_merge", object_type=models.TimelineMergeRecord._meta.label, object_id=str(record.pk),
        after={"source_id": str(source.pk), "target_id": str(target.pk), "merge_id": str(record.pk), "fingerprint": request_fingerprint,
               "operation": "merge", "saved_version": record.rollback_fingerprint})
    return record


def rollback_preview(record):
    fingerprint = digest(scope_state(record.source, record.target))
    blockers = []
    if record.rolled_back_at:
        blockers.append("这次归并已经回退。")
    if fingerprint != record.rollback_fingerprint:
        blockers.append("归并后事件、编排、引用或修订已经变化，不能覆盖后续工作。")
    return {"fingerprint": fingerprint, "can_rollback": not blockers, "blockers": blockers}


@transaction.atomic
def rollback_merge(record_id, *, actor, fingerprint, confirmed):
    actor = _actor(actor)
    if confirmed is not True:
        raise ValidationError("请先核对回退影响。")
    acquire_generation_lock(shared=True)
    record = get_object_or_404(models.TimelineMergeRecord.objects.select_for_update(), pk=record_id)
    if record.rolled_back_at:
        return record
    source, target = _pair(record.source_id, record.target_id)
    state = scope_state(source, target, lock=True)
    if digest(state) != fingerprint or fingerprint != record.rollback_fingerprint:
        raise AuthorityConflict("归并后已有修改，请重新预览；不会覆盖后续资料。")
    source.merged_into = None
    source.save(update_fields=["merged_into", "updated_at"])
    _apply(source, record.before["source"], actor, "回退重复事件归并")
    _apply(target, record.before["target"], actor, "回退重复事件归并")
    if record.before["source_page"]["items"] or record.before["source_page"]["groups"]:
        for event, key in ((source, "source_page"), (target, "target_page")):
            _save_page(event, actor, record.before[key])
    record.rolled_back_at = timezone.now()
    record.save(update_fields=["rolled_back_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="timeline_merge_rollback", object_type="timeline_event", object_id=str(source.pk), after={"merge_id": str(record.pk), "target_id": str(target.pk)})
    return record


def resolved_event_id(identifier):
    row = models.TheoryTimelineEvent.objects.only("merged_into_id").filter(pk=identifier).first()
    return row.merged_into_id if row and row.merged_into_id else identifier
