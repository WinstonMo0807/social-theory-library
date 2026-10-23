from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanViewSystemStatus
from catalog.local_services import check_service, services_snapshot


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
