from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from catalog.services.timeline_media import primary_image_media
from catalog.services.timeline_publication import public_events
from catalog.theory_system_views import TheorySystemFeatureMixin


class PublicTimelineImageView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def get(self, request, pk):
        from catalog.views import _public_media_response
        event = get_object_or_404(public_events(), pk=pk)
        media = primary_image_media(event)
        if media is None:
            raise NotFound("事件尚无已发布的图片。")
        response = _public_media_response(request, media)
        # Re-check withdrawal and image replacement on every new request.
        response["Cache-Control"] = "private, no-store"
        return response
