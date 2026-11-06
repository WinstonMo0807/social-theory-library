from __future__ import annotations

from rest_framework import serializers

from common.ai_runtime import (
    AICapability,
    SUPPORTED_AI_PROVIDERS,
)
from .models import ReaderAIConnection


class StrictRuntimeInput(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('只接受当前模型配置字段。')
        return super().to_internal_value(data)


class AIRuntimeProfileSerializer(StrictRuntimeInput):
    key = serializers.RegexField(r"^[a-z][a-z0-9_-]{1,63}$", max_length=64)
    capability = serializers.ChoiceField(choices=[(value, value) for value in AICapability.VALUES])
    provider = serializers.ChoiceField(choices=[(value, value) for value in sorted(SUPPORTED_AI_PROVIDERS)])
    model = serializers.CharField(max_length=300, allow_blank=True)
    enabled = serializers.BooleanField()
    temperature = serializers.FloatField(min_value=0, max_value=2)
    max_output_tokens = serializers.IntegerField(min_value=128, max_value=8192)
    timeout_seconds = serializers.IntegerField(min_value=3, max_value=600)
    max_input_chars = serializers.IntegerField(min_value=1000, max_value=100000)
    endpoint_alias = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,63}$", max_length=64, required=False)
    credential_alias = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,63}$", max_length=64, required=False)
    retrieval_profile = serializers.ChoiceField(choices=[("stable", "stable"), ("experimental_v2", "experimental_v2")])
    answer_behavior = serializers.CharField(max_length=64)
    fallback_profile_key = serializers.CharField(max_length=64, allow_blank=True, required=False)
    reasoning = serializers.JSONField(required=False, default=dict)


class RuntimeCredentialInput(StrictRuntimeInput):
    action = serializers.ChoiceField(choices=['set', 'delete'])
    profile_key = serializers.RegexField(r'^[a-z][a-z0-9_-]{1,63}$')
    alias = serializers.RegexField(r'^[a-z][a-z0-9_-]{0,63}$')
    secret = serializers.CharField(write_only=True, max_length=16384, trim_whitespace=False, required=False)
    confirm_delete = serializers.BooleanField(default=False)

    def validate(self, values):
        if values['action'] == 'set' and not values.get('secret'):
            raise serializers.ValidationError('请输入要加密保存的新凭据。')
        return values


class AIRuntimeVersionInput(StrictRuntimeInput):
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')


class RuntimeEndpointInput(StrictRuntimeInput):
    profile_key = serializers.RegexField(r'^[a-z][a-z0-9_-]{1,63}$')
    base_url = serializers.CharField(max_length=2000, write_only=True)


class AIRuntimeProfileDocumentSerializer(AIRuntimeVersionInput):
    active = serializers.DictField(child=serializers.CharField(max_length=64))
    profiles = AIRuntimeProfileSerializer(many=True, min_length=1, max_length=48)
    credential = RuntimeCredentialInput(required=False)
    endpoint = RuntimeEndpointInput(required=False)

    def validate_active(self, value):
        if set(value) - set(AICapability.VALUES):
            raise serializers.ValidationError('存在未知模型能力。')
        return value


class AIRuntimeProfileTestSerializer(AIRuntimeVersionInput):
    profile_key = serializers.CharField(max_length=64)


class RuntimeEnvironmentOutput(serializers.Serializer):
    endpoint_configured = serializers.BooleanField()
    credential_configured = serializers.BooleanField()
    restart_may_be_required = serializers.BooleanField()


class AIRuntimeProfileOutput(AIRuntimeProfileSerializer):
    endpoint_alias = serializers.CharField(allow_blank=True)
    credential_alias = serializers.CharField(allow_blank=True)
    environment = RuntimeEnvironmentOutput()
    credential_storage = serializers.ChoiceField(choices=['environment', 'saved', 'absent'])
    credential_managed_here = serializers.BooleanField()


class RuntimePermissionsOutput(serializers.Serializer):
    can_edit_profiles = serializers.BooleanField()
    can_edit_sensitive_aliases = serializers.BooleanField()
    can_remove_profiles = serializers.BooleanField()


class AIRuntimeSnapshot(serializers.Serializer):
    configuration_version = serializers.CharField()
    version = serializers.CharField()
    source = serializers.CharField()
    active = serializers.DictField(child=serializers.CharField())
    profiles = AIRuntimeProfileOutput(many=True)
    permissions = RuntimePermissionsOutput()
    secret_values_exposed = serializers.BooleanField()
    hot_reload_fields = serializers.ListField(child=serializers.CharField())
    deployment_fields = serializers.ListField(child=serializers.CharField())
    credential_alias_options = serializers.ListField(child=serializers.CharField())
    more_credential_aliases = serializers.BooleanField()


class AIRuntimeProbeResult(serializers.Serializer):
    profile_key = serializers.CharField()
    capability = serializers.CharField()
    provider = serializers.CharField()
    model = serializers.CharField()
    configured = serializers.BooleanField()
    available = serializers.BooleanField()
    status = serializers.CharField()
    detail = serializers.CharField()
    secret_values_exposed = serializers.BooleanField()


class ReaderAIConnectionSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=ReaderAIConnection.Provider.choices)
    base_url = serializers.URLField(max_length=2000)
    model = serializers.CharField(max_length=300)
    api_key = serializers.CharField(max_length=4000, write_only=True, required=False, allow_blank=True)
    enabled = serializers.BooleanField(default=True)
