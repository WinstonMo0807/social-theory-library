from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryAdmin

from .runtime_profiles import (
    runtime_profile_payload,
    save_runtime_profile_document,
    test_runtime_profile,
)
from .runtime_serializers import (
    AIRuntimeProfileDocumentSerializer,
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


class AdminAIRuntimeProfilesView(APIView):
    # ADMIN remains the compatibility operator for the existing runtime page;
    # destructive provider/credential changes still stay in server settings.
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        return Response(runtime_profile_payload())

    def put(self, request):
        serializer = AIRuntimeProfileDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")
        return Response(
            save_runtime_profile_document(
                serializer.validated_data,
                actor=request.user,
                request_id=request_id,
            )
        )


class AdminAIRuntimeProfileTestView(APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request):
        serializer = AIRuntimeProfileTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = test_runtime_profile(serializer.validated_data["profile_key"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(result)


class ReaderAIConnectionView(APIView):
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


class ReaderAIConnectionTestView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "library_qa"

    def post(self, request):
        try:
            return Response(test_connection(request.user))
        except ReaderAIConfigurationError as exc:
            return Response({"detail": str(exc), "code": getattr(exc, "code", "invalid_configuration")}, status=400)
