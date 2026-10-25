from uuid import UUID

from django.conf import settings
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import KnowledgeNode, KnowledgeNodeMergeRecord
from catalog.scholar_commands import PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.services import knowledge_merge_commands as service
from catalog.theory_serializers import KnowledgeNodeMergeRecordSerializer
from common.permissions import CanMergeAuthority, CanRunSystemRecovery


class NodeMergePair(serializers.Serializer):
    target_node = serializers.UUIDField()


class NodeMergeInput(NodeMergePair):
    fingerprint = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()
    change_note = serializers.CharField(max_length=500, allow_blank=True, required=False, default="")


class NodeRollbackInput(serializers.Serializer):
    fingerprint = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()


class NodeMergeSummary(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    name_en = serializers.CharField(allow_blank=True)
    node_type = serializers.CharField()
    status = serializers.CharField()
    editor_url = serializers.CharField()


class NodeMergePreview(serializers.Serializer):
    source = NodeMergeSummary()
    target = NodeMergeSummary()
    fingerprint = serializers.CharField()
    can_merge = serializers.BooleanField()
    affected = serializers.DictField(child=serializers.IntegerField())
    blockers = serializers.ListField(child=serializers.CharField())
    rule = serializers.CharField()


class NodeRollbackState(serializers.Serializer):
    fingerprint = serializers.CharField(allow_blank=True)
    can_rollback = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())


class NodeMergeReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    node_merge_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class NodeMergeResult(KnowledgeNodeMergeRecordSerializer):
    rollback = serializers.SerializerMethodField()
    save_receipt = NodeMergeReceipt(required=False)

    class Meta(KnowledgeNodeMergeRecordSerializer.Meta):
        fields = (*KnowledgeNodeMergeRecordSerializer.Meta.fields, "rollback", "save_receipt")

    @extend_schema_field(NodeRollbackState)
    def get_rollback(self, record):
        try:
            return service.rollback_state(record)
        except ValueError as error:
            return {"fingerprint": "", "can_rollback": False, "blockers": [str(error)]}


class NodeMergeRows(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = KnowledgeNodeMergeRecordSerializer(many=True)


class MergePrivateView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanMergeAuthority]

    def initial(self, request, *args, **kwargs):
        if not settings.THEORY_SYSTEM_ENABLED:
            raise NotFound("新版理论知识系统当前未启用。")
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("账户已变化，请重新核对条目合并。")


class AdminKnowledgeNodeMergePreviewView(MergePrivateView):
    @extend_schema(parameters=[NodeMergePair], responses=NodeMergePreview)
    def get(self, request, pk):
        data = NodeMergePair(data=request.query_params)
        data.is_valid(raise_exception=True)
        source, target = service.pair(pk, data.validated_data["target_node"])
        try:
            result = service.preview(source, target)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return Response(NodeMergePreview(result).data)


class AdminKnowledgeNodeMergeView(MergePrivateView):
    @extend_schema(request=NodeMergeInput, responses={201: NodeMergeResult})
    def post(self, request, pk):
        data = NodeMergeInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            request_id = UUID(request.headers.get("Idempotency-Key", ""))
        except (ValueError, TypeError):
            raise ValidationError("合并需要固定请求编号。") from None
        payload = dict(data.validated_data)
        try:
            record = service.merge(pk, payload.pop("target_node"), actor=request.user, request_id=request_id, **payload)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        result = NodeMergeResult(record).data
        result["save_receipt"] = receipt(request.user, request_id)
        return Response(result, status=201)


class AdminKnowledgeNodeMergeRollbackView(MergePrivateView):
    def get_permissions(self):
        return [CanRunSystemRecovery()] if self.request.method == "POST" else super().get_permissions()

    @extend_schema(responses=NodeMergeResult)
    def get(self, request, record_id):
        return Response(NodeMergeResult(get_object_or_404(KnowledgeNodeMergeRecord.objects.select_related("source_node", "target_node"), pk=record_id)).data)

    @extend_schema(request=NodeRollbackInput, responses=NodeMergeResult)
    def post(self, request, record_id):
        data = NodeRollbackInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            record = service.rollback(record_id, actor=request.user, **data.validated_data)
        except ValueError as error:
            raise ValidationError(str(error)) from error
        return Response(NodeMergeResult(record).data)


class NodeMergeHistoryView(MergePrivateView):
    @extend_schema(parameters=[OpenApiParameter("page", int)], responses=NodeMergeRows)
    def get(self, request, pk):
        get_object_or_404(KnowledgeNode, pk=pk)
        number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        rows = KnowledgeNodeMergeRecord.objects.filter(Q(source_node_id=pk) | Q(target_node_id=pk)).select_related("source_node", "target_node").order_by("-created_at", "pk")
        pages = Paginator(rows, 12)
        try:
            page = pages.page(number)
        except EmptyPage:
            raise ValidationError("记录页已变化，请返回第一页。") from None
        return Response(NodeMergeRows({"count": pages.count, "page": page.number, "pages": pages.num_pages, "results": page.object_list}).data)


def receipt(actor, request_id):
    return command_receipt(actor, request_id, action=service.ACTION, model=KnowledgeNodeMergeRecord, identity="node_merge_id")


class NodeMergeReceiptView(MergePrivateView):
    @extend_schema(responses=NodeMergeReceipt)
    def get(self, request, request_id):
        return Response(NodeMergeReceipt(receipt(request.user, request_id)).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=NodeMergeReceipt)
    def post(self, request, request_id):
        return Response(NodeMergeReceipt(stop_pending_save(request, request_id, action=service.ACTION,
            model=KnowledgeNodeMergeRecord, identity="node_merge_id", lock=service.LOCK)).data)
