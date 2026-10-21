"""A public projection of the existing path and editorial revision ledger.

GETs never create a version. Historical snapshots are rechecked against current
publication/access; private readers reuse this projection, never draft JSON.
"""
from catalog.services.contribution_scope import whole_edition_contribution
from copy import deepcopy
from hashlib import sha256
import json
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from django.db import transaction
from django.db.models import F, Q, Window
from django.db.models.functions import RowNumber
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import Discipline, EditorialRevision, KnowledgeNode, Page, ReadingPath, Topic
from catalog.services.publication_eligibility import public_editions

PATH_FIELDS = ("title", "slug", "introduction", "learning_goal", "audience", "difficulty", "estimated_reading",
               "estimated_weeks", "prerequisite", "learning_questions", "related_debate_ids", "curator_note", "credits")
SOURCE_NOTICES = {
    "available": "当前公开版本可按所列位置阅读。",
    "no_fulltext": "书目已公开，暂无可公开阅读的全文。",
    "unavailable": "材料当前不可公开访问；已有阅读记录不因此删除。",
    "withdrawn": "策划已撤回此材料；已有阅读记录与笔记保留。",
    "revision_changed": "指定阅读文件或正文修订已变化，请核对版本；不会自动改指其他来源。",
}


def _id(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError):
        return None


def _ids(values):
    return {identifier for value in values if (identifier := _id(value))}


def _raw(path):
    from catalog.services.editorial_revision import editorial_target_snapshot
    return editorial_target_snapshot(target_type="reading_path", target=path)


def _pinned_groups(groups):
    """Resolve only previously unspecified sources; never substitute a pinned one."""
    groups = deepcopy(groups)
    rows = [item for group in groups for item in group.get("items", [])]
    wanted = _ids(row.get("edition") for row in rows)
    work_ids = _ids(row.get("work") for row in rows if not row.get("edition"))
    editions, preferred = {}, {}
    for edition in public_editions().filter(Q(pk__in=wanted) | Q(work_id__in=work_ids)).order_by("-is_primary", "-published_at", "id"):
        editions[str(edition.pk)] = edition
        preferred.setdefault(str(edition.work_id), edition)
    for row in rows:
        if row.get("node"):
            row["material_kind"] = "node"
            continue
        edition = editions.get(str(row.get("edition"))) if row.get("edition") else preferred.get(str(row.get("work")))
        if not edition or str(edition.work_id) != str(row.get("work")):
            continue
        row["edition"] = str(edition.pk)
        active = edition.active_catalog_revision
        if not row.get("asset") and not row.get("document_revision") and active.fulltext_ready and active.reader_asset_id and active.document_revision_id:
            row["asset"], row["document_revision"] = str(active.reader_asset_id), str(active.document_revision_id)
    return groups


@transaction.atomic
def capture_reading_path_publication(path, *, actor, revision=None, change_note="发布阅读路径"):
    """Called inside authorized publication, including the legacy direct writer."""
    from catalog.services.reading_paths import reading_path_stage_groups
    ReadingPath.objects.select_for_update().get(pk=path.pk)
    groups = _pinned_groups(reading_path_stage_groups(path))
    for group in groups:
        for row in group["items"]:
            path.items.filter(pk=row["id"]).update(
                edition_id=row.get("edition"), asset_id=row.get("asset"),
                document_revision_id=row.get("document_revision"), material_kind=row.get("material_kind", "work"))
    snapshot = _raw(path)
    if revision is not None:
        revision.materialized_preview = snapshot
        return revision
    last = EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk).order_by("-revision").first()
    return EditorialRevision.objects.create(target_type="reading_path", target_id=path.pk,
        revision=(last.revision if last else 0) + 1, base_revision=last.revision if last else 0,
        patch={}, materialized_preview=snapshot, changed_fields=[], status="published",
        idempotency_key=f"reading-path-publication:{uuid4()}", change_note=change_note,
        created_by=actor, published_by=actor, published_at=timezone.now())


def _revision_output(row=None, *, raw=None):
    return {"id": str(row.pk) if row else None, "token": str(row.pk) if row else "legacy:" + sha256(
        json.dumps(raw, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest(),
        "number": row.revision if row else None, "published_at": row.published_at.isoformat() if row and row.published_at else None,
        "change_note": row.change_note if row else "历史已发布路径，尚无独立发布快照。", "legacy": row is None}


def _link(row, kind):
    return {"id": str(row.pk), "title": row.canonical_name_zh if kind == "node" else row.name,
            "slug": row.slug, "href": f"/theories/nodes/{row.slug}" if kind == "node" else f"/topics/{row.slug}"}


def _projection_context(raws):
    groups = [group for raw in raws for group in raw.get("stage_groups", [])]
    rows = [row for group in groups for row in group.get("items", [])]
    edition_ids = _ids([*(row.get("edition") for row in rows), *(value for row in rows for value in row.get("substitute_edition_ids", []))])
    editions = {str(row.pk): row for row in public_editions().filter(pk__in=edition_ids)}
    node_ids = _ids([*(row.get("node") for row in rows), *(value for raw in raws for value in raw.get("related_debate_ids", [])),
                     *(value for group in groups for value in group.get("related_debate_ids", []))])
    nodes = {str(row.pk): row for row in KnowledgeNode.objects.filter(pk__in=node_ids, status="published")}
    topics = {str(row.pk): row for row in Topic.objects.filter(pk__in=_ids(value for raw in raws for value in raw.get("topics", [])), editorial_status="published").order_by("name", "id")}
    # Only boundary pages are needed. Neither text nor any unpublished file is returned.
    pages = set(Page.objects.filter(asset_id__in=_ids(row.get("asset") for row in rows),
        index__in={row.get("page_start") or 1 for row in rows} | {row.get("page_end") for row in rows if row.get("page_end")})
        .values_list("asset_id", "index"))

    disciplines = {str(row.pk): row for row in Discipline.objects.filter(pk__in=_ids(raw.get("primary_discipline") for raw in raws), editorial_status="published")}
    return {"editions": editions, "nodes": nodes, "topics": topics, "pages": pages, "disciplines": disciplines}


def _projection(path, raw, selected, versions, *, request=None, preview=False, context=None):
    groups = raw.get("stage_groups") or []
    context = context or _projection_context([raw])
    editions, nodes, pages = context["editions"], context["nodes"], context["pages"]
    topics = [_link(row, "topic") for key, row in context["topics"].items() if key in _ids(raw.get("topics", []))]
    def debates(values):
        return [_link(nodes[key], "node") for key in map(str, values or []) if key in nodes and nodes[key].node_type == "debate"]

    def bibliography(edition):
        snapshot = edition.active_catalog_revision.snapshot or {}
        work, data = snapshot.get("work") or {}, snapshot.get("edition") or {}
        cover = work.get("cover_media") or {}
        return {"work_id": str(edition.work_id), "edition_id": str(edition.pk), "title": str(work.get("title") or "未题名材料"),
            "version_label": str(data.get("version_label") or ""), "publication_year": data.get("publication_year"),
            "authors": [str(row.get("name") or (row.get("person") or {}).get("preferred_name") or "") for row in snapshot.get("contributions", []) if isinstance(row, dict) and row.get("role") == "author" and whole_edition_contribution(row)],
            "href": f"/works/{data.get('public_slug') or edition.pk}",
            "cover_url": f"{reverse('public-work-cover', kwargs={'work_id': edition.work_id})}?edition_id={edition.pk}" if cover or work.get("cover") else ""}

    output_stages, flat, order = [], [], 0
    for group_position, group in enumerate(groups):
        stage_id = str(group.get("id") or uuid5(NAMESPACE_URL, f"reading-path:{path.pk}:{selected['token']}:stage:{group_position}"))
        stage = {"id": stage_id, "name": str(group.get("name") or f"第{group_position + 1}阶段"), "description": str(group.get("description") or ""),
            "position": group.get("position", group_position), "estimated_reading": str(group.get("estimated_reading") or ""),
            "learning_questions": group.get("learning_questions") or [], "related_debates": debates(group.get("related_debate_ids")), "items": []}
        for local_order, row in enumerate(group.get("items", [])):
            material = {"id": str(row.get("id") or uuid5(NAMESPACE_URL, f"reading-path:{path.pk}:{selected['token']}:item:{order}")),
                "stage_id": stage_id, "kind": "node" if row.get("node") else row.get("material_kind", "work"),
                "title": "当前不可用的材料", "work_id": None, "edition_id": None, "node_id": None,
                "asset_id": None, "document_revision_id": None, "chapter_title": "", "page_start": None, "page_end": None,
                "printed_page_label": "", "version_label": "", "authors": [], "publication_year": None, "cover_url": "",
                "href": None, "reader_url": None, "source_status": "unavailable", "reason": "", "prerequisite": "",
                "is_required": bool(row.get("is_required")), "position": row.get("position", local_order), "reading_order": order, "substitutes": []}
            node, edition = nodes.get(str(row.get("node"))), editions.get(str(row.get("edition")))
            eligible = node is not None if row.get("node") else bool(edition and str(edition.work_id) == str(row.get("work")))
            if eligible:
                material.update(reason=str(row.get("recommendation_reason") or ""), prerequisite=str(row.get("prerequisite") or ""))
                if node:
                    material.update(node_id=str(node.pk), title=node.canonical_name_zh, href=f"/theories/nodes/{node.slug}", source_status="available")
                else:
                    material.update(bibliography(edition))
                    material.update(chapter_title=str(row.get("chapter_title") or ""), printed_page_label=str(row.get("printed_page_label") or ""),
                        page_start=row.get("page_start"), page_end=row.get("page_end"))
                    active = edition.active_catalog_revision
                    asset, document = active.reader_asset, active.document_revision
                    pinned = bool(row.get("asset") or row.get("document_revision"))
                    exact = bool(asset and document and str(asset.pk) == str(row.get("asset")) and str(document.pk) == str(row.get("document_revision"))
                        and asset.edition_id == edition.pk and document.asset_id == asset.pk and document.source_checksum == asset.sha256)
                    readable = bool(exact and active.fulltext_ready and asset.kind == "normalized" and asset.status == "ready"
                        and asset.validation_status == "valid" and asset.access_status in {"public", "inherit"} and asset.file)
                    start, end = row.get("page_start") or 1, row.get("page_end") or row.get("page_start") or 1
                    located = bool(readable and 1 <= start <= end <= (asset.page_count or 0) and (asset.pk, start) in pages and (asset.pk, end) in pages)
                    material["source_status"] = "available" if located else "revision_changed" if pinned and not exact else "no_fulltext"
                    if located:
                        material.update(asset_id=str(asset.pk), document_revision_id=str(document.pk),
                            reader_url=f"/reader/{asset.pk}?page={start}&revision={document.pk}")
                if row.get("status") == "withdrawn":
                    material.update(source_status="withdrawn", reader_url=None, asset_id=None, document_revision_id=None)
                material["substitutes"] = [bibliography(editions[key]) for key in map(str, row.get("substitute_edition_ids") or []) if key in editions]
            material["source_notice"] = SOURCE_NOTICES[material["source_status"]]
            stage["items"].append(material)
            flat.append(material)
            order += 1
        output_stages.append(stage)
    discipline = context["disciplines"].get(_id(raw.get("primary_discipline")))
    from catalog.services.knowledge_media import image_media
    cover_media = image_media(path, selection=raw.get("image_selection"), private=preview)
    cover_url = next((row["url"] for row in (cover_media or {}).get("renditions", []) if row["id"] == cover_media["primary_rendition_id"]), "")
    if not cover_url and not (raw.get("image_selection") or {}).get("rendition_id") and path.cover_asset and (raw.get("image_selection") or {}).get("legacy_path") == path.cover_asset.name:
        cover_url = path.cover_asset.url
    result = {key: raw.get(key, [] if key in {"credits", "learning_questions"} else None if key == "estimated_weeks" else "") for key in PATH_FIELDS if key != "related_debate_ids"}
    result.update(id=str(path.pk), slug=path.slug, cover_url=cover_url, cover_media=cover_media, topics=topics,
        primary_discipline_data={"id": str(discipline.pk), "name": discipline.name, "slug": discipline.slug} if discipline else None,
        related_debates=debates(raw.get("related_debate_ids")), revision=selected, latest_revision=versions[0],
        is_current_revision=selected["token"] == versions[0]["token"], versions=versions[:50], versions_truncated=len(versions) > 50,
        stages=output_stages, items=flat, counts={"stages": len(output_stages), "items": len(flat), "required": sum(row["is_required"] for row in flat),
        "readable": sum(bool(row["reader_url"]) or bool(row["node_id"] and row["source_status"] == "available") for row in flat)})
    if preview:
        result["preview"] = True
    return result


def public_reading_path_snapshot(path_id, *, revision=None, request=None):
    path = ReadingPath.objects.filter(pk=_id(path_id), status="published").first()
    if path is None:
        raise NotFound("阅读路径当前未公开。")
    history = list(EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk, status="published", materialized_preview__status="published").only("id", "revision", "published_at", "change_note").order_by("-revision")[:51])
    if history:
        selected = history[0]
        if revision:
            selected = next((row for row in history if str(row.pk) == str(revision)), None)
            if selected is None and _id(revision):
                selected = EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk, status="published", pk=revision).first()
            if selected is None:
                raise NotFound("该路径的公开版本不存在。")
        raw, revision_data = deepcopy(selected.materialized_preview), _revision_output(selected)
        if raw.get("status") != "published":
            raise NotFound("该修订没有公开阅读路径。")
        versions = [_revision_output(row) for row in history]
    else:
        raw = _raw(path)
        raw["stage_groups"] = _pinned_groups(raw.get("stage_groups") or [])
        revision_data = _revision_output(raw=raw)
        if revision and str(revision) != revision_data["token"]:
            raise NotFound("历史路径已变化，原版本没有独立发布快照。")
        versions = [revision_data]
    return _projection(path, raw, revision_data, versions, request=request)


def public_reading_path_snapshots(paths, *, request=None):
    """Batch all current list-card projections, preserving the detail DTO."""
    from collections import defaultdict
    from django.db.models import prefetch_related_objects
    paths = list(paths)
    if not paths:
        return []
    prefetch_related_objects(paths, "stages", "items", "topics")
    histories = defaultdict(list)
    rows = EditorialRevision.objects.filter(target_type="reading_path", target_id__in=[path.pk for path in paths],
        status="published", materialized_preview__status="published").only("id", "target_id", "revision", "published_at", "change_note").annotate(
        path_row=Window(RowNumber(), partition_by=[F("target_id")], order_by=F("revision").desc())).filter(path_row__lte=51).order_by("target_id", "-revision")
    for row in rows:
        histories[str(row.target_id)].append(row)
    snapshots = {str(row.pk): row.materialized_preview for row in EditorialRevision.objects.filter(pk__in=[rows[0].pk for rows in histories.values()]).only("id", "materialized_preview")}
    prepared = []
    for path in paths:
        if path.status != "published":
            continue
        history = histories.get(str(path.pk))
        if history:
            raw = snapshots[str(history[0].pk)]
            versions = [_revision_output(row) for row in history]
        else:
            raw = _raw(path)
            raw["stage_groups"] = _pinned_groups(raw.get("stage_groups") or [])
            versions = [_revision_output(raw=raw)]
        prepared.append((path, raw, versions))
    context = _projection_context([raw for _, raw, _ in prepared])
    return [_projection(path, raw, versions[0], versions, request=request, context=context) for path, raw, versions in prepared]


def preview_reading_path(path, *, snapshot=None, request=None):
    from common.capabilities import Capability, has_capability
    from rest_framework.exceptions import PermissionDenied
    if not has_capability(getattr(request, "user", None), Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("阅读路径草稿预览需要编辑权限。")
    raw = deepcopy(snapshot) if snapshot is not None else _raw(path)
    raw["stage_groups"] = _pinned_groups(raw.get("stage_groups") or [])
    revision = _revision_output(raw=raw)
    revision.update(token="preview:" + revision["token"].split(":", 1)[1], change_note="只读草稿预览，尚未发布。")
    return _projection(path, raw, revision, [revision], request=request, preview=True)


def diff_reading_path_snapshots(old, new):
    if str(old["id"]) != str(new["id"]):
        raise ValidationError("只能比较同一阅读路径的版本。")
    result = {"from_revision": old["revision"], "to_revision": new["revision"]}
    for kind in ("items", "stages"):
        before, after = ({str(row["id"]): row for row in value[kind]} for value in (old, new))
        def brief(row):
            return {"id": row["id"], "title": row.get("title", row.get("name", "")), "source_status": row.get("source_status"), "change_note": new["revision"]["change_note"]}
        result["added_" + kind] = [brief(row) for key, row in after.items() if key not in before]
        result["removed_" + kind] = [brief(row) for key, row in before.items() if key not in after]
        result["changed_" + kind] = [brief(row) for key, row in after.items() if key in before and row != before[key]]
        if kind == "items":
            result.update(added=[row["id"] for row in result["added_items"]], removed=[row["id"] for row in result["removed_items"]],
                changed=[row["id"] for row in result["changed_items"]], unchanged=[key for key, row in after.items() if key in before and row == before[key]])
    return result
