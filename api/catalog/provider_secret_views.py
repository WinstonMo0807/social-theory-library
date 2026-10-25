from django.db import transaction
from drf_spectacular.utils import extend_schema, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from common.permissions import CanManageProviders
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.provider_secrets import ProviderSecretError
from catalog import provider_secret_configuration as configuration


class CredentialVersionInput(serializers.Serializer):
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('只接受当前凭据管理字段。')
        return super().to_internal_value(data)


class CredentialCommandInput(CredentialVersionInput):
    action = serializers.ChoiceField(choices=['set','delete'])
    alias = serializers.RegexField(r'^[a-z][a-z0-9_-]{0,63}$')
    purpose = serializers.ChoiceField(choices=['research_source','ai_runtime'], required=False)
    provider_key = serializers.RegexField(r'^[a-z][a-z0-9_-]{0,119}$', required=False)
    secret = serializers.CharField(max_length=16384,trim_whitespace=False,write_only=True,required=False)
    confirm_delete = serializers.BooleanField(default=False)

    def validate(self, values):
        if values['action'] == 'set' and any(not values.get(field) for field in ('purpose','provider_key','secret')):
            raise serializers.ValidationError('保存凭据须包含用途、服务与新凭据。')
        if values['action'] == 'delete' and 'secret' in values:
            raise serializers.ValidationError('删除操作不接受密钥内容。')
        return values


class CredentialBinding(serializers.Serializer):
    kind = serializers.CharField()
    key = serializers.CharField()
    url = serializers.CharField()


class CredentialRecord(serializers.Serializer):
    alias = serializers.CharField()
    purpose = serializers.CharField()
    provider_key = serializers.CharField()
    configured = serializers.BooleanField()
    updated_at = serializers.DateTimeField()
    last_tested_at = serializers.DateTimeField(allow_null=True)
    last_test_status = serializers.CharField(allow_blank=True)
    last_test_message = serializers.CharField(allow_blank=True)
    secret_values_exposed = serializers.BooleanField()
    bindings = CredentialBinding(many=True)
    can_edit_here = serializers.BooleanField()


class CredentialSnapshot(serializers.Serializer):
    configuration_version = serializers.CharField()
    secrets = CredentialRecord(many=True)
    summary = serializers.DictField(child=serializers.IntegerField())
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    page_size = serializers.IntegerField()
    has_next = serializers.BooleanField()
    secret_values_exposed = serializers.BooleanField()


class AdminProviderSecretView(AdminPrivateResponseMixin, APIView):
    """Owner-only compatibility inventory; bound secrets use their atomic editor."""
    permission_classes = [CanManageProviders]

    @extend_schema(parameters=[OpenApiParameter('page',int)], responses=CredentialSnapshot)
    @transaction.atomic
    def get(self, request):
        configuration.locked_actor(request,read=True)
        try:
            if set(request.query_params)-{'page'}:
                raise ValidationError('凭据记录只接受页码筛选。')
            return Response(configuration.snapshot(page=request.query_params.get('page',1)))
        except ProviderSecretError as exc:
            raise ValidationError({'code':exc.code,'detail':str(exc)}) from exc

    @extend_schema(request=CredentialCommandInput,responses=CredentialSnapshot)
    @transaction.atomic
    def post(self, request):
        serializer=CredentialCommandInput(data=request.data);serializer.is_valid(raise_exception=True)
        actor=configuration.locked_actor(request,serializer.validated_data['expected_version'])
        try:
            result=configuration.save(actor,serializer.validated_data,request_id=str(request.META.get('HTTP_X_REQUEST_ID') or ''))
        except ProviderSecretError as exc:
            raise ValidationError({'code':exc.code,'detail':str(exc)}) from exc
        return Response(result)

    @extend_schema(request=CredentialVersionInput,responses=CredentialSnapshot)
    @transaction.atomic
    def patch(self, request):
        serializer=CredentialVersionInput(data=request.data);serializer.is_valid(raise_exception=True)
        expected=serializer.validated_data['expected_version']
        actor=configuration.locked_actor(request,expected,allow_changed=True)
        configuration.fence(actor,expected)
        return Response(configuration.snapshot())
