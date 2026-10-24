"""Scholar-centred directory over original person-node and scholar relations."""
from django.core.paginator import Paginator, EmptyPage
from django.db.models import CharField, F, OuterRef, Q, Subquery, Value
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Replace
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import EditorialRevision, KnowledgePublicationStatus, PersonNodeRelation, ScholarProfile, ScholarRelation
from catalog.node_relation_directory import NodeRelationPage
from catalog.services.shared_curation import DIRECTIONS, relation_payload
from common.permissions import IsKnowledgeEditor

SCHOLAR_TYPES = {"teaching": "师承", "cooperation": "合作", "influence": "影响", "criticism": "批评", "comparative_reading": "比较阅读", "other": "其他关系"}
RELATION_TYPES = {**dict(PersonNodeRelation.RelationType.choices), **SCHOLAR_TYPES}
RELATION_TYPES.update(influence="影响（学者间）", influences="影响（人物与概念）")


class ScholarRelationDirectoryFilters(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=24, default=24)
    review_only = serializers.BooleanField(default=False)
    q = serializers.CharField(max_length=300, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=["", *KnowledgePublicationStatus.values], default="")
    kind = serializers.ChoiceField(choices=["", "person", "scholar"], default="")
    relation_type = serializers.ChoiceField(choices=[("", "全部类型"), *RELATION_TYPES.items()], default="")
    direction = serializers.ChoiceField(choices=["", *DIRECTIONS], default="")


def relations_for_scholar(rows, scholar_id):
    key = serializers.UUIDField().run_validation(scholar_id)
    latest = EditorialRevision.objects.filter(target_type="scholar_relation", target_id=OuterRef("pk")).order_by("-revision")
    return rows.alias(link_draft=Subquery(latest.values("materialized_preview")[:1])).alias(
        draft_source=Replace(KeyTextTransform("source_scholar", "link_draft"), Value("-"), Value(""), output_field=CharField()),
        draft_target=Replace(KeyTextTransform("target_scholar", "link_draft"), Value("-"), Value(""), output_field=CharField()),
    ).filter(Q(source_scholar_id=key) | Q(target_scholar_id=key) | Q(draft_source=key.hex) | Q(draft_target=key.hex))


def directory_queries(scholar_id, person_id, filters):
    people = relations_for_scholar(ScholarRelation.objects.all(), scholar_id).alias(
        selected_type=Coalesce(KeyTextTransform("relation_type", "link_draft"), F("relation_type"), output_field=CharField()),
        selected_direction=Coalesce(KeyTextTransform("direction", "link_draft"), F("direction"), output_field=CharField()),
    )
    nodes = PersonNodeRelation.objects.filter(person_id=person_id)
    if filters.get("review_only"):
        nodes = nodes.filter(status__in=["draft", "pending"])
        people = people.filter(status__in=["draft", "pending"])
    for field in ("status", "direction", "relation_type"):
        if filters.get(field):
            nodes = nodes.filter(**{field: filters[field]})
            people = people.filter(**{f"selected_{'type' if field == 'relation_type' else field}" if field != "status" else field: filters[field]})
    if query := filters.get("q"):
        matching = ScholarProfile.objects.filter(Q(person__preferred_name__icontains=query) | Q(person__original_name__icontains=query)).annotate(
            compact_id=Replace(Cast("pk", CharField()), Value("-"), Value(""))).values("compact_id")
        people = people.filter(Q(source_scholar__person__preferred_name__icontains=query) | Q(target_scholar__person__preferred_name__icontains=query)
            | Q(summary__icontains=query) | Q(source__icontains=query) | Q(link_draft__summary__icontains=query) | Q(link_draft__source__icontains=query)
            | Q(draft_source__in=matching) | Q(draft_target__in=matching))
        nodes = nodes.filter(Q(node__canonical_name_zh__icontains=query) | Q(node__canonical_name_en__icontains=query)
            | Q(relation_label__icontains=query) | Q(source__icontains=query))
    if filters.get("kind") == "person": people = people.none()
    if filters.get("kind") == "scholar": nodes = nodes.none()
    def index(rows, kind):
        return rows.order_by().annotate(directory_kind=Value(kind, output_field=CharField())).values("pk", "directory_kind", "updated_at")
    return index(nodes, "person").union(index(people, "scholar"), all=True).order_by("-updated_at", "directory_kind", "pk")


class ScholarKnowledgeRelationDirectoryView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]
    http_method_names = ["get", "head", "options"]

    @extend_schema(parameters=[ScholarRelationDirectoryFilters], responses=NodeRelationPage)
    def get(self, request, scholar_id):
        scholar = get_object_or_404(ScholarProfile.objects.select_related("person"), pk=scholar_id)
        incoming = ScholarRelationDirectoryFilters(data=request.query_params)
        incoming.is_valid(raise_exception=True)
        try:
            page = Paginator(directory_queries(scholar.pk, scholar.person_id, incoming.validated_data), incoming.validated_data["page_size"]).page(incoming.validated_data["page"])
        except EmptyPage:
            raise NotFound("当前筛选已无这一页，请返回第一页重新读取。") from None
        entries, result = list(page), {}
        nodes = PersonNodeRelation.objects.filter(pk__in=[item["pk"] for item in entries if item["directory_kind"] == "person"]).select_related("node")
        for row in nodes:
            source, target = (row.node.canonical_name_zh, scholar.person.preferred_name) if row.node_is_source else (scholar.person.preferred_name, row.node.canonical_name_zh)
            result[("person", str(row.pk))] = {"id": str(row.pk), "kind": "person", "scholar_id": str(scholar.pk), "source_name": source, "target_name": target,
                "source_kind": "知识条目" if row.node_is_source else "人物", "target_kind": "人物" if row.node_is_source else "知识条目",
                "relation_type": row.relation_type, "relation_label": row.get_relation_type_display(), "direction": row.direction,
                "description": row.relation_label, "evidence_source": row.source, "has_source_anchor": bool(row.evidence_span_id),
                "status": row.status, "has_unpublished_changes": False, "remains_in_draft": True}
        for row in ScholarRelation.objects.filter(pk__in=[item["pk"] for item in entries if item["directory_kind"] == "scholar"]).select_related("source_scholar__person", "target_scholar__person"):
            data = relation_payload(row, include_source=False)
            result[("scholar", str(row.pk))] = {"id": str(row.pk), "kind": "scholar", "scholar_id": str(scholar.pk),
                "source_name": data.get("source_name") or row.source_scholar.person.preferred_name,
                "target_name": data.get("target_name") or row.target_scholar.person.preferred_name,
                "source_kind": "人物", "target_kind": "人物", "relation_type": data.get("relation_type", row.relation_type),
                "relation_label": SCHOLAR_TYPES.get(data.get("relation_type", row.relation_type), "其他关系"), "direction": data.get("direction", row.direction),
                "description": data.get("summary", row.summary), "evidence_source": data.get("source", row.source), "has_source_anchor": bool(data.get("source_anchor")),
                "status": row.status, "has_unpublished_changes": data["has_unpublished_changes"],
                "remains_in_draft": str(scholar.pk) in {str(data.get("source_scholar", row.source_scholar_id)), str(data.get("target_scholar", row.target_scholar_id))}}
        return Response(NodeRelationPage({"count": page.paginator.count, "next": page.next_page_number() if page.has_next() else None,
            "previous": page.previous_page_number() if page.has_previous() else None,
            "results": [result[(item["directory_kind"], str(item["pk"]))] for item in entries if (item["directory_kind"], str(item["pk"])) in result],
            "relation_types": [{"value": value, "label": label} for value, label in RELATION_TYPES.items()]}).data)
