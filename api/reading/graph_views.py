"""Authenticated graph views never share storage or authorization with public graphs."""
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import graph_saves as service
from .graph_models import SavedGraphView
from .graph_serializers import (GraphViewCommandOutput, GraphViewCreateInput, GraphViewPageOutput,
    GraphViewUpdateInput)
from .research_views import PrivateResponses

OWNER_HEADER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


class GraphViewPagination(PageNumberPagination):
    page_size = 20


@extend_schema_view(
    list=extend_schema(parameters=[OWNER_HEADER, OpenApiParameter("page", int)], responses=GraphViewPageOutput),
    retrieve=extend_schema(parameters=[OWNER_HEADER], responses=GraphViewCommandOutput),
    create=extend_schema(parameters=[OWNER_HEADER], request=GraphViewCreateInput, responses={201: GraphViewCommandOutput}),
    partial_update=extend_schema(parameters=[OWNER_HEADER], request=GraphViewUpdateInput, responses=GraphViewCommandOutput),
    destroy=extend_schema(parameters=[OWNER_HEADER, OpenApiParameter("request_id", str, required=True),
        OpenApiParameter("expected_revision", int, required=True)], responses=GraphViewCommandOutput),
)
class SavedGraphViewSet(PrivateResponses, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = GraphViewCommandOutput
    pagination_class = GraphViewPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请携带当前账户标识，再读取或保存本人的图谱视图。")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return SavedGraphView.objects.none()
        return SavedGraphView.objects.filter(user=self.request.user)

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        response = self.get_paginated_response([service.record_output(row, request.user) for row in page])
        response.data["owner_id"] = str(request.user.pk)
        return response

    def retrieve(self, request, pk=None):
        return Response(service.command_output(request.user, record=self.get_object()))

    def create(self, request):
        return Response(service.create_view(request.user, request.data), status=201)

    def partial_update(self, request, pk=None):
        return Response(service.update_view(request.user, pk, request.data))

    def destroy(self, request, pk=None):
        return Response(service.delete_view(request.user, pk, request.query_params))

    @extend_schema(parameters=[OWNER_HEADER, OpenApiParameter("request_id", str, required=True)],
        responses=GraphViewCommandOutput)
    @action(detail=False, methods=["get"], url_path="by-request")
    def by_request(self, request):
        return Response(service.by_request(request.user, request.query_params.get("request_id")))
