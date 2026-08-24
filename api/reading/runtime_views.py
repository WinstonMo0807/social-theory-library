from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

from accounts.ownership import is_library_owner
from common.ai_runtime import current_profile_document, validate_profile_document
from common.permissions import CanManageAI

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
    permission_classes = [CanManageAI]

    @staticmethod
    def _payload(request):
        return {
            **runtime_profile_payload(),
            "permissions": {
                "can_edit_profiles": True,
                "can_edit_sensitive_aliases": is_library_owner(request.user),
                "can_remove_profiles": is_library_owner(request.user),
            },
        }

    def get(self, request):
        return Response(self._payload(request))

    def put(self, request):
        serializer = AIRuntimeProfileDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not is_library_owner(request.user):
            before = validate_profile_document(current_profile_document())
            after = serializer.validated_data
            before_rows = {row["key"]: row for row in before["profiles"]}
            after_rows = {row["key"]: row for row in after["profiles"]}
            removed = set(before_rows) - set(after_rows)
            aliases_changed = any(
                (
                    key in before_rows
                    and (
                        row.get("endpoint_alias") != before_rows[key].get("endpoint_alias")
                        or row.get("credential_alias") != before_rows[key].get("credential_alias")
                    )
                )
                or (
                    key not in before_rows
                    and (
                        row.get("endpoint_alias") not in {None, "", "default"}
                        or row.get("credential_alias") not in {None, "", "default"}
                    )
                )
                for key, row in after_rows.items()
            )
            if removed or aliases_changed:
                raise PermissionDenied(
                    "只有 System Owner 可以修改 endpoint/credential alias 或删除 AI runtime profile。"
                )
        request_id = str(request.META.get("HTTP_X_REQUEST_ID") or "")
        save_runtime_profile_document(
            serializer.validated_data,
            actor=request.user,
            request_id=request_id,
        )
        return Response(self._payload(request))


class AdminAIRuntimeProfileTestView(APIView):
    permission_classes = [CanManageAI]

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
