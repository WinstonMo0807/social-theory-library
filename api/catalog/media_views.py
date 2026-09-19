from django.core.exceptions import ValidationError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition, MediaAsset, MediaRendition
from catalog.services.media import MEDIA_SOURCE_TYPES, build_rendition, ingest_image, select_work_image, update_media_metadata, media_reference_inventory
from common.permissions import CanAccessBackOffice, CanEditMetadata


class MediaRenditionSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaRendition
        fields = ("id", "kind", "requested_width", "width", "height", "checksum", "byte_size", "url")

    def get_url(self, obj) -> str:
        return f"/api/catalog/admin/media/renditions/{obj.pk}/file/"


class MediaAssetSerializer(serializers.ModelSerializer):
    renditions = MediaRenditionSerializer(many=True, read_only=True)

    class Meta:
        model = MediaAsset
        fields = ("id", "media_type", "source_type", "source_url", "source_label", "rights", "license", "credit", "alt_text",
                  "width", "height", "checksum", "byte_size", "focal_x", "focal_y", "created_at", "updated_at", "renditions")


class MediaMetadataSerializer(serializers.Serializer):
    expected_updated_at = serializers.DateTimeField(required=False)
    source_type = serializers.ChoiceField(choices=MEDIA_SOURCE_TYPES, required=False)
    source_url = serializers.URLField(max_length=1000, allow_blank=True, required=False)
    source_label = serializers.CharField(max_length=300, allow_blank=True, required=False)
    rights = serializers.CharField(max_length=4000, allow_blank=True, required=False)
    license = serializers.CharField(max_length=200, allow_blank=True, required=False)
    credit = serializers.CharField(max_length=500, allow_blank=True, required=False)
    alt_text = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    focal_x = serializers.FloatField(min_value=0, max_value=1, required=False)
    focal_y = serializers.FloatField(min_value=0, max_value=1, required=False)


class MediaUploadSerializer(MediaMetadataSerializer):
    image = serializers.FileField()


class MediaCollectionSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = MediaAssetSerializer(many=True)


class MediaCollectionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=MediaCollectionSerializer)
    def get(self, request):
        from django.core.paginator import Paginator, InvalidPage
        rows = MediaAsset.objects.prefetch_related("renditions").order_by("-created_at", "pk")
        pagination = Paginator(rows, 30)
        try:
            page = pagination.page(request.query_params.get("page", 1))
        except (ValueError, InvalidPage):
            return Response({"detail": "媒体页码不存在，请返回第一页。"}, status=404)
        return Response(MediaCollectionSerializer({"count": pagination.count, "page": page.number, "page_size": 30,
                                                  "pages": pagination.num_pages, "results": page.object_list}).data)


class MediaDetailSerializer(MediaAssetSerializer):
    references = serializers.JSONField(read_only=True)

    class Meta(MediaAssetSerializer.Meta):
        fields = MediaAssetSerializer.Meta.fields + ("references",)


class MediaListView(AdminPrivateResponseMixin, APIView):
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(responses=MediaAssetSerializer(many=True))
    def get(self, request):
        rows = MediaAsset.objects.prefetch_related("renditions").order_by("-created_at")[:60]
        return Response(MediaAssetSerializer(rows, many=True).data)

    @extend_schema(request=MediaUploadSerializer, responses={201: MediaAssetSerializer, 200: MediaAssetSerializer})
    def post(self, request):
        serializer = MediaUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("expected_updated_at", None)
        try:
            row, created = ingest_image(data.pop("image"), actor=request.user, metadata=data)
            build_rendition(row.pk, width=320, kind="thumbnail")
        except (ValueError, ValidationError) as error:
            return Response({"code": "media.invalid_image", "detail": str(error)}, status=400)
        return Response(MediaAssetSerializer(row).data, status=201 if created else 200)


class MediaDetailView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "PATCH" else [CanAccessBackOffice()]

    @extend_schema(responses=MediaDetailSerializer)
    def get(self, request, media_id):
        media = get_object_or_404(MediaAsset.objects.prefetch_related("renditions"), pk=media_id)
        media.references = media_reference_inventory(media.pk)
        return Response(MediaDetailSerializer(media).data)

    @extend_schema(request=MediaMetadataSerializer, responses=MediaAssetSerializer)
    def patch(self, request, media_id):
        get_object_or_404(MediaAsset, pk=media_id)
        serializer = MediaMetadataSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            data = dict(serializer.validated_data)
            expected = data.pop("expected_updated_at", None)
            row = update_media_metadata(media_id, actor=request.user, metadata=data, expected_updated_at=expected)
        except (ValueError, ValidationError) as error:
            return Response({"code": "media.invalid_metadata", "detail": str(error)}, status=400)
        return Response(MediaAssetSerializer(row).data)


class MediaRenditionRequestSerializer(serializers.Serializer):
    width = serializers.ChoiceField(choices=[320, 640, 1280], default=640)
    kind = serializers.ChoiceField(choices=["cover", "portrait", "hero", "card", "thumbnail"], default="cover")


class MediaRenditionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(request=MediaRenditionRequestSerializer, responses=MediaRenditionSerializer)
    def post(self, request, media_id):
        get_object_or_404(MediaAsset, pk=media_id)
        serializer = MediaRenditionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(MediaRenditionSerializer(build_rendition(media_id, **serializer.validated_data)).data)


class MediaRenditionFileView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(exclude=True)
    def get(self, request, rendition_id):
        rendition = get_object_or_404(MediaRendition, pk=rendition_id)
        try:
            handle = rendition.file.open("rb")
        except OSError:
            return Response({"code": "media.file_unavailable", "detail": "图片暂时无法读取。"}, status=503)
        response = FileResponse(handle, content_type="image/webp")
        response["X-Content-Type-Options"] = "nosniff"
        response["ETag"] = f'"{rendition.checksum}"'
        return response


class CoverMediaSelectionSerializer(serializers.Serializer):
    media_id = serializers.UUIDField()


class CoverMediaSelectionResultSerializer(serializers.Serializer):
    saved = serializers.BooleanField()
    media_id = serializers.UUIDField(allow_null=True)
    edition_id = serializers.UUIDField()
    editorial_revision_id = serializers.UUIDField(allow_null=True)
    workbench_url = serializers.CharField()
    canonical_write_deferred = serializers.BooleanField()


class WorkCoverMediaSelectionView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]
    image_slot = "cover"

    @extend_schema(request=CoverMediaSelectionSerializer, responses=CoverMediaSelectionResultSerializer)
    def post(self, request, edition_id):
        get_object_or_404(Edition, pk=edition_id)
        serializer = CoverMediaSelectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = get_object_or_404(MediaAsset, pk=serializer.validated_data["media_id"])
        try:
            result = select_work_image(edition_id, media.pk, slot=self.image_slot, actor=request.user)
        except (ValueError, ValidationError) as error:
            return Response({"code": "media.selection_failed", "detail": str(error)}, status=409)
        return Response(result)


class WorkRecommendationMediaSelectionView(WorkCoverMediaSelectionView):
    image_slot = "recommendation"


class PublicMediaRenditionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    width = serializers.IntegerField()
    height = serializers.IntegerField()
    url = serializers.CharField()


class PublicCoverMediaSerializer(serializers.Serializer):
    media_id = serializers.UUIDField()
    primary_rendition_id = serializers.UUIDField()
    alt_text = serializers.CharField(allow_blank=True)
    source_label = serializers.CharField(allow_blank=True)
    source_url = serializers.CharField(allow_blank=True)
    rights = serializers.CharField(allow_blank=True)
    license = serializers.CharField(allow_blank=True)
    credit = serializers.CharField(allow_blank=True)
    renditions = PublicMediaRenditionSerializer(many=True)


class PublicCoverMetadataView(APIView):
    permission_classes = [AllowAny]
    image_slot = "cover"

    @extend_schema(responses=PublicCoverMediaSerializer)
    def get(self, request, work_id):
        from catalog.views import _active_work_snapshot, public_works

        work = get_object_or_404(public_works(), pk=work_id)
        values = _active_work_snapshot(work).get("work") or {}
        media = values.get("cover_media")
        if self.image_slot == "recommendation" and values.get("recommendation_image"):
            media = values.get("recommendation_media")
        if media is None:
            return Response({"detail": "该公开版本没有可用的媒体图片。"}, status=404)
        return Response(media)


class PublicRecommendationMetadataView(PublicCoverMetadataView):
    image_slot = "recommendation"


class RecommendationImagePreviewSerializer(serializers.Serializer):
    work_id = serializers.UUIDField()
    document_type = serializers.CharField()
    available = serializers.BooleanField()
    source = serializers.CharField()
    preview_url = serializers.CharField(allow_blank=True)
    public_url = serializers.CharField(allow_blank=True)
    updated_at = serializers.DateTimeField()
    canonical_write_deferred = serializers.BooleanField()
    editorial_revision_id = serializers.UUIDField(allow_null=True)
    workbench_url = serializers.CharField(allow_blank=True)
    media_library_url = serializers.CharField(allow_blank=True)
    detail = serializers.CharField()


class RecommendationImageMetadataView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=RecommendationImagePreviewSerializer, parameters=[OpenApiParameter("edition_id", OpenApiTypes.UUID)])
    def get(self, request, work_id):
        from catalog.models import Work
        from catalog.views import AdminWorkRecommendationImageView

        work = get_object_or_404(Work, pk=work_id)
        return Response(AdminWorkRecommendationImageView()._payload(request, work))
