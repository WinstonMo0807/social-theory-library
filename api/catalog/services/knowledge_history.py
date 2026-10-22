"""M18 history over canonical knowledge and existing immutable editorial revisions."""
from hashlib import sha256
import json

from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied

from catalog.editorial_read import current_editorial_version
from catalog.models import EditorialRevision, KnowledgeNode, KnowledgePublicationEvent, Person
from catalog.services.editorial_revision import (
    TARGET_POLICIES, EditorialRevisionConflict, EditorialRevisionError,
    create_editorial_revision, editorial_target_snapshot,
)
from catalog.services.knowledge_studio import KnowledgeObjectEditorAdapter, NODE_OBJECT_TYPES
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent


OBJECT_TYPES = tuple(key for key in KnowledgeObjectEditorAdapter.TARGET_TYPES if key != "work")
LIFECYCLE_KINDS = {"scholar": "scholar", "topic": "topic", "discipline": "discipline",
                   "subdiscipline": "subdiscipline", "reading_path": "reading-path"}
FIELD_LABELS = {
    "name": "名称", "title": "标题", "code": "学科代码", "slug": "页面路径", "foreign_name": "原文名称",
    "canonical_name_zh": "中文名称", "canonical_name_en": "原文名称", "node_type": "知识类型",
    "description": "说明", "introduction": "导言", "summary": "概述", "definition": "定义",
    "editorial_status": "发布状态", "status": "发布状态", "search_aliases": "检索别名", "aliases": "别名",
    "curation_level": "编排层级", "sort_order": "显示次序", "parent": "上级条目", "discipline": "所属学科",
    "primary_discipline": "主要学科", "core_questions": "核心问题", "basic_propositions": "基本命题",
    "theoretical_boundary": "理论边界", "start_year": "开始年份", "end_year": "结束年份", "period_label": "时期说明",
    "research_object": "研究对象", "formation_period": "形成时期", "research_directions": "研究方向",
    "methods": "研究方法", "representative_issues": "代表议题", "problem_statement": "问题说明",
    "research_dimensions": "研究维度", "formation_context": "形成背景", "key_concepts": "关键概念",
    "timeline": "时间线", "curation": "人工编排", "short_description": "人物简介", "affiliations": "机构",
    "key_concerns": "研究关注", "featured_quote": "代表引语", "quote_source": "引语出处", "person": "人物资料",
    "portrait_selection": "学者头像", "image_selection": "页面图片", "discipline_links": "学科关联",
    "subdiscipline_links": "子学科关联", "topic_links": "主题关联", "discipline_relations": "学科关联",
    "theory_relations": "理论关联", "subdiscipline_relations": "子学科关联", "stage_groups": "阅读阶段",
    "learning_goal": "学习目标", "audience": "目标读者", "difficulty": "难度", "estimated_reading": "预计阅读量",
    "estimated_weeks": "预计周数", "prerequisite": "先修准备", "topics": "关联主题", "learning_questions": "学习问题",
    "related_debate_ids": "相关争论", "curator_note": "策划说明", "credits": "署名",
}


def history_target(object_type, object_id, *, lock=False):
    if object_type not in OBJECT_TYPES:
        raise Http404
    target_type = KnowledgeObjectEditorAdapter.TARGET_TYPES[object_type]
    query = TARGET_POLICIES[target_type].model.objects.all()
    if lock:
        query = query.select_for_update()
    target = query.filter(pk=object_id).first()
    if target is None or isinstance(target, KnowledgeNode) and target.node_type != NODE_OBJECT_TYPES.get(object_type):
        raise Http404
    return target_type, target


def actor_label(actor):
    return (actor.display_name or actor.get_full_name() or actor.get_username()) if actor else "历史账户"


def _status_field(target):
    return "editorial_status" if hasattr(target, "editorial_status") else "status"


def history_rows(target_type, object_id):
    return EditorialRevision.objects.filter(target_type=target_type, target_id=object_id).select_related("created_by", "published_by").order_by("-revision", "-pk")


def history_projection(*, object_type, object_id, actor, page=1, selected_id=None):
    from catalog.lifecycle_views import LIFECYCLE_MODELS, lifecycle_snapshot
    from catalog.knowledge_publication_views import publication_status

    target_type, target = history_target(object_type, object_id)
    version = current_editorial_version(target_type, object_id)
    target.refresh_from_db()
    if isinstance(target, KnowledgeNode) and target.node_type != NODE_OBJECT_TYPES.get(object_type):
        raise EditorialRevisionConflict("知识对象类型已变化，请从原编辑页重新进入历史。")
    current = editorial_target_snapshot(target_type=target_type, target=target)
    rows = history_rows(target_type, object_id)
    draft = rows.filter(status="draft").first()
    paginator = Paginator(rows, 20)
    selected_page = paginator.page(page)
    selected = rows.filter(pk=selected_id).first() if selected_id else draft or rows.first()
    if selected_id and selected is None:
        raise Http404
    status_field = _status_field(target)
    can_publish = has_capability(actor, Capability.PUBLISH_AUTHORITY)
    def item(row):
        # A published revision is historical unless its captured values still
        # match canonical data. Direct canonical changes need not have a row.
        matches = bool(row.materialized_preview) and row.materialized_preview == current
        public_snapshot = row.materialized_preview.get(status_field) == "published"
        return {
            "id": str(row.pk), "revision": row.revision, "status": row.status,
            "snapshot_public": public_snapshot,
            "matches_current": matches, "note": row.change_note,
            "actor": actor_label(row.published_by or row.created_by),
            "created_at": row.created_at, "published_at": row.published_at,
            "can_restore": can_publish and draft is None and row.status == "published" and public_snapshot and not matches,
        }
    captured = selected.materialized_preview if selected else current
    changes = []
    policy = TARGET_POLICIES[target_type]
    for key in sorted(policy.editable_fields.intersection(captured)):
        before, after = current.get(key), captured[key]
        label = FIELD_LABELS.get(key, key)
        changes.append({"field": key, "label": label, "before": before, "after": after, "changed": before != after})
    kind = LIFECYCLE_KINDS.get(object_type, "knowledge-node")
    impact = lifecycle_snapshot(kind, target, LIFECYCLE_MODELS[kind])
    events = KnowledgePublicationEvent.objects.filter(object_type=target_type, object_id=object_id).select_related("actor").prefetch_related("deliveries").order_by("-created_at", "-pk")[:20]
    result = {
        "object_type": object_type, "object_id": str(object_id), "edit_version": version,
        "title": str(getattr(target, "title", "") or getattr(target, "name", "") or getattr(target, "canonical_name_zh", "") or getattr(target, "canonical_name_en", "") or (target.person.preferred_name if object_type == "scholar" else "")),
        "status": getattr(target, status_field), "is_public": KnowledgeObjectEditorAdapter._is_public(object_type, target),
        "has_draft": draft is not None, "draft_id": str(draft.pk) if draft else None,
        "can_withdraw": can_publish and draft is None and getattr(target, status_field) == "published",
        "history": {"count": paginator.count, "page": selected_page.number, "pages": paginator.num_pages, "results": [item(row) for row in selected_page]},
        "selected": item(selected) if selected else None, "changes": changes,
        "dependencies": impact["dependencies"],
        "events": [{"id": str(event.pk), "created_at": event.created_at, "actor": actor_label(event.actor), **publication_status(event, actor)} for event in events],
        "scope": "历史内容限于本对象修订所保存的字段和关联。独立原文策展、其他对象、私人记录与原始文件保持各自历史；关联数量不是受影响页面或访问量。",
    }
    if current_editorial_version(target_type, object_id) != version:
        raise EditorialRevisionConflict("读取期间保存内容发生变化，请重新读取版本历史。")
    return result


@transaction.atomic
def prepare_history_command(*, object_type, object_id, actor, action, request_key, expected_version, reason, source_revision_id=None):
    if not has_capability(actor, Capability.PUBLISH_AUTHORITY):
        raise PermissionDenied("当前账户没有撤回或恢复知识页面的权限。")
    target_type, target = history_target(object_type, object_id, lock=True)
    if object_type == "scholar":
        Person.objects.select_for_update().get(pk=target.person_id)
    key = f"knowledge-history:{actor.pk}:{request_key}"
    intent = {"object_type": object_type, "object_id": str(object_id), "action": action, "version": expected_version,
              "source": str(source_revision_id) if source_revision_id else None, "reason": reason}
    digest = sha256(json.dumps(intent, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    # The original receipt takes precedence over today's version/draft. A lost
    # response must not create a second revision or publish the original one.
    existing = EditorialRevision.objects.filter(idempotency_key=key).first()
    if existing is not None:
        receipt = AuditEvent.objects.filter(action="knowledge_history_prepare", object_id=str(existing.pk), actor=actor).first()
        if not receipt or receipt.after.get("command_digest") != digest or existing.target_type != target_type or existing.target_id != target.pk:
            raise EditorialRevisionConflict("这个请求标识已用于另一项操作，请先核对原操作记录。")
        return _receipt(existing, object_type, object_id)
    if current_editorial_version(target_type, object_id) != expected_version:
        raise EditorialRevisionConflict("保存版本已变化，请重新读取并确认。")
    if EditorialRevision.objects.filter(target_type=target_type, target_id=object_id, status="draft").exists():
        raise EditorialRevisionConflict("已有未发布修改。请先处理原草稿，撤回或恢复不会覆盖它。")
    if object_type == "topic" and (target.curation or {}).get("topic_merge"):
        raise EditorialRevisionConflict("主题已合并，请在原合并记录中处理。")
    status_field = _status_field(target)
    if action == "withdraw":
        if getattr(target, status_field) != "published":
            raise EditorialRevisionConflict("当前对象没有可撤回的公开状态。")
        patch = {status_field: "archived"}
        note = "撤回公开页面：" + reason
    else:
        source = EditorialRevision.objects.filter(pk=source_revision_id, target_type=target_type, target_id=object_id, status="published").first()
        if source is None or source.materialized_preview.get(status_field) != "published":
            raise EditorialRevisionError("所选记录不是这个对象曾公开的内容版本。")
        # Only captured editable fields: never fabricate absent historical
        # fields or revive identities, other targets, private data or files.
        patch = {name: value for name, value in source.materialized_preview.items() if name in TARGET_POLICIES[target_type].editable_fields}
        if isinstance(target, KnowledgeNode) and patch.get("node_type", target.node_type) != target.node_type:
            raise EditorialRevisionError("历史内容属于另一种知识类型，请在知识对象编辑中先核对身份。")
        note = f"恢复第 {source.revision} 版：{reason}"
    revision = create_editorial_revision(target_type=target_type, target_id=object_id, patch=patch, actor=actor,
                                         idempotency_key=key, change_note=note)
    AuditEvent.objects.create(actor=actor, action="knowledge_history_prepare", object_type="catalog.EditorialRevision",
                              object_id=str(revision.pk), before={"edit_version": expected_version},
                              after={"command_digest": digest, "action": action, "source_revision_id": str(source_revision_id) if source_revision_id else None})
    return _receipt(revision, object_type, object_id)


def _receipt(revision, object_type, object_id):
    return {"revision_id": str(revision.pk), "revision": revision.revision, "status": revision.status,
            "object_type": object_type, "object_id": str(object_id),
            "edit_version": current_editorial_version(revision.target_type, object_id)}
