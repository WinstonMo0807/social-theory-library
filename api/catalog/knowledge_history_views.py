from django.core.exceptions import ValidationError as ModelValidationError
from django.core.paginator import InvalidPage
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from catalog.publication_command_views import PublicationReadView
from catalog.services.editorial_revision import EditorialRevisionConflict, EditorialRevisionError
from catalog.services.knowledge_history import history_projection, prepare_history_command
from common.permissions import CanAccessBackOffice


class KnowledgeHistoryQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    selected = serializers.UUIDField(required=False)


class KnowledgeHistoryCommand(serializers.Serializer):
    action = serializers.ChoiceField(choices=["withdraw", "restore"])
    request_key = serializers.UUIDField()
    expected_version = serializers.RegexField(r"^[0-9a-f]{64}$")
    reason = serializers.CharField(max_length=400, allow_blank=False)
    source_revision_id = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if (attrs["action"] == "restore") != ("source_revision_id" in attrs):
            raise serializers.ValidationError("恢复须指定本对象的历史修订，撤回不接受历史修订。")
        return attrs


class KnowledgeHistoryRow(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    status = serializers.CharField()
    snapshot_public = serializers.BooleanField()
    matches_current = serializers.BooleanField()
    note = serializers.CharField()
    actor = serializers.CharField()
    created_at = serializers.DateTimeField()
    published_at = serializers.DateTimeField(allow_null=True)
    can_restore = serializers.BooleanField()


class KnowledgeHistoryPage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = KnowledgeHistoryRow(many=True)


class KnowledgeHistoryResult(serializers.Serializer):
    object_type = serializers.CharField()
    object_id = serializers.UUIDField()
    edit_version = serializers.CharField()
    title = serializers.CharField()
    status = serializers.CharField()
    is_public = serializers.BooleanField()
    has_draft = serializers.BooleanField()
    draft_id = serializers.UUIDField(allow_null=True)
    can_withdraw = serializers.BooleanField()
    history = KnowledgeHistoryPage()
    selected = KnowledgeHistoryRow(allow_null=True)
    changes = serializers.ListField(child=serializers.DictField())
    dependencies = serializers.ListField(child=serializers.DictField())
    events = serializers.ListField(child=serializers.DictField())
    scope = serializers.CharField()


class KnowledgeHistoryReceipt(serializers.Serializer):
    revision_id = serializers.UUIDField()
    revision = serializers.IntegerField()
    status = serializers.CharField()
    object_type = serializers.CharField()
    object_id = serializers.UUIDField()
    edit_version = serializers.CharField()


class KnowledgeHistoryView(PublicationReadView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OpenApiParameter("page", int), OpenApiParameter("selected", str)], responses=KnowledgeHistoryResult)
    def get(self, request, object_type, object_id):
        query = KnowledgeHistoryQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            return Response(history_projection(object_type=object_type, object_id=object_id, actor=request.user,
                                               page=query.validated_data["page"], selected_id=query.validated_data.get("selected")))
        except InvalidPage:
            return Response({"detail": "这页历史记录不存在，请回到第一页。"}, status=404)
        except EditorialRevisionConflict as exc:
            return Response({"detail": str(exc)}, status=409)

    @extend_schema(request=KnowledgeHistoryCommand, responses={202: KnowledgeHistoryReceipt})
    def post(self, request, object_type, object_id):
        command = KnowledgeHistoryCommand(data=request.data)
        command.is_valid(raise_exception=True)
        try:
            receipt = prepare_history_command(object_type=object_type, object_id=object_id, actor=request.user, **command.validated_data)
            return Response(receipt, status=202)
        except EditorialRevisionConflict as exc:
            return Response({"detail": str(exc)}, status=409)
        except (EditorialRevisionError, ModelValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)
