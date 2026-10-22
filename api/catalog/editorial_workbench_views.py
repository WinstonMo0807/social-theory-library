"""Issue-scoped source choices and durable version history on the existing ledger."""
from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.content_placement_views import PlacementSourcesView, _page
from catalog.models import EditorialRevision, KnowledgeNode, Person, ReadingPath, RecommendationIssue, TheoryTimelineEvent
from catalog.services.editorial_blocks import resolve_target
from common.permissions import CanAccessBackOffice, CanEditMetadata


class IssueSourceChoiceSerializer(serializers.Serializer):
    target = serializers.DictField()
    source = serializers.DictField()


class IssueSourcesPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = IssueSourceChoiceSerializer(many=True)


class IssueSourcesView(PlacementSourcesView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=IssueSourcesPageSerializer, parameters=[OpenApiParameter(key, type=str) for key in ("type", "q", "page", "work_id", "edition_id", "node_type", "id", "document_revision_id")])
    def get(self, request, issue_id):
        get_object_or_404(RecommendationIssue, pk=issue_id)
        kind = request.query_params.get("type", "edition")
        if request.query_params.get("id"):
            target, source = resolve_target({"type": kind, "id": request.query_params["id"],
                **{key: request.query_params[key] for key in ("edition_id", "document_revision_id") if request.query_params.get(key)}})
            return Response({"count": 1, "next": None, "previous": None, "results": [{"target": target, "source": source}]})
        if kind in {"work", "edition", "span"} or kind == "node" and request.query_params.get("node_type") != "concept":
            return super().get(request)
        if kind not in {"person", "timeline", "reading_path", "node"}:
            return Response({"detail": "请选择馆藏、人物、知识节点、时间线、路径或原文。"}, status=400)
        model = {"person": Person, "timeline": TheoryTimelineEvent, "reading_path": ReadingPath, "node": KnowledgeNode}[kind]
        label = "preferred_name" if kind == "person" else "canonical_name_zh" if kind == "node" else "title"
        rows = model.objects.all()
        if kind == "node":
            rows = rows.filter(node_type="concept")
        query = request.query_params.get("q", "").strip()[:500]
        if query:
            rows = rows.filter(**{f"{label}__icontains": query})
        def serialize(row):
            target, source = resolve_target({"type": kind, "id": str(row.pk)})
            try:
                resolve_target(target, public=True)
                source["public_eligible"] = True
            except (Http404, ValidationError):
                source["public_eligible"] = False
            return {"target": target, "source": source}
        return Response(_page(request, rows.order_by(label, "pk"), serialize))


class IssueHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    is_current = serializers.BooleanField()
    block_count = serializers.IntegerField()


class IssueHistoryPageSerializer(IssueSourcesPageSerializer):
    results = IssueHistoryItemSerializer(many=True)


class IssueHistoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=IssueHistoryPageSerializer, parameters=[OpenApiParameter("page", type=int)])
    def get(self, request, issue_id):
        get_object_or_404(RecommendationIssue, pk=issue_id)
        rows = EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=issue_id).select_related("created_by").order_by("-revision")
        latest = rows.values_list("pk", flat=True).first()
        return Response(_page(request, rows, lambda row: {
            "id": str(row.pk), "revision": row.revision, "status": row.status,
            "created_at": row.created_at, "created_by": row.created_by.display_name if row.created_by else "",
            "note": row.change_note, "is_current": row.pk == latest,
            "block_count": len(row.materialized_preview.get("body_blocks", [])),
        }))


class IssueSuggestionSerializer(IssueSourceChoiceSerializer):
    key = serializers.CharField()
    token = serializers.CharField()
    kind = serializers.ChoiceField(choices=["work", "person", "concept"])
    reason = serializers.CharField()


class IssueSuggestionsSerializer(serializers.Serializer):
    results = IssueSuggestionSerializer(many=True)
    query = serializers.CharField(allow_blank=True)
    kind = serializers.CharField()
    batch = serializers.IntegerField()
    has_more = serializers.BooleanField()
    edit_version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    notice = serializers.CharField()


class DismissIssueSuggestionSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    token = serializers.CharField(max_length=4000)


class IssueSuggestionDismissedSerializer(serializers.Serializer):
    dismissed = serializers.BooleanField()
    key = serializers.CharField()


class IssueSuggestionsView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(responses=IssueSuggestionsSerializer, parameters=[OpenApiParameter(key, type=str) for key in ("q", "kind", "batch")])
    def get(self, request, issue_id):
        from catalog.services.editorial_suggestions import suggestions
        issue = get_object_or_404(RecommendationIssue, pk=issue_id)
        try:
            batch = int(request.query_params.get("batch", "1"))
        except (TypeError, ValueError):
            raise ValidationError("材料批次无效。")
        return Response(suggestions(issue, request.user, query=request.query_params.get("q", ""), kind=request.query_params.get("kind", "all"), batch=batch))

    @extend_schema(request=DismissIssueSuggestionSerializer, responses=IssueSuggestionDismissedSerializer)
    def post(self, request, issue_id):
        from catalog.services.editorial_suggestions import dismiss
        data = DismissIssueSuggestionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(dismiss(issue_id, request.user, data.validated_data))


class IssuePresenceCommandSerializer(serializers.Serializer):
    session_id = serializers.UUIDField()
    mode = serializers.ChoiceField(choices=["editing", "viewing", "leave"])


class IssueParticipantSerializer(serializers.Serializer):
    id = serializers.CharField()
    name = serializers.CharField()
    is_self = serializers.BooleanField()
    mode = serializers.ChoiceField(choices=["editing", "viewing"])
    last_seen = serializers.DateTimeField()


class IssuePresenceSerializer(serializers.Serializer):
    participants = IssueParticipantSerializer(many=True)
    checked_at = serializers.DateTimeField()
    expires_after_seconds = serializers.IntegerField()
    shared = serializers.BooleanField()
    notice = serializers.CharField()


class IssuePresenceView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(request=IssuePresenceCommandSerializer, responses=IssuePresenceSerializer)
    def post(self, request, issue_id):
        from catalog.services.editorial_presence import observe
        data = IssuePresenceCommandSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(observe(issue_id, request.user, data.validated_data))
