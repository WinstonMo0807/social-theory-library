"""Owner-only public-path follows; copies reuse the existing personal plans."""
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import path_plans as service
from .path_serializers import (PathCommandOutput, PathCopyInput, PathCreateInput, PathPageOutput,
    PathUpdateInput, PathUpgradeInput, PathUpgradePreviewOutput)
from .research_models import PersonalReadingPlan
from .research_views import PrivateResponses

OWNER = OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)


class PathFollowPagination(PageNumberPagination):
    page_size = 20


@extend_schema_view(
    list=extend_schema(parameters=[OWNER, OpenApiParameter("page", int)], responses=PathPageOutput),
    retrieve=extend_schema(parameters=[OWNER], responses=PathCommandOutput),
    create=extend_schema(parameters=[OWNER], request=PathCreateInput, responses={201: PathCommandOutput}),
    partial_update=extend_schema(parameters=[OWNER], request=PathUpdateInput, responses=PathCommandOutput),
    destroy=extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True),
        OpenApiParameter("expected_revision", int, required=True)], responses=PathCommandOutput),
)
class PathFollowViewSet(PrivateResponses, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PathCommandOutput
    pagination_class = PathFollowPagination
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请携带当前账户标识，再读取或保存本人的路径进度。")

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return PersonalReadingPlan.objects.none()
        return PersonalReadingPlan.objects.filter(user=self.request.user, public_path_id__isnull=False).order_by("-updated_at", "-id")

    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        response = self.get_paginated_response([service.record_output(row, request.user) for row in page])
        response.data["owner_id"] = str(request.user.pk)
        return response

    def retrieve(self, request, pk=None):
        return Response(service.command_output(request.user, record=service.owned(request.user, pk)))

    def create(self, request):
        return Response(service.create_follow(request.user, request.data), status=201)

    def partial_update(self, request, pk=None):
        return Response(service.update_follow(request.user, pk, request.data))

    def destroy(self, request, pk=None):
        return Response(service.delete_plan(request.user, pk, request.query_params, follow_only=True))

    @extend_schema(parameters=[OWNER, OpenApiParameter("path_id", str, required=True)], responses=PathCommandOutput)
    @action(detail=False, methods=["get"], url_path="by-path")
    def by_path(self, request):
        return Response(service.by_path(request.user, request.query_params.get("path_id")))

    @extend_schema(parameters=[OWNER, OpenApiParameter("request_id", str, required=True)], responses=PathCommandOutput)
    @action(detail=False, methods=["get"], url_path="by-request")
    def by_request(self, request):
        return Response(service.by_request(request.user, request.query_params.get("request_id")))

    @extend_schema(parameters=[OWNER], request=PathCopyInput, responses={201: PathCommandOutput})
    @action(detail=True, methods=["post"], url_path="copy-plan")
    def copy_plan(self, request, pk=None):
        return Response(service.copy_plan(request.user, pk, request.data), status=201)

    @extend_schema(parameters=[OWNER, OpenApiParameter("target_revision", str, required=True)], responses=PathUpgradePreviewOutput)
    @action(detail=True, methods=["get"], url_path="upgrade-preview")
    def upgrade_preview(self, request, pk=None):
        return Response(service.upgrade_preview(request.user, pk, request.query_params.get("target_revision")))

    @extend_schema(parameters=[OWNER], request=PathUpgradeInput, responses=PathCommandOutput)
    @action(detail=True, methods=["post"])
    def upgrade(self, request, pk=None):
        return Response(service.upgrade(request.user, pk, request.data))
