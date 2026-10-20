"""Bounded public hierarchy over existing knowledge and subdiscipline identities."""
from math import ceil

from django.db.models import Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import Discipline, KnowledgeNode, Subdiscipline
from catalog.query_filters import filter_slug_or_uuid
from catalog.services.knowledge_media import image_legacy_file, image_media
from catalog.services.scoped_search import SearchContext, SearchService
from catalog.theory_system_views import TheorySystemFeatureMixin, _node_filter

KINDS = ("theory_tradition", "concept", "debate", "research_problem", "subdiscipline")
PAGE_SIZE = 20


class DirectoryIdentitySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()
    kind = serializers.CharField()
    href = serializers.CharField()


class DirectoryItemSerializer(DirectoryIdentitySerializer):
    summary = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    parent_id = serializers.UUIDField(allow_null=True)
    child_count = serializers.IntegerField(min_value=0)


class DirectoryGroupSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    parent = DirectoryIdentitySerializer(allow_null=True)
    items = DirectoryItemSerializer(many=True)


class DirectoryDisciplineSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    slug = serializers.CharField()


class TheoryDirectorySerializer(serializers.Serializer):
    disciplines = DirectoryDisciplineSerializer(many=True)
    kind = serializers.CharField()
    discipline = serializers.CharField(allow_null=True)
    parent = DirectoryIdentitySerializer(allow_null=True)
    breadcrumbs = DirectoryIdentitySerializer(many=True)
    hierarchy_truncated = serializers.BooleanField()
    count = serializers.IntegerField(min_value=0)
    page = serializers.IntegerField(min_value=1)
    total_pages = serializers.IntegerField(min_value=1)
    groups = DirectoryGroupSerializer(many=True)


def identity(row):
    subdiscipline = isinstance(row, Subdiscipline)
    return {
        "id": str(row.pk), "name": row.name if subdiscipline else row.canonical_name_zh,
        "slug": row.slug, "kind": "subdiscipline" if subdiscipline else row.node_type,
        "href": f"/subdisciplines/{row.slug}" if subdiscipline else f"/theories/nodes/{row.slug}",
    }


def visible(row):
    if row is None:
        return False
    if isinstance(row, Subdiscipline):
        return row.editorial_status == "published"
    # Historical mirror nodes must not replace independent taxonomy identities.
    return row.status == "published" and row.node_type in KINDS[:-1]


def breadcrumbs(parent):
    result, seen = [], set()
    current = parent
    while visible(current):
        if current.pk in seen or len(result) >= 20:
            return list(reversed(result)), True
        seen.add(current.pk)
        result.append(identity(current))
        current = current.parent
    return list(reversed(result)), False


def cover(row, request):
    media = image_media(row)
    if media:
        return next(item["url"] for item in media["renditions"] if item["id"] == media["primary_rendition_id"])
    field = image_legacy_file(row)
    return request.build_absolute_uri(field.url) if field else ""


class TheoryDirectoryView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        responses=TheoryDirectorySerializer,
        parameters=[
            OpenApiParameter("type", str, enum=list(KINDS)),
            OpenApiParameter("discipline", str),
            OpenApiParameter("parent", str, description="A published parent UUID or slug; absence shows all current-page groups."),
            OpenApiParameter("q", str),
            OpenApiParameter("page", int),
        ],
    )
    def get(self, request):
        kind = request.query_params.get("type", "theory_tradition").strip()
        if kind not in KINDS:
            raise ValidationError({"type": "请选择有效的条目类型。"})
        query = request.query_params.get("q", "").strip()
        if len(query) > 240:
            raise ValidationError({"q": "目录搜索词不能超过240个字符。"})
        try:
            page = int(request.query_params.get("page", "1"))
        except (TypeError, ValueError):
            raise ValidationError({"page": "页码必须是正整数。"})
        if page < 1:
            raise ValidationError({"page": "页码必须是正整数。"})
        disciplines = Discipline.objects.filter(editorial_status="published").order_by("sort_order", "name", "pk")
        discipline_key = request.query_params.get("discipline", "").strip()
        discipline = get_object_or_404(filter_slug_or_uuid(disciplines, discipline_key, slug_field="slug", id_field="pk")) if discipline_key else None
        if kind == "subdiscipline":
            parents = Subdiscipline.objects.filter(editorial_status="published")
            scope = parents
            if discipline:
                scope = scope.filter(discipline=discipline)
            rows = SearchService(request=request).queryset(SearchContext.SUBDISCIPLINES, query, base_queryset=scope)
            order = ("_search_rank", "name", "pk") if query else ("name", "pk")
        else:
            parents = KnowledgeNode.objects.filter(status="published", node_type__in=KINDS[:-1])
            scope = _node_filter(parents, {"type": kind, "discipline": discipline.slug if discipline else ""})
            rows = _node_filter(scope, {"q": query})
            order = ("_search_rank", "sort_order", "canonical_name_zh", "pk") if query else ("sort_order", "canonical_name_zh", "pk")
        parent_key = request.query_params.get("parent", "").strip()
        parent = get_object_or_404(filter_slug_or_uuid(parents, parent_key, slug_field="slug", id_field="pk")) if parent_key else None
        if parent:
            rows = rows.filter(parent=parent).exclude(pk=parent.pk)
        rows = rows.select_related("parent").order_by(*order).distinct()
        count = rows.count()
        pages = max(1, ceil(count / PAGE_SIZE))
        if page > pages:
            raise NotFound("目录页码已超出当前结果，请返回第一页。")
        values = list(rows[(page - 1) * PAGE_SIZE:page * PAGE_SIZE])
        child_counts = {
            row["parent_id"]: row["total"]
            for row in scope.filter(parent_id__in=[value.pk for value in values]).exclude(
                pk__in=[value.pk for value in values if value.parent_id == value.pk],
            ).values("parent_id").annotate(total=Count("pk", distinct=True))
        }
        groups = {}
        for row in values:
            public_parent = row.parent if visible(row.parent) and row.parent_id != row.pk else None
            key = str(public_parent.pk) if public_parent else None
            group = groups.setdefault(key, {
                "id": key, "title": identity(public_parent)["name"] if public_parent else "公开条目",
                "parent": identity(public_parent) if public_parent else None, "items": [],
            })
            group["items"].append({
                **identity(row),
                "summary": (row.description or row.research_object) if kind == "subdiscipline" else row.summary,
                "cover_url": cover(row, request), "parent_id": key, "child_count": child_counts.get(row.pk, 0),
            })
        trail, truncated = breadcrumbs(parent)
        response = Response({
            "disciplines": [{"id": str(row.pk), "name": row.name, "slug": row.slug} for row in disciplines],
            "kind": kind, "discipline": discipline.slug if discipline else None,
            "parent": identity(parent) if parent else None, "breadcrumbs": trail, "hierarchy_truncated": truncated,
            "count": count, "page": page, "total_pages": pages, "groups": list(groups.values()),
        })
        response["Cache-Control"] = "no-store"
        return response
