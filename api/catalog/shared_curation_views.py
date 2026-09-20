from django.core.paginator import Paginator
from django.db.models import CharField, F, OuterRef, Q, Subquery, Value
from django.db.models.functions import Cast
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_serializers import EditorialPublishSerializer
from catalog.models import EditorialRevision, ScholarRelation
from catalog.services import shared_curation as service
from catalog.services.scoped_search import public_scholar_queryset
from common.permissions import IsKnowledgeEditor, CanPublishAuthority


class CurationSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    source_type = serializers.CharField()
    text = serializers.CharField()
    context_before = serializers.CharField()
    context_after = serializers.CharField()
    work_id = serializers.UUIDField()
    work_title = serializers.CharField()
    edition_id = serializers.UUIDField()
    edition_label = serializers.CharField()
    asset_id = serializers.UUIDField()
    page_start = serializers.IntegerField()
    page_end = serializers.IntegerField()
    printed_label = serializers.CharField()
    document_revision_id = serializers.UUIDField(allow_null=True)
    reader_url = serializers.CharField()
    public_eligible = serializers.BooleanField()


class CurationItemSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    source_type = serializers.ChoiceField(choices=["span", "passage"])
    source_id = serializers.UUIDField()
    group_title = serializers.CharField(required=False, allow_blank=True)
    reason = serializers.CharField(required=False, allow_blank=True)
    order = serializers.IntegerField(required=False)
    source = CurationSourceSerializer(read_only=True)


class EvidenceCurationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True, allow_null=True)
    configured = serializers.BooleanField(read_only=True)
    object_type = serializers.CharField(read_only=True)
    object_id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    edit_version = serializers.CharField(required=False)
    has_unpublished_changes = serializers.BooleanField(read_only=True)
    items = CurationItemSerializer(many=True)


class ScholarRelationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    source_scholar = serializers.UUIDField()
    target_scholar = serializers.UUIDField()
    source_name = serializers.CharField(read_only=True)
    target_name = serializers.CharField(read_only=True)
    source_slug = serializers.CharField(read_only=True)
    target_slug = serializers.CharField(read_only=True)
    relation_type = serializers.ChoiceField(choices=service.RELATION_TYPES)
    direction = serializers.ChoiceField(choices=service.DIRECTIONS)
    summary = serializers.CharField(allow_blank=True)
    source = serializers.CharField(allow_blank=True)
    status = serializers.CharField(read_only=True)
    edit_version = serializers.CharField(required=False)
    has_unpublished_changes = serializers.BooleanField(read_only=True)


class CurationSourcesPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = CurationSourceSerializer(many=True)


class ScholarRelationPageSerializer(CurationSourcesPageSerializer):
    results = ScholarRelationSerializer(many=True)


def paged(request, queryset, serialize):
    paginator = Paginator(queryset, 24)
    page = paginator.get_page(request.query_params.get("page", 1))
    def link(number):
        params = request.query_params.copy()
        params["page"] = number
        return f"{request.path}?{params.urlencode()}"
    return {"count": paginator.count, "next": link(page.next_page_number()) if page.has_next() else None,
            "previous": link(page.previous_page_number()) if page.has_previous() else None,
            "results": [result for row in page.object_list if (result := serialize(row)) is not None]}


class CurationSourcesView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=CurationSourcesPageSerializer)
    def get(self, request):
        lists = []
        for kind in ("span", "passage"):
            queryset = service.sources(kind)
            for param, path in (("work", "page__asset__edition__work_id"), ("edition", "page__asset__edition_id"), ("asset", "page__asset_id")):
                if request.query_params.get(param):
                    queryset = queryset.filter(**{path: service.identifier(request.query_params[param])})
            query = request.query_params.get("q", "").strip()
            if query:
                queryset = queryset.filter(**{f"{'original_text' if kind == 'span' else 'text'}__icontains": query})
            if kind == "span":
                queryset = queryset.filter(is_stale=False)
            queryset = queryset.order_by().annotate(source_kind=Value(kind), source_key=Cast("pk", CharField()), page_order=F("page__index"))
            lists.append(queryset.values("source_kind", "source_key", "page_order"))
        keys = lists[0].union(lists[1], all=True).order_by("page_order", "source_kind", "source_key")
        paginator = Paginator(keys, 24)
        page = paginator.get_page(request.query_params.get("page", 1))
        selected = list(page.object_list)
        found = {kind: {str(row.pk): row for row in service.sources(kind).filter(pk__in=[key["source_key"] for key in selected if key["source_kind"] == kind])} for kind in ("span", "passage")}
        def serialize(key):
            return service.source_payload(key["source_kind"], found[key["source_kind"]][key["source_key"]])
        # Reuse the already paginated keys: do not re-evaluate the source tables.
        params = request.query_params.copy()
        def link(number):
            params["page"] = number
            return f"{request.path}?{params.urlencode()}"
        return Response({"count": paginator.count, "next": link(page.next_page_number()) if page.has_next() else None,
                         "previous": link(page.previous_page_number()) if page.has_previous() else None,
                         "results": [serialize(key) for key in selected]})


class AdminEvidenceCurationView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=EvidenceCurationSerializer)
    def get(self, request, object_type, object_id):
        return Response(service.curation_payload(object_type, object_id))

    @extend_schema(request=EvidenceCurationSerializer, responses=EvidenceCurationSerializer)
    def put(self, request, object_type, object_id):
        return Response(service.save_curation(object_type, object_id, request.data, request.user))


class PublishEvidenceCurationView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishAuthority]

    @extend_schema(request=EditorialPublishSerializer, responses=EvidenceCurationSerializer)
    def post(self, request, object_type, object_id):
        return Response(service.publish_curation(object_type, object_id, request.data.get("edit_version"), request.user))


class PublicEvidenceCurationView(EditorialErrorMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=EvidenceCurationSerializer)
    def get(self, request, object_type, object_id):
        return Response(service.curation_payload(object_type, object_id, public=True))


class AdminScholarRelationListView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(operation_id="catalog_admin_scholar_relations_list", responses=ScholarRelationPageSerializer)
    def get(self, request):
        rows = ScholarRelation.objects.select_related("active_revision")
        if request.query_params.get("scholar"):
            key = str(service.identifier(request.query_params["scholar"]))
            latest = EditorialRevision.objects.filter(target_type="scholar_relation", target_id=OuterRef("pk")).order_by("-revision")
            rows = rows.annotate(draft_source=Subquery(latest.values("materialized_preview__source_scholar")[:1]), draft_target=Subquery(latest.values("materialized_preview__target_scholar")[:1]))
            rows = rows.filter(Q(source_scholar_id=key) | Q(target_scholar_id=key) | Q(draft_source=key) | Q(draft_target=key))
        return Response(paged(request, rows.order_by("-updated_at", "pk"), service.relation_payload))

    @extend_schema(request=ScholarRelationSerializer, responses={201: ScholarRelationSerializer})
    def post(self, request):
        return Response(service.save_relation(None, request.data, request.user), status=201)


class AdminScholarRelationDetailView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=ScholarRelationSerializer)
    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        return Response(service.relation_payload(get_object_or_404(ScholarRelation, pk=pk)))

    @extend_schema(request=ScholarRelationSerializer, responses=ScholarRelationSerializer)
    def put(self, request, pk):
        return Response(service.save_relation(pk, request.data, request.user))


class PublishScholarRelationView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishAuthority]

    @extend_schema(request=EditorialPublishSerializer, responses=ScholarRelationSerializer)
    def post(self, request, pk):
        return Response(service.publish_relation(pk, request.data.get("edit_version"), request.user))


class PublicScholarRelationListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=ScholarRelationPageSerializer)
    def get(self, request):
        public = public_scholar_queryset().values("pk")
        rows = ScholarRelation.objects.filter(status="published", active_revision__status="published", source_scholar_id__in=public, target_scholar_id__in=public).select_related("active_revision")
        if request.query_params.get("scholar"):
            key = service.identifier(request.query_params["scholar"])
            rows = rows.filter(Q(source_scholar_id=key) | Q(target_scholar_id=key))
        return Response(paged(request, rows.order_by("-updated_at", "pk"), lambda row: service.relation_payload(row, public=True)))


class ArchiveScholarRelationView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishAuthority]

    @extend_schema(request=EditorialPublishSerializer, responses=ScholarRelationSerializer)
    def post(self, request, pk):
        return Response(service.archive_relation(pk, request.data.get("edit_version"), request.user))
