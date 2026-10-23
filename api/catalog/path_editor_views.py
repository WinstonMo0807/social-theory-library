from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from common.permissions import CanAccessBackOffice, IsKnowledgeEditor
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import ReadingPath
from catalog.scholar_commands import ScholarCommandMixin, command_receipt, stop_pending_save, PendingSaveStopSerializer
from catalog.reading_path_serializers import PathStageGroupInput
from catalog.services.reading_paths import normalize_reading_path_stage_groups, ReadingPathStructureError
from catalog.path_editor import dependency_report


class PathCommandMixin(ScholarCommandMixin):
    save_action = "path_editor_save"
    save_model = ReadingPath
    save_identity = "path_id"
    save_salt = "stl4-path-editor"
    save_lock = "path_editor_request"
    save_label = "阅读路径"

    def perform_create(self, serializer):
        from catalog.services.editorial_drafts import save_object_editorial_patch
        publish = serializer.validated_data.get("status") == "published"
        target = serializer.save(status="draft" if publish else serializer.validated_data.get("status", "draft"))
        if publish:
            save_object_editorial_patch("reading_path", target.pk, {"status": "published"}, actor=self.request.user, change_note="准备首次发布")


class PathSaveReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    path_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class PathSaveReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=PathSaveReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(PathSaveReceipt(command_receipt(request.user, request_id,
            action="path_editor_save", model=ReadingPath, identity="path_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=PathSaveReceipt)
    def post(self, request, request_id):
        return Response(PathSaveReceipt(stop_pending_save(request, request_id,
            action="path_editor_save", model=ReadingPath, identity="path_id", lock="path_editor_request")).data)


class PathValidationInput(serializers.Serializer):
    path_id = serializers.UUIDField(allow_null=True, required=False)
    stage_groups = PathStageGroupInput(many=True, max_length=60)


class PathValidationResult(serializers.Serializer):
    material_count = serializers.IntegerField()
    active_count = serializers.IntegerField()
    relation_counts = serializers.DictField(child=serializers.IntegerField())
    dependencies_valid = serializers.BooleanField()
    problems = serializers.ListField(child=serializers.DictField())
    notice = serializers.CharField()


class PathValidationView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(request=PathValidationInput, responses=PathValidationResult)
    def post(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取阅读路径。")
        if not isinstance(request.data, dict) or set(request.data) - {"path_id", "stage_groups"}:
            raise ValidationError("只接受本次路径与阶段编排。")
        incoming = PathValidationInput(data=request.data); incoming.is_valid(raise_exception=True)
        values = incoming.validated_data
        path = get_object_or_404(ReadingPath, pk=values["path_id"]) if values.get("path_id") else ReadingPath()
        try:
            groups = normalize_reading_path_stage_groups(path, values["stage_groups"])
        except ReadingPathStructureError as error:
            raise ValidationError(str(error)) from error
        return Response(PathValidationResult(dependency_report(groups)).data)
