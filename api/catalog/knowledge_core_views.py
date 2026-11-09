"""Transport adapters: source permissions also live in the application service."""
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import path
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import DocumentRevision, DocumentNode, EvidenceAnchor, RevisionPage, KnowledgePage, Entity, Assertion
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
        from catalog.models import Page
        from catalog.services.page_geometry import locator_geometry
        physical = Page.objects.filter(asset_id=revision.asset_id, index=page_number).values_list("id", flat=True).first()
        rect = page.geometry.get("page_rect", [0, 0, 0, 0])
        blocks = [{**block, "type": block.get("kind", "text"), "confidence": block.get("confidence", 0),
                   "geometry": page.geometry, **locator_geometry(block.get("bbox"), page.geometry)} for block in page.blocks]
        return Response({"asset_id": str(revision.asset_id), "document_revision_id": str(revision.pk),
            "page_id": str(physical) if physical else None, "snapshot_id": str(page.pk),
            "width": rect[2] - rect[0], "height": rect[3] - rect[1],
            "chapter_title": "", "text_available": bool(page.text),
            "page_index": page.page_number, "printed_label": page.printed_label, "text": page.text,
            "text_source": page.text_source, "content_hash": page.content_hash, "geometry": page.geometry,
            "blocks": blocks, "passages": [], "offset_unit": "unicode_code_point"})


class RevisionManifestView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, asset_id):
        from catalog.public_work_detail import PublicReaderWorkSerializer
        from catalog.serializers import AssetCompactSerializer
        revision = sources.requested_revision(request, asset_id)
        asset = revision.asset
        data = PublicReaderWorkSerializer(asset.edition.work, context={"request": request,
            "selected_edition": asset.edition, "reader_asset": asset}).data
        if not data.get("edition") or str(data["edition"].get("id")) != str(asset.edition_id):
            from rest_framework.exceptions import ValidationError
            raise ValidationError("该来源的版本书目信息尚不能读取。")
        data["edition"] = {**data["edition"], "readable_asset": AssetCompactSerializer(asset).data,
            "availability": "readable", "access_state": "readable"}
        structure = revision.structures.select_related("outline_revision").order_by("-created_at").first()
        outline_revision = structure.outline_revision if structure else revision.outline_revisions.filter(
            is_active=True, source_checksum=asset.sha256).first()
        from catalog.services.document_outline import reader_outline_nodes
        outline = reader_outline_nodes(outline_revision) if outline_revision and (
            outline_revision.document_revision_id == revision.pk and outline_revision.source_checksum == asset.sha256) else []
        return Response({"asset_id": str(asset.pk), "edition_id": str(asset.edition_id), "document_revision_id": str(revision.pk),
            "page_count": asset.page_count, "work": data, "outline": outline, "related_scholars": [], "related_theories": [], "related_topics": []},
            headers={"Cache-Control": "private, no-store"})


class KnowledgePageView(APIView):
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]

    def get(self, request, page_id):
        from catalog.services.knowledge_public import page_data
        page = get_object_or_404(KnowledgePage, pk=page_id)
        return Response(page_data(page, request.user, draft=request.query_params.get("preview") == "1"))

    def post(self, request, page_id):
        from catalog.services.knowledge_public import publish_page
        from rest_framework import serializers
        revision = serializers.UUIDField().run_validation(request.data.get("revision_id"))
        return Response(publish_page(page_id, revision, request.user))


class KnowledgeExportView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, page_id):
        from catalog.services.knowledge_core import export_page
        from catalog.services.knowledge_public import page_data
        page = get_object_or_404(KnowledgePage, pk=page_id)
        draft = request.query_params.get("preview") == "1"
        page_data(page, request.user, draft=draft)
        return HttpResponse(export_page(page, request.user, draft=draft), content_type="text/markdown; charset=utf-8")


class WorkKnowledgeView(APIView):
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]

    def get(self, request, work_id):
        from catalog.services.knowledge_public import page_data
        page = KnowledgePage.objects.filter(work_id=work_id, status="published").first()
        return Response({"page": page_data(page, request.user) if page else None})


class EntitiesView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request):
        from catalog.services.knowledge_core import entity_data, require_editor
        rows = Entity.objects.filter(merged_into__isnull=True)
        if request.query_params.get("preview") == "1":
            require_editor(request.user)
        else:
            rows = rows.filter(status="published")
        query = request.query_params.get("q", "")[:300]
        if query:
            rows = rows.filter(label__icontains=query)
        return Response({"entities": [entity_data(row) for row in rows.order_by("label")[:50]]})


class AssertionView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, assertion_id):
        from catalog.services.knowledge_public import assertion_data
        return Response(assertion_data(get_object_or_404(Assertion, pk=assertion_id), request.user, draft=request.query_params.get("preview") == "1"))


urlpatterns = [
    path("entities/", EntitiesView.as_view()),
    path("assertions/<uuid:assertion_id>/", AssertionView.as_view()),
    path("pages/<uuid:page_id>/", KnowledgePageView.as_view()),
    path("pages/<uuid:page_id>/export/", KnowledgeExportView.as_view()),
    path("works/<uuid:work_id>/", WorkKnowledgeView.as_view()),
    path("assets/<uuid:asset_id>/manifest/", RevisionManifestView.as_view()),
    path("revisions/<uuid:revision_id>/structure/", RevisionStructureView.as_view()),
    path("revisions/<uuid:revision_id>/pages/<int:page_number>/", RevisionPageView.as_view()),
    path("anchors/<uuid:anchor_id>/", AnchorView.as_view()),
    path("nodes/<uuid:node_id>/context/", NodeContextView.as_view()),
]
