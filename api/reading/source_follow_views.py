from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from . import source_follow
from .research_views import PrivateResponses
from .source_models import SourceFollow


class PublicSourceStatus(serializers.Serializer):
    path = serializers.CharField(allow_blank=True)
    canonical_path = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["available", "replaced", "unavailable", "page"])
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    cover_url = serializers.CharField(allow_blank=True)
    source_type = serializers.CharField(allow_blank=True)
    version_label = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    checked_at = serializers.DateTimeField()
    can_subscribe = serializers.BooleanField()
    reader_url = serializers.CharField(allow_blank=True)
    work_id = serializers.UUIDField(allow_null=True)
    edition_id = serializers.UUIDField(allow_null=True)
    asset_id = serializers.UUIDField(allow_null=True)
    catalog_revision_id = serializers.UUIDField(allow_null=True)
    document_revision_id = serializers.UUIDField(allow_null=True)
    notice = serializers.CharField()


class SourceEventOutput(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["subscribe", "unsubscribe", "mark_read", "changed"])
    before_status = serializers.CharField(allow_blank=True)
    after_status = serializers.CharField(allow_blank=True)
    observed_at = serializers.DateTimeField()
    revision = serializers.IntegerField()


class SourceHistoryOutput(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    results = SourceEventOutput(many=True)


class SourceFollowOutput(serializers.Serializer):
    id = serializers.UUIDField()
    owner_id = serializers.CharField()
    path = serializers.CharField()
    active = serializers.BooleanField()
    revision = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    last_checked_at = serializers.DateTimeField(allow_null=True)
    check_error = serializers.CharField(allow_blank=True)
    unread_count = serializers.IntegerField()
    updates_paused = serializers.BooleanField()
    source = PublicSourceStatus()
    notice = serializers.CharField()
    history = SourceHistoryOutput()


class SourceFollowsPage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    owner_id = serializers.CharField()
    results = SourceFollowOutput(many=True)
    notice = serializers.CharField()


class SourceFollowCommand(serializers.Serializer):
    path = serializers.CharField(max_length=400)
    action = serializers.ChoiceField(choices=["subscribe", "unsubscribe", "mark_read"])
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=0)


def positive(value):
    return serializers.IntegerField(min_value=1, max_value=100000).run_validation(value)


class PublicSourceStatusView(PrivateResponses, APIView):
    permission_classes = [AllowAny]

    @extend_schema(parameters=[OpenApiParameter("path", str, required=True)], responses=PublicSourceStatus)
    def get(self, request):
        path = serializers.CharField(max_length=400).run_validation(request.query_params.get("path"))
        return Response(source_follow.resolve_public_source(path))


class SourceFollowsView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="reading_source_follows_list", parameters=[OpenApiParameter("path", str), OpenApiParameter("page", int)], responses=SourceFollowsPage)
    def get(self, request):
        page = positive(request.query_params.get("page", 1))
        query = SourceFollow.objects.filter(user=request.user)
        if "path" in request.query_params:
            raw = serializers.CharField(max_length=400).run_validation(request.query_params["path"])
            query = query.filter(path=source_follow.canonical_path(raw))
        count = query.count()
        records = list(query[(page - 1) * source_follow.PAGE_SIZE:page * source_follow.PAGE_SIZE])
        results = []
        for row in records:
            current = source_follow.refresh(row.pk, request.user.pk)
            if current:
                results.append(source_follow.output(current))
        return Response({"owner_id": str(request.user.pk), "count": count, "page": page,
            "page_size": source_follow.PAGE_SIZE, "results": results, "notice": source_follow.NOTICE})

    @extend_schema(request=SourceFollowCommand,
        parameters=[OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)],
        responses=SourceFollowOutput)
    def post(self, request):
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取当前账户资料；本次操作尚未保存。")
        data = SourceFollowCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(source_follow.command(request.user, data.validated_data))


class SourceFollowDetailView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("history_page", int)], responses=SourceFollowOutput)
    def get(self, request, pk):
        row = source_follow.refresh(pk, request.user.pk)
        if row is None:
            raise NotFound("本人来源关注记录不存在。")
        return Response(source_follow.output(row, history_page=positive(request.query_params.get("history_page", 1))))
