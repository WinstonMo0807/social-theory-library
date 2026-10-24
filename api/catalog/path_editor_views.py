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
from catalog.reading_path_serializers import PathMetadataInput, PublicReadingPathSerializer


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

    def to_internal_value(self, data):
        groups = data.get("stage_groups") if isinstance(data, dict) else None
        if isinstance(groups, list) and sum(len(group.get("items", [])) for group in groups
                if isinstance(group, dict) and isinstance(group.get("items", []), list)) > 600:
            raise ValidationError("一条阅读路径最多600项材料。")
        return super().to_internal_value(data)

    def validate_stage_groups(self, groups):
        if sum(len(group["items"]) for group in groups) > 600:
            raise ValidationError("一条阅读路径最多600项材料。")
        return groups


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


class PathPreviewInput(PathValidationInput, PathMetadataInput):
    edit_version = serializers.CharField(max_length=128, allow_blank=True, required=False)
    title = serializers.CharField(max_length=240, allow_blank=True)
    slug = serializers.SlugField(max_length=240, allow_blank=True)
    introduction = serializers.CharField(max_length=50000, allow_blank=True)
    learning_goal = serializers.CharField(max_length=10000, allow_blank=True)
    audience = serializers.CharField(max_length=240, allow_blank=True)
    difficulty = serializers.ChoiceField(choices=["beginner", "intermediate", "advanced"])
    estimated_reading = serializers.CharField(max_length=120, allow_blank=True)
    primary_discipline = serializers.UUIDField(allow_null=True)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise ValidationError("预览只接受本次路线与材料选择，不保存资料。")
        return super().to_internal_value(data)


class PathPreviewView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(request=PathPreviewInput, responses=PublicReadingPathSerializer)
    def post(self, request):
        import json
        from django.core.serializers.json import DjangoJSONEncoder
        from django.utils.crypto import constant_time_compare
        from catalog.editorial_read import current_editorial_version
        from catalog.models import EditorialRevision
        from catalog.services.public_reading_paths import preview_reading_path, _raw

        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新打开阅读路径。")
        incoming = PathPreviewInput(data=request.data)
        incoming.is_valid(raise_exception=True)
        values = incoming.validated_data
        path = get_object_or_404(ReadingPath, pk=values["path_id"]) if values.get("path_id") else ReadingPath()
        version = current_editorial_version("reading_path", path.pk) if values.get("path_id") else None
        if version is not None and not constant_time_compare(values.get("edit_version", ""), version):
            return Response({"detail": "原路径已被更新，当前输入仍保留，请先核对最新版本。", "code": "preview_changed"}, status=409)
        try:
            groups = normalize_reading_path_stage_groups(path, values["stage_groups"])
        except ReadingPathStructureError as error:
            raise ValidationError(str(error)) from error
        revision = EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk, status="draft").order_by("-revision").first() if version else None
        snapshot = dict(revision.materialized_preview if revision else _raw(path) if version else {})
        snapshot.update(json.loads(json.dumps({key: value for key, value in values.items()
            if key not in {"path_id", "edit_version", "stage_groups"}}, cls=DjangoJSONEncoder)))
        snapshot["stage_groups"] = groups
        path.slug = snapshot.get("slug", path.slug)
        data = preview_reading_path(path, snapshot=snapshot, request=request)
        if version is not None and current_editorial_version("reading_path", path.pk) != version:
            return Response({"detail": "预览期间原路径已变化，请重新核对。", "code": "preview_changed"}, status=409)
        return Response(PublicReadingPathSerializer(data).data)
