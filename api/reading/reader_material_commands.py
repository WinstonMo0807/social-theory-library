"""R22 selection commands delegate to the original private workspaces."""
from uuid import uuid5, NAMESPACE_URL

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from ingestion.models import AuditEvent
from . import booklists, notebook, privacy, reader_center, research

ACTION = "reader_material_command"
RENAMABLE = {"research", "lists", "bookmarks"}


def receipt(user, request_id):
    row = AuditEvent.objects.filter(actor=user, action=ACTION, request_id=str(research.identifier(request_id))).first()
    if row is None:
        raise NotFound("尚未找到本人的原操作回执；请求可能仍在途中，可稍后查回或停止尚未执行的请求。")
    return {"owner_id": str(user.pk), "request_id": row.request_id, **{key: row.after[key] for key in ("state", "action", "applied")}}


@transaction.atomic
def stop(user, request_id):
    user = privacy.command_owner(user)
    request_id = str(research.identifier(request_id))
    try:
        return receipt(user, request_id)
    except NotFound:
        AuditEvent.objects.create(actor=user, action=ACTION, object_type="ReaderMaterial", object_id="",
            request_id=request_id, after={"state": "cancelled", "action": "", "applied": []})
        return receipt(user, request_id)


@transaction.atomic
def command(user, data):
    user = privacy.command_owner(user)
    request_id = str(research.identifier(data["request_id"]))
    fingerprint = research.request_fingerprint(data, ("action", "targets"))
    prior = AuditEvent.objects.filter(actor=user, action=ACTION, request_id=request_id).first()
    if prior:
        if prior.after.get("state") == "cancelled":
            raise research.ResearchConflict("原操作已停止，迟到的同一请求不会生效。请重新选择资料。")
        if prior.after.get("fingerprint") != fingerprint:
            raise research.ResearchConflict("原编号已用于另一项操作，请查回原结果。")
        return receipt(user, request_id)
    verb, targets = data["action"], data["targets"]
    if verb not in {"rename", "archive", "restore"} or not targets or len(targets) > (20 if verb == "rename" else 100):
        raise ValidationError("重命名一次最多20项；归档或恢复一次最多100项。")
    seen, locked = set(), []
    for target in sorted(targets, key=lambda row: (row["kind"], str(row["id"]))):
        kind, pk = target["kind"], str(research.identifier(target["id"]))
        if kind not in (RENAMABLE if verb == "rename" else {"research"}):
            raise ValidationError("只能重命名研究、书单与书签，或归档/恢复研究。笔记正文和计划目标请在原工作台编辑。")
        if (kind, pk) in seen:
            raise ValidationError("同一份资料不能重复选择。")
        seen.add((kind, pk))
        row = reader_center.collection(user, kind).select_for_update().filter(pk=pk).first()
        if row is None:
            raise NotFound("所选本人资料已不存在；本次全部更改均未执行。")
        if privacy.version(row) != target["revision"]:
            raise research.ResearchConflict("所选资料已变化；本次全部更改均未执行，请刷新后重新选择。")
        if verb == "rename":
            research.text(target.get("title"), "title", 240, True)
        locked.append((target, row))
    applied = []
    for target, row in locked:
        kind = target["kind"]
        if kind == "research":
            changes = {"title": target["title"]} if verb == "rename" else {"archived": verb == "archive"}
            if verb == "rename" or row.archived != changes["archived"]:
                row = research.update_project(user, row.pk, {"expected_revision": row.revision, **changes})
        elif kind == "lists":
            booklists.command(user, {"list_id": str(row.pk), "request_id": str(uuid5(NAMESPACE_URL, f"stl:reader-material:{request_id}:{row.pk}")),
                "expected_version": booklists.version(row), "action": "edit", "title": research.text(target["title"], "title", 240, True)})
            row.refresh_from_db()
        else:
            notebook.edit(user, "bookmarks", row.pk, {"expected_version": privacy.version(row), "label": research.text(target["title"], "title", 240, True)})
            row.refresh_from_db()
        applied.append({"kind": kind, "id": str(row.pk), "revision": privacy.version(row)})
    AuditEvent.objects.create(actor=user, action=ACTION, object_type="ReaderMaterial", object_id="", request_id=request_id,
        after={"state": "applied", "action": verb, "applied": applied, "fingerprint": fingerprint})
    return receipt(user, request_id)
