"""Read-only complete page projection for the existing placement editor."""
from django.http import Http404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin, current_editorial_version
from catalog.services import content_placements as placements
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from common.permissions import CanEditMetadata, IsKnowledgeEditor


class PlacementParentQuery(serializers.Serializer):
    expected_revision = serializers.CharField(max_length=80)


class PlacementParentPreviewSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    page_type = serializers.CharField()
    page_id = serializers.UUIDField()
    expected_revision = serializers.CharField()
    parent_version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    kind = serializers.ChoiceField(choices=["knowledge", "issue", "timeline_event"])
    page = serializers.JSONField()
    config = serializers.JSONField()


class PlacementParentPreviewView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(parameters=[PlacementParentQuery], responses=PlacementParentPreviewSerializer)
    def get(self, request, page_type, page_id):
        placements.authorize(request.user, page_type)
        if page_type == "site":
            raise ValidationError("首页编排请使用首页编辑器中的完整预览。")
        parent = placements.parent_object(page_type, page_id, actor=request.user)
        params = PlacementParentQuery(data=request.query_params)
        params.is_valid(raise_exception=True)
        expected = params.validated_data["expected_revision"]
        def placement_version():
            return placements.version(placements.revisions(page_type, page_id).first())
        if placement_version() != expected:
            raise EditConflict("编排已有新版本，当前输入保留，请重新核对后预览。")

        if page_type == "issue":
            from catalog.services.editorial_issues import edit_version
            from catalog.services.issue_publication_review import review
            version = edit_version("recommendation_issue", parent.pk)
            page = review(parent, request.user)["reader_preview"]
            unchanged = edit_version("recommendation_issue", parent.pk) == version
            kind = "issue"
        elif page_type == "timeline_event":
            from types import SimpleNamespace
            from django.contrib.auth.models import AnonymousUser
            from catalog.models import EditorialRevision
            from catalog.theory_serializers import NormalizedTimelineDetailSerializer
            from catalog.services.relation_editorial import timeline_preview_instance
            version = current_editorial_version("timeline_event", parent.pk)
            revision = EditorialRevision.objects.filter(target_type="timeline_event", target_id=parent.pk, status="draft").order_by("-revision").first()
            draft = timeline_preview_instance(parent, revision) if revision else parent
            viewer = SimpleNamespace(user=AnonymousUser(), path="/api/catalog/theories/timeline/", build_absolute_uri=request.build_absolute_uri)
            page = NormalizedTimelineDetailSerializer(draft, context={"request": viewer}).data
            unchanged = current_editorial_version("timeline_event", parent.pk) == version
            kind = "timeline_event"
        else:
            if not has_capability(request.user, Capability.VIEW_EVIDENCE):
                raise PermissionDenied("完整知识页面预览需要查看证据权限；当前编排输入保留。")
            from catalog.services.knowledge_studio import KnowledgeObjectEditorAdapter, NODE_OBJECT_TYPES, knowledge_object_preview_payload
            object_type = next((key for key, value in NODE_OBJECT_TYPES.items() if value == parent.node_type), None) if page_type == "node" else page_type
            target_type = KnowledgeObjectEditorAdapter.TARGET_TYPES.get(object_type)
            if not target_type:
                raise ValidationError("此知识对象类型尚无完整页面模板，请在原编辑器核对。")
            version = current_editorial_version(target_type, parent.pk)
            page = knowledge_object_preview_payload(object_type=object_type, object_id=str(parent.pk), reviewer=request.user)
            if page is None:
                raise Http404
            unchanged = current_editorial_version(target_type, parent.pk) == version
            kind = "knowledge"
        if not version or not unchanged or placement_version() != expected:
            raise EditConflict("生成预览期间资料已变化，请重新读取；当前编排输入保留。")
        from catalog.views import current_site_config
        return Response({"owner_id": str(request.user.pk), "page_type": page_type, "page_id": str(parent.pk),
                         "expected_revision": expected, "parent_version": version, "checked_at": timezone.now(),
                         "kind": kind, "page": page, "config": current_site_config()})
