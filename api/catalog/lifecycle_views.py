from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db.models.deletion import ProtectedError, RestrictedError
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryStaff
from ingestion.models import AuditEvent

from .models import (
    Discipline,
    KnowledgeNode,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
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
    for relation in obj._meta.related_objects:
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
        rows.append(
            {
                "key": relation.related_model._meta.label_lower,
                "label": str(relation.related_model._meta.verbose_name_plural),
                "count": count,
                "delete_rule": getattr(relation.on_delete, "__name__", "unknown"),
            }
        )

    if isinstance(obj, ScholarProfile):
        contribution_count = obj.person.contributions.count()
        if contribution_count:
            rows.append(
                {
                    "key": "catalog.contribution",
                    "label": "馆藏作者、编者、译者或研究对象关系",
                    "count": contribution_count,
                    "delete_rule": "PROTECT",
                }
            )
    return sorted(rows, key=lambda row: (-row["count"], row["label"]))


def lifecycle_snapshot(kind: str, obj, config: LifecycleConfig) -> dict:
    status_value = getattr(obj, config.status_field)
    dependencies = _dependency_rows(obj)
    return {
        "kind": kind,
        "id": str(obj.pk),
        "name": _name(obj, config.name_field),
        "status": status_value,
        "is_public": status_value == config.published_value,
        "dependencies": dependencies,
        "dependency_count": sum(row["count"] for row in dependencies),
        "actions": {
            "archive": status_value != config.archived_value,
            "restore": status_value == config.archived_value,
            "delete": status_value != config.published_value,
        },
        "guidance": (
            "公开内容应先下线。永久删除会同时删除可级联的关系记录，受保护的馆藏关系会阻止删除。"
        ),
    }


class AdminEntityLifecycleView(APIView):
    permission_classes = [IsLibraryStaff]

    def _object(self, kind, pk):
        config = _config(kind)
        if config is None:
            return None, None
        queryset = config.model.objects.all()
        if kind == "scholar":
            queryset = queryset.select_related("person")
        return config, get_object_or_404(queryset, pk=pk)

    def get(self, request, kind, pk):
        config, obj = self._object(kind, pk)
        if config is None:
            return Response({"detail": "不支持的实体类型。"}, status=404)
        return Response(lifecycle_snapshot(kind, obj, config))

    @transaction.atomic
    def post(self, request, kind, pk):
        config, obj = self._object(kind, pk)
        if config is None:
            return Response({"detail": "不支持的实体类型。"}, status=404)

        action = str(request.data.get("action", "")).strip()
        snapshot = lifecycle_snapshot(kind, obj, config)
        before = {"status": snapshot["status"], "name": snapshot["name"]}

        if action in {"archive", "restore"}:
            if request.user.role != "admin":
                return Response({"detail": "只有管理员可以下线或恢复公开实体。"}, status=403)
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
            return Response(lifecycle_snapshot(kind, obj, config))

        if action == "delete":
            if request.user.role != "admin":
                return Response({"detail": "只有管理员可以永久删除实体。"}, status=403)
            if snapshot["is_public"]:
                return Response({"detail": "公开实体必须先下线，再执行永久删除。", "impact": snapshot}, status=409)
            legacy_confirmation = str(request.data.get("confirmation", "")).strip()
            confirmed = request.data.get("confirmed") is True or legacy_confirmation == snapshot["name"]
            if not confirmed:
                return Response(
                    {"confirmed": ["请在影响范围确认框中确认永久删除。"], "impact": snapshot},
                    status=400,
                )
            object_id = str(obj.pk)
            model_label = obj._meta.label
            try:
                obj.delete()
            except (ProtectedError, RestrictedError) as exc:
                blocked_objects = getattr(
                    exc,
                    "protected_objects",
                    getattr(exc, "restricted_objects", []),
                )
                protected = sorted({item._meta.verbose_name for item in blocked_objects})
                return Response(
                    {
                        "detail": "该实体仍被受保护的数据引用，不能永久删除。请先调整这些关系，或保留下线状态。",
                        "protected": protected,
                        "impact": snapshot,
                    },
                    status=409,
                )
            AuditEvent.objects.create(
                actor=request.user,
                action="entity_delete",
                object_type=model_label,
                object_id=object_id,
                before={**before, "impact": snapshot["dependencies"]},
                after={"deleted": True},
            )
            return Response(status=204)

        return Response({"action": ["请选择 archive、restore 或 delete。"]}, status=400)
