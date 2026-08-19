from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent

from catalog.models import (
    ReadingPath,
    ReadingPathItem,
    ReadingPathStage,
    RecommendationItem,
    RecommendationOverride,
    RecommendationPolicy,
    Work,
)
from catalog.services.recommendations import PLACEMENT_TARGETS


WORK_RECOMMENDATION_PLACEMENTS = tuple(
    placement
    for placement, target_type in PLACEMENT_TARGETS.items()
    if target_type == "work"
)


class CurationConflict(RuntimeError):
    """Raised when a contextual edit is based on stale or conflicting state."""

    code = "curation_conflict"


class CurationNotFound(RuntimeError):
    code = "curation_not_found"


class CurationValidationError(RuntimeError):
    code = "curation_validation_error"


@dataclass(frozen=True, slots=True)
class WorkCurationSummary:
    work: Work
    placements: tuple[ReadingPathItem, ...]
    current_recommendations: tuple[RecommendationItem, ...]
    overrides: tuple[RecommendationOverride, ...]
    policies: tuple[RecommendationPolicy, ...]


def _get_work(work_id, *, for_update: bool = False) -> Work:
    queryset = Work.objects.all()
    if for_update:
        queryset = queryset.select_for_update(of=("self",))
    try:
        return queryset.get(pk=work_id)
    except Work.DoesNotExist as exc:
        raise CurationNotFound("馆藏作品不存在或已被删除。") from exc


def _path_snapshot(path: ReadingPath) -> dict[str, Any]:
    return {
        "id": str(path.id),
        "title": path.title,
        "status": path.status,
        "updated_at": path.updated_at.isoformat(),
    }


def _stage_snapshot(stage: ReadingPathStage | None) -> dict[str, Any] | None:
    if stage is None:
        return None
    return {
        "id": str(stage.id),
        "name": stage.name,
        "description": stage.description,
        "position": stage.position,
    }


def _item_snapshot(item: ReadingPathItem) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "reading_path_id": str(item.reading_path_id),
        "work_id": str(item.work_id) if item.work_id else None,
        "stage": _stage_snapshot(item.stage),
        "recommendation_reason": item.recommendation_reason,
        "is_required": item.is_required,
        "editorial_note": item.editorial_note,
        "position": item.position,
        "reading_order": item.reading_order,
    }


def _override_snapshot(override: RecommendationOverride) -> dict[str, Any]:
    return {
        "id": str(override.id),
        "policy_id": str(override.policy_id),
        "placement": override.policy.placement,
        "work_id": str(override.work_id) if override.work_id else None,
        "action": override.action,
        "position": override.position,
        "active": override.active,
        "note": override.note,
    }


def _record_audit(*, actor, action: str, object_type: str, object_id, before, after) -> None:
    AuditEvent.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before=before,
        after=after,
    )


def _require_path_edit_permission(path: ReadingPath, actor) -> None:
    if path.status == "published" and not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("修改已发布阅读路径需要 authority 发布权限。")
    if not has_capability(actor, Capability.EDIT_DRAFT_AUTHORITY):
        raise PermissionDenied("当前账户不能编辑阅读路径。")


def _assert_expected_path_version(path: ReadingPath, expected_updated_at) -> None:
    if expected_updated_at is None:
        return
    if path.updated_at != expected_updated_at:
        raise CurationConflict("阅读路径已被其他操作更新，请刷新后重试。")


def _touch_path(path: ReadingPath) -> None:
    path.updated_at = timezone.now()
    path.save(update_fields=["updated_at"])


def _next_order(queryset, field_name: str) -> int:
    current = queryset.aggregate(value=Max(field_name))["value"]
    return 0 if current is None else int(current) + 1


def build_work_curation_summary(work_id) -> WorkCurationSummary:
    work = _get_work(work_id)
    placements = tuple(
        ReadingPathItem.objects.filter(work=work)
        .select_related("reading_path", "stage")
        .order_by("reading_path__sort_order", "reading_path__title", "reading_order", "position")
    )
    current_recommendations = tuple(
        RecommendationItem.objects.filter(
            work=work,
            snapshot__is_current=True,
            snapshot__policy__placement__in=WORK_RECOMMENDATION_PLACEMENTS,
        )
        .select_related("snapshot__policy")
        .order_by("snapshot__policy__placement", "position")
    )
    overrides = tuple(
        RecommendationOverride.objects.filter(
            work=work,
            policy__placement__in=WORK_RECOMMENDATION_PLACEMENTS,
        )
        .select_related("policy")
        .order_by("policy__placement", "-active", "position", "created_at")
    )
    policies = tuple(
        RecommendationPolicy.objects.filter(placement__in=WORK_RECOMMENDATION_PLACEMENTS)
        .order_by("placement")
    )
    return WorkCurationSummary(
        work=work,
        placements=placements,
        current_recommendations=current_recommendations,
        overrides=overrides,
        policies=policies,
    )


@transaction.atomic
def create_work_reading_path_placement(
    *,
    work_id,
    reading_path_id,
    stage_id,
    actor,
    recommendation_reason: str = "",
    is_required: bool = False,
    editorial_note: str = "",
    expected_path_updated_at=None,
) -> ReadingPathItem:
    work = _get_work(work_id)
    try:
        path = ReadingPath.objects.select_for_update().get(pk=reading_path_id)
    except ReadingPath.DoesNotExist as exc:
        raise CurationNotFound("阅读路径不存在或已被删除。") from exc
    _require_path_edit_permission(path, actor)
    _assert_expected_path_version(path, expected_path_updated_at)
    try:
        stage = ReadingPathStage.objects.select_for_update().get(
            pk=stage_id,
            reading_path=path,
        )
    except ReadingPathStage.DoesNotExist as exc:
        raise CurationNotFound("所选阅读阶段不存在，或不属于当前阅读路径。") from exc

    existing = (
        ReadingPathItem.objects.select_for_update()
        .filter(reading_path=path, work=work)
        .first()
    )
    if existing is not None:
        raise CurationConflict("当前作品已经加入这条阅读路径。")

    item = ReadingPathItem.objects.create(
        reading_path=path,
        stage=stage,
        stage_name=stage.name,
        stage_description=stage.description,
        node=None,
        work=work,
        recommendation_reason=recommendation_reason,
        reading_order=_next_order(path.items.all(), "reading_order"),
        position=_next_order(stage.items.all(), "position"),
        is_required=is_required,
        editorial_note=editorial_note,
    )
    _touch_path(path)
    item.refresh_from_db()
    _record_audit(
        actor=actor,
        action="work_reading_path_placement_create",
        object_type="catalog.ReadingPathItem",
        object_id=item.id,
        before={},
        after={**_item_snapshot(item), "reading_path": _path_snapshot(path)},
    )
    return item


def _locked_work_item(*, work_id, item_id) -> tuple[ReadingPath, ReadingPathItem]:
    identity = ReadingPathItem.objects.filter(pk=item_id).values(
        "reading_path_id",
        "work_id",
    ).first()
    if identity is None or str(identity["work_id"] or "") != str(work_id):
        raise CurationNotFound("当前作品的阅读路径 placement 不存在。")
    path = ReadingPath.objects.select_for_update().get(pk=identity["reading_path_id"])
    try:
        item = (
            ReadingPathItem.objects.select_for_update()
            .select_related("reading_path", "stage")
            .get(pk=item_id, reading_path=path, work_id=work_id)
        )
    except ReadingPathItem.DoesNotExist as exc:
        raise CurationNotFound("当前作品的阅读路径 placement 不存在。") from exc
    return path, item


@transaction.atomic
def update_work_reading_path_placement(
    *,
    work_id,
    item_id,
    actor,
    changes: dict[str, Any],
    expected_path_updated_at=None,
) -> ReadingPathItem:
    path, item = _locked_work_item(work_id=work_id, item_id=item_id)
    _require_path_edit_permission(path, actor)
    _assert_expected_path_version(path, expected_path_updated_at)
    before = _item_snapshot(item)
    update_fields: list[str] = []

    if "stage_id" in changes:
        try:
            stage = ReadingPathStage.objects.select_for_update().get(
                pk=changes["stage_id"],
                reading_path=path,
            )
        except ReadingPathStage.DoesNotExist as exc:
            raise CurationNotFound("所选阅读阶段不存在，或不属于当前阅读路径。") from exc
        if item.stage_id != stage.id:
            item.stage = stage
            item.stage_name = stage.name
            item.stage_description = stage.description
            item.position = _next_order(stage.items.exclude(pk=item.pk), "position")
            update_fields.extend(["stage", "stage_name", "stage_description", "position"])

    for field_name in ("recommendation_reason", "is_required", "editorial_note"):
        if field_name not in changes:
            continue
        setattr(item, field_name, changes[field_name])
        update_fields.append(field_name)

    if update_fields:
        item.save(update_fields=[*dict.fromkeys(update_fields), "updated_at"])
        _touch_path(path)
    item.refresh_from_db()
    _record_audit(
        actor=actor,
        action="work_reading_path_placement_update",
        object_type="catalog.ReadingPathItem",
        object_id=item.id,
        before=before,
        after={**_item_snapshot(item), "reading_path": _path_snapshot(path)},
    )
    return item


@transaction.atomic
def delete_work_reading_path_placement(
    *,
    work_id,
    item_id,
    actor,
    expected_path_updated_at=None,
) -> dict[str, Any]:
    path, item = _locked_work_item(work_id=work_id, item_id=item_id)
    _require_path_edit_permission(path, actor)
    _assert_expected_path_version(path, expected_path_updated_at)
    before = {**_item_snapshot(item), "reading_path": _path_snapshot(path)}
    item_id_value = item.id
    item.delete()
    _touch_path(path)
    _record_audit(
        actor=actor,
        action="work_reading_path_placement_delete",
        object_type="catalog.ReadingPathItem",
        object_id=item_id_value,
        before=before,
        after={"deleted": True, "reading_path": _path_snapshot(path)},
    )
    return {
        "id": str(item_id_value),
        "deleted": True,
        "reading_path_id": str(path.id),
        "path_updated_at": path.updated_at,
    }


def _work_policy_for_update(placement: str) -> RecommendationPolicy:
    if placement not in WORK_RECOMMENDATION_PLACEMENTS:
        raise CurationValidationError("该推荐位置不接受 Work placement。")
    try:
        return RecommendationPolicy.objects.select_for_update().get(placement=placement)
    except RecommendationPolicy.DoesNotExist as exc:
        raise CurationNotFound("推荐位置不存在或尚未配置。") from exc


@transaction.atomic
def upsert_work_recommendation_override(
    *,
    work_id,
    placement: str,
    actor,
    action: str,
    position: int | None = None,
    note: str = "",
) -> RecommendationOverride:
    work = _get_work(work_id)
    policy = _work_policy_for_update(placement)
    overrides = list(
        RecommendationOverride.objects.select_for_update()
        .filter(policy=policy, work=work, active=True)
        .order_by("created_at", "id")
    )
    before = [_override_snapshot(row) for row in overrides]
    canonical = overrides[0] if overrides else None
    duplicate_ids = [row.id for row in overrides[1:]]
    if duplicate_ids:
        RecommendationOverride.objects.filter(pk__in=duplicate_ids).update(
            active=False,
            updated_at=timezone.now(),
        )
    if canonical is None:
        canonical = RecommendationOverride.objects.create(
            policy=policy,
            work=work,
            action=action,
            position=position if action == RecommendationOverride.Action.PIN else None,
            active=True,
            note=note,
            created_by=actor,
        )
    else:
        canonical.action = action
        canonical.position = position if action == RecommendationOverride.Action.PIN else None
        canonical.active = True
        canonical.note = note
        canonical.save(update_fields=["action", "position", "active", "note", "updated_at"])
    policy.updated_by = actor
    policy.save(update_fields=["updated_by", "updated_at"])
    canonical.refresh_from_db()
    _record_audit(
        actor=actor,
        action="work_recommendation_override_upsert",
        object_type="catalog.RecommendationOverride",
        object_id=canonical.id,
        before={"active_overrides": before},
        after={
            **_override_snapshot(canonical),
            "deactivated_duplicate_ids": [str(identifier) for identifier in duplicate_ids],
        },
    )
    return canonical


@transaction.atomic
def deactivate_work_recommendation_override(
    *,
    work_id,
    placement: str,
    actor,
) -> dict[str, Any]:
    work = _get_work(work_id)
    policy = _work_policy_for_update(placement)
    overrides = list(
        RecommendationOverride.objects.select_for_update()
        .filter(policy=policy, work=work, active=True)
        .order_by("created_at", "id")
    )
    before = [_override_snapshot(row) for row in overrides]
    if overrides:
        RecommendationOverride.objects.filter(pk__in=[row.id for row in overrides]).update(
            active=False,
            updated_at=timezone.now(),
        )
        policy.updated_by = actor
        policy.save(update_fields=["updated_by", "updated_at"])
    _record_audit(
        actor=actor,
        action="work_recommendation_override_deactivate",
        object_type="catalog.Work",
        object_id=work.id,
        before={"active_overrides": before},
        after={
            "placement": placement,
            "active": False,
            "deactivated_ids": [str(row.id) for row in overrides],
        },
    )
    return {
        "work_id": str(work.id),
        "placement": placement,
        "active": False,
        "deactivated_count": len(overrides),
    }
