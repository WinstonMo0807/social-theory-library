from __future__ import annotations

import json
from django.core.serializers.json import DjangoJSONEncoder
from copy import deepcopy
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction

from catalog.models import Asset, DocumentRevision, Edition, KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage, Work
from catalog.reading_path_serializers import PathMaterialInput, PathStageInput
from rest_framework.exceptions import ValidationError

STAGE_METADATA = ("estimated_reading", "learning_questions", "related_debate_ids")
MATERIAL_METADATA = ("learning_goal", "dependencies", "material_kind", "chapter_title", "page_start", "page_end", "printed_page_label", "status", "substitute_edition_ids")
MATERIAL_RELATIONS = ("edition", "asset", "document_revision")


def _json_metadata(serializer, source):
    checked = serializer(data=source)
    try:
        checked.is_valid(raise_exception=True)
    except ValidationError as exc:
        raise ReadingPathStructureError(str(exc.detail)) from exc
    return json.loads(json.dumps(checked.validated_data, cls=DjangoJSONEncoder))


class ReadingPathStructureError(ValueError):
    pass


def _identifier(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "pk", value) or "")


def _stable_id(value):
    try:
        return str(UUID(_identifier(value))) if value else str(uuid4())
    except ValueError as exc:
        raise ReadingPathStructureError("阶段或材料编号无效。") from exc


def reading_path_stage_groups(path: ReadingPath) -> list[dict[str, Any]]:
    items_by_stage: dict[str, list[dict[str, Any]]] = {}
    for item in sorted(path.items.all(), key=lambda row: (row.reading_order, row.position, row.created_at, str(row.pk))):
        stage_id = _identifier(item.stage_id)
        items_by_stage.setdefault(stage_id, []).append(
            {
                "id": str(item.id),
                "node": _identifier(item.node_id) or None,
                "work": _identifier(item.work_id) or None,
                "recommendation_reason": item.recommendation_reason,
                "prerequisite": item.prerequisite,
                "position": item.position,
                "is_required": item.is_required,
                "editorial_note": item.editorial_note,
                **{key: getattr(item, key) for key in MATERIAL_METADATA},
                **{key: _identifier(getattr(item, key + "_id")) or None for key in MATERIAL_RELATIONS},
            }
        )
    groups = [
        {
            "id": str(stage.id),
            "name": stage.name,
            "description": stage.description,
            "position": stage.position,
            **{key: getattr(stage, key) for key in STAGE_METADATA},
            "items": items_by_stage.pop(str(stage.id), []),
        }
        for stage in sorted(path.stages.all(), key=lambda row: (row.position, row.created_at, str(row.pk)))
    ]
    # catalog.0031 backfilled stages for legacy rows. Keep a bounded fallback so
    # an older or manually repaired row is still visible in the revision draft.
    for item_rows in items_by_stage.values():
        for fallback_position, item in enumerate(item_rows, start=len(groups)):
            groups.append(
                {
                    "id": "",
                    "name": f"第 {fallback_position + 1} 阶段",
                    "description": "",
                    "position": fallback_position,
                    "items": [item],
                }
            )
    return groups


def normalize_reading_path_stage_groups(
    path: ReadingPath,
    groups,
) -> list[dict[str, Any]]:
    if not isinstance(groups, list) or len(groups) > 60:
        raise ReadingPathStructureError("stage_groups 必须是最多60个阶段的列表。")
    if sum(len(group.get("items", [])) for group in groups if isinstance(group, dict) and isinstance(group.get("items", []), list)) > 600:
        raise ReadingPathStructureError("一条阅读路径最多600项材料。")
    existing_stages = {str(row.pk): row for row in path.stages.all()}
    existing_stage_ids = set(existing_stages)
    used_stage_ids: set[str] = set()
    existing_items = {str(row.pk): row for row in path.items.all()}
    requested_stages = [_stable_id(group["id"]) for group in groups if isinstance(group, dict) and group.get("id")]
    requested_items = [_stable_id(item["id"]) for group in groups if isinstance(group, dict) and isinstance(group.get("items"), list)
                       for item in group["items"] if isinstance(item, dict) and item.get("id")]
    if ReadingPathStage.objects.filter(pk__in=requested_stages).exclude(reading_path=path).exists() or ReadingPathItem.objects.filter(pk__in=requested_items).exclude(reading_path=path).exists():
        raise ReadingPathStructureError("阶段或材料编号属于另一条阅读路径。")
    used_item_ids = set()
    work_ids: list[str] = []
    node_ids: list[str] = []
    normalized: list[dict[str, Any]] = []
    for stage_position, source_group in enumerate(groups):
        if not isinstance(source_group, dict):
            raise ReadingPathStructureError("阅读阶段格式无效。")
        stage_id = _stable_id(source_group.get("id"))
        if stage_id in used_stage_ids:
            raise ReadingPathStructureError("同一阅读阶段不能重复。")
        used_stage_ids.add(stage_id)
        name = str(source_group.get("name") or "").strip()
        if not name or len(name) > 160:
            raise ReadingPathStructureError("每个阶段需要不超过160字的名称。")
        try:
            position = int(source_group.get("position", stage_position))
        except (TypeError, ValueError) as exc:
            raise ReadingPathStructureError("阶段排序必须是整数。") from exc
        if position < 0:
            raise ReadingPathStructureError("阶段排序不能小于 0。")
        source_items = source_group.get("items") or []
        if not isinstance(source_items, list):
            raise ReadingPathStructureError("阅读阶段项目必须是列表。")
        normalized_items: list[dict[str, Any]] = []
        for item_position, source_item in enumerate(source_items):
            if not isinstance(source_item, dict):
                raise ReadingPathStructureError("阅读路径项目格式无效。")
            item_id = _stable_id(source_item.get("id"))
            if item_id in used_item_ids:
                raise ReadingPathStructureError("同一材料编号不能重复。")
            used_item_ids.add(item_id)
            existing = existing_items.get(item_id)
            previous = ({key: getattr(existing, key) for key in MATERIAL_METADATA} | {
                key: _identifier(getattr(existing, key + "_id")) or None for key in MATERIAL_RELATIONS}) if existing else {}
            details = _json_metadata(PathMaterialInput, {**previous, **source_item})
            node_id = _identifier(source_item.get("node"))
            work_id = _identifier(source_item.get("work"))
            try:
                node_id = str(UUID(node_id)) if node_id else ""
                work_id = str(UUID(work_id)) if work_id else ""
            except ValueError as exc:
                raise ReadingPathStructureError("作品或知识节点编号无效。") from exc
            if "is_required" in source_item and not isinstance(source_item["is_required"], bool):
                raise ReadingPathStructureError("必读标记必须为布尔值。")
            if int(bool(node_id)) + int(bool(work_id)) != 1:
                raise ReadingPathStructureError(
                    "每个路径项目必须且只能关联一个知识节点或馆藏作品。"
                )
            if node_id:
                details["material_kind"] = "node"
                if any(details[key] for key in MATERIAL_RELATIONS) or details["page_start"] or details["page_end"]:
                    raise ReadingPathStructureError("知识条目不能同时携带文献版本或页码。")
            elif details["material_kind"] == "node":
                raise ReadingPathStructureError("知识条目材料必须关联知识节点。")
            start, end = details["page_start"], details["page_end"]
            if end is not None and (start is None or end < start):
                raise ReadingPathStructureError("末页不能早于起始页，且须同时填写起始页。")
            if work_id:
                work_ids.append(work_id)
            if node_id:
                node_ids.append(node_id)
            try:
                item_sort = int(source_item.get("position", item_position))
            except (TypeError, ValueError) as exc:
                raise ReadingPathStructureError("路径项目排序必须是整数。") from exc
            if item_sort < 0:
                raise ReadingPathStructureError("路径项目排序不能小于 0。")
            normalized_items.append(
                {
                    "id": item_id,
                    "node": node_id or None,
                    "work": work_id or None,
                    "recommendation_reason": str(
                        source_item.get("recommendation_reason") or ""
                    ),
                    "prerequisite": str(source_item.get("prerequisite") or ""),
                    "position": item_sort,
                    "is_required": bool(source_item.get("is_required")),
                    "editorial_note": str(source_item.get("editorial_note") or ""),
                    **details,
                }
            )
        normalized.append(
            {
                "id": stage_id,
                "name": name,
                "description": str(source_group.get("description") or ""),
                "position": position,
                "items": normalized_items,
                **_json_metadata(PathStageInput, {**({key: getattr(existing_stages[stage_id], key) for key in STAGE_METADATA} if stage_id in existing_stage_ids else {}), **source_group}),
            }
        )
    from catalog.path_editor import validate_dependency_references
    validate_dependency_references(normalized)
    material_rows = [row for group in normalized for row in group["items"]]
    if len(material_rows) > 600:
        raise ReadingPathStructureError("一条阅读路径最多600项材料。")
    debates = {value for group in normalized for value in group["related_debate_ids"]}
    if KnowledgeNode.objects.filter(pk__in=debates, node_type="debate").count() != len(debates):
        raise ReadingPathStructureError("阶段相关争论须关联现有争论知识节点。")
    substitutes = {value for row in material_rows for value in row["substitute_edition_ids"]}
    if Edition.objects.filter(pk__in=substitutes).count() != len(substitutes):
        raise ReadingPathStructureError("替代材料须关联现有出版版本。")
    if Work.objects.filter(pk__in=work_ids).count() != len(set(work_ids)):
        raise ReadingPathStructureError("阅读路径引用了不存在的作品。")
    if KnowledgeNode.objects.filter(pk__in=node_ids).count() != len(set(node_ids)):
        raise ReadingPathStructureError("阅读路径引用了不存在的知识节点。")
    editions = {str(row.pk): row for row in Edition.objects.filter(pk__in=[row["edition"] for row in material_rows if row["edition"]])}
    assets = {str(row.pk): row for row in Asset.objects.filter(pk__in=[row["asset"] for row in material_rows if row["asset"]])}
    documents = {str(row.pk): row for row in DocumentRevision.objects.filter(pk__in=[row["document_revision"] for row in material_rows if row["document_revision"]])}
    identities = set()
    for row in material_rows:
        edition, asset, document = editions.get(row["edition"]), assets.get(row["asset"]), documents.get(row["document_revision"])
        if row["edition"] and (edition is None or str(edition.work_id) != row["work"]):
            raise ReadingPathStructureError("出版版本不属于该材料作品。")
        if row["asset"] and (asset is None or edition is None or asset.edition_id != edition.pk or asset.kind != "normalized"):
            raise ReadingPathStructureError("阅读文件不属于指定出版版本。")
        if row["document_revision"] and (document is None or asset is None or document.asset_id != asset.pk):
            raise ReadingPathStructureError("正文修订不属于指定阅读文件。")
        if row["page_start"] and (asset is None or document is None or (row["page_end"] or row["page_start"]) > (asset.page_count or 0)):
            raise ReadingPathStructureError("页码需要准确阅读文件与正文修订，且不能超过文件页数。")
        identity = tuple(row[key] for key in ("node", "work", "edition", "material_kind", "chapter_title", "page_start", "page_end"))
        if identity in identities:
            raise ReadingPathStructureError("同一准确材料不能重复；同一作品的不同章节可以分别加入。")
        identities.add(identity)
    return normalized


@transaction.atomic
def sync_reading_path_stage_groups(path: ReadingPath, groups) -> None:
    ReadingPath.objects.select_for_update().get(pk=path.pk)
    normalized = normalize_reading_path_stage_groups(path, groups)
    existing_stages = {
        str(stage.id): stage
        for stage in path.stages.select_for_update()
    }
    existing_items = {str(row.pk): row for row in path.items.select_for_update()}
    retained_item_ids = []
    retained_stage_ids = []
    reading_order = 0
    for group in normalized:
        stage = existing_stages.get(group["id"])
        if stage is None:
            stage = ReadingPathStage.objects.create(
                id=group["id"],
                reading_path=path,
                name=group["name"],
                description=group["description"],
                position=group["position"],
                **{key: group[key] for key in STAGE_METADATA},
            )
        else:
            stage.name = group["name"]
            stage.description = group["description"]
            stage.position = group["position"]
            for key in STAGE_METADATA:
                setattr(stage, key, group[key])
            stage.save(update_fields=["name", "description", "position", *STAGE_METADATA, "updated_at"])
        retained_stage_ids.append(stage.id)
        for item in sorted(group["items"], key=lambda row: row["position"]):
            values = dict(
                stage=stage,
                stage_name=stage.name,
                stage_description=stage.description,
                node_id=item["node"],
                work_id=item["work"],
                recommendation_reason=item["recommendation_reason"],
                prerequisite=item["prerequisite"],
                position=item["position"],
                reading_order=reading_order,
                is_required=item["is_required"],
                editorial_note=item["editorial_note"],
                **{key: item[key] for key in MATERIAL_METADATA},
                **{key + "_id": item[key] for key in MATERIAL_RELATIONS},
            )
            record = existing_items.get(item["id"])
            if record is None:
                record = ReadingPathItem.objects.create(id=item["id"], reading_path=path, **values)
            else:
                for key, value in values.items():
                    setattr(record, key, value)
                record.save()
            retained_item_ids.append(record.pk)
            reading_order += 1
    path.items.exclude(pk__in=retained_item_ids).delete()
    path.stages.exclude(pk__in=retained_stage_ids).delete()


def stage_groups_from_items(path: ReadingPath, items) -> list[dict[str, Any]]:
    source_items = list(items or [])
    groups = deepcopy(reading_path_stage_groups(path))
    previous = [(group, row) for group in groups for row in group["items"]]
    for group in groups:
        group["items"] = []
    for fallback_position, source_row in enumerate(source_items):
        row = dict(source_row)
        matches = [(group, item) for group, item in previous if (_identifier(row.get("id")) == item["id"] if row.get("id") else
                   _identifier(row.get("work")) == _identifier(item.get("work")) and _identifier(row.get("node")) == _identifier(item.get("node")))]
        if len(matches) == 1:
            group, prior = matches[0]
            row = {**prior, "stage": group["id"], **row}
        elif matches and not row.get("id"):
            raise ReadingPathStructureError("同一作品已有多个章节，请携带各材料的稳定编号。")
        stage_id = _identifier(row.get("stage"))
        if stage_id:
            target = next((group for group in groups if group["id"] == stage_id), None)
            if target is None:
                raise ReadingPathStructureError(
                    "阅读阶段必须属于当前阅读路径。"
                )
        else:
            target = {
                "id": "",
                "name": str(row.get("stage_name") or f"第 {fallback_position + 1} 阶段"),
                "description": str(row.get("stage_description") or ""),
                "position": int(row.get("reading_order", fallback_position)),
                "items": [],
            }
            groups.append(target)
        target["items"].append(
            {
                "id": _identifier(row.get("id")),
                "node": _identifier(row.get("node")) or None,
                "work": _identifier(row.get("work")) or None,
                "recommendation_reason": str(row.get("recommendation_reason") or ""),
                "prerequisite": str(row.get("prerequisite") or ""),
                "position": int(row.get("position", 0)),
                "is_required": bool(row.get("is_required")),
                "editorial_note": str(row.get("editorial_note") or ""),
                **{key: row[key] for key in MATERIAL_METADATA if key in row},
                **{key: _identifier(row[key]) or None for key in MATERIAL_RELATIONS if key in row},
            }
        )
    return normalize_reading_path_stage_groups(path, [group for group in groups if group["items"]])


def stage_groups_with_created_work(
    path: ReadingPath,
    *,
    stage_id,
    work_id,
    recommendation_reason: str = "",
    prerequisite: str = "",
    is_required: bool = False,
    editorial_note: str = "",
) -> list[dict[str, Any]]:
    groups = deepcopy(reading_path_stage_groups(path))
    if any(
        _identifier(item.get("work")) == _identifier(work_id)
        for group in groups
        for item in group["items"]
    ):
        raise ReadingPathStructureError("当前作品已经加入这条阅读路径。")
    target = next(
        (group for group in groups if group["id"] == _identifier(stage_id)),
        None,
    )
    if target is None:
        raise ReadingPathStructureError("所选阅读阶段不存在，或不属于当前阅读路径。")
    target["items"].append(
        {
            "id": "",
            "node": None,
            "work": _identifier(work_id),
            "recommendation_reason": recommendation_reason,
            "prerequisite": prerequisite,
            "position": len(target["items"]),
            "is_required": is_required,
            "editorial_note": editorial_note,
        }
    )
    return normalize_reading_path_stage_groups(path, groups)


def stage_groups_with_updated_item(
    path: ReadingPath,
    *,
    item_id,
    changes: dict[str, Any],
) -> list[dict[str, Any]]:
    groups = deepcopy(reading_path_stage_groups(path))
    source_group = None
    item = None
    for group in groups:
        for candidate in group["items"]:
            if candidate["id"] == _identifier(item_id):
                source_group = group
                item = candidate
                break
        if item is not None:
            break
    if item is None or source_group is None:
        raise ReadingPathStructureError("当前作品的阅读路径 placement 不存在。")
    for field_name in (
        "recommendation_reason",
        "prerequisite",
        "is_required",
        "editorial_note",
    ):
        if field_name in changes:
            item[field_name] = changes[field_name]
    if changes.get("stage_id") and _identifier(changes["stage_id"]) != source_group["id"]:
        target_group = next(
            (
                group
                for group in groups
                if group["id"] == _identifier(changes["stage_id"])
            ),
            None,
        )
        if target_group is None:
            raise ReadingPathStructureError(
                "所选阅读阶段不存在，或不属于当前阅读路径。"
            )
        source_group["items"].remove(item)
        item["position"] = len(target_group["items"])
        target_group["items"].append(item)
    return normalize_reading_path_stage_groups(path, groups)


def stage_groups_without_item(path: ReadingPath, *, item_id) -> list[dict[str, Any]]:
    groups = deepcopy(reading_path_stage_groups(path))
    for group in groups:
        for item in list(group["items"]):
            if item["id"] == _identifier(item_id):
                group["items"].remove(item)
                return normalize_reading_path_stage_groups(path, groups)
    raise ReadingPathStructureError("当前作品的阅读路径 placement 不存在。")
