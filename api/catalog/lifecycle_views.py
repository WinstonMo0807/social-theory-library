from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from uuid import UUID

from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from accounts.models import User
from .editorial_read import AdminPrivateResponseMixin

from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from common.recycle import RECYCLE_MODELS
from ingestion.models import AuditEvent

from .models import (
    CanonicalObjectRevision,
    Discipline,
    EditorialRevision,
    KnowledgeNode,
    ReadingPath,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    Work, Edition, Person, PublisherAuthority, TheoryTimelineEvent, KnowledgeRelation,
    EvidenceCuration, ScholarRelation, RecommendationIssue, RecommendationIssueItem, AboutPageBlock,
)
from ingestion.models import UploadItem
from .services.canonical_mutations import record_admin_canonical_change
from .services.editorial_revision import (
    EditorialRevisionError,
    create_editorial_revision,
    editorial_idempotency_key,
    serialize_editorial_revision,
)
from .services.knowledge_nodes import record_node_version


@dataclass(frozen=True)
class LifecycleConfig:
    model: type
    name_field: str
    status_field: str
    published_value: str = "published"
    archived_value: str = "archived"
    draft_value: str = "draft"


LIFECYCLE_MODELS = {
    "discipline": LifecycleConfig(Discipline, "name", "editorial_status"),
    "subdiscipline": LifecycleConfig(Subdiscipline, "name", "editorial_status"),
    "theory-school": LifecycleConfig(TheorySchool, "name", "editorial_status"),
    "topic": LifecycleConfig(Topic, "name", "editorial_status"),
    "scholar": LifecycleConfig(ScholarProfile, "person__preferred_name", "editorial_status"),
    "knowledge-node": LifecycleConfig(KnowledgeNode, "canonical_name_zh", "status"),
    "reading-path": LifecycleConfig(ReadingPath, "title", "status"),
    "work": LifecycleConfig(Work, "title", ""),
    "edition": LifecycleConfig(Edition, "work__title", ""),
    "upload": LifecycleConfig(UploadItem, "source_filename", ""),
    "person": LifecycleConfig(Person, "preferred_name", ""),
    "publisher": LifecycleConfig(PublisherAuthority, "canonical_name", ""),
    "timeline-event": LifecycleConfig(TheoryTimelineEvent, "title", "review_status", published_value="approved", archived_value="rejected", draft_value="suggested"),
    "knowledge-relation": LifecycleConfig(KnowledgeRelation, "id", "status"),
    "evidence-curation": LifecycleConfig(EvidenceCuration, "id", ""),
    "scholar-relation": LifecycleConfig(ScholarRelation, "id", ""),
    "recommendation-issue": LifecycleConfig(RecommendationIssue, "title", ""),
    "recommendation-item": LifecycleConfig(RecommendationIssueItem, "id", ""),
    "about-block": LifecycleConfig(AboutPageBlock, "title", ""),
}

CANONICAL_OBJECT_TYPES = {
    "discipline": "discipline",
    "subdiscipline": "subdiscipline",
    "theory-school": "theory_school",
    "topic": "topic",
    "scholar": "scholar_profile",
    "knowledge-node": "knowledge_node",
    "reading-path": "reading_path",
    "timeline-event": "timeline_event",
    "knowledge-relation": "knowledge_relation",
}

EDITORIAL_LIFECYCLE_TARGETS = {
    "discipline": EditorialRevision.TargetType.DISCIPLINE,
    "subdiscipline": EditorialRevision.TargetType.SUBDISCIPLINE,
    "topic": EditorialRevision.TargetType.TOPIC,
    "scholar": EditorialRevision.TargetType.SCHOLAR_PROFILE,
    "knowledge-node": EditorialRevision.TargetType.KNOWLEDGE_NODE,
    "reading-path": EditorialRevision.TargetType.READING_PATH,
    "timeline-event": "timeline_event",
    "knowledge-relation": "knowledge_relation",
}


def _config(kind: str) -> LifecycleConfig | None:
    return LIFECYCLE_MODELS.get(kind)


def _name(obj, field: str) -> str:
    value = obj
    for part in field.split("__"):
        value = getattr(value, part)
    return str(value)


def _dependency_rows(obj) -> list[dict]:
    rows: list[dict] = []
    catalog_links = {
        "catalog.personnoderelation": "人物与知识条目关系", "catalog.worknoderelation": "作品与知识条目关系",
        "catalog.evidencesnippet": "原文证据片段", "catalog.timelineeventrelation": "时间线对象关联",
        "catalog.readingpathitem": "阅读路径条目", "catalog.persontopicrelation": "人物与主题关系",
        "catalog.personsubdisciplinerelation": "人物与子学科关系", "catalog.persondisciplinerelation": "人物与学科关系",
        "catalog.knowledgerelation": "知识条目关系", "catalog.scholarrelation": "学者关系",
    }
    for relation in obj._meta.related_objects:
        # Lifecycle previews show catalog structure, never per-reader data counts.
        model_key = relation.related_model._meta.label_lower
        if model_key not in RECYCLE_MODELS | set(catalog_links) | {"catalog.asset", "catalog.contribution", "catalog.publicationrevision", "catalog.editorialrevision"}:
            continue
        accessor = relation.get_accessor_name()
        if not accessor:
            continue
        try:
            related = getattr(obj, accessor)
        except relation.related_model.DoesNotExist:
            count = 0
        else:
            count = related.count() if hasattr(related, "count") else int(related is not None)
        if not count:
            continue
        label = catalog_links.get(model_key, str(relation.related_model._meta.verbose_name_plural))
        if model_key in {"catalog.knowledgerelation", "catalog.scholarrelation"}:
            label += "（作为来源）" if relation.field.name.startswith("source_") else "（作为目标）" if relation.field.name.startswith("target_") else ""
        rows.append(
            {
                "key": model_key, "accessor": accessor,
                "label": label,
                "count": count,
                "delete_rule": getattr(relation.on_delete, "__name__", "unknown"),
            }
        )

    if isinstance(obj, ScholarProfile):
        for accessor, label in (("node_relations", "人物与知识条目关系"), ("topic_relations", "人物与主题关系"),
                                ("subdiscipline_relations", "人物与子学科关系"), ("discipline_relations", "人物与学科关系")):
            related = getattr(obj.person, accessor)
            count = related.count()
            if count:
                rows.append({"key": related.model._meta.label_lower, "accessor": f"person.{accessor}",
                    "label": label, "count": count, "delete_rule": "INDIRECT"})
        contribution_count = obj.person.contributions.count()
        if contribution_count:
            rows.append(
                {
                    "key": "catalog.contribution",
                    "accessor": "person.contributions",
                    "label": "馆藏作者、编者、译者或研究对象关系",
                    "count": contribution_count,
                    "delete_rule": "INDIRECT",
                }
            )
    return sorted(rows, key=lambda row: (-row["count"], row["label"]))


def lifecycle_snapshot(kind: str, obj, config: LifecycleConfig) -> dict:
    status_value = getattr(obj, config.status_field, "")
    dependencies = _dependency_rows(obj)
    merged_topic = isinstance(obj, Topic) and bool((obj.curation or {}).get("topic_merge"))
    return {
        "kind": kind,
        "id": str(obj.pk),
        "name": _name(obj, config.name_field),
        "status": status_value,
        "is_public": status_value == config.published_value,
        "dependencies": dependencies,
        "dependency_count": sum(row["count"] for row in dependencies),
        "actions": {
            "archive": bool(config.status_field) and status_value != config.archived_value,
            "restore": bool(config.status_field) and status_value == config.archived_value and not merged_topic,
            "delete": not merged_topic,
        },
        "guidance": (
            "删除后移入回收站，保留原文件、历史和关联记录；恢复后需重新检查并发布。下架仅撤下公开展示，条目仍留在管理列表。"
        ),
    }


def _draft_public_withdrawal(*, request, kind: str, obj, config: LifecycleConfig):
    target_type = EDITORIAL_LIFECYCLE_TARGETS[kind]
    patch = {config.status_field: config.archived_value}
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=target_type,
            object_id=obj.id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    return create_editorial_revision(
        target_type=target_type,
        target_id=obj.id,
        patch=patch,
        actor=request.user,
        idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
        or editorial_idempotency_key(
            target_type=target_type,
            target_id=obj.id,
            base_revision=current_revision,
            patch=patch,
        ),
        change_note=f"下线已发布{_name(obj, config.name_field)}",
    )


class AdminEntityLifecycleView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    def _object(self, kind, pk):
        config = _config(kind)
        if config is None:
            return None, None
        queryset = config.model.objects.all()
        if kind == "scholar":
            queryset = queryset.select_related("person")
        obj = get_object_or_404(queryset, pk=pk)
        from .services.curation_projects import protect_related_object
        protect_related_object(obj, self.request.user)
        return config, obj

    def get(self, request, kind, pk):
        config, obj = self._object(kind, pk)
        if config is None:
            return Response({"detail": "不支持的实体类型。"}, status=404)
        return Response(lifecycle_snapshot(kind, obj, config))

    @transaction.atomic
    def post(self, request, kind, pk):
        actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
        if not actor or actor.token_version != request.user.token_version:
            raise PermissionDenied("账户会话已经变化，请重新登录后操作。")
        request.user = actor
        if kind == "knowledge-relation":
            from catalog.academic_relation_views import relation_response
            if request.data.get("action") not in {"archive", "delete"}:
                return Response({"detail": "历史关系通过知识编纂修订，不直接恢复旧正式行。", "workspace_url": "/admin/knowledge?relations=1"}, status=409)
            return relation_response(request, "node", values={**request.data, "operation": "withdraw"}, legacy_id=pk)
        delete_key, delete_fingerprint = "", ""
        if request.data.get("action") == "delete" and request.headers.get("Idempotency-Key"):
            if not has_capability(actor, Capability.EDIT_METADATA):
                raise PermissionDenied("当前账户没有移入回收站的权限。")
            try:
                delete_key = str(UUID(request.headers["Idempotency-Key"]))
            except (ValueError, TypeError):
                raise ValidationError("删除请求编号无效。")
            from .services.query_lexicon.mutations import acquire_entity_lock
            acquire_entity_lock("lifecycle_delete", delete_key)
            delete_fingerprint = sha256(json.dumps({"kind":kind,"id":str(pk),"reason":request.data.get("reason",""),
                "confirmed":request.data.get("confirmed"),"confirmation":request.data.get("confirmation","")},sort_keys=True).encode()).hexdigest()
            receipt = AuditEvent.objects.filter(action="lifecycle_delete_confirmed",request_id=delete_key).first()
            if receipt:
                if receipt.actor_id != actor.pk or receipt.after.get("fingerprint") != delete_fingerprint:
                    return Response({"detail":"该请求编号对应不同的删除操作。"},status=409)
                return Response(receipt.after["result"])
        config, obj = self._object(kind, pk)
        if config is None:
            return Response({"detail": "不支持的实体类型。"}, status=404)

        action = str(request.data.get("action", "")).strip()
        snapshot = lifecycle_snapshot(kind, obj, config)
        before = {"status": snapshot["status"], "name": snapshot["name"]}

        if isinstance(obj, Topic) and (obj.curation or {}).get("topic_merge"):
            return Response({"detail": "该主题已合并，保留原记录供审计。请编辑合并后的主题。", "code": "merged_topic_read_only", "impact": snapshot}, status=409)

        if kind == "theory-school" and action == "restore":
            return Response(
                {
                    "detail": (
                        "TheorySchool 已进入迁移兼容期，只允许下线。"
                        "恢复或删除须在规范映射完成后的专用迁移中执行。"
                    ),
                    "code": "legacy_theory_school_read_only",
                    "impact": snapshot,
                },
                status=409,
            )

        if action in {"archive", "restore"}:
            if kind == "timeline-event" and obj.merged_into_id:
                return Response({"detail": "此事件已归并，请从原归并记录核对回退。"}, status=409)
            if not config.status_field:
                return Response({"detail": "请通过此内容的发布控制进行下架。"}, status=400)
            if not has_capability(request.user, Capability.PUBLISH_AUTHORITY):
                return Response({"detail": "只有管理员可以下线或恢复公开实体。"}, status=403)
            if action == "restore":
                from .services.recycle import restore_archived_object
                obj = restore_archived_object(kind, obj, actor=request.user)
                return Response(lifecycle_snapshot(kind, obj, config))
            if (
                action == "archive"
                and snapshot["is_public"]
                and kind in EDITORIAL_LIFECYCLE_TARGETS
            ):
                try:
                    revision = _draft_public_withdrawal(
                        request=request,
                        kind=kind,
                        obj=obj,
                        config=config,
                    )
                except EditorialRevisionError as error:
                    return Response(
                        {"detail": str(error), "code": "editorial_revision_error"},
                        status=400,
                    )
                return Response(
                    {
                        "detail": "已建立下线草稿，正式内容尚未改变。",
                        "impact": snapshot,
                        "editorial_revision": serialize_editorial_revision(revision),
                    },
                    status=202,
                )
            next_status = config.archived_value if action == "archive" else config.draft_value
            setattr(obj, config.status_field, next_status)
            update_fields = [config.status_field, "updated_at"]
            if hasattr(obj, "published_at"):
                obj.published_at = None
                update_fields.append("published_at")
            obj.save(update_fields=update_fields)
            if isinstance(obj, KnowledgeNode):
                record_node_version(
                    obj,
                    request.user,
                    "管理员下线节点" if action == "archive" else "管理员恢复节点为草稿",
                )
            AuditEvent.objects.create(
                actor=request.user,
                action=f"entity_{action}",
                object_type=obj._meta.label,
                object_id=str(obj.pk),
                before=before,
                after={"status": next_status, "name": snapshot["name"]},
            )
            record_admin_canonical_change(
                object_type=CANONICAL_OBJECT_TYPES[kind],
                target=obj,
                change_kind="withdraw" if action == "archive" else "update",
                changed_fields=[config.status_field, "published_at"],
                actor=request.user,
                request_idempotency_key=request.headers.get(
                    "Idempotency-Key", ""
                ),
            )
            return Response(lifecycle_snapshot(kind, obj, config))

        if action == "delete":
            legacy_confirmation = str(request.data.get("confirmation", "")).strip()
            confirmed = request.data.get("confirmed") is True or legacy_confirmation == snapshot["name"]
            if not confirmed:
                return Response(
                    {"confirmed": ["请确认移入回收站。"], "impact": snapshot},
                    status=400,
                )
            from .services.recycle import recycle_object
            reason = request.data.get("reason", "")
            if not isinstance(reason, str) or len(reason) > 500:
                return Response({"reason": ["操作原因须为500字以内的文字。"]}, status=400)
            entry = recycle_object(obj, actor=request.user, kind=kind, name=snapshot["name"], reason=reason)
            result = {"deleted": True, "recoverable": True, "recycle_id": str(entry.pk)}
            if delete_key:
                AuditEvent.objects.create(actor=actor,action="lifecycle_delete_confirmed",object_type=obj._meta.label_lower,
                    object_id=str(obj.pk),request_id=delete_key,after={"fingerprint":delete_fingerprint,"result":result})
            return Response(result)

        return Response({"action": ["请选择 archive、restore 或 delete。"]}, status=400)
