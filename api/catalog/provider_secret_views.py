from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanManageProviders

from catalog.services.provider_secrets import (
    ProviderSecretError,
    delete_provider_secret,
    provider_secret_registry_payload,
    set_provider_secret,
)


class AdminProviderSecretView(APIView):
    """Owner-only encrypted credential management; never returns plaintext."""

    permission_classes = [CanManageProviders]

    def get(self, request):
        return Response(provider_secret_registry_payload())

    def post(self, request):
        action = str(request.data.get("action") or "set").strip().casefold()
        try:
            if action == "set":
                set_provider_secret(
                    alias=request.data.get("alias"),
                    purpose=str(request.data.get("purpose") or ""),
                    provider_key=request.data.get("provider_key"),
                    secret=request.data.get("secret"),
                    actor=request.user,
                    request_id=str(request.META.get("HTTP_X_REQUEST_ID") or ""),
                )
            elif action == "delete":
                delete_provider_secret(
                    alias=request.data.get("alias"),
                    actor=request.user,
                    request_id=str(request.META.get("HTTP_X_REQUEST_ID") or ""),
                )
            else:
                raise ProviderSecretError("invalid_action", "action 必须是 set 或 delete。")
        except ProviderSecretError as exc:
            return Response(
                {"code": exc.code, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(provider_secret_registry_payload())
