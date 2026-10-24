"""Recover original review decisions without repeating candidate side effects."""
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from catalog.models import TheoryReviewTask
from catalog.node_editor_views import NodeSaveReceiptView
from catalog.scholar_commands import PendingSaveStopSerializer, ScholarCommandMixin
from catalog.services.person_authority import AuthorityConflict
from common.capabilities import Capability, capability_snapshot, has_capability
from ingestion.models import AuditEvent
from accounts.models import User


def review_version(task):
    return f"{task.pk}:{task.updated_at.isoformat()}"


class TheoryReviewInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["confirm", "modify_confirm", "create_node", "alias_existing", "merge_existing", "reject", "defer", "insufficient", "needs_changes", "delete"])
    edit_version = serializers.CharField(max_length=120)
    candidate_node = serializers.UUIDField(required=False, allow_null=True)
    relation_type = serializers.CharField(max_length=40, required=False, allow_blank=True)
    review_note = serializers.CharField(max_length=6000, required=False, allow_blank=True)
    canonical_name_zh = serializers.CharField(max_length=240, required=False, allow_blank=True)
    canonical_name_en = serializers.CharField(max_length=240, required=False, allow_blank=True)
    node_type = serializers.CharField(max_length=24, required=False)
    primary_discipline = serializers.UUIDField(required=False, allow_null=True)
    assigned_to = serializers.IntegerField(min_value=1, required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - self.fields.keys():
            raise ValidationError("审核请求含未知字段，请重新读取原任务。")
        return super().to_internal_value(data)


class TheoryReviewReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    task_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class TheoryReviewCommandMixin(ScholarCommandMixin):
    save_action = "theory_review_command"
    save_model = TheoryReviewTask
    save_identity = "task_id"
    save_salt = "stl4-theory-review"
    save_lock = "theory_review_request"
    save_label = "原审核任务"

    def _draft_read_rows(self, rows):
        from catalog.theory_serializers import TheoryReviewTaskSerializer
        return [TheoryReviewTaskSerializer(row, context={"request":self.request}).data for row in rows]

    def _lock_editorial_scope(self):
        if not has_capability(self.request.user, Capability.REVIEW_CANDIDATE):
            raise PermissionDenied("当前账户已无候选审核权限。")

    def review_command(self, request, task_id, handler):
        if not request.headers.get("Idempotency-Key"):
            raise ValidationError("审核决定需要固定请求编号，以便断线后查回原操作。")
        incoming = TheoryReviewInput(data=request.data)
        incoming.is_valid(raise_exception=True)

        def apply():
            task = get_object_or_404(TheoryReviewTask.objects.select_for_update(), pk=task_id)
            data = incoming.validated_data
            if data["edit_version"] != review_version(task):
                raise AuthorityConflict("原候选已被修改或审核，请重新读取后核对，当前决定未写入。")
            action = data["action"]
            if data.get("assigned_to"):
                assignee = get_object_or_404(User, pk=data["assigned_to"], is_active=True)
                if not has_capability(assignee, Capability.REVIEW_CANDIDATE):
                    raise ValidationError("所选账户不能审核候选，请选择当前有效的审核人员。")
            if action == "delete":
                if capability_snapshot(request.user).access_level not in {"admin", "superadmin"}:
                    raise PermissionDenied("只有管理员可以删除错误的审核候选。")
                payload = dict(self._draft_read_rows([task])[0])
                AuditEvent.objects.create(actor=request.user, action="theory_review_task_delete", object_type="catalog.TheoryReviewTask",
                    object_id=str(task.pk), before={"task_type":task.task_type,"status":task.status,"edit_version":review_version(task)}, after={"deleted":True})
                task.delete()
                return Response({**payload, "deleted":True})
            if action == "create_node" and not has_capability(request.user, Capability.CREATE_AUTHORITY):
                raise PermissionDenied("当前账户不能从候选创建规范条目。")
            if action in {"create_node", "alias_existing", "merge_existing"} and task.status in {"confirmed", "rejected"}:
                raise AuthorityConflict("这条候选已有最终决定，请核对已生成条目，不能再次创建或归并。")
            if action in {"confirm", "modify_confirm"} and task.task_type != "work_node":
                raise ValidationError("此任务不能直接确认为文献关联。新增条目请使用建档或别名操作，其他类型须回原专用编辑器核对。")
            if action in {"confirm", "modify_confirm", "create_node", "alias_existing", "merge_existing"} and task.file_id and task.work_id and task.file.edition.work_id != task.work_id:
                raise ValidationError("任务文献与原文件版本不一致，请先修正来源，当前决定未写入。")
            return handler()

        return self._scholar_write(request, apply)


class TheoryReviewReceiptView(NodeSaveReceiptView):
    receipt_serializer = TheoryReviewReceipt
    action = "theory_review_command"
    model = TheoryReviewTask
    identity = "task_id"
    request_lock = "theory_review_request"

    @extend_schema(responses=TheoryReviewReceipt)
    def get(self, request, request_id):
        return super().get(request, request_id)

    @extend_schema(request=PendingSaveStopSerializer, responses=TheoryReviewReceipt)
    def post(self, request, request_id):
        return super().post(request, request_id)
