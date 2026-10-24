"""Login context is anonymous-public metadata, never a user's recent history."""
import re
from urllib.parse import urlsplit
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from catalog.services.public_feedback import safe_public_path
from .views import AuthEntryView


class ReturnContextQuery(serializers.Serializer):
    path = serializers.CharField(max_length=400)


class ReturnContextOutput(serializers.Serializer):
    path = serializers.CharField(allow_blank=True)
    state = serializers.ChoiceField(choices=["available", "replaced", "unavailable", "page"])
    title = serializers.CharField(allow_blank=True)
    authors = serializers.ListField(child=serializers.CharField())
    cover_url = serializers.CharField(allow_blank=True)
    display_uses = serializers.ListField(child=serializers.ChoiceField(choices=["detail", "list", "mobile", "share"]))
    source_type = serializers.CharField(allow_blank=True)
    version_label = serializers.CharField(allow_blank=True)
    location = serializers.CharField(allow_blank=True)
    notice = serializers.CharField()


def summary(raw):
    from reading.source_follow import resolve_public_source
    from catalog.models import MediaRendition
    from catalog.services.editorial_issues import public_issue_revision
    from catalog.services.public_editorial import published_projection, directory_card
    from catalog.services.media import DEFAULT_MEDIA_DISPLAY_USES
    path = safe_public_path(raw)
    empty = {"path": path, "state": "unavailable", "title": "", "authors": [], "cover_url": "", "display_uses": [],
        "source_type": "", "version_label": "", "location": "", "notice": "当前无法核对公开内容。登录后仍会返回原位置，再按当前权限读取。"}
    if not path:
        return empty
    match = re.fullmatch(r"/recommendations/([^/]+)/?", urlsplit(path).path)
    if match:
        issue = published_projection().filter(slug=match.group(1)).first()
        if not issue:
            return empty
        revision = public_issue_revision(issue)
        card = directory_card(issue)
        rendition_id = (revision.materialized_preview or {}).get("cover_rendition_id")
        try:
            rendition_id = UUID(str(rendition_id)) if rendition_id else None
        except ValueError:
            rendition_id = None
        media = MediaRendition.objects.filter(pk=rendition_id).first() if rendition_id else None
        current = published_projection().filter(pk=issue.pk, slug=match.group(1)).first()
        if not current or public_issue_revision(current).pk != revision.pk:
            return empty
        return {**empty, "state": "available", "title": card["title"], "authors": [card["public_byline"]] if card["public_byline"] else [],
            "cover_url": card["cover_url"] if media else "", "display_uses": (media.metadata_snapshot or {}).get("display_uses", list(DEFAULT_MEDIA_DISPLAY_USES)) if media else [],
            "source_type": "特别策划", "version_label": card["issue_label"],
            "notice": "显示当前公开版本，不读取私人浏览记录；登录后返回原文章位置。"}
    source = resolve_public_source(path)
    # The existing public resolver performs publication, version and source checks.
    current = resolve_public_source(path)
    keys = ("status", "catalog_revision_id", "public_revision", "asset_id", "title", "cover_url", "cover_media", "location")
    if any(source.get(key) != current.get(key) for key in keys):
        return empty
    return {**empty, "state": source["status"], "title": source["title"], "authors": source["authors"],
        "cover_url": source["cover_url"], "display_uses": (source.get("cover_media") or {}).get("display_uses", list(DEFAULT_MEDIA_DISPLAY_USES)),
        "source_type": source["source_type"], "version_label": source["version_label"], "location": source["location"], "notice": source["notice"]}


class AuthReturnContextView(AuthEntryView):
    @extend_schema(parameters=[ReturnContextQuery], responses=ReturnContextOutput)
    def get(self, request):
        query = ReturnContextQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        return Response(summary(query.validated_data["path"]))
