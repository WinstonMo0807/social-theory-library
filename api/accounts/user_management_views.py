from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanManageUsers
from common.private_responses import PrivateAccountResponses
from .models import User
from .ownership import is_library_owner
from . import user_management as service


class StrictInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("包含不支持的字段，请重新读取账户后操作。")
        return super().to_internal_value(data)


class ManagementInput(StrictInput):
    operation = serializers.ChoiceField(choices=["create", "update", "password"])
    user_id = serializers.IntegerField(min_value=1, required=False)
    expected_version = serializers.CharField(min_length=64, max_length=64, required=False)
    username = serializers.CharField(max_length=20, required=False)
    email = serializers.EmailField(required=False)
    display_name = serializers.CharField(max_length=120, allow_blank=False, required=False)
    role = serializers.ChoiceField(choices=["reader", "editor", "admin"], required=False)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(min_length=10, max_length=128, trim_whitespace=False, write_only=True, required=False)

    def validate(self, data):
        base = {"operation", "request_id", "confirmed", "preview_hash"}
        required = {"create": {"username", "email", "display_name", "role", "is_active", "password"},
            "update": {"user_id", "expected_version"}, "password": {"user_id", "expected_version", "password"}}[data["operation"]]
        allowed = required | base | ({"display_name", "role", "is_active"} if data["operation"] == "update" else set())
        if required - set(data) or set(data) - allowed:
            raise serializers.ValidationError("字段与本次账户操作不匹配。")
        if data["operation"] == "update" and not set(data) & {"display_name", "role", "is_active"}:
            raise serializers.ValidationError("请选择需要修改的账户资料。")
        return data


class ManagementCommand(ManagementInput):
    request_id = serializers.UUIDField()
    confirmed = serializers.BooleanField()
    preview_hash = serializers.CharField(min_length=64, max_length=64)


class UserOutput(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    email = serializers.EmailField()
    display_name = serializers.CharField()
    role = serializers.CharField()
    role_label = serializers.CharField()
    is_active = serializers.BooleanField()
    is_owner = serializers.BooleanField()
    date_joined = serializers.DateTimeField()
    last_login = serializers.DateTimeField(allow_null=True)
    version = serializers.CharField()
    can_edit = serializers.BooleanField()
    can_change_role = serializers.BooleanField()
    capabilities = serializers.ListField(child=serializers.CharField())
    notice = serializers.CharField()


class CapabilityOutput(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()


class RoleOutput(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    capabilities = CapabilityOutput(many=True)
    public_access = serializers.CharField()
    private_access = serializers.CharField()
    assignable = serializers.BooleanField()


class RoleMatrix(serializers.Serializer):
    actor_id = serializers.CharField()
    roles = RoleOutput(many=True)
    can_assign_roles = serializers.BooleanField()


class ProposedUser(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    display_name = serializers.CharField()
    username = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()
    role_label = serializers.CharField()
    is_active = serializers.BooleanField()


class ManagementPreview(serializers.Serializer):
    actor_id = serializers.CharField()
    target = ProposedUser()
    retained = CapabilityOutput(many=True)
    gained = CapabilityOutput(many=True)
    lost = CapabilityOutput(many=True)
    public_access = serializers.CharField()
    private_access = serializers.CharField()
    sessions_revoked = serializers.BooleanField()
    notice = serializers.CharField()
    preview_hash = serializers.CharField()


class ManagementReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    user_id = serializers.IntegerField()
    exists = serializers.BooleanField()
    version = serializers.CharField(allow_null=True)
    operation = serializers.CharField()
    created_at = serializers.DateTimeField()


class ManagementQuery(serializers.Serializer):
    q = serializers.CharField(max_length=180, default="", allow_blank=True)
    role = serializers.ChoiceField(choices=["", "reader", "editor", "admin"], default="")
    state = serializers.ChoiceField(choices=["", "active", "inactive"], default="")
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.ChoiceField(choices=[10, 20, 50], default=10)
    user_id = serializers.IntegerField(min_value=1, required=False)


class ManagementDirectory(serializers.Serializer):
    actor_id = serializers.CharField()
    results = UserOutput(many=True)
    selected = UserOutput(allow_null=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    can_assign_roles = serializers.BooleanField()


class AuditRecord(serializers.Serializer):
    id = serializers.UUIDField()
    created_at = serializers.DateTimeField()
    actor = serializers.CharField()
    user_id = serializers.CharField()
    action = serializers.CharField()
    before = serializers.DictField()
    after = serializers.DictField()
    sessions_revoked = serializers.BooleanField(allow_null=True)
    password_reset = serializers.BooleanField()


class ManagementHistory(serializers.Serializer):
    actor_id = serializers.CharField()
    results = AuditRecord(many=True)
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()


class ManagementBase(PrivateAccountResponses, APIView):
    permission_classes = [CanManageUsers]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前管理账户。")


class ManagementWorkspaceView(ManagementBase):
    @extend_schema(parameters=[ManagementQuery], responses=ManagementDirectory)
    def get(self, request):
        data = ManagementQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        options = data.validated_data
        rows = User.objects.all().order_by("-date_joined", "-pk")
        if options["q"]:
            rows = rows.filter(Q(username__icontains=options["q"]) | Q(email__icontains=options["q"]) | Q(display_name__icontains=options["q"]))
        if options["role"]:
            rows = rows.filter(role__in=["editor", "reviewer"] if options["role"] == "editor" else [options["role"]])
        if options["state"]:
            rows = rows.filter(is_active=options["state"] == "active")
        count, page, size = rows.count(), options["page"], options["page_size"]
        if page > 1 and (page - 1) * size >= count:
            raise NotFound("此页已没有账户，请返回第一页。")
        selected = None
        if options.get("user_id"):
            selected = User.objects.filter(pk=options["user_id"]).first()
            if selected is None:
                raise NotFound("所选账户已不存在。")
        return Response({"actor_id": str(request.user.pk), "results": [service.record(row, request.user) for row in rows[(page - 1) * size:page * size]],
            "selected": service.record(selected, request.user) if selected else None, "count": count, "page": page, "page_size": size,
            "total_pages": max(1, (count + size - 1) // size), "can_assign_roles": is_library_owner(request.user)})


class ManagementRolesView(ManagementBase):
    @extend_schema(responses=RoleMatrix)
    def get(self, request):
        return Response({"actor_id": str(request.user.pk), "roles": service.roles(), "can_assign_roles": is_library_owner(request.user)})


class ManagementPreviewView(ManagementBase):
    @extend_schema(request=ManagementInput, responses=ManagementPreview)
    def post(self, request):
        data = ManagementInput(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(service.preview(request.user, data.validated_data))


class ManagementCommandView(ManagementBase):
    @extend_schema(request=ManagementCommand, responses=ManagementReceipt)
    def post(self, request):
        data = ManagementCommand(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(service.command(request.user, data.validated_data))


class ReceiptQuery(serializers.Serializer):
    request_id = serializers.UUIDField()


class ManagementReceiptView(ManagementBase):
    @extend_schema(parameters=[ReceiptQuery], responses=ManagementReceipt)
    def get(self, request):
        data = ReceiptQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(service.lookup(request.user, data.validated_data["request_id"]))


class ManagementHistoryView(ManagementBase):
    @extend_schema(parameters=[ManagementQuery], responses=ManagementHistory)
    def get(self, request):
        data = ManagementQuery(data=request.query_params)
        data.is_valid(raise_exception=True)
        options = data.validated_data
        rows = service.audit_rows()
        if options.get("user_id"):
            rows = rows.filter(object_id=str(options["user_id"]))
        page, size, count = options["page"], 20, rows.count()
        if page > 1 and (page - 1) * size >= count:
            raise NotFound("此页已没有操作记录，请返回第一页。")
        return Response({"actor_id": str(request.user.pk), "results": [service.audit_record(row) for row in rows[(page - 1) * size:page * size]],
            "count": count, "page": page, "total_pages": max(1, (count + size - 1) // size)})


def legacy_command(request, user_id, operation):
    """Compatibility URLs must not bypass the same preview and concurrency rules."""
    if request.headers.get("X-Editor-Owner") != str(request.user.pk):
        raise PermissionDenied("请重新核对当前管理账户。")
    if not isinstance(request.data, dict):
        raise serializers.ValidationError("账户操作必须使用结构化请求。")
    values = dict(request.data)
    if "user_id" in values and str(values["user_id"]) != str(user_id):
        raise serializers.ValidationError("请求账户与当前地址不一致。")
    if "operation" in values and values["operation"] != operation:
        raise serializers.ValidationError("操作与当前地址不一致。")
    if operation == "password" and "new_password" in values:
        if "password" in values:
            raise serializers.ValidationError("不能重复提交密码字段。")
        values["password"] = values.pop("new_password")
    data = ManagementCommand(data={**values, "user_id": user_id, "operation": operation})
    data.is_valid(raise_exception=True)
    return Response(service.command(request.user, data.validated_data))
