from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import privacy, research
from .models import ReaderDataOperation
from .privacy_serializers import (PrivacyCommandInput, PrivacyItemsOutput, PrivacyOperationInput,
    PrivacyOperationOutput, PrivacyOperationsPage, PrivacyPreferencesInput, PrivacySummaryOutput,
    PrivacyRequestReceipt, PrivacyRequestStopInput)
from .research_views import PrivateResponses, command


class ReaderPrivacyView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivacySummaryOutput

    @extend_schema(responses=PrivacySummaryOutput)
    def get(self, request):
        return Response(privacy.privacy_summary(request.user))

    @extend_schema(request=PrivacyPreferencesInput, responses=PrivacySummaryOutput)
    def patch(self, request):
        data = command(request, PrivacyPreferencesInput)
        return Response(privacy.update_preferences(request.user, data))


class ReaderPrivacyItemsView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivacyItemsOutput

    @extend_schema(responses=PrivacyItemsOutput)
    def get(self, request):
        try:
            page = int(request.query_params.get("page", 1))
            if page < 1:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValidationError({"page": "页码需要正整数。"}) from exc
        return Response(privacy.list_items(request.user, request.query_params.get("category", "reading_history"), page))


class ReaderPrivacyRequestView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("请从当前账户的资料页面核对原请求。")

    @extend_schema(responses=PrivacyRequestReceipt)
    def get(self, request, request_id):
        return Response(privacy.request_receipt(request.user, request_id))

    @extend_schema(request=PrivacyRequestStopInput, responses=PrivacyRequestReceipt)
    def post(self, request, request_id):
        serializer = PrivacyRequestStopInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(privacy.stop_request(request.user, request_id))


class ReaderDataOperationViewSet(PrivateResponses, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PrivacyOperationOutput

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return ReaderDataOperation.objects.none()
        return ReaderDataOperation.objects.filter(user=self.request.user)

    @extend_schema(responses=PrivacyOperationsPage)
    def list(self, request):
        privacy.close_stale(request.user)
        page = self.paginate_queryset(self.get_queryset())
        records = page if page is not None else self.get_queryset()[:20]
        result = [privacy.operation_output(row) for row in records]
        return self.get_paginated_response(result) if page is not None else Response({"count": len(result), "next": None, "previous": None, "results": result})

    @extend_schema(responses=PrivacyOperationOutput)
    def retrieve(self, request, pk=None):
        privacy.close_stale(request.user)
        return Response(privacy.operation_output(self.get_object()))

    @extend_schema(request=PrivacyOperationInput, responses={202: PrivacyOperationOutput})
    def create(self, request):
        privacy.close_stale(request.user)
        record = privacy.create_operation(request.user, command(request, PrivacyOperationInput))
        record.refresh_from_db()
        return Response(privacy.operation_output(record), status=202)

    @extend_schema(request=PrivacyCommandInput, responses=PrivacyOperationOutput)
    @action(detail=True, methods=["post"])
    def command(self, request, pk=None):
        record = privacy.command_operation(request.user, pk, command(request, PrivacyCommandInput))
        record.refresh_from_db()
        return Response(privacy.operation_output(record))

    @extend_schema(parameters=[OpenApiParameter("export_format", str, enum=["json", "zip", "csv"], default="json")],
        responses={(200, "application/json"): OpenApiTypes.OBJECT, (200, "application/zip"): OpenApiTypes.BINARY, (200, "text/csv"): OpenApiTypes.BINARY})
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        format_ = request.query_params.get("export_format", "json")
        if format_ != "json":
            from .privacy_exports import download
            return download(request.user, pk, format_)
        response = Response(privacy.download_operation(request.user, pk))
        response["Content-Disposition"] = f'attachment; filename="reader-data-{research.identifier(pk)}.json"'
        response["X-Content-Type-Options"] = "nosniff"
        return response
