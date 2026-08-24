from __future__ import annotations

from copy import deepcopy
from typing import Any

from django.db import transaction

from catalog.models import KnowledgeNode, ReadingPath, ReadingPathItem, ReadingPathStage, Work


class ReadingPathStructureError(ValueError):
    pass


def _identifier(value) -> str:
    if value is None:
        return ""
    return str(getattr(value, "pk", value) or "")


def reading_path_stage_groups(path: ReadingPath) -> list[dict[str, Any]]:
    items_by_stage: dict[str, list[dict[str, Any]]] = {}
    for item in path.items.select_related("stage").order_by(
        "reading_order", "position", "created_at"
    ):
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
            }
        )
    groups = [
        {
            "id": str(stage.id),
            "name": stage.name,
            "description": stage.description,
            "position": stage.position,
            "items": items_by_stage.pop(str(stage.id), []),
        }
        for stage in path.stages.order_by("position", "created_at")
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
    if not isinstance(groups, list):
        raise ReadingPathStructureError("stage_groups 必须是列表。")
    existing_stage_ids = {
        str(value)
        for value in path.stages.values_list("id", flat=True)
    }
    used_stage_ids: set[str] = set()
    work_ids: list[str] = []
    node_ids: list[str] = []
    normalized: list[dict[str, Any]] = []
    for stage_position, source_group in enumerate(groups):
        if not isinstance(source_group, dict):
            raise ReadingPathStructureError("阅读阶段格式无效。")
        stage_id = _identifier(source_group.get("id"))
        if stage_id:
            if stage_id not in existing_stage_ids:
                raise ReadingPathStructureError("阶段已被其他编辑删除，请刷新后重试。")
            if stage_id in used_stage_ids:
                raise ReadingPathStructureError("同一阅读阶段不能重复。")
            used_stage_ids.add(stage_id)
        name = str(source_group.get("name") or "").strip()
        if not name:
            raise ReadingPathStructureError("每个阶段都需要名称。")
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
            node_id = _identifier(source_item.get("node"))
            work_id = _identifier(source_item.get("work"))
            if int(bool(node_id)) + int(bool(work_id)) != 1:
                raise ReadingPathStructureError(
                    "每个路径项目必须且只能关联一个知识节点或馆藏作品。"
                )
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
                    "id": _identifier(source_item.get("id")),
                    "node": node_id or None,
                    "work": work_id or None,
                    "recommendation_reason": str(
                        source_item.get("recommendation_reason") or ""
                    ),
                    "prerequisite": str(source_item.get("prerequisite") or ""),
                    "position": item_sort,
                    "is_required": bool(source_item.get("is_required")),
                    "editorial_note": str(source_item.get("editorial_note") or ""),
                }
            )
        normalized.append(
            {
                "id": stage_id,
                "name": name,
                "description": str(source_group.get("description") or ""),
                "position": position,
                "items": normalized_items,
            }
        )
    if len(work_ids) != len(set(work_ids)):
        raise ReadingPathStructureError("同一作品在一条阅读路径中只能出现一次。")
    if Work.objects.filter(pk__in=work_ids).count() != len(set(work_ids)):
        raise ReadingPathStructureError("阅读路径引用了不存在的作品。")
    if KnowledgeNode.objects.filter(pk__in=node_ids).count() != len(set(node_ids)):
        raise ReadingPathStructureError("阅读路径引用了不存在的知识节点。")
    return normalized


def sync_reading_path_stage_groups(path: ReadingPath, groups) -> None:
    normalized = normalize_reading_path_stage_groups(path, groups)
    existing_stages = {
        str(stage.id): stage
        for stage in path.stages.select_for_update()
    }
    path.items.all().delete()
    retained_stage_ids = []
    reading_order = 0
    for group in normalized:
        stage = existing_stages.get(group["id"])
        if stage is None:
            stage = ReadingPathStage.objects.create(
                reading_path=path,
                name=group["name"],
                description=group["description"],
                position=group["position"],
            )
        else:
            stage.name = group["name"]
            stage.description = group["description"]
            stage.position = group["position"]
            stage.save(update_fields=["name", "description", "position", "updated_at"])
        retained_stage_ids.append(stage.id)
        for item in sorted(group["items"], key=lambda row: row["position"]):
            ReadingPathItem.objects.create(
                reading_path=path,
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
            )
            reading_order += 1
    path.stages.exclude(pk__in=retained_stage_ids).delete()


def stage_groups_from_items(path: ReadingPath, items) -> list[dict[str, Any]]:
    source_items = list(items or [])
    has_explicit_stage = any(_identifier(row.get("stage")) for row in source_items)
    groups = deepcopy(reading_path_stage_groups(path)) if has_explicit_stage else []
    for group in groups:
        group["items"] = []
    for fallback_position, source_row in enumerate(source_items):
        row = dict(source_row)
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
                "id": "",
                "node": _identifier(row.get("node")) or None,
                "work": _identifier(row.get("work")) or None,
                "recommendation_reason": str(row.get("recommendation_reason") or ""),
                "prerequisite": str(row.get("prerequisite") or ""),
                "position": int(row.get("position", 0)),
                "is_required": bool(row.get("is_required")),
                "editorial_note": str(row.get("editorial_note") or ""),
            }
        )
    return normalize_reading_path_stage_groups(path, groups)


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
