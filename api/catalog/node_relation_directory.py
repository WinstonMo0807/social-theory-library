"""One paginated editing directory over the two original node relation models."""
from django.core.paginator import EmptyPage, Paginator
from django.db.models import CharField, F, Q, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Replace
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response

from catalog.editorial_read import AdminEditorialDraftReadMixin
from catalog.models import KnowledgeNode, KnowledgePublicationStatus, KnowledgeRelation, PersonNodeRelation
from catalog.relation_editorial_views import relations_for_node
from catalog.theory_serializers import AdminKnowledgeRelationSerializer
from common.permissions import IsKnowledgeEditor


KNOWLEDGE_RELATION_TYPES = KnowledgeRelation.RelationType.choices
RELATION_TYPES = dict([*KNOWLEDGE_RELATION_TYPES, *PersonNodeRelation.RelationType.choices])


class NodeRelationFilters(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    q = serializers.CharField(max_length=300, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["", *KnowledgePublicationStatus.values], default="")
    kind = serializers.ChoiceField(choices=["", "node", "person"], default="")
    relation_type = serializers.ChoiceField(choices=[("", "全部类型"), *RELATION_TYPES.items()], default="")
    direction = serializers.ChoiceField(choices=[("", "全部方向"), *KnowledgeRelation.Direction.choices], default="")


class NodeRelationRow(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["node", "person", "scholar"])
    scholar_id = serializers.UUIDField(allow_null=True)
    source_name = serializers.CharField()
    target_name = serializers.CharField()
    source_kind = serializers.CharField()
    target_kind = serializers.CharField()
    relation_type = serializers.CharField()
    relation_label = serializers.CharField()
    direction = serializers.ChoiceField(choices=["directed", "bidirectional", "undirected"])
    description = serializers.CharField(allow_blank=True)
    evidence_source = serializers.CharField(allow_blank=True)
    has_source_anchor = serializers.BooleanField()
    status = serializers.CharField()
    has_unpublished_changes = serializers.BooleanField()
    remains_in_draft = serializers.BooleanField()


class NodeRelationTypeOption(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class NodeRelationPage(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.IntegerField(allow_null=True)
    previous = serializers.IntegerField(allow_null=True)
    results = NodeRelationRow(many=True)
    relation_types = NodeRelationTypeOption(many=True)


def directory_queries(node_id, filters):
    nodes = relations_for_node(KnowledgeRelation.objects.all(), node_id).alias(
        selected_type=Coalesce(KeyTextTransform("relation_type", "link_draft"), F("relation_type"), output_field=CharField()),
        selected_direction=Coalesce(KeyTextTransform("direction", "link_draft"), F("direction"), output_field=CharField()),
    )
    people = PersonNodeRelation.objects.filter(node_id=node_id)
    for field in ("status", "direction", "relation_type"):
        if filters.get(field):
            nodes = nodes.filter(**{f"selected_{'type' if field == 'relation_type' else field}" if field != "status" else field: filters[field]})
            people = people.filter(**{field: filters[field]})
    query = filters.get("q")
    if query:
        matching = KnowledgeNode.objects.filter(Q(canonical_name_zh__icontains=query) | Q(canonical_name_en__icontains=query)).annotate(
            compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")
        nodes = nodes.filter(Q(source_node__canonical_name_zh__icontains=query) | Q(target_node__canonical_name_zh__icontains=query)
            | Q(description__icontains=query) | Q(evidence_source__icontains=query)
            | Q(draft_source__in=matching) | Q(draft_target__in=matching)
            | Q(link_draft__description__icontains=query) | Q(link_draft__evidence_source__icontains=query))
        people = people.filter(Q(person__preferred_name__icontains=query) | Q(person__original_name__icontains=query)
            | Q(node__canonical_name_zh__icontains=query) | Q(relation_label__icontains=query) | Q(source__icontains=query))
    if filters.get("kind") == "person":
        nodes = nodes.none()
    if filters.get("kind") == "node":
        people = people.none()
    def index(rows, kind):
        return rows.order_by().annotate(directory_kind=Value(kind, output_field=CharField())).values("pk", "directory_kind", "updated_at")
    # Pagination happens in SQL before either original model is serialized.
    return index(nodes, "node").union(index(people, "person"), all=True).order_by("-updated_at", "directory_kind", "pk")


class NodeRelationDirectoryView(AdminEditorialDraftReadMixin, generics.GenericAPIView):
    http_method_names = ["get", "head", "options"]
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeRelationSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "omit_relation_material": True}
    editorial_target_type = "knowledge_relation"

    @extend_schema(parameters=[NodeRelationFilters, OpenApiParameter("node_id", str, location=OpenApiParameter.PATH)], responses=NodeRelationPage)
    def get(self, request, node_id):
        node = get_object_or_404(KnowledgeNode, pk=node_id)
        incoming = NodeRelationFilters(data=request.query_params)
        incoming.is_valid(raise_exception=True)
        try:
            page = Paginator(directory_queries(node.pk, incoming.validated_data), 24).page(incoming.validated_data["page"])
        except EmptyPage:
            raise NotFound("当前筛选已无这一页，请返回第一页重新读取。") from None
        entries = list(page)
        nodes = KnowledgeRelation.objects.filter(pk__in=[item["pk"] for item in entries if item["directory_kind"] == "node"]).select_related("source_node", "target_node")
        result = {}
        for data in self._draft_read_rows(nodes):
            result[("node", data["id"])] = {
                "id": data["id"], "kind": "node", "scholar_id": None,
                "source_name": data["source_name"], "target_name": data["target_name"],
                "source_kind": "知识条目", "target_kind": "知识条目", "relation_type": data["relation_type"],
                "relation_label": data["relation_label"], "direction": data["direction"],
                "description": data["description"], "evidence_source": data["evidence_source"],
                "has_source_anchor": bool(data.get("source_anchor") or data.get("evidence")),
                "status": data.get("public_status", data["status"]), "has_unpublished_changes": data["has_unpublished_changes"],
                "remains_in_draft": str(node.pk) in {str(data["source_node"]), str(data["target_node"])},
            }
        people = PersonNodeRelation.objects.filter(pk__in=[item["pk"] for item in entries if item["directory_kind"] == "person"]).select_related("person__scholar_profile", "node")
        for row in people:
            scholar = getattr(row.person, "scholar_profile", None)
            source, target = (row.node.canonical_name_zh, row.person.preferred_name) if row.node_is_source else (row.person.preferred_name, row.node.canonical_name_zh)
            result[("person", str(row.pk))] = {"id": str(row.pk), "kind": "person", "scholar_id": str(scholar.pk) if scholar else None,
                "source_name": source, "target_name": target, "source_kind": "知识条目" if row.node_is_source else "人物",
                "target_kind": "人物" if row.node_is_source else "知识条目", "relation_type": row.relation_type,
                "relation_label": row.get_relation_type_display(), "direction": row.direction, "description": row.relation_label,
                "evidence_source": row.source, "has_source_anchor": bool(row.evidence_span_id), "status": row.status, "has_unpublished_changes": False, "remains_in_draft": True}
        return Response(NodeRelationPage({"count": page.paginator.count,
            "next": page.next_page_number() if page.has_next() else None,
            "previous": page.previous_page_number() if page.has_previous() else None,
            "results": [result[(item["directory_kind"], str(item["pk"]))] for item in entries if (item["directory_kind"], str(item["pk"])) in result],
            "relation_types": [{"value": value, "label": label} for value, label in RELATION_TYPES.items()]}).data)
