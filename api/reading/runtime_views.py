from __future__ import annotations

from common.private_responses import PrivateAccountResponses
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from django.db import transaction
from drf_spectacular.utils import extend_schema
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.services.provider_secrets import ProviderSecretError
from . import runtime_configuration as configuration

from common.permissions import CanManageAI

from .runtime_profiles import (
    test_runtime_profile,
)
from .runtime_serializers import (
    AIRuntimeProfileDocumentSerializer, AIRuntimeSnapshot, AIRuntimeVersionInput, AIRuntimeProbeResult,
    AIRuntimeProfileTestSerializer,
    ReaderAIConnectionSerializer,
)
from .user_ai import (
    ReaderAIConfigurationError,
    connection_payload,
    delete_connection,
    save_connection,
    test_connection,
)
from rest_framework.permissions import IsAuthenticated


class AdminAIRuntimeProfilesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanManageAI]

    @extend_schema(responses=AIRuntimeSnapshot)
    @transaction.atomic
    def get(self, request):
        return Response(configuration.snapshot(configuration.locked_actor(request, read=True)))

    @extend_schema(request=AIRuntimeProfileDocumentSerializer, responses=AIRuntimeSnapshot)
    @transaction.atomic
    def put(self, request):
        serializer = AIRuntimeProfileDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actor = configuration.locked_actor(request, serializer.validated_data['expected_version'])
        try:
            result = configuration.save(actor, serializer.validated_data, request_id=str(request.META.get('HTTP_X_REQUEST_ID') or ''))
        except ProviderSecretError as exc:
            raise ValidationError(str(exc)) from exc
        return Response(result)

    @extend_schema(request=AIRuntimeVersionInput, responses=AIRuntimeSnapshot)
    @transaction.atomic
    def patch(self, request):
        serializer = AIRuntimeVersionInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        expected = serializer.validated_data['expected_version']
        actor = configuration.locked_actor(request, expected, allow_changed=True)
        configuration.fence(actor, expected)
        return Response(configuration.snapshot(actor))


class AdminAIRuntimeProfileTestView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanManageAI]

    @extend_schema(request=AIRuntimeProfileTestSerializer, responses=AIRuntimeProbeResult)
    @transaction.atomic
    def post(self, request):
        serializer = AIRuntimeProfileTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        configuration.locked_actor(request, serializer.validated_data['expected_version'])
        try:
            result = test_runtime_profile(serializer.validated_data['profile_key'])
        except ValueError as exc:
            raise ValidationError('当前模型配置不能执行连通检查，请重新读取并核对配置。') from exc
        return Response(result)


class ReaderAIConnectionView(PrivateAccountResponses, APIView):
    """Per-reader provider connection; the encrypted key is never serialized."""

    permission_classes = [IsAuthenticated]
    throttle_scope = "library_qa"

    def get(self, request):
        return Response(connection_payload(request.user))

    def put(self, request):
        serializer = ReaderAIConnectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = save_connection(request.user, **serializer.validated_data)
        except ReaderAIConfigurationError as exc:
            return Response({"detail": str(exc), "code": getattr(exc, "code", "invalid_configuration")}, status=400)
        return Response(payload)

    def delete(self, request):
        delete_connection(request.user)
        return Response({"configured": False, "status": "not_configured"})


class ReaderAIConnectionTestView(PrivateAccountResponses, APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "library_qa"

    def post(self, request):
        try:
            return Response(test_connection(request.user))
        except ReaderAIConfigurationError as exc:
            return Response({"detail": str(exc), "code": getattr(exc, "code", "invalid_configuration")}, status=400)
