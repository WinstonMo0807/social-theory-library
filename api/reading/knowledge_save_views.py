from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from . import knowledge_saves
from .research_views import PrivateResponses


class KnowledgeSaveCommand(serializers.Serializer):
    saved = serializers.BooleanField()
    request_id = serializers.UUIDField()
    expected_version = serializers.CharField(max_length=100)


class KnowledgeSaveNode(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    slug = serializers.CharField()
    node_type = serializers.CharField()


class KnowledgeSaveReceiptOutput(serializers.Serializer):
    request_id = serializers.UUIDField()
    applied_saved = serializers.BooleanField()


class KnowledgeSaveOutput(serializers.Serializer):
    owner_id = serializers.CharField()
    node_id = serializers.UUIDField()
    record_id = serializers.UUIDField(allow_null=True)
    saved = serializers.BooleanField()
    version = serializers.CharField()
    node = KnowledgeSaveNode(allow_null=True)
    receipt = KnowledgeSaveReceiptOutput(allow_null=True)


class KnowledgeSaveView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    def check_owner(self, request):
        if request.headers.get("X-Reader-Owner") != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新核对当前账户。")

    @extend_schema(parameters=[OpenApiParameter("request_id", str),
        OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)],
        responses=KnowledgeSaveOutput)
    def get(self, request, node_id):
        self.check_owner(request)
        request_id = request.query_params.get("request_id")
        receipt = knowledge_saves.receipt_for(request.user, node_id,
            serializers.UUIDField().run_validation(request_id)) if request_id else None
        return Response(knowledge_saves.output(request.user, node_id, receipt))

    @extend_schema(request=KnowledgeSaveCommand,
        parameters=[OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)],
        responses=KnowledgeSaveOutput)
    def post(self, request, node_id):
        self.check_owner(request)
        data = KnowledgeSaveCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(knowledge_saves.command(request.user, node_id, data.validated_data))
