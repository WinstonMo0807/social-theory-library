"""Explicit copies of an article's work list, with owner-bound retry receipts."""
from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import RecommendationIssue
from catalog.services import editorial_issues
from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .models import ReadingList, ReadingListItem


def identity(issue, revision):
    return sha256(f"issue-list:{issue.pk}:{revision}".encode()).hexdigest()


def output(user, key, receipt=None):
    row = ReadingList.objects.filter(user=user, description=f"专题书目副本 / {key}").first()
    return {"owner_id": str(user.pk), "id": str(row.pk) if row else None, "title": row.title if row else "",
        "item_count": row.items.count() if row else 0, "saved": row is not None,
        "receipt": {"request_id": str(receipt.request_id)} if receipt else None,
        "notice": "书单按作品保存，不记录原文版本、页码或阅读进度。原文引用请使用文章中的引用入口。"}


def receipt_for(user, key, request_id):
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if receipt and receipt.target_key != key:
        raise research.ResearchConflict("原请求用于另一份书单，请核对原操作。")
    return receipt


def state(user, slug, revision, request_id):
    issue = get_object_or_404(RecommendationIssue, slug=slug)
    key = identity(issue, revision)
    receipt = receipt_for(user, key, request_id)
    if not receipt:
        raise NotFound("尚未找到本次保存回执。可以使用原请求重试。")
    return output(user, key, receipt)


@transaction.atomic
def save(user, slug, data):
    privacy.lock_owner(user)
    issue = get_object_or_404(RecommendationIssue, slug=slug)
    key = identity(issue, data["public_revision_id"])
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    receipt = receipt_for(user, key, data["request_id"])
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容已经改变，请先核对保存结果。")
        return output(user, key, receipt)
    current = editorial_issues.published_issues().filter(pk=issue.pk).first()
    if not current or str(editorial_issues.public_issue_revision(current).pk) != str(data["public_revision_id"]):
        raise research.ResearchConflict("文章公开版本已变化，请刷新文章后再保存书单。")
    privacy.require_retention(user, "saved_knowledge")
    payload = editorial_issues.issue_payload(current, public=True, include_body=False)
    work_ids = list(dict.fromkeys(row["available_work_id"] for row in payload["items"] if row.get("available_work_id")))
    if not work_ids:
        raise ValidationError("本期没有可加入私人书单的公开馆藏。计划上架项不会自动变成馆藏。")
    row = ReadingList.objects.filter(user=user, description=f"专题书目副本 / {key}").first()
    if row is None:
        row = ReadingList.objects.create(user=user, title=payload["title"][:240], description=f"专题书目副本 / {key}")
        ReadingListItem.objects.bulk_create([ReadingListItem(reading_list=row, work_id=value, order=index) for index, value in enumerate(work_ids)])
    receipt = KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"], target_key=key, fingerprint=fingerprint, applied_saved=True)
    return output(user, key, receipt)
