"""Bounded lookups for the existing topic association editor, never new content."""
from django.core.paginator import Paginator
from django.db.models import Prefetch, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsKnowledgeEditor
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Contribution
from catalog.services.public_topics import CURATION_IDS


class TopicAssociationRowSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    cover_url = serializers.CharField(allow_blank=True)
    status = serializers.CharField(allow_blank=True)


class TopicAssociationPageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = TopicAssociationRowSerializer(many=True)


def association_queryset(field, actor):
    model, node_type = CURATION_IDS[field]
    rows = model.objects.all()
    if node_type:
        return rows.filter(node_type=node_type), "canonical_name_zh"
    if field.endswith("edition_ids"):
        return rows.select_related("work").prefetch_related(Prefetch("contributions",
            queryset=Contribution.objects.filter(approved=True).select_related("person").order_by("order", "pk"))), "work__title"
    if field == "related_scholar_ids":
        return rows.select_related("person"), "person__preferred_name"
    if field == "issue_ids":
        from catalog.services.curation_projects import visible_issues
        rows = visible_issues(actor)
    return rows, "title"


def association_row(row, field, request):
    subtitle, cover = "", ""
    if field.endswith("edition_ids"):
        name = row.work.title
        version = " · ".join(str(value) for value in (row.version_label, row.publication_year, row.publisher) if value)
        labels = dict(Contribution.Role.choices)
        people = "、".join(f"{entry.person.preferred_name}（{labels.get(entry.role, '其他贡献者')}）" for entry in row.contributions.all())
        subtitle = " · ".join(value for value in (people, version) if value)
        rendition = row.work.cover_rendition_id
        if not rendition and row.work.cover:
            from catalog.cover_views import cover_state
            cover = cover_state(row, request)[0]["image_url"]
        status = row.state
    elif field == "related_scholar_ids":
        name, subtitle = row.person.preferred_name, row.short_description
        rendition, status = row.person.portrait_rendition_id, row.editorial_status
    else:
        name = row.canonical_name_zh if CURATION_IDS[field][1] else row.title
        rendition, status = getattr(row, "cover_rendition_id", None), getattr(row, "status", "")
    if rendition:
        cover = f"/api/catalog/admin/media/renditions/{rendition}/file/"
    return {"id": str(row.pk), "name": name, "subtitle": subtitle, "cover_url": cover, "status": status}


class TopicAssociationChoicesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=TopicAssociationPageSerializer, parameters=[
        OpenApiParameter("field", str, enum=list(CURATION_IDS)), OpenApiParameter("q", str),
        OpenApiParameter("ids", str, description="最多200个已选编号，以逗号分隔；仍受当前账户权限限制。"),
        OpenApiParameter("page", int)])
    def get(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        data = request.query_params
        field = serializers.ChoiceField(choices=list(CURATION_IDS)).run_validation(data.get("field"))
        rows, name_field = association_queryset(field, request.user)
        if "ids" in data:
            values = data["ids"].split(",") if data["ids"] else []
            if len(values) > 200:
                raise ValidationError({"ids": "每次最多读取200个关联编号。"})
            identifiers = [serializers.UUIDField().run_validation(value) for value in values]
            rows = rows.filter(pk__in=identifiers)
        query = serializers.CharField(max_length=240, allow_blank=True).run_validation(data.get("q", ""))
        if query:
            rows = rows.filter(Q(**{f"{name_field}__icontains": query}))
        page = serializers.IntegerField(min_value=1).run_validation(data.get("page", 1))
        pages = Paginator(rows.order_by(name_field, "pk"), 24)
        current = pages.get_page(page)
        return Response(TopicAssociationPageSerializer({"count": pages.count, "page": current.number,
            "page_size": 24, "total_pages": pages.num_pages,
            "results": [association_row(row, field, request) for row in current.object_list]}).data)
