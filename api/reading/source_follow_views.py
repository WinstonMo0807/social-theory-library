from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from . import source_follow
from .research_views import PrivateResponses
from .source_models import SourceFollow
from catalog.media_views import PublicCoverMediaSerializer

OWNER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


def require_owner(request):
    if request.headers.get("X-Reader-Owner") != str(request.user.pk):
        raise PermissionDenied("请核对当前账户后再读取回执或保存操作。")


class PublicSourceStatus(serializers.Serializer):
    path = serializers.CharField(allow_blank=True)
    canonical_path = serializers.CharField(allow_blank=True)
    status = serializers.ChoiceField(choices=["available", "replaced", "unavailable", "page"])
    title = serializers.CharField()
    authors = serializers.ListField(child=serializers.CharField())
    cover_url = serializers.CharField(allow_blank=True)
    cover_media = PublicCoverMediaSerializer(allow_null=True, required=False)
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
    scholar_profile_id = serializers.UUIDField(allow_null=True)
    topic_id = serializers.UUIDField(allow_null=True)
    person_id = serializers.UUIDField(allow_null=True)
    public_revision = serializers.CharField(allow_blank=True)
    href = serializers.CharField(allow_blank=True)
    scope_notice = serializers.CharField(allow_blank=True)
    notice = serializers.CharField()


class SourceEventOutput(serializers.Serializer):
    id = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["subscribe", "unsubscribe", "mark_read", "changed", "delete"])
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
    scholar_profile_id = serializers.UUIDField(allow_null=True)
    topic_id = serializers.UUIDField(allow_null=True)
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


class SourceCommandInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not hasattr(data, "items") or set(data) - set(self.fields):
            raise serializers.ValidationError("操作包含不支持的字段。")
        if isinstance(data.get("expected_revision"), bool):
            raise serializers.ValidationError({"expected_revision": "修订号不能使用布尔值。"})
        return super().to_internal_value(data)


class SourceFollowCommand(SourceCommandInput):
    path = serializers.CharField(max_length=400)
    action = serializers.ChoiceField(choices=["subscribe", "unsubscribe", "mark_read"])
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=0)
    scholar_profile_id = serializers.UUIDField(required=False)
    topic_id = serializers.UUIDField(required=False)

    def validate(self, data):
        if data.get("scholar_profile_id") and data.get("topic_id"):
            raise serializers.ValidationError("一次关注只能指定一个公开对象。")
        return data


class SourceFollowDelete(SourceCommandInput):
    request_id = serializers.UUIDField()
    expected_revision = serializers.IntegerField(min_value=1)


class SourceCommandReceipt(serializers.Serializer):
    request_id = serializers.UUIDField()
    applied_revision = serializers.IntegerField(min_value=1)
    deleted = serializers.BooleanField()


class SourceCommandOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    record = SourceFollowOutput(allow_null=True)
    receipt = SourceCommandReceipt()


def positive(value):
    return serializers.IntegerField(min_value=1, max_value=100000).run_validation(value)


class PublicSourceStatusView(PrivateResponses, APIView):
    permission_classes = [AllowAny]

    @extend_schema(parameters=[OpenApiParameter("path", str), OpenApiParameter("scholar_profile_id", str), OpenApiParameter("topic_id", str)], responses=PublicSourceStatus)
    def get(self, request):
        profile = request.query_params.get("scholar_profile_id")
        if profile is not None:
            profile = serializers.UUIDField().run_validation(profile)
        topic = request.query_params.get("topic_id")
        if topic is not None:
            topic = serializers.UUIDField().run_validation(topic)
        if profile is not None and topic is not None:
            raise serializers.ValidationError("一次查询只能指定一个公开对象。")
        path = serializers.CharField(max_length=400, allow_blank=profile is not None or topic is not None).run_validation(request.query_params.get("path", ""))
        return Response(source_follow.resolve_public_source(path, scholar_profile_id=profile, topic_id=topic))


class SourceFollowsView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="reading_source_follows_list", parameters=[OpenApiParameter("path", str), OpenApiParameter("scholar_profile_id", str), OpenApiParameter("topic_id", str), OpenApiParameter("page", int)], responses=SourceFollowsPage)
    def get(self, request):
        page = positive(request.query_params.get("page", 1))
        if request.headers.get("X-Reader-Owner") is not None:
            require_owner(request)
        query = SourceFollow.objects.filter(user=request.user)
        if "scholar_profile_id" in request.query_params and "topic_id" in request.query_params:
            raise serializers.ValidationError("一次查询只能指定一个公开对象。")
        if "scholar_profile_id" in request.query_params:
            query = query.filter(scholar_profile_id=serializers.UUIDField().run_validation(request.query_params["scholar_profile_id"]))
        elif "topic_id" in request.query_params:
            query = query.filter(topic_id=serializers.UUIDField().run_validation(request.query_params["topic_id"]))
        elif "path" in request.query_params:
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
        parameters=[OWNER], responses=SourceCommandOutput)
    def post(self, request):
        require_owner(request)
        data = SourceFollowCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(source_follow.command(request.user, data.validated_data))


class SourceFollowDetailView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("history_page", int)], responses=SourceFollowOutput)
    def get(self, request, pk):
        if request.headers.get("X-Reader-Owner") is not None:
            require_owner(request)
        row = source_follow.refresh(pk, request.user.pk)
        if row is None:
            raise NotFound("本人来源关注记录不存在。")
        return Response(source_follow.output(row, history_page=positive(request.query_params.get("history_page", 1))))

    @extend_schema(parameters=[OWNER], request=SourceFollowDelete, responses=SourceCommandOutput)
    def delete(self, request, pk):
        require_owner(request)
        data = SourceFollowDelete(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(source_follow.delete_follow(request.user, pk, data.validated_data))


class SourceFollowReceiptView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True)], responses=SourceCommandOutput)
    def get(self, request):
        require_owner(request)
        return Response(source_follow.by_request(request.user, request.query_params.get("request_id")))
