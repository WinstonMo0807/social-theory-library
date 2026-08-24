from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.ownership import is_library_owner
from common.permissions import CanConfigureProviders, CanViewSystemStatus

from catalog.services.research_sources import (
    ResearchSourceError,
    research_source_registry_payload,
    test_research_source,
    update_research_source_registry,
)


class AdminResearchSourceRegistryView(APIView):
    """Safe configuration and explicit tests for registered research sources."""

    def get_permissions(self):
        if self.request.method in {"PUT", "POST"}:
            return [CanConfigureProviders()]
        return [CanViewSystemStatus()]

    def get(self, request):
        return Response(research_source_registry_payload(user=request.user))

    def put(self, request):
        try:
            update_research_source_registry(
                request.data.get("adapters"),
                actor=request.user,
                allow_sensitive_aliases=is_library_owner(request.user),
                request_id=str(request.META.get("HTTP_X_REQUEST_ID") or ""),
            )
        except ResearchSourceError as exc:
            response_status = (
                status.HTTP_403_FORBIDDEN
                if exc.code == "owner_required"
                else status.HTTP_400_BAD_REQUEST
            )
            return Response(
                {"code": exc.code, "detail": str(exc)},
                status=response_status,
            )
        return Response(research_source_registry_payload(user=request.user))

    def post(self, request):
        action = str(request.data.get("action") or "").strip().casefold()
        if action != "test":
            return Response(
                {"detail": "action 必须是 test。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            result = test_research_source(
                str(request.data.get("source_key") or ""),
                actor=request.user,
            )
        except ResearchSourceError as exc:
            return Response(
                {"code": exc.code, "detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(result)
