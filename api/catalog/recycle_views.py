from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from common.permissions import IsLibraryStaff
from .editorial_read import AdminPrivateResponseMixin
from .recycle_workspace import LABELS, directory, detail, confirm_restore, recovery_receipt
from .services.recycle import require_editor
from .recycle_related import related_page


class StrictRecoveryQuery(serializers.Serializer):
    def to_internal_value(self, data):
        if set(data)-set(self.fields) or hasattr(data,"getlist") and any(len(data.getlist(key))!=1 for key in data):
            raise serializers.ValidationError("查询参数重复或不受支持，请重新读取。")
        return super().to_internal_value(data)


class RecoveryQuery(StrictRecoveryQuery):
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


class RecoveryRenameInfo(serializers.Serializer):
    allowed = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)
    max_length = serializers.IntegerField()
    suggested_name = serializers.CharField(allow_blank=True)
    version = serializers.CharField(allow_blank=True)
    public_count = serializers.IntegerField()


class RecoveryLinkedObject(serializers.Serializer):
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    name = serializers.CharField()
    state = serializers.CharField()
    destination = serializers.CharField()


class RecoveryDependency(serializers.Serializer):
    kind = serializers.CharField()
    object_id = serializers.UUIDField()
    name = serializers.CharField()
    label = serializers.CharField()
    state = serializers.CharField()
    blocking = serializers.BooleanField()
    destination = serializers.CharField()
    detail = serializers.CharField()
    rename = RecoveryRenameInfo(required=False)
    relation_id = serializers.UUIDField(required=False)
    linked_objects = RecoveryLinkedObject(many=True,required=False)


class RecoveryHistory(serializers.Serializer):
    id = serializers.UUIDField()
    at = serializers.DateTimeField()
    action = serializers.CharField()
    actor = serializers.CharField()
    detail = serializers.CharField()


class RecoveryStorage(serializers.Serializer):
    state = serializers.CharField()
    checked_at = serializers.DateTimeField(allow_null=True)
    total = serializers.IntegerField(allow_null=True)


class RecoveryDetailQuery(StrictRecoveryQuery):
    check_files = serializers.BooleanField(default=False)


class RecoveryNames(serializers.Serializer):
    count = serializers.IntegerField()
    results = RecoveryDependency(many=True)
    limited = serializers.BooleanField()


class RecoveryRelatedQuery(StrictRecoveryQuery):
    category = serializers.ChoiceField(choices=["dependencies","history","names"], default="dependencies")
    relation = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)
    as_of = serializers.DateTimeField(required=False)

    def validate(self, values):
        if values["category"]!="dependencies" and values["relation"]:
            raise serializers.ValidationError("此栏目不支持关联类型筛选。")
        return values


class RecoveryRelationGroup(RecoveryKind):
    count = serializers.IntegerField()


class RecoveryRelatedPage(serializers.Serializer):
    category = serializers.CharField()
    relation = serializers.CharField(allow_blank=True)
    groups = RecoveryRelationGroup(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    as_of = serializers.DateTimeField()
    dependencies = RecoveryDependency(many=True)
    history = RecoveryHistory(many=True)
    names = RecoveryDependency(many=True)
    notice = serializers.CharField()


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
    history_count = serializers.IntegerField()
    names = RecoveryNames()
    rename = RecoveryRenameInfo()
    blockers = serializers.ListField(child=serializers.CharField())
    can_restore = serializers.BooleanField()
    notice = serializers.CharField()
    storage = RecoveryStorage()


class RecoveryRenameInput(serializers.Serializer):
    target = serializers.ChoiceField(choices=["restored","existing"])
    object_id = serializers.UUIDField()
    expected_version = serializers.RegexField(r"^[a-f0-9]{64}$")
    new_name = serializers.CharField(max_length=600)

    def to_internal_value(self, data):
        if not isinstance(data,dict) or set(data)!=set(self.fields):
            raise serializers.ValidationError("请完整确认改名对象与新名称。")
        return super().to_internal_value(data)


class RecoveryConfirmInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    object_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=list(LABELS))
    expected_version = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()
    keep_separate = serializers.BooleanField(required=False)
    rename = RecoveryRenameInput(required=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data)-set(self.fields):
            raise serializers.ValidationError("请先预览恢复影响，再提交本次确认字段。")
        return super().to_internal_value(data)

    def validate(self, values):
        if "rename" in values and "keep_separate" in values:
            raise serializers.ValidationError("只能选择一种名称冲突处理方式。")
        return values

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


class RecoveryReceipt(serializers.Serializer):
    request_id = serializers.UUIDField()
    actor_id = serializers.CharField()
    state = serializers.ChoiceField(choices=["applied","cancelled"])
    created_at = serializers.DateTimeField()
    result = RecoveryResult(allow_null=True)


class RecoveryCancelInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class AdminRecoveryReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(operation_id="recovery_receipt",responses=RecoveryReceipt)
    def get(self, request, request_id):
        return Response(recovery_receipt(request,request_id))

    @extend_schema(operation_id="recovery_cancel_pending",request=RecoveryCancelInput,responses=RecoveryReceipt)
    def post(self, request, request_id):
        return Response(recovery_receipt(request,request_id,cancel=True))


class AdminRecycleDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(operation_id="recovery_object_detail",parameters=[RecoveryDetailQuery],responses=RecoveryDetail)
    def get(self, request, kind, object_id):
        require_editor(request.user)
        query=RecoveryDetailQuery(data=request.query_params);query.is_valid(raise_exception=True)
        return Response(detail(kind,object_id,request.user,**query.validated_data))


class AdminRecycleRelatedView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(operation_id="recovery_object_related",parameters=[RecoveryRelatedQuery],responses=RecoveryRelatedPage)
    def get(self, request, kind, object_id):
        require_editor(request.user)
        query=RecoveryRelatedQuery(data=request.query_params);query.is_valid(raise_exception=True)
        return Response(related_page(kind,object_id,request.user,**query.validated_data))
