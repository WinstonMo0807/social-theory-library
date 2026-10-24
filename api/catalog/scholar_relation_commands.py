"""Original scholar relations, with the existing editor request receipts."""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import ScholarRelation
from catalog.scholar_commands import ScholarCommandMixin, PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.services.shared_curation import relation_payload
from common.capabilities import Capability, has_capability
from common.permissions import CanAccessBackOffice


class ScholarRelationCommandMixin(ScholarCommandMixin):
    save_action = "scholar_relation_command"
    save_model = ScholarRelation
    save_identity = "relation_id"
    save_salt = "stl4-scholar-relation"
    save_lock = "scholar_relation_request"
    save_label = "学者关系"
    relation_publish = False

    def _draft_read_rows(self, rows):
        return [relation_payload(row) for row in rows]

    def _lock_editorial_scope(self):
        if self.relation_publish and not has_capability(self.request.user, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("当前账户已无学者关系发布或撤回权限。")

    def relation_command(self, request, handler, *, creating=False):
        if not request.headers.get("Idempotency-Key"):
            raise ValidationError("请使用固定请求编号保存或发布关系，以便查回操作结果。")
        return self._scholar_write(request, handler, creating=creating)


class ScholarRelationReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    relation_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ScholarRelationReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=ScholarRelationReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(ScholarRelationReceipt(command_receipt(request.user, request_id,
            action="scholar_relation_command", model=ScholarRelation, identity="relation_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=ScholarRelationReceipt)
    def post(self, request, request_id):
        return Response(ScholarRelationReceipt(stop_pending_save(request, request_id,
            action="scholar_relation_command", model=ScholarRelation, identity="relation_id", lock="scholar_relation_request")).data)
