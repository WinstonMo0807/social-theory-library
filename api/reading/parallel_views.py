"""Private owner-scoped tasks and separately reviewed public contributions."""
from common.permissions import CanReadLibrary
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from common.permissions import CanPublishAuthority, CanReviewCandidate
from . import parallel_reading as service
from . import research
from .parallel_models import ParallelCalibration, ParallelReadingTask
from .parallel_serializers import (
    ParallelCalibrationCreateInput, ParallelCalibrationOutput, ParallelCalibrationPageOutput,
    ParallelReviewInput, ParallelTaskCreateInput, ParallelTaskOutput, ParallelTaskPageOutput, ParallelTaskUpdateInput,
    PublicParallelCalibrationPageOutput,
)
from .research_views import PrivateResponses


class ParallelPagination(PageNumberPagination):
    page_size = 20


class FixedReaderOwner(PrivateResponses):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请携带当前账户标识，再读取或保存本人的并读记录。")


class ParallelReadingTaskViewSet(FixedReaderOwner, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ParallelTaskOutput
    pagination_class = ParallelPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ParallelReadingTask.objects.none()
        rows = ParallelReadingTask.objects.filter(user=self.request.user)
        if asset_id := self.request.query_params.get("left_asset"):
            rows = rows.filter(left_asset_id=research.identifier(asset_id, "left_asset"))
        return rows

    @extend_schema(responses=ParallelTaskPageOutput,
        parameters=[OpenApiParameter("left_asset", type=str), OpenApiParameter("page", type=int)])
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([service.task_output(row, request.user) for row in page])

    def retrieve(self, request, pk=None):
        return Response(service.task_output(self.get_object(), request.user))

    @extend_schema(request=ParallelTaskCreateInput, responses={201: ParallelTaskOutput})
    def create(self, request):
        return Response(service.create_task(request.user, request.data), status=201)

    @extend_schema(request=ParallelTaskUpdateInput, responses=ParallelTaskOutput)
    def partial_update(self, request, pk=None):
        return Response(service.update_task(request.user, pk, request.data))

    @extend_schema(parameters=[OpenApiParameter("expected_revision", type=int, required=True)], responses={204: None})
    def destroy(self, request, pk=None):
        value = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("expected_revision"))
        service.delete_task(request.user, pk, value)
        return Response(status=204)

    @extend_schema(parameters=[OpenApiParameter("request_id", type=str, required=True)], responses=ParallelTaskOutput)
    @action(detail=False, methods=["get"], url_path="by-request")
    def by_request(self, request):
        return Response(service.task_by_request(request.user, request.query_params.get("request_id")))


class ParallelCalibrationViewSet(FixedReaderOwner, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ParallelCalibrationOutput
    pagination_class = ParallelPagination

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ParallelCalibration.objects.none()
        rows = ParallelCalibration.objects.filter(user=self.request.user)
        if asset_id := self.request.query_params.get("left_asset"):
            rows = rows.filter(left_asset_id=research.identifier(asset_id, "left_asset"))
        return rows

    @extend_schema(responses=ParallelCalibrationPageOutput)
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([service.calibration_output(row, request.user) for row in page])

    def retrieve(self, request, pk=None):
        return Response(service.calibration_output(self.get_object(), request.user))

    @extend_schema(request=ParallelCalibrationCreateInput, responses={201: ParallelCalibrationOutput})
    def create(self, request):
        return Response(service.create_calibration(request.user, request.data), status=201)

    @extend_schema(parameters=[OpenApiParameter("request_id", type=str, required=True)], responses=ParallelCalibrationOutput)
    @action(detail=False, methods=["get"], url_path="by-request")
    def by_request(self, request):
        return Response(service.calibration_by_request(request.user, request.query_params.get("request_id")))


class AdminParallelCalibrationViewSet(PrivateResponses, viewsets.GenericViewSet):
    permission_classes = [CanReviewCandidate]
    serializer_class = ParallelCalibrationOutput
    pagination_class = ParallelPagination

    def get_queryset(self):
        rows = ParallelCalibration.objects.all()
        if state := self.request.query_params.get("status"):
            if state not in {"submitted", "reviewed", "published", "rejected"}:
                raise ValidationError({"status": "请选择有效的审核状态。"})
            rows = rows.filter(status=state)
        return rows

    @extend_schema(responses=ParallelCalibrationPageOutput,
        parameters=[OpenApiParameter("status", type=str), OpenApiParameter("page", type=int)])
    def list(self, request):
        page = self.paginate_queryset(self.get_queryset())
        return self.get_paginated_response([service.calibration_output(row, request.user, admin=True) for row in page])

    def retrieve(self, request, pk=None):
        return Response(service.calibration_output(self.get_object(), request.user, admin=True))

    @extend_schema(request=ParallelReviewInput, responses=ParallelCalibrationOutput)
    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        return Response(service.review_calibration(request.user, pk, "review", request.data))

    @extend_schema(request=ParallelReviewInput, responses=ParallelCalibrationOutput)
    @action(detail=True, methods=["post"], permission_classes=[CanReviewCandidate, CanPublishAuthority])
    def publish(self, request, pk=None):
        return Response(service.review_calibration(request.user, pk, "publish", request.data))

    @extend_schema(request=ParallelReviewInput, responses=ParallelCalibrationOutput)
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        return Response(service.review_calibration(request.user, pk, "reject", request.data))


class PublicParallelCalibrationViewSet(viewsets.GenericViewSet):
    permission_classes = [CanReadLibrary]
    serializer_class = ParallelCalibrationOutput
    pagination_class = ParallelPagination

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ParallelCalibration.objects.none()
        rows = ParallelCalibration.objects.filter(status="published")
        if self.action == "list" and not self.request.query_params.get("left_asset"):
            raise ValidationError({"left_asset": "请选择正在并读的左侧版本，再读取公开校准。"})
        if asset_id := self.request.query_params.get("left_asset"):
            rows = rows.filter(left_asset_id=research.identifier(asset_id, "left_asset"))
        if asset_id := self.request.query_params.get("right_asset"):
            rows = rows.filter(right_asset_id=research.identifier(asset_id, "right_asset"))
        return rows

    @extend_schema(responses=PublicParallelCalibrationPageOutput,
        parameters=[OpenApiParameter("left_asset", type=str, required=True),
                    OpenApiParameter("right_asset", type=str), OpenApiParameter("page", type=int)])
    def list(self, request):
        # Resolve at most twenty submissions per call; candidate count is not
        # presented as the number of sources still authorized for public display.
        page = self.paginate_queryset(self.get_queryset())
        visible = [value for row in page
                   if (value := service.calibration_output(row, request.user, public=True)) is not None]
        response = self.get_paginated_response(visible)
        response.data["count"] = None
        response.data["notice"] = "按页核对当前公开来源，失效投稿不展示；后续页仍可能有可用校准。" if len(visible) < len(page) else ""
        return response

    def retrieve(self, request, pk=None):
        value = service.calibration_output(self.get_object(), request.user, public=True)
        if value is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("此公开校准的来源当前不可读取。")
        return Response(value)
