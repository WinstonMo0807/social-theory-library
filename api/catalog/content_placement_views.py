"""Protected editing, exact-revision preview, and public placement reads."""
from django.core.paginator import Paginator
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition, KnowledgeNode
from catalog.services import content_placements as service
from catalog.services import shared_curation
from common.permissions import CanEditMetadata, IsKnowledgeEditor


class PlacementTargetSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["work", "edition", "node", "span"])
    id = serializers.UUIDField()
    edition_id = serializers.UUIDField(required=False)
    document_revision_id = serializers.UUIDField(required=False)


class PlacementSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    area = serializers.CharField(max_length=80, required=False)
    group = serializers.CharField(max_length=240, allow_blank=True, required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    target = PlacementTargetSerializer()
    reason = serializers.CharField(max_length=6000, allow_blank=True, required=False)
    local_text = serializers.CharField(max_length=6000, allow_blank=True, required=False)
    reading_target = serializers.DictField(required=False, allow_null=True)
    concept_usage = serializers.DictField(required=False, allow_null=True)


class PlacementCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=service.ACTIONS)
    request_id = serializers.UUIDField()
    expected_revision = serializers.CharField(max_length=80)
    items = PlacementSerializer(many=True, max_length=100, required=False)
    item = PlacementSerializer(required=False)
    item_id = serializers.UUIDField(required=False)
    position = serializers.IntegerField(min_value=0, max_value=100, required=False)
    area = serializers.CharField(max_length=80, required=False)
    group = serializers.CharField(max_length=240, allow_blank=True, required=False)
    patch = serializers.DictField(required=False)
    revision_id = serializers.UUIDField(required=False)


class PlacementReaderTargetSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField(min_value=1)


class PlacementUsageAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class PlacementSourceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["work", "edition", "node", "span"])
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    public_eligible = serializers.BooleanField()
    work_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)
    edition_label = serializers.CharField(required=False, allow_blank=True)
    reader_url = serializers.CharField(required=False, allow_blank=True)
    work_url = serializers.CharField(required=False, allow_blank=True)
    edit_url = serializers.CharField(required=False, allow_blank=True)
    source_type = serializers.CharField(required=False)
    text = serializers.CharField(required=False)
    context_before = serializers.CharField(required=False, allow_blank=True)
    context_after = serializers.CharField(required=False, allow_blank=True)
    work_title = serializers.CharField(required=False, allow_blank=True)
    asset_id = serializers.UUIDField(required=False)
    page_start = serializers.IntegerField(required=False, min_value=1)
    page_end = serializers.IntegerField(required=False, min_value=1)
    printed_label = serializers.CharField(required=False, allow_blank=True)
    document_revision_id = serializers.UUIDField(required=False, allow_null=True)
    reader_target = PlacementReaderTargetSerializer(required=False)
    usage_author = PlacementUsageAuthorSerializer(required=False, allow_null=True)


class PlacementResultItemSerializer(PlacementSerializer):
    id = serializers.UUIDField()
    source = PlacementSourceSerializer(allow_null=True)
    reading_target = PlacementReaderTargetSerializer(required=False, allow_null=True)


class PlacementSourceChoiceSerializer(serializers.Serializer):
    target = PlacementTargetSerializer()
    source = PlacementSourceSerializer()


class PlacementSourcesPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = PlacementSourceChoiceSerializer(many=True)


class PlacementHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    base_revision = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["draft", "published", "superseded"])
    created_at = serializers.DateTimeField()
    published_at = serializers.DateTimeField(allow_null=True)
    item_count = serializers.IntegerField()
    withdrawn = serializers.BooleanField()


class PlacementHistoryPageSerializer(PlacementSourcesPageSerializer):
    results = PlacementHistoryItemSerializer(many=True)


class PublicConceptAuthorSerializer(PlacementUsageAuthorSerializer):
    original_name = serializers.CharField(allow_blank=True)
    birth_year = serializers.IntegerField(allow_null=True)
    death_year = serializers.IntegerField(allow_null=True)
    portrait_url = serializers.CharField(allow_blank=True)
    scholar_slug = serializers.CharField(allow_blank=True)


class PublicConceptUsageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    term = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    usage_type = serializers.CharField()
    interpretation = serializers.CharField(allow_blank=True)
    attribution_note = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    explanatory_object = serializers.CharField(allow_blank=True)
    period = serializers.CharField(allow_blank=True)
    context = serializers.CharField(allow_blank=True)
    author = PublicConceptAuthorSerializer(allow_null=True)
    source = PlacementSourceSerializer()


class PublicConceptDetailSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    revision_id = serializers.UUIDField(allow_null=True)
    usages = PublicConceptUsageSerializer(many=True)
    unavailable_usage_count = serializers.IntegerField(min_value=0)


class PlacementReadSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    page_type = serializers.CharField()
    page_id = serializers.UUIDField()
    revision_id = serializers.UUIDField(allow_null=True)
    configured = serializers.BooleanField()
    items = PlacementResultItemSerializer(many=True)
    withdrawn = serializers.BooleanField()
    expected_revision = serializers.CharField(required=False)
    is_current_revision = serializers.BooleanField(required=False)
    published_revision_id = serializers.UUIDField(required=False, allow_null=True)
    has_unpublished_changes = serializers.BooleanField(required=False)
    source_problems = serializers.ListField(child=serializers.DictField(), required=False)
    publication_blockers = serializers.ListField(child=serializers.DictField(), required=False)
    state = serializers.CharField(required=False)
    can_publish = serializers.BooleanField(required=False)
    impact = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    replayed = serializers.BooleanField(required=False)
    applied_revision_id = serializers.UUIDField(required=False)
    public_detail = PublicConceptDetailSerializer(required=False)


def _page(request, rows, serialize):
    paginator = Paginator(rows, 24)
    page = paginator.get_page(request.query_params.get("page", 1))
    def url(number):
        params = request.query_params.copy()
        params["page"] = number
        return f"{request.path}?{params.urlencode()}"
    return {"count": paginator.count, "next": url(page.next_page_number()) if page.has_next() else None,
            "previous": url(page.previous_page_number()) if page.has_previous() else None,
            "results": [serialize(row) for row in page.object_list]}


class PlacementSourcesView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(responses=PlacementSourcesPageSerializer)
    def get(self, request):
        kind = request.query_params.get("type", "edition")
        query = request.query_params.get("q", "").strip()[:500]
        if kind in {"work", "edition"}:
            rows = Edition.objects.select_related("work", "active_catalog_revision")
            if query:
                rows = rows.filter(Q(work__title__icontains=query) | Q(isbn__icontains=query) | Q(doi__icontains=query))
            if request.query_params.get("work_id"):
                rows = rows.filter(work_id=shared_curation.identifier(request.query_params["work_id"]))
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.work_id if kind == "work" else row.pk), "edition_id": str(row.pk)})
                return {"target": reference, "source": source}
            return Response(_page(request, rows.order_by("work__title", "publication_year", "pk"), serialize))
        if kind == "node":
            rows = KnowledgeNode.objects.all()
            if query:
                rows = rows.filter(Q(canonical_name_zh__icontains=query) | Q(canonical_name_en__icontains=query))
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.pk)})
                return {"target": reference, "source": source}
            return Response(_page(request, rows.order_by("canonical_name_zh", "pk"), serialize))
        if kind == "span":
            rows = shared_curation.sources("span").filter(is_stale=False)
            if query:
                rows = rows.filter(original_text__icontains=query)
            for parameter, field in (("work_id", "page__asset__edition__work_id"), ("edition_id", "page__asset__edition_id")):
                if request.query_params.get(parameter):
                    rows = rows.filter(**{field: shared_curation.identifier(request.query_params[parameter])})
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.pk)})
                return {"target": reference, "source": source}
            return Response(_page(request, rows.order_by("page__asset_id", "page__index", "start_offset", "pk"), serialize))
        return Response({"detail": "未知馆藏选择类型。"}, status=400)


class AdminPlacementView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(responses=PlacementReadSerializer)
    def get(self, request, page_type, page_id):
        return Response(service.read(page_type, page_id, actor=request.user, revision_id=request.query_params.get("revision")))

    @extend_schema(request=PlacementCommandSerializer, responses=PlacementReadSerializer)
    def post(self, request, page_type, page_id):
        incoming = PlacementCommandSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        # Keep the original JSON: the service rejects source/body fields that
        # DRF would otherwise silently discard as unknown serializer fields.
        return Response(service.command(page_type, page_id, request.data, request.user))


class PlacementHistoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(responses=PlacementHistoryPageSerializer)
    def get(self, request, page_type, page_id):
        service.authorize(request.user, page_type)
        parent = service.parent_object(page_type, page_id)
        rows = service.revisions(page_type, parent.pk)
        return Response(_page(request, rows, lambda row: {
            "id": str(row.pk), "revision": row.revision, "base_revision": row.base_revision,
            "status": row.status, "created_at": row.created_at, "published_at": row.published_at,
            "item_count": len(row.materialized_preview.get("items", [])),
            "withdrawn": row.materialized_preview.get("withdrawn", False),
        }))


class PublicPlacementView(EditorialErrorMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PlacementReadSerializer)
    def get(self, request, page_type, page_id):
        # Anonymous requests cannot select a draft or a historical publication.
        return Response(service.read(page_type, page_id, public=True))
