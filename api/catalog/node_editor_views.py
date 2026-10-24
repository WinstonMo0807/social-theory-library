"""Recoverable node edits using original scholar-editor receipt infrastructure."""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import KnowledgeNode
from catalog.scholar_commands import ScholarCommandMixin, PendingSaveStopSerializer, command_receipt, stop_pending_save
from common.permissions import CanAccessBackOffice


class NodeCommandMixin(ScholarCommandMixin):
    save_action = "node_editor_save"
    save_model = KnowledgeNode
    save_identity = "node_id"
    save_salt = "stl4-node-editor"
    save_lock = "node_editor_request"
    save_label = "理论或概念"


class NodeSaveReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    node_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class NodeSaveReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=NodeSaveReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(NodeSaveReceipt(command_receipt(request.user, request_id,
            action="node_editor_save", model=KnowledgeNode, identity="node_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=NodeSaveReceipt)
    def post(self, request, request_id):
        return Response(NodeSaveReceipt(stop_pending_save(request, request_id,
            action="node_editor_save", model=KnowledgeNode, identity="node_id", lock="node_editor_request")).data)
