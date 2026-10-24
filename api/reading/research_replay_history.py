"""Manual replay revisions never contain source paragraphs or memory grants."""
import json

from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError

from . import research
from .models import ResearchProject, ResearchReplayRevision


def values(payload):
    return {"title": payload.get("replay_title", ""), "notes": payload.get("replay_note", ""), "tags": payload.get("replay_tags", [])}


def save_snapshot(turn, payload, kind, restored_from=None):
    ResearchReplayRevision.objects.get_or_create(turn=turn, revision=turn.revision, defaults={"kind": kind,
        "data_ciphertext": research.pack({**values(payload), "source_updated_at": turn.updated_at.isoformat(),
            "restored_from": str(restored_from) if restored_from else None})})


def output(row, *, full=False):
    payload = research.unpack(row)
    result = {"id": str(row.pk), "revision": row.revision, "kind": row.kind, "recorded_at": row.created_at,
        "source_updated_at": payload.get("source_updated_at"), "title": payload.get("title", ""),
        "tags": payload.get("tags", []), "note_length": len(payload.get("notes", "")),
        "restored_from": payload.get("restored_from")}
    if full:
        result["notes"] = payload.get("notes", "")
    return result


def history(user, project_id, turn_id, page=1, revision_id=None):
    from .research_replay import turn_for
    project = research.owned(ResearchProject, user, project_id)
    turn = turn_for(user, project, turn_id)
    rows = turn.replay_revisions.order_by("-revision")
    count, start = rows.count(), (page - 1) * 20
    if page > 1 and start >= count:
        raise NotFound("这一页没有回放文字历史，请返回第一页。")
    selected = get_object_or_404(rows, pk=revision_id) if revision_id else None
    result = {"owner_id": str(user.pk), "project_id": str(project.pk), "turn_id": str(turn.pk), "current_revision": turn.revision,
        "count": count, "page": page, "total_pages": max(1, (count + 19) // 20),
        "results": [output(row) for row in rows[start:start + 20]], "selected": output(selected, full=True) if selected else None,
        "notice": "只记录开始保留历史之后的本人回放文字。保存前记录不是过去未保存的历史；原问题与起始选材不被恢复操作改写。删除本轮或整份研究会同时删除这些历史。"}
    if not project.turns.filter(pk=turn.pk, revision=turn.revision, project__user=user).exists():
        raise research.ResearchConflict("这条轮次刚刚修改或删除，请重新读取文字历史。")
    return result


def export_turn(turn, user):
    if turn.project.user_id != user.pk:
        raise NotFound("这条研究轮次不属于当前账户。")
    result = research.serialize_record(turn, user)
    history_rows, size = [], 0
    for row in turn.replay_revisions.order_by("revision").iterator(chunk_size=50):
        size += len(row.data_ciphertext)
        if size > 25 * 1024 * 1024:
            raise ValidationError("这一轮的回放历史超过25MiB，请在回放文字历史中逐版本查看和保存；没有返回不完整导出。")
        value = output(row, full=True)
        value["recorded_at"] = value["recorded_at"].isoformat()
        history_rows.append(value)
    result["data"]["replay_history"] = history_rows
    if not turn.project.turns.filter(pk=turn.pk, revision=turn.revision, project__user=user).exists():
        raise research.ResearchConflict("回放文字在导出时发生变化，请重新导出。")
    return result


def export_turns(project, user):
    output_rows, versions, size = [], {}, 0
    for turn in project.turns.select_related("project").order_by("created_at", "id").iterator(chunk_size=20):
        value = export_turn(turn, user)
        size += len(json.dumps(value, ensure_ascii=False, default=str).encode("utf-8"))
        if size > 25 * 1024 * 1024:
            raise ValidationError("研究轮次及回放历史超过单次25MiB导出范围，请在回放页逐版本保存；本次没有返回截断资料。")
        output_rows.append(value)
        versions[str(turn.pk)] = turn.revision
    if versions != {str(pk): revision for pk, revision in project.turns.values_list("pk", "revision")} or not ResearchProject.objects.filter(pk=project.pk, user=user, revision=project.revision).exists():
        raise research.ResearchConflict("研究或回放文字在导出时发生变化，请重新导出。")
    return output_rows
