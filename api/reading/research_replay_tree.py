"""Read original owner-only turn parents and explicitly created project forks."""
from time import monotonic
from uuid import UUID

from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, ValidationError

from . import research, research_replay
from .models import ResearchProject, ResearchTurn


def turn_rows(project, parent=None):
    rows = project.turns.annotate(child_count=Count("branches", filter=Q(branches__project=project)))
    if parent:
        rows = rows.filter(parent=parent)
    else:
        # A legacy parent from another project is not a readable ancestor.
        rows = rows.filter(Q(parent__isnull=True) | ~Q(parent__project=project))
    return rows.order_by("created_at", "id")


def turn_tree(user, project_id, parent_id=None, page=1):
    project = research.owned(ResearchProject, user, project_id)
    parent = research_replay.turn_for(user, project, parent_id) if parent_id else None
    rows = turn_rows(project, parent)
    count, start = rows.count(), (page - 1) * 20
    if page > 1 and start >= count:
        raise NotFound("这一页已没有分支，请返回第一页。")
    selected = list(rows[start:start + 20])
    results = [{**research_replay.descriptor(row), "child_count": row.child_count} for row in selected]
    current = list(rows.values_list("pk", "revision", "parent_id")[start:start + 20])
    if current != [(row.pk, row.revision, row.parent_id) for row in selected] or rows.count() != count or len(results) != min(20, max(0, count - start)) or not ResearchProject.objects.filter(pk=project.pk, user=user, revision=project.revision).exists():
        raise research.ResearchConflict("研究路径刚刚变化，请重新读取。")
    return {"owner_id": str(user.pk), "project_id": str(project.pk), "parent_id": str(parent.pk) if parent else None,
        "count": count, "page": page, "total_pages": max(1, (count + 19) // 20), "results": results}


def project_links(user, project_id, page=1):
    project = research.owned(ResearchProject, user, project_id)
    base = ResearchProject.objects.filter(user=user).order_by("created_at", "id")
    count = base.count()
    # ponytail: encrypted fork metadata reuses original records, bounded to
    # 5000 projects/32 MiB/20 seconds; larger accounts need an indexed migration.
    if count > 5000:
        raise ValidationError("研究超过5000份，当前关联读取范围过大；可继续按研究目录打开原记录。")
    summaries, versions, origins = {}, {}, {}
    size, started = 0, monotonic()
    for row in base.iterator(chunk_size=100):
        size += len(row.data_ciphertext)
        if size > 32 * 1024 * 1024 or monotonic() - started > 20:
            raise ValidationError("研究关联读取范围过大，未返回不完整关系；请从研究目录继续。")
        payload = research.unpack(row)
        key = str(row.pk)
        versions[key] = row.revision
        summaries[key] = {"id": key, "revision": row.revision, "title": payload.get("title") or "未命名研究",
            "archived": row.archived, "created_at": row.created_at}
        origins[key] = payload.get("replay_origin") or {}
    key = str(project.pk)
    if key not in summaries:
        raise NotFound("这份本人研究已经删除。")
    origin = origins[key]
    parent = summaries.get(str(origin.get("project_id")))
    if parent and parent["id"] == key:
        parent = None
    # Missing/deleted/out-of-owner source identities are never reflected back.
    try:
        source_id = UUID(str(origin.get("turn_id"))) if parent else None
    except (ValueError, TypeError, AttributeError):
        source_id = None
    source_turn = ResearchTurn.objects.filter(pk=source_id, project_id=parent["id"], project__user=user).first() if parent and source_id else None
    parent_link = {**parent, "turn_id": str(source_turn.pk) if source_turn else None} if parent else None
    children = [value for child_id, value in summaries.items() if child_id != key and str(origins[child_id].get("project_id")) == key]
    start = (page - 1) * 20
    if page > 1 and start >= len(children):
        raise NotFound("这一页已没有派生研究，请返回第一页。")
    selected = children[start:start + 20]
    own_turns = {str(value) for value in project.turns.values_list("pk", flat=True)}
    results = [{**value, "turn_id": str(origins[value["id"]].get("turn_id")) if str(origins[value["id"]].get("turn_id")) in own_turns else None}
        for value in selected]
    current = {str(pk): revision for pk, revision in base.values_list("pk", "revision")}
    if current != versions or len(versions) != count:
        raise research.ResearchConflict("研究关联在读取时发生变化，请重新读取。")
    return {"owner_id": str(user.pk), "project_id": key, "parent": parent_link,
        "origin_unavailable": bool(origin) and parent_link is None, "count": len(children),
        "page": page, "total_pages": max(1, (len(children) + 19) // 20), "results": results}
