from __future__ import annotations

from rest_framework import serializers

from common.ai_runtime import (
    AICapability,
    SUPPORTED_AI_PROVIDERS,
    validate_profile_document,
)
from .models import ReaderAIConnection


class AIRuntimeProfileSerializer(serializers.Serializer):
    key = serializers.RegexField(r"^[a-z][a-z0-9_-]{1,63}$", max_length=64)
    capability = serializers.ChoiceField(choices=[(value, value) for value in AICapability.VALUES])
    provider = serializers.ChoiceField(choices=[(value, value) for value in sorted(SUPPORTED_AI_PROVIDERS)])
    model = serializers.CharField(max_length=300, allow_blank=True)
    enabled = serializers.BooleanField()
    temperature = serializers.FloatField(min_value=0, max_value=2)
    max_output_tokens = serializers.IntegerField(min_value=128, max_value=8192)
    timeout_seconds = serializers.IntegerField(min_value=3, max_value=600)
    max_input_chars = serializers.IntegerField(min_value=1000, max_value=100000)
    endpoint_alias = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,63}$", max_length=64)
    credential_alias = serializers.RegexField(r"^[a-z][a-z0-9_-]{0,63}$", max_length=64)
    retrieval_profile = serializers.ChoiceField(choices=[("stable", "stable"), ("experimental_v2", "experimental_v2")])
    answer_behavior = serializers.CharField(max_length=64)
    fallback_profile_key = serializers.CharField(max_length=64, allow_blank=True, required=False)
    reasoning = serializers.JSONField(required=False, default=dict)


class AIRuntimeProfileDocumentSerializer(serializers.Serializer):
    active = serializers.DictField(child=serializers.CharField(max_length=64))
    profiles = AIRuntimeProfileSerializer(many=True, min_length=1, max_length=24)

    def validate(self, attrs):
        try:
            return validate_profile_document(attrs)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class AIRuntimeProfileTestSerializer(serializers.Serializer):
    profile_key = serializers.CharField(max_length=64)


class ReaderAIConnectionSerializer(serializers.Serializer):
    provider = serializers.ChoiceField(choices=ReaderAIConnection.Provider.choices)
    base_url = serializers.URLField(max_length=2000)
    model = serializers.CharField(max_length=300)
    api_key = serializers.CharField(max_length=4000, write_only=True, required=False, allow_blank=True)
    enabled = serializers.BooleanField(default=True)
