"""Replay existing private turn inputs; never reconstruct missing history from live state."""
import hashlib
import json

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from . import privacy, research, research_replay_history
from .models import ResearchImportReceipt, ResearchProject, ResearchTurn, ResearchReplayRevision

STOPPED_FORK = "cancelled:replay_fork"


def turn_for(user, project, pk):
    turn = research.owned(ResearchTurn, user, pk)
    if turn.project_id != project.pk:
        raise NotFound("该轮次不属于这份研究。")
    return turn


def inputs(turn):
    data = research.unpack(turn)
    return {"title": data.get("replay_title") or data.get("question") or "未命名轮次",
        "question": data.get("question", ""), "scope": data.get("scope", {}),
        "selections": data.get("selected_refs", []), "notes": data.get("replay_note", ""),
        "tags": data.get("replay_tags", []), "project_snapshot": data.get("project_snapshot"), "mode": data.get("mode", "search")}


def descriptor(turn):
    data = inputs(turn)
    parent_id = str(turn.parent_id) if turn.parent_id and ResearchTurn.objects.filter(pk=turn.parent_id, project_id=turn.project_id).exists() else None
    return {"id": str(turn.pk), "parent_id": parent_id,
        "revision": turn.revision, "title": data["title"], "question": data["question"], "status": turn.status,
        "created_at": turn.created_at, "updated_at": turn.updated_at,
        "material_count": len({research.reference_identity(ref) for ref in data["selections"]}),
        "snapshot_available": data["project_snapshot"] is not None}


def timeline(user, project_id, page):
    project = research.owned(ResearchProject, user, project_id)
    rows = project.turns.order_by("-created_at", "-id")
    count, start = rows.count(), (page - 1) * 20
    if page > 1 and start >= count:
        raise NotFound("这一页已没有轮次，请返回第一页。")
    payload = research.unpack(project)
    return {"owner_id": str(user.pk), "project": {"id": str(project.pk), "title": payload.get("title") or "未命名研究", "revision": project.revision, "archived": project.archived},
        "count": count, "page": page, "total_pages": max(1, (count + 19) // 20),
        "current_turn_id": payload.get("last_turn_id"), "results": [descriptor(row) for row in rows[start:start + 20]]}


def references(turn, key="selected_refs"):
    seen, result = set(), []
    for ref in research.unpack(turn).get(key, []):
        identity = research.reference_identity(ref)
        if identity not in seen:
            seen.add(identity)
            result.append(ref)
    return result


def detail(user, project_id, turn_id, compare_id=None):
    project = research.owned(ResearchProject, user, project_id)
    turn = turn_for(user, project, turn_id)
    compared = turn_for(user, project, compare_id) if compare_id else project.turns.filter(pk=turn.parent_id).first() if turn.parent_id else None
    data = inputs(turn)
    current, previous = references(turn), references(compared) if compared else []
    before, after = {research.reference_identity(ref) for ref in previous}, {research.reference_identity(ref) for ref in current}
    resolved = [research.resolve_reference(ref, user) for ref in current]
    previous_results = {research.reference_identity(ref) for ref in references(compared, "result_refs")} if compared else set()
    new_evidence = [research.resolve_reference(ref, user) for ref in references(turn, "result_refs")
        if research.reference_identity(ref) not in previous_results | after]
    removed = [research.resolve_reference(ref, user) for ref in previous if research.reference_identity(ref) not in after]
    snapshot = data["project_snapshot"]
    # Snapshot selections are locators, never cached source paragraphs or model authorization.
    return {"owner_id": str(user.pk), "project_id": str(project.pk), "project_revision": project.revision,
        "turn": descriptor(turn), "scope": data["scope"], "materials": resolved, "evidence": new_evidence,
        "added_ids": sorted(after - before), "unchanged_ids": sorted(after & before), "removed": removed,
        "compared": descriptor(compared) if compared else None,
        "scope_changed": compared is not None and data["scope"] != inputs(compared)["scope"],
        "previous_scope": inputs(compared)["scope"] if compared else None,
        "notes": data["notes"], "tags": data["tags"], "snapshot_notes": snapshot.get("notes", "") if snapshot else None,
        "snapshot_title": snapshot.get("title", "") if snapshot else None,
        "unavailable_count": sum(ref.get("source_status") != "available" for ref in resolved),
        "notice": "材料与范围来自本轮开始时实际保存的输入；来源在查看时重新核对。当前选材的后来变化不会补写为过去的历史。"}


@transaction.atomic
def edit_turn(user, project_id, turn_id, data):
    privacy.command_owner(user)
    project = research.owned(ResearchProject, user, project_id, lock=True)
    turn = turn_for(user, project, turn_id)
    turn = research.owned(ResearchTurn, user, turn.pk, lock=True)
    payload = research.unpack(turn)
    previous = research_replay_history.values(payload)
    if data.get("restore_id"):
        snapshot = ResearchReplayRevision.objects.filter(pk=data["restore_id"], turn=turn).first()
        if snapshot is None:
            raise NotFound("这条回放文字历史不属于当前轮次，或已删除。")
        saved = research.unpack(snapshot)
        changed = {key: saved[key] for key in ("title", "notes", "tags")}
    else:
        changed = {key: data[key] for key in ("title", "notes", "tags") if key in data}
    if all(previous[key] == value for key, value in changed.items()):
        return detail(user, project.pk, turn.pk)
    research.expect(turn, data["expected_revision"])
    if turn.status in research.ACTIVE:
        raise research.ResearchConflict("本轮仍在处理中，完成或取消后再编辑回放笔记。")
    research_replay_history.save_snapshot(turn, payload, "baseline")
    for key, value in changed.items():
        payload[{"title": "replay_title", "notes": "replay_note", "tags": "replay_tags"}[key]] = value
    research.save_data(turn, payload)
    research_replay_history.save_snapshot(turn, payload, "restore" if data.get("restore_id") else "edit", data.get("restore_id"))
    return detail(user, project.pk, turn.pk)


def fork_receipt(user, request_id):
    row = ResearchImportReceipt.objects.filter(user=user, request_id=request_id).first()
    if row is None:
        raise NotFound("尚未找到此账户的原创建回执。")
    project = ResearchProject.objects.filter(pk=row.project_id, user=user).first() if row.project_id else None
    if row.project_id and (project is None or not research.unpack(project).get("replay_origin")):
        raise NotFound("此回执不属于研究回放的创建操作。")
    # The caller learns only its own original project identity, never another owner's record.
    return {"owner_id": str(user.pk), "request_id": str(request_id), "project_id": str(row.project_id) if row.project_id else None,
        "deleted": row.project_id is None and row.fingerprint != STOPPED_FORK,
        "state": "cancelled" if row.fingerprint == STOPPED_FORK else "applied"}


@transaction.atomic
def stop_fork(user, request_id):
    privacy.command_owner(user)
    ResearchImportReceipt.objects.get_or_create(user=user, request_id=request_id, defaults={"fingerprint": STOPPED_FORK})
    return fork_receipt(user, request_id)


@transaction.atomic
def fork_project(user, project_id, turn_id, data):
    privacy.command_owner(user)
    fingerprint = hashlib.sha256(json.dumps({"operation": "replay_fork", "project_id": str(project_id), "turn_id": str(turn_id), **data}, sort_keys=True, default=str).encode()).hexdigest()
    previous = ResearchImportReceipt.objects.filter(user=user, request_id=data["request_id"]).first()
    if previous:
        if previous.fingerprint == STOPPED_FORK:
            return fork_receipt(user, data["request_id"])
        if previous.fingerprint != fingerprint:
            raise research.ResearchConflict("原创建请求已用于不同内容，请核对原结果。")
        return fork_receipt(user, data["request_id"])
    project = research.owned(ResearchProject, user, project_id, lock=True)
    research.expect(project, data["expected_project_revision"])
    turn = turn_for(user, project, turn_id)
    turn = research.owned(ResearchTurn, user, turn.pk, lock=True)
    research.expect(turn, data["expected_revision"])
    all_refs = {research.reference_identity(ref): ref for ref in [*references(turn), *references(turn, "result_refs")]}
    ids = data["reference_ids"]
    if not ids or len(ids) > 400 or len(set(ids)) != len(ids) or any(key not in all_refs for key in ids):
        raise ValidationError("请选择本轮实际保存的1至400项材料，不能混入其他轮次。")
    refs = [research.compact_reference(research.resolve_reference(all_refs[key], user, strict=True)) for key in ids]
    if ResearchProject.objects.filter(user=user, request_id=data["request_id"]).exists():
        raise research.ResearchConflict("此请求标识已用于另一研究创建，请核对原操作。")
    # New research is constrained to the explicitly selected passages. It does not
    # enqueue a query or carry forward any private-memory grants.
    result = research.create_project(user, {"request_id": data["request_id"], "title": data["title"], "question": data.get("question", ""),
        "scope": {"kind": "passages", "references": refs, "allow_neighbors": False}})
    payload = research.unpack(result)
    payload.update(selections=refs, notes=inputs(turn)["notes"] if data["include_notes"] else "",
        replay_origin={"project_id": str(project.pk), "turn_id": str(turn.pk), "turn_revision": turn.revision},
        use_confirmed_memories=False, confirmed_memory_ids=[])
    research.save_data(result, payload)
    for ref in refs:
        research.resolve_reference(ref, user, strict=True)
    ResearchImportReceipt.objects.create(user=user, project=result, request_id=data["request_id"], fingerprint=fingerprint)
    return fork_receipt(user, data["request_id"])
