"""Transport adapters: source permissions also live in the application service."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import DocumentRevision, DocumentNode, EvidenceAnchor, RevisionPage
from catalog.services import knowledge_sources as sources
from common.permissions import CanReadLibrary, CanEditMetadata


class RevisionStructureView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, revision_id):
        revision = get_object_or_404(DocumentRevision.objects.select_related("asset__edition"), pk=revision_id)
        sources.require_revision_access(revision, request.user, editorial=request.query_params.get("preview") == "1")
        structure = revision.structures.order_by("-created_at").first()
        return Response({"document_revision_id": str(revision.pk), "structure_id": str(structure.pk) if structure else None,
            "coverage": structure.coverage if structure else {"structure_status": "not_prepared"},
            "nodes": list(structure.nodes.exclude(kind="paragraph").values("id", "parent_id", "kind", "order", "title", "content_hash")) if structure else []})

    def post(self, request, revision_id):
        self.check_object_permissions(request, None)
        if not CanEditMetadata().has_permission(request, self):
            self.permission_denied(request)
        revision = get_object_or_404(DocumentRevision, pk=revision_id)
        structure = sources.build_structure(revision)
        return Response({"structure_id": str(structure.pk), "coverage": structure.coverage})


class AnchorView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, anchor_id):
        anchor = get_object_or_404(EvidenceAnchor.objects.select_related("document_revision__asset__edition"), pk=anchor_id)
        return Response(sources.locator(anchor, request.user, editorial=request.query_params.get("preview") == "1"))


class NodeContextView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, node_id):
        from rest_framework import serializers
        field = serializers.IntegerField(min_value=1, max_value=60000)
        budget = field.run_validation(request.query_params.get("budget", 12000))
        node = get_object_or_404(DocumentNode, pk=node_id)
        return Response(sources.context(node, request.user, budget=budget, editorial=request.query_params.get("preview") == "1"))


class RevisionPageView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, revision_id, page_number):
        revision = get_object_or_404(DocumentRevision, pk=revision_id)
        sources.require_revision_access(revision, request.user, editorial=request.query_params.get("preview") == "1")
        page = get_object_or_404(RevisionPage, document_revision=revision, page_number=page_number)
        return Response({"asset_id": str(revision.asset_id), "document_revision_id": str(revision.pk),
            "page_index": page.page_number, "printed_label": page.printed_label, "text": page.text,
            "text_source": page.text_source, "content_hash": page.content_hash, "geometry": page.geometry,
            "blocks": page.blocks, "passages": [], "offset_unit": "unicode_code_point"})


urlpatterns = [
    path("revisions/<uuid:revision_id>/structure/", RevisionStructureView.as_view()),
    path("revisions/<uuid:revision_id>/pages/<int:page_number>/", RevisionPageView.as_view()),
    path("anchors/<uuid:anchor_id>/", AnchorView.as_view()),
    path("nodes/<uuid:node_id>/context/", NodeContextView.as_view()),
]
