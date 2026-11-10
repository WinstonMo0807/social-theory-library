"""Bind the existing node merge/rollback to a reviewed scope and recoverable request."""
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.models import User
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from catalog import models
from catalog.services import knowledge_nodes
from catalog.services.knowledge_merge_guard import merge_scope_fingerprint, merge_scope_fingerprints
from catalog.services.person_authority import AuthorityConflict, digest
from catalog.services.query_lexicon.mutations import acquire_entity_lock, acquire_generation_lock

ACTION = "knowledge_node_merge"
LOCK = "knowledge_node_merge_request"


def actor_lock(actor, *, rollback=False):
    current = get_object_or_404(User.objects.select_for_update(), pk=actor.pk, is_active=True)
    capability = Capability.RUN_SYSTEM_RECOVERY if rollback else Capability.MERGE_AUTHORITY
    if current.token_version != actor.token_version or not has_capability(current, capability):
        raise PermissionDenied("账户会话或归并权限已变化，请重新核对。")
    return current


def pair(source_id, target_id, *, lock=False):
    rows = models.KnowledgeNode.objects.filter(pk__in=[source_id, target_id]).order_by("pk")
    if lock:
        rows = rows.select_for_update()
    values = {str(row.pk): row for row in rows}
    if str(source_id) not in values or str(target_id) not in values:
        raise ValidationError("原理论或概念已不存在，请重新读取。")
    return values[str(source_id)], values[str(target_id)]


def summary(node):
    return {"id": str(node.pk), "name": node.canonical_name_zh, "name_en": node.canonical_name_en,
            "node_type": node.node_type, "status": node.status,
            "editor_url": f"/admin/theories?node={node.pk}"}


def pending_queries(source_id, target_id):
    work_ids = models.WorkNodeRelation.objects.filter(node_id=source_id).values("work_id")
    relation_ids = models.KnowledgeRelation.objects.filter(
        Q(source_node_id__in=[source_id, target_id]) | Q(target_node_id__in=[source_id, target_id])
    ).values("pk")
    path_ids = models.ReadingPathItem.objects.filter(node_id__in=[source_id, target_id]).values("reading_path_id")
    revisions = models.EditorialRevision.objects.filter(
        Q(target_type="work", target_id__in=work_ids)
        | Q(target_type="knowledge_node", target_id__in=[source_id, target_id])
        | Q(target_type="knowledge_relation", target_id__in=relation_ids)
        | Q(target_type="reading_path", target_id__in=path_ids), status="draft")
    preparing = models.CatalogPublicationRevision.objects.filter(edition__work_id__in=work_ids, status="preparing")
    return revisions, preparing


def preview(source, target, *, lock=False):
    # Reuse the rollback graph scope. Work drafts/publication jobs are also inputs
    # to the original merge; a new one must invalidate an already reviewed proposal.
    graph = merge_scope_fingerprint(source.pk, target.pk, lock=lock)
    revisions, preparing = pending_queries(source.pk, target.pk)
    if lock:
        revisions, preparing = revisions.select_for_update(), preparing.select_for_update()
    draft_rows = list(revisions.order_by("pk").values("id", "updated_at")[:5001])
    task_rows = list(preparing.order_by("pk").values("id", "updated_at")[:5001])
    if len(draft_rows) > 5000 or len(task_rows) > 5000:
        raise ValueError("相关修订超过单次安全范围，请先整理原工作区。")
    blockers = []
    if source.pk == target.pk:
        blockers.append("不能将条目合并到自身。")
    if source.status == "archived":
        blockers.append("来源条目已经下线或归并，请先核对原记录。")
    if target.status != "published":
        blockers.append("保留条目须为已发布版本。")
    if source.node_type != target.node_type:
        blockers.append("两项条目类型不同，不能直接合并理论与概念等不同对象。")
    if draft_rows:
        blockers.append("条目、关系、阅读路径或相关作品存在未发布草稿，请先处理原修订。")
    if task_rows:
        blockers.append("相关作品正在更新智能内容，请等待原任务结束。")
    from catalog.services.knowledge_identity import pending_identity_edits
    if pending_identity_edits(models.Entity.objects.filter(node_id__in=[source.pk, target.pk])):
        blockers.append("相关知识页或ChangeSet仍有待处理编辑，请先审核或暂缓归并。")
    affected = knowledge_nodes.merge_preview(source)
    affected.pop("public_url", None)
    return {"source": summary(source), "target": summary(target), "affected": affected,
            "fingerprint": digest({"graph": graph, "drafts": draft_rows, "preparing": task_rows}),
            "can_merge": not blockers, "blockers": blockers,
            "rule": "保留右侧条目的名称与正文；汇入来源的已确认别名、馆藏关系和证据，迁移原阅读路径及审核关联，来源条目下线且保留历史。原页面编排和文章引用保留原编号，需在受影响对象中逐项核对。确认会更新相关公开内容。"}


@transaction.atomic
def merge(source_id, target_id, *, actor, request_id, fingerprint, confirmed, change_note=""):
    actor = actor_lock(actor)
    if confirmed is not True:
        raise ValidationError("请先核对保留条目及合并影响。")
    acquire_generation_lock(shared=True)
    acquire_entity_lock(LOCK, request_id)
    request_fingerprint = digest({"source": str(source_id), "target": str(target_id), "actor": actor.pk,
                                  "fingerprint": fingerprint, "change_note": change_note})
    old = AuditEvent.objects.filter(pk=request_id).first()
    if old:
        if old.action != ACTION or old.actor_id != actor.pk or old.after.get("fingerprint") != request_fingerprint:
            raise AuthorityConflict("原请求已停止或用于另一项操作，请查回原回执。")
        return get_object_or_404(models.KnowledgeNodeMergeRecord, pk=old.object_id)
    source, target = pair(source_id, target_id, lock=True)
    state = preview(source, target, lock=True)
    if state["fingerprint"] != fingerprint or not state["can_merge"]:
        raise AuthorityConflict({"detail": "条目、关联或草稿已变化，请重新预览。", "blockers": state["blockers"]})
    record = knowledge_nodes.merge_nodes(source.pk, target.pk, actor=actor, change_note=change_note)
    AuditEvent.objects.create(pk=request_id, actor=actor, action=ACTION,
        object_type=models.KnowledgeNodeMergeRecord._meta.label, object_id=str(record.pk),
        after={"operation": "merge", "fingerprint": request_fingerprint,
               "saved_version": record.rollback_payload.get("scope_fingerprint", "")})
    return record


def rollback_state(record, *, lock=False):
    fingerprints = merge_scope_fingerprints(record.source_node_id, record.target_node_id, lock=lock)
    current = fingerprints[0]
    expected = (record.rollback_payload or {}).get("scope_fingerprint")
    blockers = []
    if record.rolled_back_at:
        blockers.append("这次合并已经回退。")
    if not expected or expected not in fingerprints:
        blockers.append("缺少原范围记录或合并后已有修改，不能覆盖后续工作。")
    return {"fingerprint": current, "can_rollback": not blockers, "blockers": blockers}


@transaction.atomic
def rollback(record_id, *, actor, fingerprint, confirmed):
    actor = actor_lock(actor, rollback=True)
    if confirmed is not True:
        raise ValidationError("请先核对原合并记录和回退影响。")
    acquire_generation_lock(shared=True)
    record = get_object_or_404(models.KnowledgeNodeMergeRecord.objects.select_for_update(), pk=record_id)
    if record.rolled_back_at:
        return record
    pair(record.source_node_id, record.target_node_id, lock=True)
    state = rollback_state(record, lock=True)
    if state["fingerprint"] != fingerprint or not state["can_rollback"]:
        raise AuthorityConflict("合并后的条目或关联已经变化，不能回退覆盖后续工作。")
    return knowledge_nodes.rollback_merge(record.pk, actor=actor)
