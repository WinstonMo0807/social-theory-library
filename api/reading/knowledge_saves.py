from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from catalog.models import KnowledgeNode
from . import privacy, research
from .knowledge_models import KnowledgeSaveReceipt, SavedKnowledgeNode


def target_key(node_id):
    return sha256(str(node_id).encode()).hexdigest()


def version(row):
    return f"{row.id}:{row.updated_at.isoformat()}" if row else "0"


def output(user, node_id, receipt=None):
    row = SavedKnowledgeNode.objects.filter(user=user, node_id=node_id).first()
    node = KnowledgeNode.objects.filter(pk=node_id, status="published").first()
    return {"owner_id": str(user.pk), "node_id": str(node_id), "saved": row is not None,
            "record_id": str(row.pk) if row else None, "version": version(row),
            "node": {"id": str(node.pk), "title": node.canonical_name_zh, "slug": node.slug,
                     "node_type": node.node_type} if node else None,
            "receipt": {"request_id": str(receipt.request_id), "applied_saved": receipt.applied_saved}
                if receipt else None}


def receipt_for(user, node_id, request_id):
    receipt = KnowledgeSaveReceipt.objects.filter(user=user, request_id=request_id).first()
    if receipt and receipt.target_key != target_key(node_id):
        raise research.ResearchConflict("请求标识已用于另一个知识条目，不能改绑。")
    return receipt


@transaction.atomic
def command(user, node_id, data):
    privacy.lock_owner(user)
    fingerprint = sha256(json.dumps({"node_id": str(node_id), **data}, sort_keys=True, default=str).encode()).hexdigest()
    receipt = receipt_for(user, node_id, data["request_id"])
    if receipt:
        if receipt.fingerprint != fingerprint:
            raise research.ResearchConflict("原请求内容不能改变，请先核对收藏状态。")
        return output(user, node_id, receipt)
    row = SavedKnowledgeNode.objects.filter(user=user, node_id=node_id).first()
    if data["expected_version"] != version(row):
        raise research.ResearchConflict("收藏已在其他页面修改，请先读取当前状态。")
    if data["saved"]:
        privacy.require_retention(user, "saved_knowledge")
        node = get_object_or_404(KnowledgeNode.objects.filter(status="published"), pk=node_id)
        if not row:
            SavedKnowledgeNode.objects.create(user=user, node=node)
    elif row:
        row.delete()
    receipt = KnowledgeSaveReceipt.objects.create(user=user, request_id=data["request_id"],
        target_key=target_key(node_id), fingerprint=fingerprint, applied_saved=data["saved"])
    return output(user, node_id, receipt)
