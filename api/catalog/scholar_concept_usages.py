"""Scholar view of original node concept usages; no copied placements or writes."""
from django.core.paginator import Paginator, EmptyPage
from django.db.models import BooleanField, CharField, F, Func, OuterRef, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Replace
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.content_placement_views import PlacementResultItemSerializer
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import EditorialRevision, KnowledgeNode, ScholarProfile
from catalog.services import content_placements as service
from common.permissions import IsKnowledgeEditor


class HasUsagePerson(Func):
    output_field = BooleanField()

    def as_sql(self, compiler, connection, **extra_context):
        snapshot, params = compiler.compile(self.source_expressions[0])
        person, person_params = compiler.compile(self.source_expressions[1])
        if connection.vendor == "postgresql":
            rows = f"jsonb_array_elements(CASE WHEN jsonb_typeof({snapshot}->'items') = 'array' THEN {snapshot}->'items' ELSE '[]'::jsonb END) AS usage(value)"
            subject = "usage.value->'concept_usage'->>'source_person_id'"
        else:
            rows = f"json_each(CASE WHEN json_type({snapshot}, '$.items') = 'array' THEN json_extract({snapshot}, '$.items') ELSE '[]' END) AS usage"
            subject = "json_extract(CASE WHEN usage.type = 'object' THEN usage.value ELSE '{}' END, '$.concept_usage.source_person_id')"
        return f"EXISTS (SELECT 1 FROM {rows} WHERE {subject} = {person})", [*params, *params, *person_params]


def usage_revisions(person_id):
    latest = EditorialRevision.objects.filter(target_type=service.KIND, target_id=OuterRef("target_id")).order_by("-revision")
    nodes = KnowledgeNode.objects.annotate(compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")
    return EditorialRevision.objects.filter(target_type=service.KIND, pk=Subquery(latest.values("pk")[:1]),
        materialized_preview__page_type="node").alias(
        author_match=HasUsagePerson(F("materialized_preview"), Value(str(person_id))),
        node_key=Replace(KeyTextTransform("page_id", "materialized_preview"), Value("-"), Value(""), output_field=CharField()),
    ).filter(author_match=True, node_key__in=nodes).order_by("-updated_at", "pk")


class ScholarUsageQuery(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)


class ScholarUsageGroup(serializers.Serializer):
    node_id = serializers.UUIDField()
    node_name = serializers.CharField()
    node_type = serializers.CharField()
    revision_id = serializers.UUIDField()
    revision_status = serializers.CharField()
    edit_url = serializers.CharField()
    items = PlacementResultItemSerializer(many=True)


class ScholarUsagePage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.IntegerField(allow_null=True)
    previous = serializers.IntegerField(allow_null=True)
    results = ScholarUsageGroup(many=True)


class ScholarConceptUsagesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]
    http_method_names = ["get", "head", "options"]

    @extend_schema(parameters=[ScholarUsageQuery], responses=ScholarUsagePage)
    def get(self, request, scholar_id):
        scholar = get_object_or_404(ScholarProfile, pk=scholar_id)
        query = ScholarUsageQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            page = Paginator(usage_revisions(scholar.person_id), 6).page(query.validated_data["page"])
        except EmptyPage:
            raise NotFound("用法分组已变化，请返回第一页重新读取。") from None
        entries = list(page)
        nodes = {str(row.pk): row for row in KnowledgeNode.objects.filter(pk__in=[entry.materialized_preview["page_id"] for entry in entries])}
        result = []
        for entry in entries:
            data = entry.materialized_preview
            node = nodes.get(data["page_id"])
            if not node or entry.target_id != service.target_id("node", node.pk):
                continue
            items = [item for item in data.get("items", []) if isinstance(item, dict) and isinstance(item.get("concept_usage"), dict)
                and item["concept_usage"].get("source_person_id") == str(scholar.person_id)]
            resolved, _ = service._resolved_items(items)
            result.append({"node_id": str(node.pk), "node_name": node.canonical_name_zh, "node_type": node.node_type,
                "revision_id": str(entry.pk), "revision_status": entry.status,
                "edit_url": f"/admin/theories/{node.pk}?section=usages", "items": resolved})
        return Response(ScholarUsagePage({"count": page.paginator.count, "next": page.next_page_number() if page.has_next() else None,
            "previous": page.previous_page_number() if page.has_previous() else None, "results": result}).data)
