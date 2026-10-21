"""Article comments never infer names from accounts or reuse private notes."""
from datetime import timedelta
from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.exceptions import NotFound, Throttled

from catalog.models import RecommendationIssue
from catalog.services import editorial_issues
from catalog.services.public_scholars import _page
from ingestion.models import AuditEvent
from . import privacy, research
from .editorial_comment_models import EditorialComment
from .knowledge_models import KnowledgeSaveReceipt


def record(row, *, private=False):
    data = research.unpack(row)
    value = {"id": str(row.pk), "public_revision_id": str(row.public_revision_id), "byline": data.get("byline", ""),
        "body": data.get("body", ""), "created_at": row.created_at.isoformat()}
    if private:
        value.update(revision=row.revision, status=row.status, moderation_reason=row.moderation_reason)
    return value


def current_issue(issue_id):
    return get_object_or_404(editorial_issues.published_issues(), pk=issue_id)


def public_page(issue_id, params):
    issue = current_issue(issue_id)
    revision = editorial_issues.public_issue_revision(issue)
    if params.get("public_revision_id") and str(params["public_revision_id"]) != str(revision.pk):
        raise research.ResearchConflict("文章版本已经变化，请刷新文章后阅读对应评论。")
    rows = EditorialComment.objects.filter(issue=issue, public_revision_id=revision.pk, status="published")
    return _page(rows, params, f"/api/reading/article-comments/public/{issue_id}/", transform=lambda values: [record(row) for row in values])


def own_page(user, issue_id, params):
    rows = EditorialComment.objects.filter(user=user, issue_id=issue_id)
    return {"owner_id": str(user.pk), **_page(rows, params, f"/api/reading/article-comments/{issue_id}/", transform=lambda values: [record(row, private=True) for row in values])}


def target_key(issue_id, request_id):
    return sha256(f"article-comment:{issue_id}:{request_id}".encode()).hexdigest()


def receipt_state(user, issue_id, request_id):
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if not receipt:
        raise NotFound("尚未查到本次评论提交，可以用原请求重试。")
    if receipt.target_key != target_key(issue_id, request_id):
        raise research.ResearchConflict("请求身份用于其他操作，请核对原提交。")
    row = EditorialComment.objects.filter(pk=request_id, user=user, issue_id=issue_id).first()
    return {"owner_id": str(user.pk), "request_id": str(request_id), "comment": record(row, private=True) if row else None,
        "notice": "评论等待编辑审核后公开，可随时删除。" if row else "原提交已完成，评论后来已删除；未重新创建。"}


@transaction.atomic
def submit(user, issue_id, data):
    privacy.lock_owner(user)
    fingerprint = sha256(json.dumps(data, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    previous = KnowledgeSaveReceipt.objects.filter(user=user, request_id=data["request_id"]).first()
    if previous:
        if previous.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容已经改变，请先核对提交结果。")
        return receipt_state(user, issue_id, data["request_id"])
    issue = current_issue(issue_id)
    if str(editorial_issues.public_issue_revision(issue).pk) != str(data["public_revision_id"]):
        raise research.ResearchConflict("文章已经更新，请重新阅读后提交评论。")
    # Bound new submissions under the same owner lock; retries do not consume the limit.
    if EditorialComment.objects.filter(user=user, created_at__gte=timezone.now()-timedelta(days=1)).count() >= 100:
        raise Throttled(detail="今日评论提交较多，请稍后继续。")
    if EditorialComment.objects.filter(pk=data["request_id"]).exists():
        raise research.ResearchConflict("请求身份不可用，请重新发起提交。")
    EditorialComment.objects.create(id=data["request_id"], user=user, issue=issue, public_revision_id=data["public_revision_id"],
        data_ciphertext=research.pack({"body": data["body"], "byline": data["byline"]}))
    KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"], target_key=target_key(issue_id, data["request_id"]), fingerprint=fingerprint, applied_saved=True)
    return receipt_state(user, issue_id, data["request_id"])


@transaction.atomic
def remove(user, issue_id, comment_id, expected_revision):
    privacy.lock_owner(user)
    row = EditorialComment.objects.select_for_update().filter(pk=comment_id, user=user, issue_id=issue_id).first()
    if row:
        if row.revision != expected_revision:
            raise research.ResearchConflict("评论审核状态已改变，请重新读取后确认删除。")
        row.delete()
    return {"owner_id": str(user.pk), "deleted": True}


def moderation_page(issue_id, params):
    get_object_or_404(RecommendationIssue, pk=issue_id)
    return _page(EditorialComment.objects.filter(issue_id=issue_id), params, f"/api/reading/article-comments/admin/{issue_id}/", transform=lambda rows: [record(row, private=True) for row in rows])


@transaction.atomic
def moderate(actor, issue_id, data):
    initial = get_object_or_404(EditorialComment.objects.select_related("user"), pk=data["id"], issue_id=issue_id)
    privacy.lock_owner(initial.user)
    row = get_object_or_404(EditorialComment.objects.select_for_update(), pk=initial.pk)
    if row.revision != data["expected_revision"]:
        raise research.ResearchConflict("评论状态已经改变，请重新读取后审核。")
    if data["status"] == "published":
        issue = current_issue(issue_id)
        if editorial_issues.public_issue_revision(issue).pk != row.public_revision_id:
            raise research.ResearchConflict("该评论针对旧版文章，不能公开到当前版本。")
    row.status, row.moderation_reason, row.moderated_by = data["status"], data.get("reason", ""), actor
    row.revision += 1
    row.save(update_fields=["status", "moderation_reason", "moderated_by", "revision", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="editorial_comment.moderate", object_type="EditorialComment", object_id=str(row.pk), after={"status": row.status, "revision": row.revision})
    return record(row, private=True)
