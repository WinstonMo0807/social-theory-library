"""Canonical search transport uses the existing durable first/deep sessions."""
from django.urls import path
from catalog.discovery_views import (DiscoverySearchView, DiscoverySearchDetailView,
    DiscoverySearchContextView, DiscoverySearchCancelView, DiscoverySearchRetryView)
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from common.permissions import CanEditMetadata
from catalog.services import source_workspace


class SourceDirectory(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        ids = {name: serializers.UUIDField().run_validation(request.query_params[name])
               for name in ("work_id", "revision_id") if request.query_params.get(name)}
        return Response(source_workspace.source_directory(request.user, query=request.query_params.get("q", "")[:300], **ids))


class InspectRetrieval(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request):
        revision = serializers.UUIDField().run_validation(request.data["revision_id"]) if request.data.get("revision_id") else None
        try:
            return Response(source_workspace.inspect_retrieval(request.user, request.data.get("q"),
                revision_id=revision, mode=request.data.get("mode", "hybrid")))
        except source_workspace.DiscoveryIndexError as exc:
            return Response({"code": exc.code, "detail": str(exc)}, status=503)

urlpatterns = [
    path("sources/", SourceDirectory.as_view()),
    path("inspect/", InspectRetrieval.as_view()),
    path("sessions/", DiscoverySearchView.as_view()),
    path("sessions/<uuid:session_id>/", DiscoverySearchDetailView.as_view()),
    path("sessions/<uuid:session_id>/context/", DiscoverySearchContextView.as_view()),
    path("sessions/<uuid:session_id>/cancel/", DiscoverySearchCancelView.as_view()),
    path("sessions/<uuid:session_id>/retry/", DiscoverySearchRetryView.as_view()),
]
