"""Cite the public knowledge entry itself, not a book or an inferred author."""
from urllib.parse import quote
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from catalog.models import KnowledgeNode


class KnowledgeEntryCitation(serializers.Serializer):
    node_id = serializers.UUIDField()
    title = serializers.CharField()
    url = serializers.CharField()
    published_at = serializers.DateTimeField(allow_null=True)
    updated_at = serializers.DateTimeField()
    accessed_on = serializers.DateField()
    text = serializers.CharField()
    notice = serializers.CharField()


class KnowledgeEntryCitationView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=KnowledgeEntryCitation)
    def get(self, request, slug):
        node = get_object_or_404(KnowledgeNode.objects.filter(status="published"), slug=slug)
        url = f"{settings.PUBLIC_WEB_URL.rstrip('/')}/theories/nodes/{quote(node.slug, safe='')}"
        accessed = timezone.localdate()
        published = f"{node.published_at.date().isoformat()}发布，" if node.published_at else ""
        response = Response({"node_id": str(node.pk), "title": node.canonical_name_zh, "url": url,
            "published_at": node.published_at, "updated_at": node.updated_at, "accessed_on": accessed,
            "text": f"{node.canonical_name_zh}[网页条目]. Social Theory Library. "
                    f"{published}{node.updated_at.date().isoformat()}更新，{accessed.isoformat()}访问. {url}",
            "notice": "引用本知识条目及其当前公开版本；引用书籍或原文，请使用对应来源的引用入口。"})
        response["Cache-Control"] = "no-store"
        return response
