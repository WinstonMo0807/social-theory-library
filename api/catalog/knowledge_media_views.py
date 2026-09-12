from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.media_views import PublicCoverMediaSerializer
from catalog.models import EditorialRevision, MediaAsset
from catalog.services.knowledge_media import TARGETS, image_fingerprint, image_media, image_selection, select_knowledge_image, validate_image_selection
from catalog.theory_system_views import TheorySystemFeatureMixin
from common.permissions import CanAccessBackOffice, IsKnowledgeEditor


class KnowledgeImageRequestSerializer(serializers.Serializer):
    media_id = serializers.UUIDField(allow_null=True)
    fingerprint = serializers.RegexField(regex=r"^[a-f0-9]{64}$")


class KnowledgeImageStateSerializer(serializers.Serializer):
    object_type = serializers.ChoiceField(choices=["knowledge_node", "reading_path"])
    object_id = serializers.UUIDField()
    name = serializers.CharField()
    media = PublicCoverMediaSerializer(allow_null=True)
    preview_url = serializers.CharField(allow_blank=True)
    editorial_revision_id = serializers.UUIDField(allow_null=True)
    canonical_write_deferred = serializers.BooleanField()
    editor_url = serializers.CharField()
    fingerprint = serializers.CharField()


def image_target(object_type, object_id, *, public=False):
    if object_type not in TARGETS:
        raise NotFound("不支持的图片对象。")
    query = TARGETS[object_type].objects.all()
    if public:
        query = query.filter(status="published")
    return get_object_or_404(query, pk=object_id)


def image_state(target, object_type):
    draft = EditorialRevision.objects.filter(target_type=object_type, target_id=target.pk, status="draft").order_by("-revision").first()
    selection = (draft.materialized_preview.get("image_selection") if draft else None) or image_selection(target)
    selection = validate_image_selection(target, selection)
    media = image_media(target, selection=selection, private=True)
    url = next(row["url"] for row in media["renditions"] if row["id"] == media["primary_rendition_id"]) if media else target.cover_asset.url if selection["legacy_path"] else ""
    return {"object_type": object_type, "object_id": target.pk, "name": getattr(target, "canonical_name_zh", getattr(target, "title", "")), "media": media, "preview_url": url,
            "editorial_revision_id": draft.pk if draft else None, "canonical_write_deferred": draft is not None, "fingerprint": image_fingerprint(target, draft),
            "editor_url": f"/admin/theory-nodes?node={target.pk}" if object_type == "knowledge_node" else f"/admin/reading-paths?path={target.pk}"}


class KnowledgeImageSelectionView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
    def get_permissions(self):
        return [IsKnowledgeEditor()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(responses=KnowledgeImageStateSerializer)
    def get(self, request, object_type, object_id):
        target = image_target(object_type, object_id)
        try:
            state = image_state(target, object_type)
        except (ValueError, ValidationError) as error:
            return Response({"detail": str(error), "code": "image_preview_unavailable"}, status=409)
        return Response(KnowledgeImageStateSerializer(state).data)

    @extend_schema(request=KnowledgeImageRequestSerializer, responses=KnowledgeImageStateSerializer)
    def post(self, request, object_type, object_id):
        target = image_target(object_type, object_id)
        serializer = KnowledgeImageRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["media_id"]:
            get_object_or_404(MediaAsset, pk=serializer.validated_data["media_id"])
        try:
            select_knowledge_image(object_type, target.pk, actor=request.user, **serializer.validated_data)
        except (ValueError, ValidationError) as error:
            return Response({"detail": str(error), "code": "image_selection_failed"}, status=409)
        target.refresh_from_db()
        return Response(KnowledgeImageStateSerializer(image_state(target, object_type)).data)


class PublicKnowledgeImageView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request, object_type, object_id):
        from catalog.views import _public_media_response

        target = image_target(object_type, object_id, public=True)
        media = image_media(target)
        if media is None:
            raise NotFound("没有已发布的媒体图片。")
        return _public_media_response(request, media)
