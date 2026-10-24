from drf_spectacular.utils import extend_schema
from django.core.paginator import Paginator, InvalidPage
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanViewSystemStatus
from catalog.local_services import check_service, check_receipt, services_snapshot, PREFIX, STATUS_LABELS, observation_payload
from catalog.models import HealthCheckRun


class LocalServiceCheckInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    service_id = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,95}$", max_length=96)
    configuration_version = serializers.RegexField(r"^[a-f0-9]{64}$")

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError("服务检查仅接受请求编号、服务与配置版本。")
        return super().to_internal_value(data)


class LocalServiceObservation(serializers.Serializer):
    id = serializers.UUIDField()
    service_id = serializers.CharField()
    status = serializers.CharField()
    checked_at = serializers.DateTimeField()
    completed_at = serializers.DateTimeField(allow_null=True)
    latency_ms = serializers.IntegerField(allow_null=True)
    detail = serializers.CharField()
    identity = serializers.DictField()
    configuration_version = serializers.CharField()


class ServiceDetail(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()


class LocalService(serializers.Serializer):
    id = serializers.CharField()
    group = serializers.CharField()
    name = serializers.CharField()
    scope = serializers.CharField()
    configured = serializers.BooleanField()
    enabled = serializers.BooleanField()
    configuration_version = serializers.CharField()
    details = ServiceDetail(many=True)
    config_url = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    observation = LocalServiceObservation(allow_null=True)
    can_check = serializers.BooleanField()
    can_configure = serializers.BooleanField()
    check_notice = serializers.CharField()


class LocalServiceGroup(serializers.Serializer):
    id = serializers.CharField()
    label = serializers.CharField()
    subtitle = serializers.CharField()
    affected_features = serializers.ListField(child=serializers.CharField())
    status = serializers.CharField()
    status_label = serializers.CharField()
    services = LocalService(many=True)
    tasks = serializers.DictField(child=serializers.IntegerField(), allow_null=True)
    task_notice = serializers.CharField()


class LocalServicesSnapshot(serializers.Serializer):
    generated_at = serializers.DateTimeField()
    last_checked_at = serializers.DateTimeField(allow_null=True)
    observation_lifetime_seconds = serializers.IntegerField()
    groups = LocalServiceGroup(many=True)
    history = LocalServiceObservation(many=True)
    summary = serializers.DictField(child=serializers.IntegerField())
    notice = serializers.CharField()


class LocalServicesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanViewSystemStatus]

    @extend_schema(responses=LocalServicesSnapshot)
    def get(self, request):
        return Response(services_snapshot(request.user))


class LocalServiceCheckView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanViewSystemStatus]
    throttle_scope = "local_service_check"

    @extend_schema(request=LocalServiceCheckInput, responses=LocalServiceObservation)
    def post(self, request):
        serializer = LocalServiceCheckInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(check_service(request, serializer.validated_data))


class LocalServiceHistoryQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    service_id = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,95}$", max_length=96, required=False)
    status = serializers.ChoiceField(choices=list(STATUS_LABELS), required=False)
    as_of = serializers.DateTimeField(required=False)


class LocalServiceReceipt(serializers.Serializer):
    request_id = serializers.UUIDField()
    actor_id = serializers.CharField()
    state = serializers.ChoiceField(choices=["applied","cancelled"])
    observation = LocalServiceObservation(allow_null=True)


class LocalServiceCancelInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class LocalServiceReceiptView(AdminPrivateResponseMixin,APIView):
    permission_classes = [CanViewSystemStatus]

    @extend_schema(responses=LocalServiceReceipt)
    def get(self,request,request_id):
        return Response(LocalServiceReceipt(check_receipt(request,request_id)).data)

    @extend_schema(request=LocalServiceCancelInput,responses=LocalServiceReceipt)
    def post(self,request,request_id):
        return Response(LocalServiceReceipt(check_receipt(request,request_id,cancel=True)).data)


class LocalServiceHistoryPage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    as_of = serializers.DateTimeField()
    results = LocalServiceObservation(many=True)


class LocalServiceHistoryView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanViewSystemStatus]

    @extend_schema(parameters=[LocalServiceHistoryQuery], responses=LocalServiceHistoryPage)
    def get(self, request):
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params) or set(request.query_params) - set(LocalServiceHistoryQuery().fields):
            raise serializers.ValidationError("历史查询参数无效或重复。")
        query = LocalServiceHistoryQuery(data=request.query_params); query.is_valid(raise_exception=True)
        values = query.validated_data
        as_of = values.get("as_of") or timezone.now()
        if as_of > timezone.now():
            raise serializers.ValidationError("不能读取未来的检查记录。")
        rows = HealthCheckRun.objects.filter(probe_key__startswith=PREFIX, started_at__lte=as_of, created_at__lte=as_of)
        if values.get("service_id"):
            rows = rows.filter(probe_key=PREFIX + values["service_id"])
        if values.get("status"):
            rows = rows.filter(details__service_status=values["status"])
        paginator = Paginator(rows.order_by("-started_at", "-id"), 24)
        try:
            page = paginator.page(values["page"])
        except InvalidPage as error:
            raise serializers.ValidationError("这一页记录已不存在，请返回第一页重新读取。") from error
        return Response(LocalServiceHistoryPage({"count": paginator.count, "page": page.number, "total_pages": paginator.num_pages,
            "as_of": as_of, "results": [observation_payload(row) for row in page.object_list]}).data)
