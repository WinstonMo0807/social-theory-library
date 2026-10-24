"""Read-only reverse references in current page placement revisions."""
from django.core.paginator import Paginator, EmptyPage
from django.db.models import BooleanField, CharField, F, Func, OuterRef, Q, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import EditorialRevision
from catalog.services import content_placements as placements
from catalog.services.curation_projects import visible_issues
from common.permissions import IsKnowledgeEditor

PAGE_LABELS = {"scholar":"学者", "node":"知识条目", "topic":"主题", "discipline":"学科", "subdiscipline":"子学科",
    "reading_path":"阅读路径", "issue":"策划文章", "site":"网站页面", "timeline_event":"时间线事件"}


class HasPlacementReference(Func):
    output_field = BooleanField()

    def __init__(self, *expressions, reference_field="id", many=False, **extra):
        if reference_field not in {"id","edition_id"}:
            raise ValueError("Unsupported placement identity field")
        self.reference_field,self.many=reference_field,many
        super().__init__(*expressions,**extra)

    def as_sql(self, compiler, connection, **extra_context):
        snapshot, params = compiler.compile(self.source_expressions[0])
        kind, kind_params = compiler.compile(self.source_expressions[1])
        key, key_params = compiler.compile(self.source_expressions[2])
        if connection.vendor == "postgresql":
            rows = f"jsonb_array_elements(CASE WHEN jsonb_typeof({snapshot}->'items') = 'array' THEN {snapshot}->'items' ELSE '[]'::jsonb END) AS placement(value)"
            source_type, source_id = "placement.value->'target'->>'type'", f"placement.value->'target'->>'{self.reference_field}'"
        else:
            rows = f"json_each(CASE WHEN json_type({snapshot}, '$.items') = 'array' THEN json_extract({snapshot}, '$.items') ELSE '[]' END) AS placement"
            item = "CASE WHEN placement.type = 'object' THEN placement.value ELSE '{}' END"
            source_type, source_id = f"json_extract({item}, '$.target.type')", f"json_extract({item}, '$.target.{self.reference_field}')"
        comparison=f"REPLACE({source_id}, '-', '') IN {key}" if self.many else f"{source_id} = {key}"
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {source_type} = {kind} AND {comparison})", [*params, *params, *kind_params, *key_params]


def allowed_pages(actor, *, include_recycled=False):
    result = {}
    for kind, (model, _, _) in placements.PAGES.items():
        try:
            placements.authorize(actor, kind)
        except PermissionDenied:
            continue
        manager=model.all_objects if include_recycled and hasattr(model,"all_objects") else model.objects
        rows = visible_issues(actor,include_recycled=include_recycled) if kind == "issue" else manager.all()
        if kind == "site":
            rows = rows.filter(key="site_config")
        result[kind] = rows
    return result


def placement_use_revisions(kind, identifier, page_rows, *, matches=None):
    revisions = EditorialRevision.objects.filter(target_type=placements.KIND, target_id=OuterRef("target_id")).order_by("-revision")
    rows = EditorialRevision.objects.filter(target_type=placements.KIND).annotate(
        latest_id=Subquery(revisions.values("pk")[:1]), published_id=Subquery(revisions.filter(status="published").values("pk")[:1]),
    ).alias(matches=matches if matches is not None else HasPlacementReference(F("materialized_preview"), Value(kind), Value(str(identifier))),
        page_key=Replace(KeyTextTransform("page_id", "materialized_preview"), Value("-"), Value(""), output_field=CharField()))
    allowed = Q(pk__in=[])
    for page_type, pages in page_rows.items():
        keys = pages.order_by().annotate(compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")
        allowed |= Q(materialized_preview__page_type=page_type, page_key__in=keys)
    return rows.filter(Q(pk=F("latest_id")) | Q(pk=F("published_id")), allowed, matches=True).order_by("-updated_at", "pk")


class PlacementUseQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)


class PlacementUseItem(serializers.Serializer):
    id = serializers.UUIDField()
    area = serializers.CharField(allow_blank=True)
    group = serializers.CharField(allow_blank=True)


class PlacementUseRow(serializers.Serializer):
    page_type = serializers.CharField()
    page_id = serializers.UUIDField()
    page_label = serializers.CharField()
    title = serializers.CharField()
    revision_id = serializers.UUIDField()
    revision = serializers.IntegerField()
    is_latest = serializers.BooleanField()
    is_published = serializers.BooleanField()
    edit_url = serializers.CharField()
    items = PlacementUseItem(many=True)


class PlacementUsePage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.IntegerField(allow_null=True)
    previous = serializers.IntegerField(allow_null=True)
    results = PlacementUseRow(many=True)


class PlacementUsesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]
    http_method_names = ["get", "head", "options"]

    @extend_schema(parameters=[PlacementUseQuery, OpenApiParameter("source_type", str, location=OpenApiParameter.PATH, enum=["node", "scholar"])], responses=PlacementUsePage)
    def get(self, request, source_type, source_id):
        if source_type not in {"node", "scholar"}:
            raise ValidationError("请选择知识条目或学者来源。")
        source = placements.parent_object(source_type, source_id, actor=request.user)
        query = PlacementUseQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            page = Paginator(placement_use_revisions(source_type, source.pk, allowed_pages(request.user)), 12).page(query.validated_data["page"])
        except EmptyPage:
            raise NotFound("引用范围已变化，请返回第一页重新读取。") from None
        result = []
        for revision in page:
            data = revision.materialized_preview
            try:
                parent = placements.parent_object(data["page_type"], data["page_id"], actor=request.user)
            except Http404:
                continue
            if revision.target_id != placements.target_id(data["page_type"], parent.pk):
                continue
            items = [{"id": item["id"], "area": item.get("area", ""), "group": item.get("group", "")} for item in data.get("items", [])
                if isinstance(item, dict) and isinstance(item.get("target"), dict)
                and item["target"].get("type") == source_type and item["target"].get("id") == str(source.pk)]
            result.append({"page_type": data["page_type"], "page_id": str(parent.pk), "page_label": PAGE_LABELS[data["page_type"]], "title": placements._title(parent),
                "revision_id": str(revision.pk), "revision": revision.revision, "is_latest": revision.pk == revision.latest_id,
                "is_published": revision.pk == revision.published_id, "edit_url": f"/admin/content/{data['page_type']}/{parent.pk}?revision={revision.pk}", "items": items})
        return Response(PlacementUsePage({"count": page.paginator.count, "next": page.next_page_number() if page.has_next() else None,
            "previous": page.previous_page_number() if page.has_previous() else None, "results": result}).data)
