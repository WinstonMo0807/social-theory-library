from django.db.models import Count
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from mimetypes import guess_type
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from common.permissions import IsLibraryStaff
from .models import RecycleEntry
from .services.recycle import require_editor, restore_object, restore_objects
from .services.recycle_preview import recycle_entry_data, recycle_preview_payload
from .services.recycle_display import recycle_display_data, retained_display_source
from .editorial_read import AdminPrivateResponseMixin


class RecycleEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    name = serializers.CharField()
    deleted_at = serializers.DateTimeField()
    reason = serializers.CharField(allow_blank=True, max_length=300)


class RecycleDisplayEntrySerializer(RecycleEntrySerializer):
    thumbnail_url = serializers.CharField(allow_blank=True)
    subtitle = serializers.CharField(allow_blank=True)
    display_warning = serializers.CharField(allow_blank=True)


class RecycleCollectionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    total_count = serializers.IntegerField()
    kind_counts = serializers.DictField(child=serializers.IntegerField())
    results = RecycleDisplayEntrySerializer(many=True)


class RecycleRestoreRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    ids = serializers.ListField(child=serializers.UUIDField(), min_length=1, max_length=50, required=False)

    def validate(self, data):
        if ("id" in data) == ("ids" in data):
            raise serializers.ValidationError("请选择一条记录或最多50条记录恢复。")
        if "ids" in data and len(data["ids"]) != len(set(data["ids"])):
            raise serializers.ValidationError("不能重复选择同一条记录。")
        return data


class RecycleRestoreResultSerializer(serializers.Serializer):
    restored = serializers.BooleanField()
    kind = serializers.CharField(required=False)
    id = serializers.UUIDField(required=False)
    count = serializers.IntegerField(required=False)
    results = serializers.ListField(child=serializers.DictField(), required=False)
    detail = serializers.CharField()


class RecyclePreviewSerializer(serializers.Serializer):
    entry = RecycleEntrySerializer()
    can_restore = serializers.BooleanField()
    blocked_reason = serializers.CharField(allow_blank=True)
    preview_kind = serializers.ChoiceField(choices=["work", "knowledge", "issue", "record"])
    preview = serializers.JSONField()
    detail = serializers.CharField()


class AdminRecycleView(APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=RecycleCollectionSerializer, parameters=[
        OpenApiParameter("search", str, description="按已删除内容名称筛选"),
        OpenApiParameter("kind", str, description="逗号分隔的回收内容类型"),
        OpenApiParameter("offset", int, description="50条分页的起始偏移"),
    ])
    def get(self, request):
        require_editor(request.user)
        active = RecycleEntry.objects.filter(restored_at__isnull=True)
        counts = dict(active.values("kind").annotate(total=Count("pk")).values_list("kind", "total"))
        rows = active.order_by("-updated_at", "id")
        search = str(request.query_params.get("search", ""))[:200]
        if search:
            rows = rows.filter(name__icontains=search)
        kinds = [value for value in str(request.query_params.get("kind", "")).split(",") if value]
        if kinds:
            rows = rows.filter(kind__in=kinds)
        try:
            offset = max(0, int(request.query_params.get("offset", 0)))
        except (ValueError, TypeError):
            offset = 0
        return Response({"count": rows.count(), "total_count": sum(counts.values()), "kind_counts": counts,
                         "results": [recycle_display_data(row) for row in rows[offset:offset+50]]},
                        headers={"Cache-Control": "private, no-store"})

    @extend_schema(request=RecycleRestoreRequestSerializer, responses=RecycleRestoreResultSerializer)
    def post(self, request):
        require_editor(request.user)
        serializer = RecycleRestoreRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        detail = "已恢复到管理列表。尚未重新发布或启动处理。"
        if "id" in data:
            entry = get_object_or_404(RecycleEntry, pk=data["id"])
            restore_object(entry.pk, actor=request.user)
            result = {"restored": True, "kind": entry.kind, "id": str(entry.object_id), "detail": detail}
        else:
            entries = restore_objects(data["ids"], actor=request.user)
            result = {"restored": True, "count": len(entries), "detail": detail,
                      "results": [{"kind": row.kind, "id": str(row.object_id)} for row in entries]}
        return Response(result, headers={"Cache-Control": "private, no-store"})


class AdminRecyclePreviewView(APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses=RecyclePreviewSerializer)
    def get(self, request, entry_id):
        require_editor(request.user)
        entry = get_object_or_404(RecycleEntry, pk=entry_id, restored_at__isnull=True)
        return Response(recycle_preview_payload(entry, actor=request.user, request=request),
                        headers={"Cache-Control": "private, no-store"})


class AdminRecycleImageView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(responses={(200, kind): OpenApiTypes.BINARY for kind in ("image/png", "image/jpeg", "image/webp", "image/avif")})
    def get(self, request, entry_id):
        require_editor(request.user)
        entry = get_object_or_404(RecycleEntry, pk=entry_id, restored_at__isnull=True)
        image, _, _ = retained_display_source(entry)
        if not image:
            raise Http404("没有保存图片。")
        content_type = guess_type(image.name)[0]
        if content_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
            raise Http404("保留文件不是可预览的图片。")
        try:
            source = image.open("rb")
        except FileNotFoundError:
            raise Http404("保留图片文件无法读取。")
        return FileResponse(source, content_type=content_type)
