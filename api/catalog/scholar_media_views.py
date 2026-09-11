from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.media_views import PublicCoverMediaSerializer
from catalog.models import EditorialRevision, MediaAsset, Person, ScholarProfile
from catalog.services.scholar_media import portrait_media, portrait_selection, portrait_selection_fingerprint, select_scholar_portrait, validate_portrait_selection
from common.permissions import CanAccessBackOffice, CanEditMetadata


class ScholarPortraitRequestSerializer(serializers.Serializer):
    media_id = serializers.UUIDField(allow_null=True)
    expected_person_id = serializers.UUIDField()
    fingerprint = serializers.RegexField(regex=r"^[a-f0-9]{64}$")


class ScholarPortraitStateSerializer(serializers.Serializer):
    scholar_id = serializers.UUIDField()
    person_id = serializers.UUIDField()
    name = serializers.CharField()
    media = PublicCoverMediaSerializer(allow_null=True)
    preview_url = serializers.CharField(allow_blank=True)
    editorial_revision_id = serializers.UUIDField(allow_null=True)
    canonical_write_deferred = serializers.BooleanField()
    editor_url = serializers.CharField()
    fingerprint = serializers.CharField()


def scholar_portrait_state(profile):
    revision = EditorialRevision.objects.filter(target_type="scholar_profile", target_id=profile.pk, status="draft").order_by("-revision").first()
    selection = (revision.materialized_preview.get("portrait_selection") if revision else None) or portrait_selection(profile)
    selection = validate_portrait_selection(profile, selection)
    media = portrait_media(profile.person, selection=selection, private=True)
    preview_url = next(row["url"] for row in media["renditions"] if row["id"] == media["primary_rendition_id"]) if media else profile.person.portrait.url if selection["legacy_path"] else ""
    return {"scholar_id": profile.pk, "person_id": profile.person_id, "name": profile.person.preferred_name, "media": media, "preview_url": preview_url,
            "editorial_revision_id": revision.pk if revision else None, "canonical_write_deferred": revision is not None, "editor_url": f"/admin/scholars/{profile.pk}", "fingerprint": portrait_selection_fingerprint(profile, draft=revision)}


class ScholarPortraitSelectionView(AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(responses=ScholarPortraitStateSerializer)
    def get(self, request, scholar_id):
        profile = get_object_or_404(ScholarProfile.objects.select_related("person"), pk=scholar_id)
        try:
            payload = scholar_portrait_state(profile)
        except (ValueError, ValidationError) as error:
            return Response({"detail": str(error), "code": "portrait_preview_unavailable"}, status=409)
        return Response(ScholarPortraitStateSerializer(payload).data)

    @extend_schema(request=ScholarPortraitRequestSerializer, responses=ScholarPortraitStateSerializer)
    def post(self, request, scholar_id):
        profile = get_object_or_404(ScholarProfile.objects.select_related("person"), pk=scholar_id)
        serializer = ScholarPortraitRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        if values["media_id"]:
            get_object_or_404(MediaAsset, pk=values["media_id"])
        try:
            select_scholar_portrait(profile.pk, actor=request.user, **values)
        except (ValueError, ValidationError) as error:
            return Response({"detail": str(error), "code": "portrait_selection_failed"}, status=409)
        profile.refresh_from_db()
        return Response(ScholarPortraitStateSerializer(scholar_portrait_state(profile)).data)


class PublicPersonPortraitView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request, person_id):
        from catalog.views import _public_media_response

        person = get_object_or_404(Person, pk=person_id, authority_status="verified", scholar_profile__editorial_status="published")
        media = portrait_media(person)
        if not media:
            return Response({"detail": "没有已发布的媒体肖像。"}, status=404)
        return _public_media_response(request, media)
