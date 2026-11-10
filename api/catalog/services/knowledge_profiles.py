"""Constrained type data; existing organization/event tables keep their identity."""
from django.core.exceptions import ValidationError as ModelValidationError
from rest_framework.exceptions import ValidationError
from catalog import models as m
from django.db import transaction
from django.shortcuts import get_object_or_404

PROFILES = {
    "organization": ("organization", m.OrganizationAuthority, ("organization_type", "country", "original_name")),
    "event": ("timeline_event", m.TheoryTimelineEvent, ("event_type", "start_year", "end_year", "start_date", "end_date", "date_label", "date_precision", "source")),
    "research_object": ("research_object", m.ResearchObjectProfile, ("object_kind", "geographic_scope", "temporal_scope", "population", "unit_of_analysis")),
}


def profile_data(entity):
    descriptor = PROFILES.get(entity.kind)
    if not descriptor:
        return None
    field, _, fields = descriptor
    target = getattr(entity, field)
    if not target:
        return None
    return {name: getattr(target, name).isoformat() if name.endswith("_date") and getattr(target, name) else getattr(target, name) for name in fields}


def create_profile(kind, label, definition, payload):
    field, model, fields = PROFILES[kind]
    if not isinstance(payload, dict) or set(payload) - set(fields):
        raise ValidationError("类型资料包含不支持的字段。")
    defaults = {"preferred_name": label, "description": definition} if kind == "organization" else {"title": label, "description": definition, "event_type": "development"} if kind == "event" else {}
    target = model(**{**defaults, **payload})
    validate_profile(kind, target)
    target.save()
    return {field: target}


def validate_profile(kind, target):
    try:
        target.full_clean()
    except ModelValidationError as exc:
        raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from exc
    if kind == "event":
        if target.start_year is not None and target.end_year is not None and target.end_year < target.start_year:
            raise ValidationError("事件结束年份不能早于开始年份。")
        if target.date_precision != "unknown" and target.start_year is None:
            raise ValidationError("请填写与日期精度对应的起始年份。")
        if target.date_precision in {"day", "month"} and not target.start_date:
            raise ValidationError("日期或月份精度须填写开始日期。")
        if target.start_date and target.end_date and target.end_date < target.start_date:
            raise ValidationError("结束日期不能早于开始日期。")
        for date, year in ((target.start_date, target.start_year), (target.end_date, target.end_year)):
            if date and year is not None and date.year != year:
                raise ValidationError("日期与年份不一致。")


def profile_workspace(entity, actor):
    from .knowledge_core import require_editor, entity_data
    from .knowledge_workspace import source_hash
    require_editor(actor)
    value = entity_data(entity)
    value["profile_hash"] = source_hash("entity", entity.pk)
    value["profile_editable"] = entity.kind in PROFILES and profile_data(entity) is not None
    value["editor_url"] = f"/admin/theories/timeline?event={entity.timeline_event_id}" if entity.timeline_event_id else None
    return value


@transaction.atomic
def submit_profile(entity, profile, actor, *, request_id, base_hash):
    from uuid import uuid5
    from .knowledge_core import require_editor, page_metadata
    from .knowledge_workspace import source_hash
    from .knowledge_sources import digest
    from .intelligence_changes import submit_draft, uuid_value
    from ingestion.models import AuditEvent
    from .query_lexicon.mutations import acquire_entity_lock
    require_editor(actor)
    key = uuid_value(request_id)
    acquire_entity_lock("knowledge_profile_request", key)
    fingerprint = digest([str(entity.pk), profile, base_hash])
    previous = AuditEvent.objects.filter(pk=key).first()
    if previous:
        if previous.actor_id != actor.pk or previous.action != "knowledge.profile_submitted" or previous.after.get("input_hash") != fingerprint:
            raise ValidationError("请求编号已用于其他修改。")
        return get_object_or_404(m.ChangeSet, pk=previous.object_id)
    if entity.kind not in PROFILES or not profile_data(entity):
        raise ValidationError("此身份请沿现有专属资料编辑入口修改。")
    if entity.merged_into_id or source_hash("entity", entity.pk) != base_hash:
        raise ValidationError({"conflict": "身份资料已经变化，请重新读取。"})
    fields = PROFILES[entity.kind][2]
    if not isinstance(profile, dict) or set(profile) - set(fields):
        raise ValidationError("类型资料包含不支持的字段。")
    current = profile_data(entity)
    if all(current.get(name) == value for name, value in profile.items()):
        raise ValidationError("资料没有实际变化。")
    page, _ = m.KnowledgePage.objects.get_or_create(entity=entity, defaults={"title": entity.label, "slug": f"entity-{entity.pk}"})
    item = str(uuid5(key, "profile"))
    metadata = page_metadata(page, draft=True)
    result = submit_draft(None, [
        {"id": item, "kind": "entity", "dependencies": [], "payload": {"operation": "profile_patch", "entity_id": str(entity.pk),
            "kind": entity.kind, "label": entity.label, "profile": profile, "base_hash": base_hash, "page_id": str(page.pk)}},
        {"id": str(uuid5(key, "page")), "kind": "wiki_patch", "dependencies": [item], "payload": {"operation": "metadata", "page_id": str(page.pk),
            "block_id": str(uuid5(page.pk, "metadata")), "title": metadata["title"], "scope": metadata.get("scope", ""),
            "base_hash": digest(metadata), "human_edited": True, "reason": "审核类型资料并预览其展示"}},
    ], actor, request_id=key, origin="human", subject_entity=entity, subject_page=page)
    AuditEvent.objects.create(pk=key, actor=actor, action="knowledge.profile_submitted", object_type="changeset",
        object_id=str(result.pk), after={"input_hash": fingerprint})
    return result


@transaction.atomic
def stage_profile(payload, actor, *, request_key):
    from .knowledge_workspace import source_hash
    from .editorial_revision import create_editorial_revision
    entity = get_object_or_404(m.Entity.objects.select_for_update(), pk=payload["entity_id"], merged_into=None)
    page = get_object_or_404(m.KnowledgePage, pk=payload["page_id"], entity=entity)
    if entity.kind not in PROFILES or payload.get("base_hash") != source_hash("entity", entity.pk):
        raise ValidationError({"conflict": "身份资料已变化，请重新审核。"})
    field, _, fields = PROFILES[entity.kind]
    patch = payload.get("profile")
    if not isinstance(patch, dict) or not patch or set(patch) - set(fields):
        raise ValidationError("请提交合法的类型资料字段。")
    target = getattr(entity, field)
    if not target:
        raise ValidationError("类型资料尚未迁移。")
    if pending_profiles(page).exists():
        raise ValidationError({"conflict": "此身份已有保存的资料稿，请先在知识页核对并发布，再提交下一次修改。"})
    from copy import copy
    proposed = copy(target)
    for key, value in patch.items():
        setattr(proposed, key, value)
    validate_profile(entity.kind, proposed)
    revision = create_editorial_revision(target_type={"organization": "organization_profile", "event": "timeline_event", "research_object": "research_object_profile"}[entity.kind],
        target_id=target.pk, patch=patch, actor=actor, idempotency_key=request_key, change_note="知识工作区类型资料审核稿")
    return {"type": "entity_profile", "id": str(entity.pk), "revision_id": str(revision.pk), "page_id": str(page.pk),
        "base_hash": payload["base_hash"], "status": "draft"}


def pending_profiles(page):
    return m.ChangeItem.objects.filter(kind="entity", decision="accepted", application__type="entity_profile",
        application__page_id=str(page.pk), application__status="draft")


def publish_profiles(page, actor):
    from .knowledge_workspace import source_hash
    from .editorial_revision import publish_editorial_revision, EditorialRevisionError
    for item in pending_profiles(page).select_for_update():
        if source_hash("entity", item.application["id"]) != item.application["base_hash"]:
            raise ValidationError({"conflict": "已审核的身份资料基准已变化，请重新核对。"})
        try:
            publish_editorial_revision(item.application["revision_id"], actor=actor)
        except EditorialRevisionError as exc:
            raise ValidationError(str(exc)) from exc
        item.application = {**item.application, "status": "published"}
        item.save(update_fields=["application", "updated_at"])
