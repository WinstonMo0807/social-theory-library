"""Explicit, version-bound copies from original booklists into original private plans."""
from hashlib import sha256
import json

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from . import booklists, privacy, research
from .models import PersonalReadingPlan
from .path_models import PlanCommandReceipt
from .plan_rules import schedule_plan
from .services import current_reader_asset_for_work


def preview(user, pk, expected_version, item_ids=None):
    row = booklists.owned(user, pk)
    if booklists.version(row) != expected_version:
        raise research.ResearchConflict("书单已变化，请读取当前版本后重新选择计划材料。")
    items = row.items.filter(removed_at__isnull=True).select_related("work").order_by("order", "created_at", "id")
    if item_ids:
        items = items.filter(pk__in=item_ids)
        if items.count() != len(item_ids):
            raise research.ResearchConflict("所选作品已变化，请重新选择。")
    count = items.count()
    if count == 0 or count > 200:
        raise ValidationError("每次计划选择1至200部作品；较长书单请分批选择。")
    results = []
    for item in items:
        entry = {"item_id": str(item.pk), "work_id": str(item.work_id), "title": "来源暂不可用",
            "reference": None, "source_status": "unavailable", "reader_url": None, "catalog_revision_id": None}
        edition = booklists.public_editions().filter(work_id=item.work_id).select_related("active_catalog_revision").first()
        if edition:
            entry["title"] = (edition.active_catalog_revision.snapshot.get("work") or {}).get("title") or "未题名"
            asset = current_reader_asset_for_work(item.work, user=user)
            revision = asset.edition.active_catalog_revision if asset else None
            if revision and revision.document_revision_id:
                entry["catalog_revision_id"] = str(revision.pk)
                ref = research.resolve_reference({"asset_id": str(asset.pk),
                    "document_revision_id": str(revision.document_revision_id), "pdf_page": 1}, user)
                if ref["source_status"] == "available":
                    entry.update(title=ref["title"], reference=research.compact_reference(ref),
                        source_status="available", reader_url=ref.get("reader_url"))
        results.append(entry)
    if booklists.version(booklists.owned(user, pk)) != expected_version:
        raise research.ResearchConflict("书单正在另一页面修改，请重新预览。")
    digest = sha256(json.dumps(results, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    return {"owner_id": str(user.pk), "list_id": str(pk), "expected_version": expected_version,
        "source_token": digest, "goal": row.goal, "items": results,
        "ready": all(entry["source_status"] == "available" for entry in results)}


def output(user, receipt):
    record = receipt.record
    if record and record.user_id != user.pk:
        raise NotFound("本人的计划回执不存在。")
    return {"owner_id": str(user.pk), "request_id": str(receipt.request_id),
        "record_id": str(record.pk) if record else None, "deleted": record is None}


def lookup(user, request_id):
    receipt = PlanCommandReceipt.objects.select_related("record").filter(user=user, request_id=request_id).first()
    if receipt is None:
        raise NotFound("尚未找到这个请求的计划回执。可以在原页面用原请求重试。")
    if receipt.record and research.unpack(receipt.record).get("origin", {}).get("type") != "booklist_copy":
        raise NotFound("这个请求没有创建书单阅读计划。")
    return output(user, receipt)


@transaction.atomic
def create(user, pk, data):
    pk = research.identifier(pk)
    data = json.loads(json.dumps(data, default=str))
    privacy.lock_owner(user)
    fingerprint = research.request_fingerprint({"action": "booklist_plan", "list_id": str(pk), **data},
        ("action", "list_id", *data))
    receipt = PlanCommandReceipt.objects.select_related("record").filter(user=user, request_id=data["request_id"]).first()
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容已变化，请先核对原计划结果。")
        return output(user, receipt)
    if PersonalReadingPlan.objects.filter(user=user, request_id=data["request_id"]).exists():
        raise research.ResearchConflict("这个请求标识已经用于其他计划。")
    # Plans are explicitly created and individually erased in the existing privacy
    # model; RETENTION has no plans switch. Never invent a gate or reuse notes' gate.
    source = preview(user, pk, data["expected_version"], data.get("item_ids"))
    if source["source_token"] != data["source_token"]:
        raise research.ResearchConflict("作品的公开版本或可读状态已变化，请重新预览材料。")
    if not source["ready"]:
        raise ValidationError("所选作品中有当前不可读的来源，请返回书单重新选择。")
    command = {key: value for key, value in data.items() if key not in {"expected_version", "source_token", "item_ids"}}
    if command.get("prefer_unread") is True:
        raise ValidationError("本次保留书单顺序。优先未读排序可在生成后由本人选择优化。")
    command["prefer_unread"] = False
    command["references"] = [item["reference"] for item in source["items"]]
    plan = research.generate_plan(user, command)
    payload = research.unpack(plan)
    ordering = {item["work_id"]: index for index, item in enumerate(source["items"])}
    payload["items"].sort(key=lambda item: ordering[item["work_id"]])
    for item in payload["items"]:
        item["reason"] = "来自本人选择的书单作品，保留书单顺序。"
    payload["items"], payload["schedule"] = schedule_plan(payload["items"], payload["prerequisites"], payload["planning_policy"], preserve_order=True)
    payload["origin"] = {"type": "booklist_copy", "booklist_id": str(pk), "booklist_version": data["expected_version"],
        "source_token": data["source_token"], "item_ids": [item["item_id"] for item in source["items"]]}
    payload["method"] = "owner_selected_booklist"
    research.save_data(plan, payload)
    current = preview(user, pk, data["expected_version"], data.get("item_ids"))
    if current["source_token"] != source["source_token"]:
        raise research.ResearchConflict("材料在生成计划时发生变化，请重新预览；本次计划没有保存。")
    receipt = PlanCommandReceipt.objects.create(user=user, record=plan, request_id=data["request_id"],
        fingerprint=fingerprint, applied_revision=plan.revision)
    return output(user, receipt)
