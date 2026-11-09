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
        structure = sources.current_structure(revision)
        return Response({"document_revision_id": str(revision.pk), "structure_id": str(structure.pk) if structure else None,
            "coverage": structure.coverage if structure else {"structure_status": "not_prepared"},
            "nodes": list(structure.nodes.exclude(kind="paragraph").values("id", "parent_id", "kind", "order", "title", "content_hash")) if structure else []})

    def post(self, request, revision_id):
        self.check_object_permissions(request, None)
        if not CanEditMetadata().has_permission(request, self):
            self.permission_denied(request)
        revision = get_object_or_404(DocumentRevision, pk=revision_id)
        sources.require_revision_access(revision,request.user,editorial=True)
        from catalog.services.knowledge_source_updates import schedule_source_update
        job=schedule_source_update(revision)
        return Response({"job_id":str(job.pk),"status":job.status},status=202)


class AnchorView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, anchor_id):
        anchor = get_object_or_404(EvidenceAnchor.objects.select_related("document_revision__asset__edition"), pk=anchor_id)
        return Response(sources.locator(anchor, request.user, editorial=request.query_params.get("preview") == "1"))


class AssertionDraftView(APIView):
    permission_classes=[CanEditMetadata]

    def post(self,request,revision_id):
        from catalog.services.knowledge_workspace import submit_assertion_draft
        from catalog.services.intelligence_queries import changeset_data
        revision=get_object_or_404(DocumentRevision,pk=revision_id)
        changeset=submit_assertion_draft(revision,request.data.get("assertion"),request.user,request_id=request.data.get("request_id"))
        return Response(changeset_data(changeset,request.user),status=201)


class ParseStructureView(APIView):
    permission_classes = [CanEditMetadata]

    def post(self,request,revision_id):
        from catalog.services.document_structure import request_structure
        revision=get_object_or_404(DocumentRevision,pk=revision_id)
        job=request_structure(revision,request.user,pages=request.data.get("pages"),request_id=request.data.get("request_id"))
        return Response({"job_id":str(job.pk),"status":job.status,"pages":job.stats["input"]["pages"]},status=202)


class VerifyAnchorView(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request):
        from rest_framework import serializers
        from catalog.services.source_workspace import verify_selection
        revision = serializers.UUIDField().run_validation(request.data.get("document_revision_id"))
        return Response(verify_selection(request.user, revision, request.data.get("segments")), status=201)


class NodeContextView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, node_id):
        from rest_framework import serializers
        field = serializers.IntegerField(min_value=1, max_value=60000)
        budget = field.run_validation(request.query_params.get("budget", 12000))
        node = get_object_or_404(DocumentNode, pk=node_id)
        offset = serializers.IntegerField(min_value=0).run_validation(request.query_params.get("offset", 0))
        return Response(sources.context(node, request.user, budget=budget, offset=offset,
            scope=request.query_params.get("scope", "node"), editorial=request.query_params.get("preview") == "1"))


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


class RevisionReindexView(APIView):
    permission_classes = [CanEditMetadata]

    def post(self,request,revision_id):
        from catalog.services.knowledge_core import require_editor
        from catalog.services.knowledge_sources import require_revision_access
        from catalog.services.discovery_indexing import request_source_reindex
        from catalog.services.discovery_projection import DiscoveryIndexError
        require_editor(request.user)
        revision=get_object_or_404(DocumentRevision,pk=revision_id)
        require_revision_access(revision,request.user,editorial=True)
        try: job=request_source_reindex(revision,keyword_only=True)
        except DiscoveryIndexError as exc:
            return Response({"code":exc.code,"detail":str(exc)},status=409)
        return Response({"job_id":str(job.pk),"status":job.status},status=202)


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
            from catalog.services.knowledge_public import public_entities
            rows = rows.filter(pk__in=public_entities().values("pk"))
        query = request.query_params.get("q", "")[:300]
        if query:
            rows = rows.filter(label__icontains=query)
        return Response({"entities": [entity_data(row) for row in rows.order_by("label")[:50]]})


class EntityKnowledgeView(APIView):
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]

    def get(self, request, source_type, source_id):
        from django.http import Http404
        from catalog.services.knowledge_public import page_data
        fields = {"person": "person_id", "node": "node_id", "topic": "topic_id",
                  "discipline": "discipline_id", "subdiscipline": "subdiscipline_id"}
        if source_type not in fields:
            raise Http404
        from catalog.services.knowledge_public import public_entities
        page = KnowledgePage.objects.filter(entity_id__in=public_entities().values("pk"),
            status="published", **{f"entity__{fields[source_type]}": source_id}).first()
        return Response({"page": page_data(page, request.user) if page else None})


class AssertionView(APIView):
    permission_classes = [CanReadLibrary]

    def get(self, request, assertion_id):
        from catalog.services.knowledge_public import assertion_data
        return Response(assertion_data(get_object_or_404(Assertion, pk=assertion_id), request.user, draft=request.query_params.get("preview") == "1"))


class KnowledgeDirectoryView(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request):
        from rest_framework import serializers
        from catalog.services.knowledge_workspace import page_directory
        offset = serializers.IntegerField(min_value=0).run_validation(request.query_params.get("offset", 0))
        limit = serializers.IntegerField(min_value=1, max_value=100).run_validation(request.query_params.get("limit", 30))
        return Response(page_directory(request.user, query=request.query_params.get("q", "")[:300],
            kind=request.query_params.get("kind", ""), state=request.query_params.get("state", ""), offset=offset, limit=limit))

    def post(self, request):
        from rest_framework import serializers
        from catalog.services.knowledge_workspace import open_page
        ids = {name: serializers.UUIDField().run_validation(request.data[name])
               for name in ("work_id", "entity_id") if request.data.get(name)}
        return Response(open_page(request.user, **ids), status=201)


class KnowledgeWorkspaceView(APIView):
    permission_classes = [CanEditMetadata]

    def get(self, request, page_id):
        from catalog.services.knowledge_workspace import page_workspace
        return Response(page_workspace(get_object_or_404(KnowledgePage, pk=page_id), request.user))

    def post(self, request, page_id):
        from rest_framework import serializers
        from catalog.services.knowledge_workspace import submit_page_changes
        from catalog.services.intelligence_queries import changeset_data
        page = get_object_or_404(KnowledgePage, pk=page_id)
        revision = get_object_or_404(DocumentRevision, pk=serializers.UUIDField().run_validation(request.data["document_revision_id"])) if request.data.get("document_revision_id") else None
        result = submit_page_changes(page, revision, request.data.get("patches"), request.user, request_id=request.data.get("request_id"))
        return Response(changeset_data(result, request.user), status=201)


class PageAssertionDraftView(APIView):
    permission_classes = [CanEditMetadata]

    def post(self, request, page_id):
        from rest_framework import serializers
        from catalog.services.knowledge_workspace import submit_page_assertion
        from catalog.services.intelligence_queries import changeset_data
        page = get_object_or_404(KnowledgePage, pk=page_id)
        revision = get_object_or_404(DocumentRevision, pk=serializers.UUIDField().run_validation(request.data["document_revision_id"])) if request.data.get("document_revision_id") else None
        result = submit_page_assertion(page, request.data.get("assertion"), request.user,
            request_id=request.data.get("request_id"), revision=revision)
        return Response(changeset_data(result, request.user), status=201)


urlpatterns = [
    path("anchors/verify/", VerifyAnchorView.as_view()),
    path("workspace/", KnowledgeDirectoryView.as_view()),
    path("pages/<uuid:page_id>/workspace/", KnowledgeWorkspaceView.as_view()),
    path("pages/<uuid:page_id>/assertions/draft/", PageAssertionDraftView.as_view()),
    path("entities/", EntitiesView.as_view()),
    path("objects/<str:source_type>/<uuid:source_id>/", EntityKnowledgeView.as_view()),
    path("assertions/<uuid:assertion_id>/", AssertionView.as_view()),
    path("pages/<uuid:page_id>/", KnowledgePageView.as_view()),
    path("pages/<uuid:page_id>/export/", KnowledgeExportView.as_view()),
    path("works/<uuid:work_id>/", WorkKnowledgeView.as_view()),
    path("revisions/<uuid:revision_id>/reindex/",RevisionReindexView.as_view()),
    path("assets/<uuid:asset_id>/manifest/", RevisionManifestView.as_view()),
    path("revisions/<uuid:revision_id>/structure/", RevisionStructureView.as_view()),
    path("revisions/<uuid:revision_id>/assertions/draft/", AssertionDraftView.as_view()),
    path("revisions/<uuid:revision_id>/structure/parse/", ParseStructureView.as_view()),
    path("revisions/<uuid:revision_id>/pages/<int:page_number>/", RevisionPageView.as_view()),
    path("anchors/<uuid:anchor_id>/", AnchorView.as_view()),
    path("nodes/<uuid:node_id>/context/", NodeContextView.as_view()),
]
