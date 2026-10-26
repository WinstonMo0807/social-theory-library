"""Manual parallel reading: exact references, encrypted decisions and durable command receipts."""
import json

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from catalog.models import Page
from catalog.services.parallel_reading import ParallelSourceChanged, resolve_parallel_reference, validate_pair
from common.capabilities import Capability, has_capability
from . import research
from .parallel_models import ParallelCalibration, ParallelReadingReceipt, ParallelReadingTask
from .parallel_serializers import (
    ParallelCalibrationCreateInput, ParallelReviewInput, ParallelTaskCreateInput, ParallelTaskUpdateInput,
)
from .privacy import lock_owner, require_retention

PAIR_KEYS = ("left_asset_id", "right_asset_id", "left_document_revision_id", "right_document_revision_id")
SOURCE_ERRORS = (NotFound, ValidationError, ParallelSourceChanged)


def validated(raw, schema):
    if not isinstance(raw, dict) or len(json.dumps(raw, ensure_ascii=False, default=str)) > 250_000:
        raise ValidationError({"detail": "请求需要对象，且内容不能超过 250000 字符。"})
    serializer = schema(data=raw)
    serializer.is_valid(raise_exception=True)
    return json.loads(json.dumps(serializer.validated_data, default=str))


def fingerprint(data):
    return research.request_fingerprint(data, data.keys())


def pair(data, user, *, public=False, require_fulltext=True):
    return validate_pair(user, data["left_asset_id"], data["right_asset_id"],
        left_document_revision_id=data["left_document_revision_id"],
        right_document_revision_id=data["right_document_revision_id"],
        public=public, require_fulltext=require_fulltext)


def unavailable(raw):
    return {**research.compact_reference(raw), "source_status": "unavailable",
            "reference_id": research.reference_identity(raw), "quote": "", "reader_url": None}


def read_reference(raw, user, *, public=False, pair_available=True):
    if raw is None:
        return None
    if not pair_available:
        return unavailable(raw)
    try:
        value = resolve_parallel_reference(raw, user, strict=False, public=public)
        return value if value.get("source_status") == "available" else unavailable(raw)
    except SOURCE_ERRORS:
        return unavailable(raw)


def source_summary(edition):
    revision = edition.active_catalog_revision
    snapshot = revision.snapshot or {}
    work, edition_values = snapshot.get("work") or {}, snapshot.get("edition") or {}
    return {"title": work.get("title") or "", "version_label": edition_values.get("version_label") or "",
        "authors": [str((row.get("person") or {}).get("preferred_name") or row.get("name") or "")
            for row in snapshot.get("contributions", []) if isinstance(row, dict) and row.get("role") == "author"],
        "asset_id": str(revision.reader_asset_id), "document_revision_id": str(revision.document_revision_id),
        "reader_url": f"/reader/{revision.reader_asset_id}?page=1&revision={revision.document_revision_id}"}


def read_data(data, user, *, public=False, require_fulltext=True):
    try:
        editions = pair(data, user, public=public, require_fulltext=require_fulltext)
    except SOURCE_ERRORS:
        editions = None
    result = {key: data[key] for key in PAIR_KEYS}
    for key in ("positions", "sync_scroll", "basis"):
        if key in data:
            result[key] = data[key]
    available = editions is not None
    for key in ("alignments", "terms"):
        if key not in data:
            continue
        result[key] = []
        for row in data[key]:
            value = {name: item for name, item in row.items() if name not in {"left", "right"}}
            for side in ("left", "right"):
                value[side] = read_reference(row.get(side), user, public=public, pair_available=editions is not None)
                if value[side] and value[side]["source_status"] != "available":
                    available = False
            result[key].append(value)
    sources = {"left": source_summary(editions[0]), "right": source_summary(editions[1])} if editions else None
    return result, available, sources


def envelope(record, data, available, sources):
    return {"id": str(record.id), "revision": record.revision, "request_id": str(record.request_id),
        "created_at": record.created_at.isoformat(), "updated_at": record.updated_at.isoformat(),
        "data": data, "source_available": available, "pair_sources": sources,
        "notice": "" if available else "来源已更新或当前不可读取；本人已保存的决定保留，原文内容暂不展示。"}


def task_output(record, user, *, applied_revision=None):
    if not user.is_authenticated or record.user_id != user.pk:
        raise PermissionDenied("只能读取本人的并读记录。")
    data, available, sources = read_data(research.unpack(record), user)
    output = envelope(record, data, available, sources)
    if applied_revision is not None:
        output["applied_revision"] = applied_revision
    return output


def reference_identity_data(raw):
    # Response decoration (schema/source kind and bibliographic IDs) is not part
    # of a client's compact exact location, but ranges and hashes always are.
    output = {key: raw[key] for key in ("asset_id", "document_revision_id", "pdf_page", "content_hash",
              "selection_start", "selection_end") if key in raw}
    output["evidence_span_id"] = raw.get("evidence_span_id")
    if raw.get("anchors"):
        output["anchors"] = [reference_identity_data(row) for row in raw["anchors"]]
    return output


def normalize_task(data, user, *, previous=None):
    if previous and any(data[key] != previous[key] for key in PAIR_KEYS):
        raise ValidationError({"data": "已保存任务的左右版本不能更换；请保留原任务并新建并读。"})
    try:
        editions = pair(data, user)
    except SOURCE_ERRORS:
        if previous is None:
            raise
        editions = None
    old_refs = [research.compact_reference(row[side])
        for key in ("alignments", "terms") for row in (previous or {}).get(key, [])
        for side in ("left", "right") if row.get(side)]
    result = {key: data[key] for key in PAIR_KEYS}
    result["sync_scroll"] = data["sync_scroll"]
    positions = data.get("positions") or {"left_page": 1, "right_page": 1}
    positions = {**positions, "left_segment_id": positions.get("left_segment_id") or None,
                 "right_segment_id": positions.get("right_segment_id") or None}
    if editions:
        for side, edition in zip(("left", "right"), editions):
            asset = edition.active_catalog_revision.reader_asset
            total = asset.page_count or Page.objects.filter(asset=asset).order_by("-index").values_list("index", flat=True).first() or 0
            if positions[f"{side}_page"] > total:
                raise ValidationError({"positions": "阅读位置超出该版本的实际页数。"})
    elif positions != previous["positions"]:
        raise ValidationError({"positions": "来源已变化；请先保留原阅读位置，再修改私人笔记。"})
    result["positions"] = positions
    for key in ("alignments", "terms"):
        rows, ids = [], set()
        for row in data[key]:
            if row["id"] in ids:
                raise ValidationError({key: "同一任务内的条目标识不能重复。"})
            ids.add(row["id"])
            value = {name: item for name, item in row.items() if name not in {"left", "right"}}
            if key == "alignments":
                required = {"confirmed": (True, True), "no_match": (True, False), "addition": (False, True)}[row["status"]]
                if tuple(bool(row.get(side)) for side in ("left", "right")) != required:
                    raise ValidationError({"alignments": "对应段需两侧原文；无对应段只选左侧；新增段只选右侧。"})
            for side in ("left", "right"):
                raw = row.get(side)
                if raw is None:
                    value[side] = None
                    continue
                compact = research.compact_reference(raw)
                # Users may continue editing their own note after withdrawal, but may
                # only carry forward references that were already verified here.
                preserved = next((old for old in old_refs
                    if reference_identity_data(old) == reference_identity_data(compact)
                    and all(old.get(name) == compact[name] for name in ("work_id", "edition_id") if name in compact)), None)
                if editions is None and preserved is not None:
                    current = preserved
                else:
                    try:
                        current = resolve_parallel_reference(raw, user, strict=True)
                    except SOURCE_ERRORS:
                        if preserved is None:
                            raise
                        current = preserved
                if (current.get("asset_id") != data[f"{side}_asset_id"]
                        or current.get("document_revision_id") != data[f"{side}_document_revision_id"]):
                    raise ValidationError({side: "选文必须属于该侧已选版本的同一文字修订。"})
                value[side] = research.compact_reference(current)
            rows.append(value)
        result[key] = rows
    return result


def existing_receipt(user, request_id, digest, *, task_id=None):
    receipt = ParallelReadingReceipt.objects.select_related("task").filter(user=user, request_id=request_id).first()
    if receipt is None:
        return None
    if receipt.task_id is None:
        raise research.ResearchConflict("此请求对应的私人任务已删除，旧保存请求不能重新创建内容。")
    if receipt.fingerprint != digest or (task_id is not None and str(receipt.task_id) != str(task_id)):
        raise research.ResearchConflict("该保存请求已用于不同内容，请保留输入并确认保存状态。")
    return receipt


def task_by_request(user, request_id):
    receipt = ParallelReadingReceipt.objects.select_related("task").filter(
        user=user, request_id=research.identifier(request_id, "request_id"), task__user=user).first()
    if receipt is None:
        raise NotFound("未找到本人的该次保存回执。")
    return task_output(receipt.task, user, applied_revision=receipt.applied_revision)


@transaction.atomic
def create_task(user, raw):
    command = validated(raw, ParallelTaskCreateInput)
    lock_owner(user)
    digest = fingerprint({"action": "create", **command})
    receipt = existing_receipt(user, command["request_id"], digest)
    if receipt:
        return task_output(receipt.task, user, applied_revision=receipt.applied_revision)
    require_retention(user, "personal_notes")
    data = normalize_task(command["data"], user)
    record = ParallelReadingTask.objects.create(user=user, request_id=command["request_id"],
        left_asset_id=data["left_asset_id"], right_asset_id=data["right_asset_id"],
        data_ciphertext=research.pack(data))
    ParallelReadingReceipt.objects.create(user=user, task=record, request_id=command["request_id"],
        fingerprint=digest, applied_revision=record.revision)
    return task_output(record, user, applied_revision=record.revision)


@transaction.atomic
def update_task(user, pk, raw):
    command = validated(raw, ParallelTaskUpdateInput)
    lock_owner(user)
    record = research.owned(ParallelReadingTask, user, pk, lock=True)
    digest = fingerprint({"action": "update", "task_id": str(record.id), **command})
    receipt = existing_receipt(user, command["request_id"], digest, task_id=record.id)
    if receipt:
        return task_output(record, user, applied_revision=receipt.applied_revision)
    research.expect(record, command["expected_revision"])
    data = normalize_task(command["data"], user, previous=research.unpack(record))
    research.save_data(record, data)
    ParallelReadingReceipt.objects.create(user=user, task=record, request_id=command["request_id"],
        fingerprint=digest, applied_revision=record.revision)
    return task_output(record, user, applied_revision=record.revision)


@transaction.atomic
def delete_task(user, pk, revision):
    lock_owner(user)
    record = research.owned(ParallelReadingTask, user, pk, lock=True)
    research.expect(record, revision)
    record.delete()


def calibration_output(record, user, *, admin=False, public=False):
    if admin and not has_capability(user, Capability.REVIEW_CANDIDATE):
        raise PermissionDenied("当前账户不能审核校准投稿。")
    if not public and not admin and (not user.is_authenticated or record.user_id != user.pk):
        raise PermissionDenied("只能读取本人的校准投稿。")
    stored = research.unpack(record)
    data = {key: stored[key] for key in (*PAIR_KEYS, "basis", "alignments")}
    # All contribution viewers get anonymous source rights, including administrators.
    data, available, sources = read_data(data, AnonymousUser(), public=True, require_fulltext=record.scope == "passages")
    if public and (record.status != "published" or not available):
        return None
    output = {**envelope(record, data, available, sources), "scope": record.scope, "status": record.status}
    if admin:
        output.update(review_note=stored.get("_review_note", ""), reviewer_id=record.reviewer_id)
    if public:
        output.pop("request_id", None)
        output["notice"] = "经审核的公开校准；不替代原文，也不改变任何人的私人笔记。"
    return output


@transaction.atomic
def create_calibration(user, raw):
    command = validated(raw, ParallelCalibrationCreateInput)
    lock_owner(user)
    digest = fingerprint(command)
    previous = ParallelCalibration.objects.filter(user=user, request_id=command["request_id"]).first()
    if previous:
        research.same_request(previous, digest)
        return calibration_output(previous, user)
    task = research.owned(ParallelReadingTask, user, command["task_id"], lock=True)
    research.expect(task, command["expected_revision"])
    data = research.unpack(task)
    pair(data, user, public=True, require_fulltext=command["scope"] == "passages")
    selected = []
    if command["scope"] == "passages":
        alignment_id = command.get("alignment_id")
        alignment = next((row for row in data["alignments"] if row["id"] == alignment_id), None)
        if alignment is None:
            raise ValidationError({"alignment_id": "请明确选择已保存的本人对齐记录。"})
        selected = [{"id": alignment["id"], "status": alignment["status"]}]
        for side in ("left", "right"):
            selected[0][side] = (research.compact_reference(resolve_parallel_reference(
                alignment[side], user, strict=True, public=True)) if alignment.get(side) else None)
    payload = {**{key: data[key] for key in PAIR_KEYS}, "basis": command["basis"], "alignments": selected,
               "request_fingerprint": digest, "_review_receipts": {}}
    record = ParallelCalibration.objects.create(user=user, request_id=command["request_id"], scope=command["scope"],
        left_asset_id=data["left_asset_id"], right_asset_id=data["right_asset_id"], data_ciphertext=research.pack(payload))
    return calibration_output(record, user)


def calibration_by_request(user, request_id):
    record = ParallelCalibration.objects.filter(user=user, request_id=research.identifier(request_id, "request_id")).first()
    if record is None:
        raise NotFound("未找到本人的该次校准投稿。")
    return calibration_output(record, user)


@transaction.atomic
def review_calibration(user, pk, action, raw):
    if not has_capability(user, Capability.REVIEW_CANDIDATE):
        raise PermissionDenied("当前账户不能审核校准投稿。")
    if action == "publish" and not has_capability(user, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前账户不能公开校准投稿。")
    command = validated(raw, ParallelReviewInput)
    record = ParallelCalibration.objects.select_for_update().filter(pk=research.identifier(pk)).first()
    if record is None:
        raise NotFound("校准投稿不存在。")
    data = research.unpack(record)
    digest = fingerprint({"actor": user.pk, "action": action, **command})
    receipts = data.get("_review_receipts", {})
    previous = receipts.get(command["request_id"])
    if previous:
        if previous["fingerprint"] != digest:
            raise research.ResearchConflict("该审核请求已用于不同内容，请确认原操作结果。")
        return {**calibration_output(record, user, admin=True), "request_id": command["request_id"],
                "applied_revision": previous["revision"]}
    research.expect(record, command["expected_revision"])
    if action not in {"review", "publish", "reject"}:
        raise ValidationError({"action": "不支持此校准操作。"})
    if action == "publish" and record.status != "reviewed":
        raise research.ResearchConflict("请先独立完成审核，再确认公开。")
    if action == "review" and record.status == "published":
        raise research.ResearchConflict("已公开记录需先撤下，再重新审核。")
    if action == "reject" and not command["note"].strip():
        raise ValidationError({"note": "请说明拒绝或撤下的依据。"})
    if action != "reject":
        pair(data, AnonymousUser(), public=True, require_fulltext=record.scope == "passages")
        for row in data["alignments"]:
            for side in ("left", "right"):
                if row.get(side):
                    resolve_parallel_reference(row[side], AnonymousUser(), strict=True, public=True)
    # A fixed receipt is never silently evicted and later treated as a new command.
    if len(receipts) >= 1000:
        raise ValidationError({"detail": "此投稿的审核记录已达上限，请另建明确的新投稿。"})
    record.status = {"review": "reviewed", "publish": "published", "reject": "rejected"}[action]
    record.reviewer = user
    data["_review_note"] = command["note"]
    data["_review_receipts"] = {**receipts, command["request_id"]: {"fingerprint": digest, "revision": record.revision + 1}}
    research.save_data(record, data, fields=("status", "reviewer"))
    return {**calibration_output(record, user, admin=True), "request_id": command["request_id"],
            "applied_revision": record.revision}
