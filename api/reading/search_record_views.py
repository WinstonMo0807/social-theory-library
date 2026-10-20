"""Read-only opt-in query history, using the existing encrypted private record."""
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from . import privacy, research
from .models import ReaderSearchRecord
from .research_views import PrivateResponses


class SearchRecordOutput(serializers.Serializer):
    id = serializers.UUIDField()
    query = serializers.CharField()
    filters = serializers.JSONField()
    created_at = serializers.DateTimeField()


class SearchRecordsPage(serializers.Serializer):
    owner_id = serializers.CharField()
    recording_enabled = serializers.BooleanField()
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = SearchRecordOutput(many=True)
    notice = serializers.CharField()


class ReaderSearchRecordsView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("owner_id", str, required=True), OpenApiParameter("page", int), OpenApiParameter("page_size", int)], responses=SearchRecordsPage)
    def get(self, request):
        if request.query_params.get("owner_id") != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取当前账户的资料。")
        page = serializers.IntegerField(min_value=1, max_value=100000).run_validation(request.query_params.get("page", 1))
        page_size = serializers.IntegerField(min_value=1, max_value=20).run_validation(request.query_params.get("page_size", 3))
        records = ReaderSearchRecord.objects.filter(user=request.user).order_by("-created_at", "-id")
        result = []
        for row in records[(page - 1) * page_size:page * page_size]:
            content = research.unpack(row)
            result.append({"id": str(row.pk), "query": content.get("query", ""), "filters": content.get("filters", {}), "created_at": row.created_at})
        return Response({"owner_id": str(request.user.pk), "recording_enabled": privacy.retention_enabled(request.user, "search_history"),
            "count": records.count(), "page": page, "page_size": page_size, "results": result,
            "notice": "仅显示本人主动开启保存后留下的检索记录。关闭保存不删除已有记录，可在隐私与资料中删除。"})
