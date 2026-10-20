"""One public-safe status endpoint; mutation retains existing administrator capabilities."""
from uuid import UUID

from django.utils.cache import patch_vary_headers
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .reader_ocr import control, reader_source, receipt_for, require_actor, status_payload
from .reader_ocr_serializers import ReaderOCRCommandInput, ReaderOCRStatusOutput


class ReaderOCRStatusView(APIView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        expected = request.headers.get("X-Reader-Owner")
        if expected is not None and expected != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取当前账户的任务状态。")

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ["Cookie", "Authorization", "X-Reader-Owner"])
        return response

    @extend_schema(responses=ReaderOCRStatusOutput,
        parameters=[
            OpenApiParameter("request_id", type=str, description="仅管理账户使用：查回本人固定命令回执，必须同时传 X-Reader-Owner。"),
            OpenApiParameter("X-Reader-Owner", type=str, location=OpenApiParameter.HEADER,
                description="当前账户 ID；普通读取可省略，传入时必须匹配当前登录账户。"),
        ])
    def get(self, request, asset_id):
        request_id = request.query_params.get("request_id")
        if request_id is not None:
            require_actor(request)
            try:
                request_id = UUID(request_id)
            except (ValueError, TypeError, AttributeError):
                raise ValidationError({"request_id": "需要有效的命令标识。"}) from None
        asset = reader_source(asset_id, request)
        receipt = receipt_for(asset, request.user, request_id) if request_id else None
        return Response(status_payload(asset, request.user, receipt=receipt))

    @extend_schema(request=ReaderOCRCommandInput, responses=ReaderOCRStatusOutput,
        parameters=[OpenApiParameter("X-Reader-Owner", type=str, location=OpenApiParameter.HEADER,
            required=True, description="固定为发起本次命令的当前账户 ID。")])
    def post(self, request, asset_id):
        return Response(control(request, asset_id, request.data))
