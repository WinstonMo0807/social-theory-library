from django.utils.cache import patch_vary_headers
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.services.discovery_sessions import (
    cancel_session, create_session, expand_session, get_session, normalize_filters,
    serialize_session, session_access,
)


class DiscoveryCreateSerializer(serializers.Serializer):
    q = serializers.CharField(min_length=2, max_length=1200)
    filters = serializers.DictField(required=False, default=dict)


class DiscoveryWorkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField(required=False)


class DiscoveryPassageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    excerpt = serializers.CharField()
    work = DiscoveryWorkSerializer()
    authors = serializers.ListField(child=serializers.CharField())
    asset_id = serializers.UUIDField()
    edition_id = serializers.UUIDField(required=False)
    document_revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField()
    printed_page = serializers.CharField(required=False)
    source_kind = serializers.CharField()
    source_revision = serializers.CharField()
    reader_url = serializers.CharField()
    locator_precision = serializers.CharField()
    context_reference = serializers.CharField()
    match_basis = serializers.ListField(child=serializers.CharField())


class DiscoveryEntitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    url = serializers.CharField()
    excerpt = serializers.CharField()
    portrait_url = serializers.CharField(required=False)
    match_basis = serializers.ListField(child=serializers.CharField())


class DiscoveryCurationSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    source_title = serializers.CharField()
    source_kind = serializers.CharField()
    recommendation_excerpt = serializers.CharField()
    url = serializers.CharField()
    linked_work_ids = serializers.ListField(child=serializers.UUIDField(), required=False)
    match_basis = serializers.ListField(child=serializers.CharField())


class DiscoveryWarningSerializer(serializers.Serializer):
    code = serializers.CharField()
    message = serializers.CharField()
    channel = serializers.CharField(required=False)


class DiscoveryResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    query = serializers.CharField()
    status = serializers.CharField(help_text="queued, running, partial, completed, failed or canceled")
    access_token = serializers.CharField(required=False)
    passages = DiscoveryPassageSerializer(many=True)
    entities = DiscoveryEntitySerializer(many=True)
    curation = DiscoveryCurationSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
    can_expand = serializers.BooleanField()
    warnings = DiscoveryWarningSerializer(many=True)
    coverage_summary = serializers.DictField()
    completed_channels = serializers.ListField(child=serializers.CharField())
    channels = serializers.DictField()
    counts = serializers.DictField()
    source_changed = serializers.BooleanField()
    expansion_count = serializers.IntegerField()
    generation = serializers.IntegerField()
    mode = serializers.CharField()
    original_query = serializers.CharField()
    filters = serializers.DictField()
    count = serializers.IntegerField()
    corpus_version = serializers.CharField()
    knowledge_version = serializers.CharField()
    pipeline_version = serializers.CharField()
    poll_after_ms = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
    notice = serializers.CharField()
    status_url = serializers.CharField(required=False)


class DiscoveryContextSerializer(serializers.Serializer):
    result_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    asset_id = serializers.UUIDField()
    excerpt = serializers.CharField()
    blocks = serializers.ListField(child=serializers.DictField())
    before = serializers.CharField()
    after = serializers.CharField()
    reader_url = serializers.CharField()
    locator_precision = serializers.CharField()
    source_kind = serializers.CharField()
    notice = serializers.CharField()


SESSION_TOKEN = OpenApiParameter("X-Discovery-Token", str, OpenApiParameter.HEADER,
                                description="Anonymous search capability returned once at creation; do not put in URLs.")


class DiscoveryView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        if self.request.method == "POST" or isinstance(self, LegacyDiscoverySearchView):
            self.throttle_scope = "semantic_search_user" if self.request.user.is_authenticated else "semantic_search_anon"
        return super().get_throttles()

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ["Authorization", "Cookie", "X-Discovery-Token"])
        return response

    def payload(self, request, session):
        try:
            limit = int(request.query_params.get("limit", 3))
        except (TypeError, ValueError):
            raise ValidationError({"limit": "每页数量必须为整数。"})
        return serialize_session(session, session_access(session, request),
                                 cursor=request.query_params.get("cursor", ""), limit=limit)


class DiscoverySearchView(DiscoveryView):
    @extend_schema(request=DiscoveryCreateSerializer, responses={202: DiscoveryResponseSerializer})
    def post(self, request):
        serializer = DiscoveryCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        session, token = create_session(request, data["q"], normalize_filters(data["filters"]))
        payload = self.payload(request, session)
        payload["access_token"] = token
        payload["status_url"] = f"/api/catalog/discovery-search/{session.id}/"
        return Response(payload, status=202, headers={"Location": payload["status_url"]})


class DiscoverySearchDetailView(DiscoveryView):
    @extend_schema(parameters=[SESSION_TOKEN, OpenApiParameter("cursor", str), OpenApiParameter("limit", int)],
                   responses=DiscoveryResponseSerializer)
    def get(self, request, session_id):
        return Response(self.payload(request, get_session(request, session_id)))


class DiscoverySearchExpandView(DiscoveryView):
    @extend_schema(parameters=[SESSION_TOKEN], request=None, responses={202: DiscoveryResponseSerializer})
    def post(self, request, session_id):
        current = get_session(request, session_id)
        session = expand_session(current, session_access(current, request))
        return Response(self.payload(request, session), status=202)


class DiscoverySearchCancelView(DiscoveryView):
    @extend_schema(parameters=[SESSION_TOKEN], request=None, responses=DiscoveryResponseSerializer)
    def post(self, request, session_id):
        session = cancel_session(get_session(request, session_id))
        return Response(self.payload(request, session))


class DiscoverySearchContextView(DiscoveryView):
    @extend_schema(parameters=[SESSION_TOKEN, OpenApiParameter("result_id", str, required=True)],
                   responses=DiscoveryContextSerializer)
    def get(self, request, session_id):
        from catalog.services.discovery_context import session_context
        session = get_session(request, session_id)
        return Response(session_context(session, request.query_params.get("result_id"), session_access(session, request)))


class LegacyDiscoverySearchView(DiscoveryView):
    """An explicit async successor for bookmarked pre-3.0.8 query URLs."""

    @extend_schema(responses={202: DiscoveryResponseSerializer})
    def get(self, request):
        filters = {key: request.query_params.getlist(key) for key in request.query_params
                   if key not in {"q", "limit", "debug", "sort", "relation", "max_per_work"}}
        for key in ("year_min", "year_max"):
            if key in filters:
                filters[key] = request.query_params.get(key)
        session, token = create_session(request, request.query_params.get("q", ""), normalize_filters(filters))
        payload = self.payload(request, session)
        payload.update({"access_token": token, "results": payload["passages"], "groups": {},
                        "stance_counts": {}, "q": session.query, "engine": "discovery_v308",
                        "search_version": "3.0.8", "status_url": f"/api/catalog/discovery-search/{session.id}/",
                        "compatibility_notice": "观点检索已升级为异步三通道检索，请读取 status_url 获取原文、知识与策展结果；旧立场分组已退役。"})
        return Response(payload, status=202, headers={"Location": payload["status_url"], "Deprecation": "true"})
