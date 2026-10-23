"""Entry points into the existing page-local editorial ledger."""
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.content_placement_views import _page
from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services import content_placements as service
from common.permissions import CanEditMetadata, IsKnowledgeEditor


class PlacementPageQuerySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=[key for key in service.PAGES if key != "site"], default="issue")
    q = serializers.CharField(max_length=240, allow_blank=True, required=False)
    page = serializers.IntegerField(min_value=1, default=1)


class PlacementPageChoiceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    public_url = serializers.CharField()
    edit_url = serializers.CharField()


class PlacementPageDirectorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = PlacementPageChoiceSerializer(many=True)


def page_rows(kind, query):
    rows = service.PAGES[kind][0].objects.all()
    title = "person__preferred_name" if kind == "scholar" else "canonical_name_zh" if kind == "node" else "title" if kind in {"issue", "reading_path", "timeline_event"} else "name"
    if kind == "scholar":
        rows = rows.select_related("person")
    if query:
        rows = rows.filter(Q(**{title + "__icontains": query}))
    return rows.order_by(title, "pk")


class PlacementPageDirectoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(parameters=[PlacementPageQuerySerializer], responses=PlacementPageDirectorySerializer)
    def get(self, request):
        incoming = PlacementPageQuerySerializer(data=request.query_params)
        incoming.is_valid(raise_exception=True)
        kind = incoming.validated_data["type"]
        service.authorize(request.user, kind)
        def serialize(row):
            status = getattr(row, service.PAGES[kind][1], "") if service.PAGES[kind][1] else ""
            return {"id": str(row.pk), "type": kind, "title": service._title(row), "status": status,
                    "public_url": service.public_url(kind, row), "edit_url": service.PAGES[kind][2] + str(row.pk)}
        return Response(_page(request, page_rows(kind, incoming.validated_data.get("q", "")), serialize))
