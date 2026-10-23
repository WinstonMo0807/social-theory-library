from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from common.permissions import IsLibraryStaff
from .editorial_read import AdminPrivateResponseMixin
from .recycle_workspace import LABELS, directory, detail, confirm_restore
from .services.recycle import require_editor


class RecoveryQuery(serializers.Serializer):
    search = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=["", *LABELS], default="")
    state = serializers.ChoiceField(choices=["", "deleted", "archived", "restored"], default="")
    since = serializers.DateTimeField(required=False)
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    operator = serializers.RegexField(r"^\d+$", max_length=20, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class RecoveryRow(serializers.Serializer):
    object_id = serializers.UUIDField()
    kind = serializers.CharField()
    title = serializers.CharField()
    changed_at = serializers.DateTimeField()
    entry_id = serializers.UUIDField(allow_null=True)
    record_state = serializers.CharField()
    actor_name = serializers.CharField()
    actor_id = serializers.CharField(allow_blank=True)
    reason = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    label = serializers.CharField()
    destination = serializers.CharField()


class RecoveryKind(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class RecoveryOperator(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField(allow_blank=True)


class RecoveryDirectory(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    counts = serializers.DictField(child=serializers.IntegerField())
    results = RecoveryRow(many=True)
    kinds = RecoveryKind(many=True)
    operators = RecoveryOperator(many=True)
    operators_limited = serializers.BooleanField()
    notice = serializers.CharField()


class RecoveryDependency(serializers.Serializer):
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    name = serializers.CharField()
    label = serializers.CharField()
    state = serializers.CharField()
    blocking = serializers.BooleanField()
    destination = serializers.CharField()
    detail = serializers.CharField()


class RecoveryHistory(serializers.Serializer):
    id = serializers.UUIDField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    actor = serializers.CharField()
    detail = serializers.CharField()


class RecoveryDetail(serializers.Serializer):
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    entry_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    label = serializers.CharField()
    record_state = serializers.CharField()
    version = serializers.CharField()
    destination = serializers.CharField()
    cover_url = serializers.CharField()
    created_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField(allow_null=True)
    changed_at = serializers.DateTimeField()
    operator = serializers.CharField()
    reason = serializers.CharField()
    dependencies = RecoveryDependency(many=True)
    dependency_count = serializers.IntegerField()
    dependencies_limited = serializers.BooleanField()
    history = RecoveryHistory(many=True)
    blockers = serializers.ListField(child=serializers.CharField())
    can_restore = serializers.BooleanField()
    notice = serializers.CharField()


class RecoveryConfirmInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    object_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=list(LABELS))
    expected_version = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data)-set(self.fields):
            raise serializers.ValidationError("请先预览恢复影响，再提交本次确认字段。")
        return super().to_internal_value(data)

    def validate_confirmed(self,value):
        if value is not True:
            raise serializers.ValidationError("请明确确认恢复。")
        return value


class RecoveryResult(serializers.Serializer):
    request_id = serializers.UUIDField()
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    restored = serializers.BooleanField()
    public_restored = serializers.BooleanField()
    destination = serializers.CharField()
    detail = serializers.CharField()


class AdminRecycleView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(operation_id="recovery_directory",parameters=[RecoveryQuery],responses=RecoveryDirectory)
    def get(self, request):
        require_editor(request.user)
        query=RecoveryQuery(data=request.query_params);query.is_valid(raise_exception=True)
        return Response(directory(actor=request.user,**query.validated_data))

    @extend_schema(request=RecoveryConfirmInput,responses=RecoveryResult)
    def post(self, request):
        values=RecoveryConfirmInput(data=request.data);values.is_valid(raise_exception=True)
        return Response(confirm_restore(request,values.validated_data))


class AdminRecycleDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(operation_id="recovery_object_detail",responses=RecoveryDetail)
    def get(self, request, kind, object_id):
        require_editor(request.user)
        return Response(detail(kind,object_id,request.user))
