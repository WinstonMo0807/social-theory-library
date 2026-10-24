"""Pinned public-path follows and explicit copies in the existing private plan store."""
from copy import deepcopy
import json

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from . import privacy, research
from .path_models import PlanCommandReceipt
from .path_serializers import PathCopyInput, PathCreateInput, PathRevisionInput, PathUpdateInput, PathUpgradeInput
from .research_models import PersonalReadingPlan

PATH_TYPES = {"path_follow", "public_path_copy"}
IDENTITY = ("kind", "work_id", "edition_id", "node_id", "asset_id", "document_revision_id", "page_start", "page_end")
PRIVATE_ITEM = ("status", "note", "owner_estimate", "source_history")


def is_path_plan(payload):
    return payload.get("origin", {}).get("type") in PATH_TYPES


def validated(raw, schema):
    if not hasattr(raw, "items") or len(json.dumps(dict(raw), ensure_ascii=False, default=str)) > 25_000:
        raise ValidationError("路径操作需要对象，且内容不能超过25000字符。")
    serializer = schema(data=raw)
    serializer.is_valid(raise_exception=True)
    return json.loads(json.dumps(serializer.validated_data, default=str))


def public_snapshot(path_id, *, revision=None, lock=False):
    from catalog.models import ReadingPath
    from catalog.services.public_reading_paths import public_reading_path_snapshot
    path_id = research.identifier(path_id, "path_id")
    if lock and not ReadingPath.objects.select_for_update().filter(pk=path_id).exists():
        raise NotFound("公开路径不存在。")
    return public_reading_path_snapshot(path_id, revision=revision)


def owned(user, pk, *, lock=False, follow_only=False):
    record = research.owned(PersonalReadingPlan, user, pk, lock=lock)
    if not is_path_plan(research.unpack(record)) or (follow_only and record.public_path_id is None):
        raise NotFound("本人的路径记录不存在。")
    return record


def _receipt(user, command, action, pk=None):
    fingerprint = research.request_fingerprint({"action": action, "record_id": str(pk) if pk else None, **command},
        ("action", "record_id", *command))
    receipt = PlanCommandReceipt.objects.select_related("record").filter(user=user, request_id=command["request_id"]).first()
    if receipt and receipt.fingerprint != fingerprint:
        raise research.ResearchConflict("原请求已用于不同内容，请先核对回执。")
    if receipt is None and PersonalReadingPlan.objects.filter(user=user, request_id=command["request_id"]).exists():
        raise research.ResearchConflict("此请求标识已用于既有私人计划，请为新操作使用新的标识。")
    return receipt, fingerprint


def _remember(user, command, fingerprint, record, *, deleted_revision=None):
    receipt = PlanCommandReceipt.objects.create(user=user, record=record, request_id=command["request_id"],
        fingerprint=fingerprint, applied_revision=record.revision if record else deleted_revision)
    return command_output(user, receipt=receipt)


def _source_item(row, stages, revision):
    stage_id = str(row.get("stage_id") or "")
    return {**deepcopy(row), "id": str(row["id"]), "source_item_id": str(row["id"]), "source_stage_id": stage_id,
        "source_revision": deepcopy(revision), "stage": stages.get(stage_id, {}).get("name", "未分组材料"),
        "status": "pending", "note": "", "source_history": [], "reference": None}


def _payload(snapshot, *, follow=True):
    stages = {str(row["id"]): row for row in snapshot["stages"]}
    return {"origin": {"type": "path_follow" if follow else "public_path_copy", "reading_path_id": snapshot["id"],
            "source_revision": deepcopy(snapshot["revision"])},
        "goal": snapshot["title"], "background": "", "bookmarked": follow, "source_snapshot": deepcopy(snapshot),
        "stages": [{key: deepcopy(value) for key, value in row.items() if key != "items"} for row in snapshot["stages"]],
        "items": [_source_item(row, stages, snapshot["revision"]) for row in snapshot["items"]],
        "history": [], "prerequisites": [], "generation_status": "completed", "enhancement_status": "not_requested",
        "use_confirmed_memories": False, "confirmed_memory_ids": [],
        "notice": "阶段与材料按公开版本原样保留；完成进度仅由本人明确记录，不推断理解或赞同。"}


def _source_identity(row):
    return tuple(row.get(key) for key in IDENTITY)


def refresh_payload(user, payload):
    """Recheck each pinned published version; a new source never replaces an old identity."""
    payload = deepcopy(payload)
    path_id = payload["origin"]["reading_path_id"]
    snapshots = {}
    try:
        latest = public_snapshot(path_id)
    except NotFound:
        latest = None
    if latest:
        snapshots[latest["revision"]["token"]] = latest
    source_revision = payload["origin"]["source_revision"]
    tokens = {source_revision["token"], *(row["source_revision"]["token"] for row in payload["items"])}
    for token in tokens - snapshots.keys():
        try:
            snapshots[token] = public_snapshot(path_id, revision=token)
        except NotFound:
            snapshots[token] = None
    indexed = {token: {str(item["id"]): item for item in snapshot["items"]} if snapshot else {}
        for token, snapshot in snapshots.items()}
    for item in payload["items"]:
        current = indexed[item["source_revision"]["token"]].get(item["source_item_id"])
        if item.get("owner_override"):
            reference = research.resolve_reference(item["reference"], user)
            item["reference"] = {**research.compact_reference(reference),
                "source_status": reference["source_status"], "reader_url": reference.get("reader_url")}
            item.update(source_status=reference["source_status"], href=reference.get("reader_url"),
                reader_url=reference.get("reader_url"), cover_url=reference.get("cover_url"), cover_media=reference.get("cover_media"))
            if reference["source_status"] == "available":
                item.update(title=reference["title"], authors=reference.get("authors", []),
                    publication_year=reference.get("publication_year"))
        elif current and _source_identity(current) == _source_identity(item):
            for key in ("source_status", "href", "reader_url", "cover_url", "cover_media", "authors", "publication_year", "substitutes"):
                item[key] = deepcopy(current.get(key))
        else:
            item.update(source_status="revision_changed" if current else "unavailable", href=None, reader_url=None, cover_url=None, cover_media=None)
        item["available"] = item.get("source_status") == "available"
        if not item["available"]:
            item["reader_url"] = None
    # Stored public prose is historical context, never an authorization to read
    # withdrawn sources. History has no active links or embedded source excerpts.
    def redact_history(value):
        if isinstance(value, dict):
            return {key: None if key in {"reader_url", "href", "cover_url", "cover_media"} else redact_history(child)
                for key, child in value.items() if key not in {"quote", "reference", "model_suggestion"}}
        if isinstance(value, list):
            return [redact_history(child) for child in value]
        return value
    payload["history"] = redact_history(payload.get("history", []))
    for item in payload["items"]:
        item["source_history"] = redact_history(item.get("source_history", []))
    current_path = snapshots[source_revision["token"]]
    path = deepcopy(current_path or payload["source_snapshot"])
    current_stages = {str(stage["id"]): stage for stage in current_path["stages"]} if current_path else {}
    path["stages"] = [{**deepcopy(current_stages.get(str(stage["id"]), {**stage, "related_debates": []})),
        "items": [deepcopy(item) for item in payload["items"] if item["source_stage_id"] == str(stage["id"])]}
        for stage in payload["stages"]]
    path["items"] = deepcopy(payload["items"])
    path["counts"] = {"stages": len(path["stages"]), "items": len(path["items"]),
        "required": sum(bool(row.get("is_required")) for row in path["items"]),
        "readable": sum(bool(row.get("reader_url")) or bool(row.get("node_id") and row["available"]) for row in path["items"])}
    if not current_path:
        path.update(topics=[], related_debates=[], cover_url="", cover_media=None)
    path.update(latest_revision=latest["revision"] if latest else source_revision,
        is_current_revision=bool(latest and latest["revision"]["token"] == source_revision["token"]),
        versions=latest.get("versions", []) if latest else [], versions_truncated=bool(latest and latest.get("versions_truncated")))
    payload["path_snapshot"] = path
    payload.pop("request_fingerprint", None)
    return payload, latest


def record_output(record, user):
    if record.user_id != user.pk:
        raise PermissionDenied("只能读取本人的路径记录。")
    payload, latest = refresh_payload(user, research.unpack(record))
    # The frozen comparison basis is internal. Responses/export expose only
    # the reauthorized projection, never cached source links from that basis.
    payload.pop("source_snapshot", None)
    revision = payload["origin"]["source_revision"]
    progress = {row["source_item_id"]: {"status": row["status"], "note": row.get("note", "")} for row in payload["items"]}
    stages = payload["path_snapshot"]["stages"]
    return {"id": str(record.pk), "revision": record.revision,
        "type": "path_follow" if record.public_path_id else "personal_plan",
        "path_id": payload["origin"]["reading_path_id"], "path_slug": payload["path_snapshot"].get("slug", ""),
        "bookmarked": payload.get("bookmarked", False), "source_revision": revision,
        "latest_source_revision": latest["revision"] if latest else None,
        "source_status": "unavailable" if not latest else "available" if latest["revision"]["token"] == revision["token"] else "revision_changed",
        "path": payload["path_snapshot"], "progress": progress,
        "completed_items": sum(row["status"] == "completed" for row in payload["items"]), "total_items": len(payload["items"]),
        "completed_stages": sum(bool(stage["items"]) and all(item["status"] == "completed" for item in stage["items"]) for stage in stages),
        "total_stages": len(stages), "history": payload.get("history", []), "data": payload,
        "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat()}


def command_output(user, *, record=None, receipt=None):
    if receipt:
        if receipt.user_id != user.pk:
            raise PermissionDenied("只能读取本人的操作回执。")
        record = receipt.record
    return {"owner_id": str(user.pk), "record": record_output(record, user) if record else None,
        "receipt": {"request_id": str(receipt.request_id), "applied_revision": receipt.applied_revision,
            "deleted": record is None} if receipt else None}


def by_request(user, request_id):
    receipt = PlanCommandReceipt.objects.select_related("record").filter(user=user,
        request_id=research.identifier(request_id, "request_id")).first()
    if receipt is None:
        raise NotFound("未找到本人的操作回执，可使用原请求标识重试。")
    return command_output(user, receipt=receipt)


def by_path(user, path_id):
    record = PersonalReadingPlan.objects.filter(user=user, public_path_id=research.identifier(path_id, "path_id")).first()
    if record is None:
        raise NotFound("尚未收藏或记录此路径的阅读进度。")
    return command_output(user, record=record)


@transaction.atomic
def create_follow(user, raw):
    command = validated(raw, PathCreateInput)
    privacy.lock_owner(user)
    receipt, digest = _receipt(user, command, "follow")
    if receipt:
        return command_output(user, receipt=receipt)
    snapshot = public_snapshot(command["path_id"], lock=True)
    if snapshot["revision"]["token"] != command["expected_source_revision"]:
        raise research.ResearchConflict("公开路径已有新版本，请重新读取后收藏。")
    record = PersonalReadingPlan.objects.select_for_update().filter(user=user, public_path_id=command["path_id"]).first()
    if record:
        # Creating another follow never overwrites an existing bookmark/progress.
        return _remember(user, command, digest, record)
    payload = _payload(snapshot)
    payload["bookmarked"] = command["bookmarked"]
    record = PersonalReadingPlan.objects.create(user=user, public_path_id=command["path_id"], request_id=command["request_id"],
        task_pending=False, data_ciphertext=research.pack(payload))
    return _remember(user, command, digest, record)


@transaction.atomic
def update_follow(user, pk, raw):
    command = validated(raw, PathUpdateInput)
    privacy.lock_owner(user)
    receipt, digest = _receipt(user, command, "follow_update", pk)
    if receipt:
        return command_output(user, receipt=receipt)
    record = owned(user, pk, lock=True, follow_only=True)
    research.expect(record, command["expected_revision"])
    payload = research.unpack(record)
    if command["action"] == "bookmark":
        payload["bookmarked"] = command["bookmarked"]
    else:
        item = next((row for row in payload["items"] if row["source_item_id"] == command["item_id"]), None)
        if item is None:
            raise NotFound("该版本的路径材料不存在。")
        key = "status" if command["action"] == "progress" else "note"
        if key == "status" and item["status"] == "completed" and command[key] != "completed":
            raise research.ResearchConflict("已完成记录保留，可补充笔记；不能将历史完成项改为未完成。")
        item[key] = command[key]
    research.save_data(record, payload)
    return _remember(user, command, digest, record)


def _schedule(payload):
    from .plan_rules import planning_policy, schedule_plan
    policy = planning_policy(payload.get("planning_inputs", {}))
    for item in payload["items"]:
        if item["status"] == "completed" and item.get("planning_estimate"):
            continue
        minutes = item.get("owner_estimate", {}).get("minutes")
        item["estimated_minutes"] = minutes
        item["difficulty"] = {"level": policy["reading_level"], "basis": "owner_plan_setting",
            "notice": "本人的计划层级，不是对材料的实测难度。"}
        item["planning_source_available"] = item.get("source_status") == "available"
        item["planning_estimate"] = {"method": "owner_estimate" if minutes else "not_estimated", "minutes": minutes,
            "limits": "公开路径的周数是策划建议；不自动换算为材料时长，缺少本人估计时保留未知。"}
    payload["items"], payload["schedule"] = schedule_plan(payload["items"], [], policy, preserve_order=True, identity_key="id")
    payload["planning_policy"] = policy
    payload["time_budget"] = payload.get("planning_inputs", {}).get("time_budget", "")


@transaction.atomic
def copy_plan(user, pk, raw):
    command = validated(raw, PathCopyInput)
    privacy.lock_owner(user)
    receipt, digest = _receipt(user, command, "copy", pk)
    if receipt:
        return command_output(user, receipt=receipt)
    follow = owned(user, pk, lock=True, follow_only=True)
    research.expect(follow, command["expected_revision"])
    payload, _ = refresh_payload(user, research.unpack(follow))
    # An unavailable source does not become a new private copy merely because
    # the owner already has old progress. Existing private records remain intact.
    public_snapshot(payload["origin"]["reading_path_id"], revision=payload["origin"]["source_revision"]["token"], lock=True)
    payload["origin"] = {**payload["origin"], "type": "public_path_copy", "follow_id": str(follow.pk)}
    payload["bookmarked"] = False
    payload["goal"] = command["title"] or payload["goal"]
    payload["request_fingerprint"] = digest
    _schedule(payload)
    payload.pop("path_snapshot", None)
    record = PersonalReadingPlan.objects.create(user=user, request_id=command["request_id"], public_path_id=None,
        task_pending=False, data_ciphertext=research.pack(payload))
    return _remember(user, command, digest, record)


def _diff(old, new):
    from catalog.services.public_reading_paths import diff_reading_path_snapshots
    difference = diff_reading_path_snapshots(old, new)
    return {key: difference[key] for key in ("added", "removed", "changed", "unchanged")}


def upgrade_preview(user, pk, target_revision):
    record = owned(user, pk)
    payload = research.unpack(record)
    target = public_snapshot(payload["origin"]["reading_path_id"])
    if target["revision"]["token"] != target_revision:
        raise research.ResearchConflict("目标版本已变化，请重新读取升级预览。")
    return {"owner_id": str(user.pk), "record_id": str(record.pk), "expected_revision": record.revision,
        "source_revision": payload["origin"]["source_revision"], "target_revision": target["revision"],
        "diff": _diff(payload["source_snapshot"], target),
        "retained_completed": [row["source_item_id"] for row in payload["items"] if row["status"] == "completed"],
        "retained_notes": [row["source_item_id"] for row in payload["items"] if row.get("note")]}


@transaction.atomic
def upgrade(user, pk, raw):
    command = validated(raw, PathUpgradeInput)
    privacy.lock_owner(user)
    receipt, digest = _receipt(user, command, "upgrade", pk)
    if receipt:
        return command_output(user, receipt=receipt)
    record = owned(user, pk, lock=True)
    research.expect(record, command["expected_revision"])
    payload = research.unpack(record)
    target = public_snapshot(payload["origin"]["reading_path_id"], lock=True)
    if target["revision"]["token"] != command["target_revision"]:
        raise research.ResearchConflict("公开路径又有新版本，请重新预览后再升级。")
    if target["revision"]["token"] == payload["origin"]["source_revision"]["token"]:
        return _remember(user, command, digest, record)
    difference = _diff(payload["source_snapshot"], target)
    old = {row["source_item_id"]: row for row in payload["items"]}
    stages = {str(row["id"]): row for row in target["stages"]}
    items = []
    changed = set(difference["changed"])
    for source in target["items"]:
        item = _source_item(source, stages, target["revision"])
        previous = old.get(item["source_item_id"])
        if previous:
            if previous["status"] == "completed" or previous.get("owner_override"):
                item = deepcopy(previous)
                if item["source_item_id"] in changed:
                    item["upgrade_status"] = "owner_replacement_preserved" if previous.get("owner_override") else "completed_original_preserved"
            else:
                item.update({key: deepcopy(previous[key]) for key in PRIVATE_ITEM if key in previous})
                if item["source_item_id"] in changed:
                    item["source_history"].append({key: deepcopy(value) for key, value in previous.items() if key != "source_history"})
        items.append(item)
    removed = [deepcopy(old[key]) for key in difference["removed"] if key in old]
    payload["history"].append({"at": timezone.now().isoformat(), "source_revision": payload["origin"]["source_revision"],
        "target_revision": target["revision"], "diff": difference, "removed_items": removed})
    old_stages = {str(row["id"]): row for row in payload["stages"]}
    new_stages = [{key: deepcopy(value) for key, value in row.items() if key != "items"} for row in target["stages"]]
    for item in items:
        if item["source_stage_id"] not in stages and item["source_stage_id"] in old_stages:
            stage = {**deepcopy(old_stages[item["source_stage_id"]]), "historical": True}
            new_stages.append(stage); stages[item["source_stage_id"]] = stage
    payload.update(items=items, stages=new_stages, source_snapshot=deepcopy(target))
    payload.pop("path_snapshot", None)
    payload["origin"]["source_revision"] = deepcopy(target["revision"])
    if record.public_path_id is None:
        _schedule(payload)
    research.save_data(record, payload)
    return _remember(user, command, digest, record)


@transaction.atomic
def delete_plan(user, pk, raw, *, follow_only=False, copy_only=False):
    command = validated(raw, PathRevisionInput)
    privacy.lock_owner(user)
    receipt, digest = _receipt(user, command, "delete", pk)
    if receipt:
        return command_output(user, receipt=receipt)
    record = owned(user, pk, lock=True, follow_only=follow_only)
    if copy_only and record.public_path_id is not None:
        raise NotFound("私人计划不存在；公共路径跟读使用专用接口。")
    research.expect(record, command["expected_revision"])
    revision = record.revision + 1
    record.delete()
    return _remember(user, command, digest, None, deleted_revision=revision)


@transaction.atomic
def update_copy(user, pk, raw):
    """Keep the legacy plan response shape, with fixed nonce receipts for writes."""
    from .research_serializers import PlanUpdateInput
    # Shared legacy inputs remain unchanged; this branch explicitly rejects
    # operations that assume one row per work or would launch model generation.
    allowed = {"expected_revision", "request_id", "goal", "background", "item_id", "status", "note", "item_minutes", "reference",
        "order", "preview", "optimize_order", *research.PLAN_POLICY_FIELDS}
    if not isinstance(raw, dict) or set(raw) - allowed or raw.get("optimize_order") is True or "item_estimates" in raw:
        raise ValidationError("公共路径副本仅支持明确的进度、笔记、阶段内顺序和时间设置；材料时长请按item_id提供。")
    for key in ("expected_revision", "item_minutes", "budget_minutes", "session_minutes", "weekly_minutes", "duration_weeks"):
        if isinstance(raw.get(key), bool):
            raise ValidationError({key: "数字不能使用布尔值。"})
    for key in ("preview", "optimize_order", "prefer_unread"):
        if key in raw and type(raw[key]) is not bool:
            raise ValidationError({key: "需要布尔值。"})
    if isinstance(raw.get("reading_pace"), dict) and any(isinstance(value, bool) for value in raw["reading_pace"].values()):
        raise ValidationError({"reading_pace": "阅读速度需要整数，不能使用布尔值。"})
    command = validated(raw, PlanUpdateInput)
    preview = command.get("preview") is True
    if not preview and not command.get("request_id"):
        raise ValidationError({"request_id": "保存公共路径副本必须提供固定请求标识。"})
    privacy.lock_owner(user)
    if not preview:
        receipt, digest = _receipt(user, command, "copy_update", pk)
        if receipt:
            if receipt.record is None:
                raise NotFound("原操作已保存，但该私人计划后来已删除；请核对回执。")
            return receipt.record
    record = owned(user, pk, lock=True)
    if record.public_path_id is not None:
        raise ValidationError("公共路径跟读使用专用进度接口，不能作为私人计划修改。")
    research.expect(record, command["expected_revision"])
    payload, _ = refresh_payload(user, research.unpack(record))
    for key in ("goal", "background"):
        if key in command:
            payload[key] = research.text(command[key], key, 4000, key == "goal")
    by_id = {row["id"]: row for row in payload["items"]}
    if "order" in command:
        order = command["order"]
        if len(order) != len(by_id) or set(order) != set(by_id):
            raise ValidationError({"order": "必须恰好包含全部计划项，每项一次。"})
        if any((row["status"] == "completed" and order[index] != row["id"])
                or by_id[order[index]]["source_stage_id"] != row["source_stage_id"]
                for index, row in enumerate(payload["items"])):
            raise research.ResearchConflict("已完成项保留原位置，仅能显式调整同一阶段内的未完成项。")
        payload["items"] = [by_id[key] for key in order]
    if any(key in command for key in ("status", "note", "item_minutes", "reference")) and "item_id" not in command:
        raise ValidationError({"item_id": "请指定要修改的计划项。"})
    if "item_id" in command:
        item = by_id.get(command["item_id"])
        if item is None:
            raise NotFound("计划项不存在。")
        if item["status"] == "completed" and (("status" in command and command["status"] != "completed") or "item_minutes" in command or "reference" in command):
            raise research.ResearchConflict("已完成的材料与时长保留，可补充本人笔记。")
        if "reference" in command:
            reference = research.resolve_reference(command["reference"], user, strict=True)
            item["source_history"].append({key: deepcopy(value) for key, value in item.items()
                if key not in {"source_history", "reference", "quote"}})
            anchors = reference.get("anchors") or [reference]
            item.update({key: reference.get(key) for key in ("work_id", "edition_id", "asset_id", "document_revision_id",
                "title", "authors", "publication_year", "cover_url", "reader_url")})
            item.update(reference=research.compact_reference(reference), owner_override=True, node_id=None,
                kind="chapter", chapter_title="", page_start=anchors[0]["pdf_page"], page_end=anchors[-1]["pdf_page"],
                printed_page_label=anchors[0].get("printed_label", ""), version_label="", href=reference.get("reader_url"),
                source_status="available", available=True, substitutes=[], owner_estimate={}, status="pending")
            for key in ("estimated_minutes", "planning_estimate", "schedule", "difficulty"):
                item.pop(key, None)
        for key in ("status", "note"):
            if key in command:
                item[key] = command[key]
        if "item_minutes" in command:
            item["owner_estimate"] = {"minutes": command["item_minutes"]} if command["item_minutes"] is not None else {}
            item.pop("planning_estimate", None)
    payload["planning_inputs"] = research.plan_policy_inputs(command, payload.get("planning_inputs", {}))
    _schedule(payload)
    # Only source identity is retained. Current text and navigation are resolved
    # again on read, including after an owner replacement or source withdrawal.
    for item in payload["items"]:
        if item.get("reference"):
            item["reference"] = research.compact_reference(item["reference"])
    payload.pop("path_snapshot", None)
    if preview:
        record.data_ciphertext = research.pack(payload)
        return record
    research.save_data(record, payload)
    PlanCommandReceipt.objects.create(user=user, record=record, request_id=command["request_id"],
        fingerprint=digest, applied_revision=record.revision)
    return record
