"""Reviewed aliases become public only with their previewed identity page."""
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from catalog import models as m


def submit_alias(entity, payload, actor, *, request_id, base_hash):
    from uuid import uuid5
    from .intelligence_changes import submit_draft, uuid_value
    key = uuid_value(request_id)
    fields = {name: payload.get(name, "") for name in ("text", "language", "script")}
    return submit_draft(None, [{"id": str(uuid5(key, "alias")), "kind": "alias", "payload": {
        **fields, "entity_id": str(entity.pk), "base_hash": base_hash}}], actor,
        request_id=key, origin="human", subject_entity=entity)


def stage_alias(payload, actor, *, request_key, changeset):
    from .knowledge_core import require_editor, page_metadata
    from .knowledge_entity_queries import identity_text
    from .editorial_revision import create_editorial_revision
    require_editor(actor)
    entity = get_object_or_404(m.Entity.objects.select_for_update(), pk=payload["entity_id"], merged_into=None)
    from .knowledge_workspace import source_hash
    if payload.get("base_hash") and source_hash("entity", entity.pk) != payload["base_hash"]:
        raise ValidationError("归属身份已变化，请重新核对异名。")
    if any(not isinstance(payload.get(name, ""), str) for name in ("text", "language", "script")):
        raise ValidationError("异名、语言与书写方式必须是文本。")
    fields = {name: str(payload.get(name, "")).strip() for name in ("text", "language", "script")}
    if not fields["text"] or len(fields["text"]) > 600 or any(len(fields[v]) > 32 for v in ("language", "script")):
        raise ValidationError("异名须填写文本，最多600字；语言与书写方式最多32字。")
    alias = m.EntityAlias.objects.filter(entity=entity, **fields).order_by("created_at", "id").first()
    if alias and alias.review_status == "confirmed":
        return {"type": "alias", "id": str(alias.pk), "status": "published"}
    if alias is None:
        alias = m.EntityAlias.objects.create(entity=entity, **fields, review_status="draft",
            source={"changeset": str(changeset.pk), "reviewed_by": str(actor.pk)})
    page, _ = m.KnowledgePage.objects.get_or_create(entity=entity,
        defaults={"slug": f"entity-{entity.pk}", "title": identity_text(entity)[0]})
    revision = create_editorial_revision(target_type="knowledge_page", target_id=page.pk,
        patch=page_metadata(page, draft=True), actor=actor, idempotency_key=request_key,
        change_note="异名已审核，随当前知识页预览后发布")
    return {"type": "alias", "id": str(alias.pk), "page_id": str(page.pk), "revision_id": str(revision.pk), "status": "draft"}


def pending_aliases(page):
    return m.ChangeItem.objects.filter(kind="alias", decision="accepted", application__type="alias",
        application__page_id=str(page.pk), application__status="draft")


def alias_preview(page):
    ids = pending_aliases(page).values_list("application__id", flat=True)
    return list(m.EntityAlias.objects.filter(pk__in=list(ids), entity_id=page.entity_id)
        .values("id", "text", "language", "script"))


def publish_aliases(page, actor):
    from .knowledge_workspace import invalidate_source
    for item in pending_aliases(page).select_for_update():
        alias = get_object_or_404(m.EntityAlias.objects.select_for_update(), pk=item.application["id"], entity_id=page.entity_id)
        expected = {name: str(item.payload.get(name, "")).strip() for name in ("text", "language", "script")}
        if any(getattr(alias, key) != value for key, value in expected.items()) or alias.entity.merged_into_id:
            raise ValidationError("已审核异名或归属身份已变化，请重新审核。")
        alias.review_status = "confirmed"
        alias.save(update_fields=["review_status", "updated_at"])
        item.application = {**item.application, "status": "published"}
        item.save(update_fields=["application", "updated_at"])
    if page.entity_id:
        invalidate_source("entity", page.entity_id)
