"""Existing SavedTopic collections with owner-scoped commands and minimal receipts."""
from hashlib import sha256
import json

from django.db import transaction
from rest_framework.exceptions import NotFound, ValidationError

from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt
from .models import SavedTopic


def target_key(topic_id):
    # Knowledge-node receipts hash an unprefixed UUID. This namespace never overlaps.
    return sha256(f"topic:{topic_id}".encode()).hexdigest()


def version(row):
    return f"{row.pk}:{row.updated_at.isoformat()}" if row else "0"


def receipt_for(user, topic_id, request_id):
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if receipt and receipt.target_key != target_key(topic_id):
        raise research.ResearchConflict("该请求标识已用于另一项收藏，请核对原操作。")
    return receipt


def output(user, topic_id, receipt=None):
    from catalog.services.public_topics import topic_follow_summary
    from .serializers import SavedTopicSerializer
    row = SavedTopic.objects.filter(user=user, topic_id=topic_id).first()
    return {"owner_id": str(user.pk), "topic_id": str(topic_id), "saved": row is not None,
            "version": version(row), "record": SavedTopicSerializer(row).data if row else None,
            "can_save": topic_follow_summary(topic_id) is not None,
            "receipt": {"request_id": str(receipt.request_id), "applied_saved": receipt.applied_saved} if receipt else None}


def state(user, topic_id, request_id=None):
    topic_id = research.identifier(topic_id, "topic")
    receipt = receipt_for(user, topic_id, research.identifier(request_id, "request_id")) if request_id else None
    if request_id and receipt is None:
        raise NotFound("尚未找到本人的主题收藏回执，可使用原请求标识重试。")
    return output(user, topic_id, receipt)


@transaction.atomic
def command(user, data):
    from catalog.services.public_topics import topic_follow_summary
    privacy.lock_owner(user)
    topic_id = research.identifier(data["topic"], "topic")
    fingerprint = sha256(json.dumps({**data, "topic": str(topic_id)}, sort_keys=True, default=str).encode()).hexdigest()
    receipt = receipt_for(user, topic_id, data["request_id"])
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容不能改变，请先核对主题收藏。")
        return output(user, topic_id, receipt)
    row = SavedTopic.objects.filter(user=user, topic_id=topic_id).first()
    if data["expected_version"] != version(row):
        raise research.ResearchConflict("主题收藏已在其他页面修改，请先读取当前状态。")
    if data["saved"]:
        privacy.require_retention(user, "followed_topics")
        if topic_follow_summary(topic_id) is None:
            raise ValidationError("该主题当前不可收藏。")
        if row is None:
            SavedTopic.objects.create(user=user, topic_id=topic_id)
    elif row:
        row.delete()
    receipt = KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"],
        target_key=target_key(topic_id), fingerprint=fingerprint, applied_saved=data["saved"])
    return output(user, topic_id, receipt)
