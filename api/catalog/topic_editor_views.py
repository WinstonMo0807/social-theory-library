from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice, IsKnowledgeEditor
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Topic
from catalog.scholar_commands import ScholarCommandMixin, command_receipt, stop_pending_save, PendingSaveStopSerializer
from catalog.topic_editor import lock_topic_hierarchy, organization_rows, topic_organization_preview


class TopicCommandMixin(ScholarCommandMixin):
    save_action = "topic_editor_save"
    save_model = Topic
    save_identity = "topic_id"
    save_salt = "stl4-topic-editor"
    save_lock = "topic_editor_request"
    save_label = "主题"

    def _lock_editorial_scope(self):
        lock_topic_hierarchy()


class TopicReceiptSerializer(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    topic_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class TopicReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=TopicReceiptSerializer)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(TopicReceiptSerializer(command_receipt(request.user, request_id,
            action="topic_editor_save", model=Topic, identity="topic_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=TopicReceiptSerializer)
    def post(self, request, request_id):
        return Response(TopicReceiptSerializer(stop_pending_save(request, request_id,
            action="topic_editor_save", model=Topic, identity="topic_id", lock="topic_editor_request")).data)


class TopicOrganizationRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    parent_id = serializers.UUIDField(allow_null=True)
    editorial_status = serializers.CharField()
    children_count = serializers.IntegerField()


class TopicOrganizationSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = TopicOrganizationRowSerializer(many=True)


class TopicOrganizationView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=TopicOrganizationSerializer, parameters=[OpenApiParameter(name, type=str) for name in ("q", "parent", "exclude", "page")])
    def get(self, request):
        data = request.query_params
        parent = serializers.UUIDField().run_validation(data["parent"]) if data.get("parent") else ""
        excluded = serializers.UUIDField().run_validation(data["exclude"]) if data.get("exclude") else None
        page = serializers.IntegerField(min_value=1).run_validation(data.get("page", 1))
        pages = Paginator(organization_rows(str(data.get("q", "")).strip()[:240], parent, exclude=excluded), 30)
        current = pages.get_page(page)
        return Response(TopicOrganizationSerializer({"count": pages.count, "page": current.number,
            "total_pages": pages.num_pages, "results": current.object_list}).data)


class TopicOrganizationInput(serializers.Serializer):
    parent = serializers.UUIDField(allow_null=True, required=False)
    curation = serializers.DictField(required=False)


class TopicParentLinkSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class TopicOrganizationPreviewSerializer(serializers.Serializer):
    topic_id = serializers.UUIDField()
    parent_id = serializers.UUIDField(allow_null=True)
    parent_changed = serializers.BooleanField()
    parent_path = TopicParentLinkSerializer(many=True)
    cycle_path = TopicParentLinkSerializer(many=True)
    descendant_count = serializers.IntegerField()
    public_descendant_count = serializers.IntegerField()
    content_counts = serializers.DictField(child=serializers.IntegerField())
    can_publish = serializers.BooleanField()
    problems = serializers.ListField(child=serializers.DictField())


class TopicOrganizationPreviewView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(request=TopicOrganizationInput, responses=TopicOrganizationPreviewSerializer)
    def post(self, request, pk):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取主题。")
        if not isinstance(request.data, dict) or set(request.data) - {"parent", "curation"}:
            raise ValidationError("只接受上级主题和本次关联内容。")
        incoming = TopicOrganizationInput(data=request.data); incoming.is_valid(raise_exception=True)
        target = get_object_or_404(Topic, pk=pk)
        return Response(TopicOrganizationPreviewSerializer(topic_organization_preview(target, incoming.validated_data)).data)
