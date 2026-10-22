"""Small owner-only project summaries and actual durable turn states for PDF184."""
from django.db.models import DateTimeField, Exists, OuterRef, Subquery
from django.db.models.functions import Coalesce, Greatest
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from . import notebook, research
from .models import ResearchProject, ResearchTurn
from .reader_center import recent_progress_query


class ResearchDirectoryQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    scope = serializers.ChoiceField(choices=["active", "archived", "all"], default="active")


class ProjectSummary(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    title = serializers.CharField()
    question = serializers.CharField(allow_blank=True)
    archived = serializers.BooleanField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    activity_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    last_turn_id = serializers.UUIDField(allow_null=True)


class RecentReadingSummary(serializers.Serializer):
    title = serializers.CharField()
    current_page = serializers.IntegerField()
    page_count = serializers.IntegerField()
    reader_url = serializers.CharField()


class ResearchDirectoryOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    count = serializers.IntegerField()
    all_count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = ProjectSummary(many=True)
    recent_reading = RecentReadingSummary(allow_null=True)


def directory_rows(user):
    turns = ResearchTurn.objects.filter(project_id=OuterRef("pk"), project__user=user)
    latest = turns.order_by("-created_at", "-id")
    changed = turns.order_by("-updated_at", "-id")
    return ResearchProject.objects.filter(user=user).annotate(
        last_turn_id=Subquery(latest.values("id")[:1]), last_turn_status=Subquery(latest.values("status")[:1]),
        has_running=Exists(turns.filter(status="running")), has_queued=Exists(turns.filter(status="queued")),
        activity_at=Greatest("updated_at", Coalesce(Subquery(changed.values("updated_at")[:1], output_field=DateTimeField()), "updated_at")),
    ).order_by("-activity_at", "-id")


def summary(row):
    data = research.unpack(row)
    # Project itself has no execution status. Only its own durable turns can
    # justify running/completed; a saved project must not masquerade as complete.
    status = "running" if row.has_running else "queued" if row.has_queued else "archived" if row.archived else row.last_turn_status or "saved"
    label = {"archived": "已归档", "running": "处理中", "queued": "等待处理", "completed": "已完成", "partial": "部分完成",
        "failed": "处理失败", "canceled": "已取消", "saved": "已保存"}.get(status, "状态待核对")
    if row.archived and status in {"queued", "running"}:
        label = "已归档 · " + label
    return {"id": str(row.pk), "revision": row.revision, "title": str(data.get("title") or "未命名研究")[:180],
        "question": str(data.get("question") or "")[:400], "archived": row.archived, "status": status, "status_label": label,
        "activity_at": row.activity_at, "updated_at": row.updated_at, "last_turn_id": str(row.last_turn_id) if row.last_turn_id else None}


class DirectoryActions:
    @extend_schema(parameters=[ResearchDirectoryQuery], responses=ResearchDirectoryOutput)
    @action(detail=False, methods=["get"])
    def directory(self, request):
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前读者账户。")
        data = ResearchDirectoryQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        page, scope = data.validated_data["page"], data.validated_data["scope"]
        base = directory_rows(request.user)
        all_count = base.count()
        rows = base if scope == "all" else base.filter(archived=scope == "archived")
        count = rows.count()
        if page > 1 and (page - 1) * 20 >= count:
            raise NotFound("当前页没有研究，请返回第一页。")
        results = [summary(row) for row in rows[(page - 1) * 20:page * 20]]
        if len(results) != min(20, max(0, count - (page - 1) * 20)):
            raise research.ResearchConflict("研究目录在读取时发生变化，请重新读取。")
        latest = list(recent_progress_query(request.user)[:1])
        recent = None
        if latest:
            progress = latest[0]
            work = notebook.published_work(progress.asset.edition.work_id)
            if work["href"]:
                recent = {"title": work["title"], "current_page": progress.current_page, "page_count": progress.asset.page_count,
                    "reader_url": f"/reader/{progress.asset_id}?page={progress.current_page}"}
        return Response({"owner_id": str(request.user.pk), "count": count, "all_count": all_count, "page": page,
            "total_pages": max(1, (count + 19) // 20), "results": results, "recent_reading": recent})
