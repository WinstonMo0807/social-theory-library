from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.ownership import is_library_owner
from common.permissions import CanConfigureProviders, CanViewSystemStatus
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services import research_sources as sources
from catalog.services.provider_secrets import ProviderSecretError, MAX_SECRET_CHARS
from catalog import research_source_configuration as configuration


class StrictSourceInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('只接受当前来源配置字段。')
        return super().to_internal_value(data)


class SourceAdapterInput(StrictSourceInput):
    key = serializers.ChoiceField(choices=list(sources.SOURCE_SPEC_BY_KEY))
    enabled = serializers.BooleanField(required=False)
    endpoint_alias = serializers.RegexField(r'^(?:[a-z][a-z0-9_-]{0,63})?$', allow_blank=True, required=False)
    credential_alias = serializers.RegexField(r'^(?:[a-z][a-z0-9_-]{0,63})?$', allow_blank=True, required=False)


class SourceCredentialInput(StrictSourceInput):
    action = serializers.ChoiceField(choices=['set', 'delete'])
    source_key = serializers.ChoiceField(choices=list(sources.SOURCE_SPEC_BY_KEY))
    alias = serializers.RegexField(r'^[a-z][a-z0-9_-]{0,63}$')
    secret = serializers.CharField(write_only=True, max_length=MAX_SECRET_CHARS, trim_whitespace=False, required=False)
    confirm_delete = serializers.BooleanField(default=False)

    def validate(self, values):
        if values['action'] == 'set' and not values.get('secret'):
            raise serializers.ValidationError('请输入要加密保存的新凭据。')
        if values['action'] == 'delete' and 'secret' in values:
            raise serializers.ValidationError('删除凭据不接收原值。')
        return values


class SourceFenceInput(StrictSourceInput):
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')


class SourceRegistryInput(SourceFenceInput):
    adapters = SourceAdapterInput(many=True, min_length=1, max_length=len(sources.SOURCE_SPECS))
    credential = SourceCredentialInput(required=False)


class SourceProbeInput(SourceFenceInput):
    action = serializers.ChoiceField(choices=['test'])
    source_key = serializers.ChoiceField(choices=list(sources.SOURCE_SPEC_BY_KEY))


class ResearchSourceOutput(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    category = serializers.CharField()
    purpose = serializers.CharField()
    affected_features = serializers.ListField(child=serializers.CharField())
    metadata_formats = serializers.ListField(child=serializers.CharField())
    execution_mode = serializers.CharField()
    usage_policy = serializers.CharField()
    configuration_requirements = serializers.ListField(child=serializers.CharField())
    enabled = serializers.BooleanField()
    status = serializers.CharField()
    configured_by = serializers.CharField()
    endpoint_configured = serializers.BooleanField()
    credential_configured = serializers.BooleanField()
    endpoint_alias_set = serializers.BooleanField()
    credential_alias_set = serializers.BooleanField()
    endpoint_alias_supported = serializers.BooleanField()
    credential_alias_supported = serializers.BooleanField()
    endpoint_alias = serializers.CharField(allow_blank=True)
    credential_alias = serializers.CharField(allow_blank=True)
    credential_alias_options = serializers.ListField(child=serializers.CharField())
    more_credential_aliases = serializers.BooleanField()
    credential_managed_here = serializers.BooleanField()
    credential_updated_at = serializers.DateTimeField(allow_null=True)
    credential_last_tested_at = serializers.DateTimeField(allow_null=True)
    credential_last_test_status = serializers.CharField(allow_blank=True)
    credential_last_test_message = serializers.CharField(allow_blank=True)
    last_success_at = serializers.DateTimeField(allow_null=True)
    last_failure_at = serializers.DateTimeField(allow_null=True)
    last_error_code = serializers.CharField(allow_blank=True)
    last_error_category = serializers.CharField(allow_blank=True)
    secret_values_exposed = serializers.BooleanField()


class ResearchSourceSnapshot(serializers.Serializer):
    version = serializers.CharField()
    configuration_version = serializers.CharField()
    generated_at = serializers.DateTimeField()
    adapters = ResearchSourceOutput(many=True)
    summary = serializers.DictField(child=serializers.IntegerField())
    permissions = serializers.DictField(child=serializers.BooleanField())
    secret_values_exposed = serializers.BooleanField()


class ResearchSourceProbeResult(serializers.Serializer):
    key = serializers.CharField()
    status = serializers.CharField()
    functional = serializers.BooleanField()
    productive = serializers.BooleanField()
    detail = serializers.CharField()


class AdminResearchSourceRegistryView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanViewSystemStatus()] if self.request.method in {'GET', 'HEAD', 'OPTIONS'} else [CanConfigureProviders()]

    @extend_schema(responses=ResearchSourceSnapshot)
    @transaction.atomic
    def get(self, request):
        actor = configuration.locked_actor(request, None, read=True)
        return Response(configuration.snapshot(actor))

    @extend_schema(request=SourceRegistryInput, responses=ResearchSourceSnapshot)
    @transaction.atomic
    def put(self, request):
        serializer = SourceRegistryInput(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = configuration.locked_actor(request, data['expected_version'])
        try:
            if data.get('credential'):
                configuration.apply_credential(actor, data['credential'], data['adapters'])
            sources.update_research_source_registry(data['adapters'], actor=actor, allow_sensitive_aliases=is_library_owner(actor))
        except (sources.ResearchSourceError, ProviderSecretError) as error:
            if error.code == 'owner_required': raise PermissionDenied({'code': error.code, 'detail': str(error)}) from error
            raise ValidationError({'code': error.code, 'detail': str(error)}) from error
        return Response(configuration.snapshot(actor))

    @extend_schema(request=SourceFenceInput, responses=ResearchSourceSnapshot)
    @transaction.atomic
    def patch(self, request):
        serializer = SourceFenceInput(data=request.data); serializer.is_valid(raise_exception=True)
        expected = serializer.validated_data['expected_version']
        actor = configuration.locked_actor(request, expected, allow_changed=True)
        configuration.fence(actor, expected)
        return Response(configuration.snapshot(actor))

    @extend_schema(request=SourceProbeInput, responses=ResearchSourceProbeResult)
    @transaction.atomic
    def post(self, request):
        serializer = SourceProbeInput(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = configuration.locked_actor(request, data['expected_version'])
        try:
            result = sources.test_research_source(data['source_key'], actor=actor)
        except sources.ResearchSourceError as error:
            raise ValidationError({'code': error.code, 'detail': str(error)}) from error
        functional = result.get('functional') is True
        return Response({'key': data['source_key'], 'status': str(result.get('status') or 'unknown')[:40],
            'functional': functional, 'productive': result.get('productive') is True,
            'detail': '公开样例检查已完成，返回内容质量仍须核对。' if functional else '该来源尚未通过公开样例检查，请核对配置、访问权限和服务状态。'})
