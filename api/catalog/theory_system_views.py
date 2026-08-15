from __future__ import annotations

from uuid import UUID, uuid4

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsKnowledgeEditor, IsKnowledgeReviewer, IsLibraryAdmin
from ingestion.models import AuditEvent

from .models import (
    Asset,
    Discipline,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeMergeRecord,
    KnowledgeNodeVersion,
    KnowledgeRelation,
    KnowledgeRelationVersion,
    Page,
    Passage,
    Person,
    PersonNodeRelation,
    PublicationState,
    ReadingPath,
    RelationReviewStatus,
    TheoryReviewTask,
    TheoryTimelineEvent,
    TimelineEventRelation,
    Work,
    WorkNodeRelation,
)
from .services.knowledge_nodes import (
    merge_nodes,
    merge_preview,
    record_node_version,
    rollback_merge,
)
from .theory_serializers import (
    AdminKnowledgeNodeSerializer,
    AdminKnowledgeRelationSerializer,
    AdminWorkNodeRelationSerializer,
    DisciplineCompactSerializer,
    EvidenceSnippetSerializer,
    KnowledgeNodeDetailSerializer,
    KnowledgeNodeListSerializer,
    KnowledgeNodeMergeRecordSerializer,
    KnowledgeNodeVersionSerializer,
    KnowledgeRelationSerializer,
    KnowledgeRelationVersionSerializer,
    NormalizedTimelineEventSerializer,
    ReadingPathSerializer,
    TheoryReviewTaskSerializer,
    WorkNodeRelationSerializer,
    compact_work,
)


class TheorySystemFeatureMixin:
    def initial(self, request, *args, **kwargs):
        if not settings.THEORY_SYSTEM_ENABLED:
            raise NotFound("新版理论知识系统当前未启用。")
        return super().initial(request, *args, **kwargs)


class PublicEvidenceFocusView(TheorySystemFeatureMixin, APIView):
    """Return a reviewed evidence locator for the existing PDF reader."""

    permission_classes = [AllowAny]

    def get(self, request, pk):
        evidence = get_object_or_404(
            EvidenceSnippet.objects.select_related(
                "file",
                "work_node_relation",
                "node",
            ).filter(
                pk=pk,
                review_status=RelationReviewStatus.APPROVED,
                work_node_relation__status="published",
                node__status="published",
                file__kind=Asset.Kind.NORMALIZED,
                file__status=Asset.Status.READY,
                file__is_current=True,
                work__editions__state=PublicationState.PUBLISHED,
            ).distinct(),
        )
        page = get_object_or_404(Page, asset=evidence.file, index=evidence.page_number)
        raw_box = evidence.bounding_box or {}
        bbox = raw_box.get("rect", []) if isinstance(raw_box, dict) else raw_box
        return Response(
            {
                "id": str(evidence.id),
                "asset_id": str(evidence.file_id),
                "title": evidence.work.title,
                "page_index": evidence.page_number,
                "printed_label": evidence.printed_page_label or page.printed_label,
                "width": page.width,
                "height": page.height,
                "bbox": bbox if isinstance(bbox, list) else [],
                "text": evidence.quote,
            }
        )


def _published_node_queryset():
    published_links = KnowledgeNodeDiscipline.objects.filter(status="published").select_related(
        "discipline"
    )
    return KnowledgeNode.objects.filter(status="published").select_related(
        "primary_discipline"
    ).prefetch_related(
        "aliases",
        Prefetch("discipline_links", queryset=published_links),
        "person_relations__person__scholar_profile",
    )


def _node_filter(queryset, params):
    node_type = params.get("type", "").strip()
    discipline = params.get("discipline", "").strip()
    status_value = params.get("status", "").strip()
    query = params.get("q", "").strip()
    if node_type:
        queryset = queryset.filter(node_type=node_type)
    if status_value:
        queryset = queryset.filter(status=status_value)
    if discipline:
        discipline_query = Q(primary_discipline__slug=discipline) | Q(
            discipline_links__discipline__slug=discipline
        )
        if _is_uuid(discipline):
            discipline_query |= Q(primary_discipline_id=discipline) | Q(
                discipline_links__discipline_id=discipline
            )
        queryset = queryset.filter(discipline_query)
    if query:
        queryset = queryset.filter(
            Q(canonical_name_zh__icontains=query)
            | Q(canonical_name_en__icontains=query)
            | Q(summary__icontains=query)
            | Q(definition__icontains=query)
            | Q(aliases__alias__icontains=query)
            | Q(aliases__normalized_alias__icontains=query.casefold())
        )
    return queryset.distinct()


def _is_uuid(value):
    try:
        UUID(str(value))
        return True
    except (TypeError, ValueError):
        return False


def _published_work_queryset():
    return Work.objects.filter(editions__state=PublicationState.PUBLISHED).distinct()


class TheorySystemOverviewView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        disciplines = Discipline.objects.filter(editorial_status="published").order_by(
            "sort_order", "name"
        )
        discipline_rows = []
        for discipline in disciplines:
            nodes = _published_node_queryset().filter(
                Q(primary_discipline=discipline)
                | Q(discipline_links__discipline=discipline, discipline_links__status="published")
            ).distinct()
            work_ids = WorkNodeRelation.objects.filter(
                node__in=nodes,
                node__status="published",
                status="published",
                work__editions__state=PublicationState.PUBLISHED,
            ).values("work_id").distinct()
            counts = {
                "theory_traditions": nodes.filter(node_type="theory_tradition").count(),
                "subdisciplines": nodes.filter(node_type="subdiscipline").count(),
                "works": work_ids.count(),
            }
            discipline_rows.append(
                {
                    **DisciplineCompactSerializer(
                        discipline,
                        context={"request": request},
                    ).data,
                    "counts": {key: value for key, value in counts.items() if value > 0},
                }
            )

        reading_paths = ReadingPath.objects.filter(status="published").select_related(
            "primary_discipline"
        ).prefetch_related("items__node", "items__work")[:6]
        recent_nodes = _published_node_queryset().order_by("-updated_at")[:6]
        recent_events = (
            TheoryTimelineEvent.objects.filter(review_status=RelationReviewStatus.APPROVED)
            .prefetch_related(
                "normalized_relations__node",
                "normalized_relations__discipline",
                "normalized_relations__scholar__person",
                "normalized_relations__work",
            )
            .order_by("-updated_at")[:6]
        )
        recent_relations = (
            WorkNodeRelation.objects.filter(
                status="published",
                node__status="published",
                work__editions__state=PublicationState.PUBLISHED,
            )
            .select_related("work", "node")
            .order_by("-reviewed_at", "-updated_at")[:6]
        )
        return Response(
            {
                "disciplines": discipline_rows,
                "browse": {
                    "theory_traditions": _published_node_queryset()
                    .filter(node_type="theory_tradition")
                    .count(),
                    "subdisciplines": _published_node_queryset()
                    .filter(node_type="subdiscipline")
                    .count(),
                    "debates": _published_node_queryset().filter(node_type="debate").count(),
                },
                "reading_paths": ReadingPathSerializer(
                    reading_paths,
                    many=True,
                    context={"request": request},
                ).data,
                "recent": {
                    "nodes": KnowledgeNodeListSerializer(
                        recent_nodes,
                        many=True,
                        context={"request": request},
                    ).data,
                    "timeline_events": NormalizedTimelineEventSerializer(
                        recent_events,
                        many=True,
                        context={"request": request},
                    ).data,
                    "work_relations": WorkNodeRelationSerializer(
                        recent_relations,
                        many=True,
                        context={"request": request},
                    ).data,
                },
            }
        )


class TheorySystemSearchView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"query": "", "results": []})
        limit = min(max(int(request.query_params.get("limit", 8)), 1), 24)
        results = []

        nodes = _published_node_queryset().filter(
            Q(canonical_name_zh__icontains=query)
            | Q(canonical_name_en__icontains=query)
            | Q(aliases__alias__icontains=query)
            | Q(summary__icontains=query)
            | Q(definition__icontains=query)
        ).distinct()[:limit]
        results.extend(
            {
                "kind": "knowledge_node",
                "id": str(node.id),
                "title": node.canonical_name_zh,
                "subtitle": node.canonical_name_en,
                "description": node.summary,
                "href": f"/theories/nodes/{node.slug}",
                "node_type": node.node_type,
            }
            for node in nodes
        )

        scholars = Person.objects.filter(
            Q(preferred_name__icontains=query)
            | Q(original_name__icontains=query)
            | Q(aliases__icontains=query),
            scholar_profile__editorial_status="published",
            node_relations__status="published",
            node_relations__node__status="published",
        ).select_related("scholar_profile").distinct()[:limit]
        results.extend(
            {
                "kind": "scholar",
                "id": str(person.id),
                "title": person.preferred_name,
                "subtitle": person.original_name,
                "description": person.scholar_profile.short_description,
                "href": f"/scholars/{person.scholar_profile.slug}",
            }
            for person in scholars
        )

        works = _published_work_queryset().filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(search_aliases__icontains=query)
            | Q(editions__contributions__person__preferred_name__icontains=query)
        ).distinct()[:limit]
        for work in works:
            work_data = compact_work(work, request)
            if not work_data:
                continue
            results.append(
                {
                    "kind": "work",
                    **work_data,
                    "description": work.abstract[:360],
                    "href": work_data.get("detail_href"),
                }
            )

        passages = Passage.objects.filter(
            normalized_text__icontains=query.casefold(),
            page__asset__edition__state=PublicationState.PUBLISHED,
            page__asset__status=Asset.Status.READY,
            page__asset__is_current=True,
        ).select_related("page__asset__edition__work")[:limit]
        results.extend(
            {
                "kind": "passage",
                "id": str(passage.id),
                "title": passage.page.asset.edition.work.title,
                "subtitle": f"PDF 第 {passage.page.index} 页",
                "description": passage.text,
                "href": (
                    f"/reader/{passage.page.asset_id}?page={passage.page.index}"
                    f"&q={query}&passage={passage.id}"
                ),
            }
            for passage in passages
        )
        return Response({"query": query, "results": results[: limit * 4]})


class KnowledgeNodeListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = KnowledgeNodeListSerializer

    def get_queryset(self):
        return _node_filter(_published_node_queryset(), self.request.query_params).order_by(
            "sort_order", "canonical_name_zh"
        )


class KnowledgeNodeDetailView(TheorySystemFeatureMixin, generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = KnowledgeNodeDetailSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return _published_node_queryset().prefetch_related(
            "outgoing_relations__target_node",
            "incoming_relations__source_node",
            "work_relations__work",
            "work_relations__evidence__file",
            "evidence__work",
            "evidence__file",
        )


class TheoryDisciplineDetailView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request, slug):
        discipline = get_object_or_404(
            Discipline,
            slug=slug,
            editorial_status="published",
        )
        nodes = _published_node_queryset().filter(
            Q(primary_discipline=discipline)
            | Q(discipline_links__discipline=discipline, discipline_links__status="published")
        ).distinct()
        node_type = request.query_params.get("type", "theory_tradition")
        displayed = nodes.filter(node_type=node_type).order_by("sort_order", "canonical_name_zh")
        work_ids = WorkNodeRelation.objects.filter(
            node__in=nodes,
            status="published",
            work__editions__state=PublicationState.PUBLISHED,
        ).values("work_id").distinct()
        scholar_ids = PersonNodeRelation.objects.filter(
            node__in=nodes,
            status="published",
        ).values("person_id").distinct()
        reading_paths = ReadingPath.objects.filter(
            status="published",
            primary_discipline=discipline,
        ).prefetch_related("items__node", "items__work")[:6]
        lineage = (
            TheoryTimelineEvent.objects.filter(
                Q(discipline=discipline)
                | Q(normalized_relations__discipline=discipline),
                review_status=RelationReviewStatus.APPROVED,
            )
            .prefetch_related(
                "normalized_relations__node",
                "normalized_relations__discipline",
                "normalized_relations__scholar__person",
                "normalized_relations__work",
            )
            .distinct()
            .order_by("start_year", "display_order")[:12]
        )
        counts = {
            "theory_traditions": nodes.filter(node_type="theory_tradition").count(),
            "subdisciplines": nodes.filter(node_type="subdiscipline").count(),
            "debates": nodes.filter(node_type="debate").count(),
            "scholars": scholar_ids.count(),
            "works": work_ids.count(),
        }
        return Response(
            {
                "discipline": DisciplineCompactSerializer(
                    discipline,
                    context={"request": request},
                ).data,
                "counts": {key: value for key, value in counts.items() if value > 0},
                "active_type": node_type,
                "nodes": KnowledgeNodeListSerializer(
                    displayed,
                    many=True,
                    context={"request": request},
                ).data,
                "lineage": NormalizedTimelineEventSerializer(
                    lineage,
                    many=True,
                    context={"request": request},
                ).data,
                "reading_paths": ReadingPathSerializer(
                    reading_paths,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )


class NormalizedTimelineListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NormalizedTimelineEventSerializer

    def get_queryset(self):
        queryset = TheoryTimelineEvent.objects.filter(
            review_status=RelationReviewStatus.APPROVED
        ).prefetch_related(
            "normalized_relations__node",
            "normalized_relations__discipline",
            "normalized_relations__scholar__person",
            "normalized_relations__work",
        )
        params = self.request.query_params
        discipline = params.get("discipline", "").strip()
        node = params.get("node", "").strip()
        event_type = params.get("event_type", "").strip()
        has_collection = params.get("has_collection", "").strip().lower()
        query = params.get("q", "").strip()
        if discipline:
            queryset = queryset.filter(
                Q(discipline__slug=discipline)
                | Q(normalized_relations__discipline__slug=discipline)
                | Q(normalized_relations__node__discipline_links__discipline__slug=discipline)
            )
        if node:
            queryset = queryset.filter(normalized_relations__node__slug=node)
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if has_collection in {"1", "true", "yes"}:
            queryset = queryset.filter(
                Q(work__editions__state=PublicationState.PUBLISHED)
                | Q(normalized_relations__work__editions__state=PublicationState.PUBLISHED)
            )
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(source__icontains=query)
                | Q(normalized_relations__node__canonical_name_zh__icontains=query)
            )
        return queryset.distinct().order_by("start_year", "display_order", "title")


class LocalTheoryGraphView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        depth = min(max(int(request.query_params.get("depth", 1)), 1), 2)
        limit = min(max(int(request.query_params.get("limit", 20)), 1), 30)
        center_value = request.query_params.get("center", "").strip()
        discipline = request.query_params.get("discipline", "").strip()
        node_type = request.query_params.get("node_type", "").strip()
        relation_type = request.query_params.get("relation_type", "").strip()
        start_year = request.query_params.get("start_year", "").strip()
        end_year = request.query_params.get("end_year", "").strip()
        has_collection = request.query_params.get("has_collection", "").strip().lower()
        nodes_base = _published_node_queryset()
        if discipline:
            nodes_base = nodes_base.filter(
                Q(primary_discipline__slug=discipline)
                | Q(discipline_links__discipline__slug=discipline)
            ).distinct()
        if node_type:
            nodes_base = nodes_base.filter(node_type=node_type)
        if start_year.lstrip("-").isdigit():
            nodes_base = nodes_base.filter(
                Q(end_year__gte=int(start_year))
                | Q(end_year__isnull=True, start_year__gte=int(start_year))
            )
        if end_year.lstrip("-").isdigit():
            nodes_base = nodes_base.filter(
                Q(start_year__lte=int(end_year)) | Q(start_year__isnull=True)
            )
        if has_collection in {"1", "true", "yes"}:
            nodes_base = nodes_base.filter(
                work_relations__status="published",
                work_relations__work__editions__state=PublicationState.PUBLISHED,
            ).distinct()
        allowed_node_ids = set(nodes_base.values_list("id", flat=True))
        center = None
        if center_value:
            center = nodes_base.filter(
                Q(slug=center_value) | Q(pk=center_value if _is_uuid(center_value) else None)
            ).first()
        if center is None:
            center = nodes_base.filter(node_type="theory_tradition").order_by(
                "sort_order", "canonical_name_zh"
            ).first()
        if center is None:
            return Response({"nodes": [], "edges": [], "center": None, "truncated": False})

        selected = {center.id: center}
        edge_rows = []
        frontier = {center.id}
        for _level in range(depth):
            if not frontier or len(selected) >= limit:
                break
            relations = KnowledgeRelation.objects.filter(
                Q(source_node_id__in=frontier) | Q(target_node_id__in=frontier),
                status="published",
                source_node__status="published",
                target_node__status="published",
            ).select_related("source_node", "target_node")
            if relation_type:
                relations = relations.filter(relation_type=relation_type)
            next_frontier = set()
            for relation in relations.order_by("-confidence", "created_at"):
                for node in (relation.source_node, relation.target_node):
                    if (
                        node.id in allowed_node_ids
                        and node.id not in selected
                        and len(selected) < limit
                    ):
                        selected[node.id] = node
                        next_frontier.add(node.id)
                if relation.source_node_id in selected and relation.target_node_id in selected:
                    edge_rows.append(relation)
            frontier = next_frontier

        graph_nodes = [
            {
                "id": str(node.id),
                "kind": "knowledge_node",
                "node_type": node.node_type,
                "name": node.canonical_name_zh,
                "foreign_name": node.canonical_name_en,
                "slug": node.slug,
                "summary": node.summary,
                "period_label": node.period_label,
                "is_center": node.id == center.id,
            }
            for node in selected.values()
        ]
        graph_edges = [
            {
                "id": str(row.id),
                "source": str(row.source_node_id),
                "target": str(row.target_node_id),
                "relation_type": row.relation_type,
                "relation_label": row.get_relation_type_display(),
                "direction": row.direction,
                "description": row.description,
            }
            for row in {row.id: row for row in edge_rows}.values()
        ]

        if len(graph_nodes) < limit:
            people = center.person_relations.filter(
                status="published",
                is_representative=True,
                person__scholar_profile__editorial_status="published",
            ).select_related("person", "person__scholar_profile")[: max(0, limit - len(graph_nodes))]
            for relation in people:
                graph_nodes.append(
                    {
                        "id": f"person:{relation.person_id}",
                        "kind": "scholar",
                        "name": relation.person.preferred_name,
                        "slug": relation.person.scholar_profile.slug,
                    }
                )
                graph_edges.append(
                    {
                        "id": f"person-edge:{relation.id}",
                        "source": str(center.id),
                        "target": f"person:{relation.person_id}",
                        "relation_type": "representative_scholar",
                        "relation_label": relation.relation_label or "代表学者",
                        "direction": "undirected",
                    }
                )

        if len(graph_nodes) < limit:
            works = center.work_relations.filter(
                status="published",
                work__editions__state=PublicationState.PUBLISHED,
            ).select_related("work").distinct()[: max(0, limit - len(graph_nodes))]
            for relation in works:
                graph_nodes.append(
                    {
                        "id": f"work:{relation.work_id}",
                        "kind": "work",
                        "name": relation.work.title,
                        "work": compact_work(relation.work, request),
                    }
                )
                graph_edges.append(
                    {
                        "id": f"work-edge:{relation.id}",
                        "source": str(center.id),
                        "target": f"work:{relation.work_id}",
                        "relation_type": relation.role,
                        "relation_label": relation.get_role_display(),
                        "direction": "undirected",
                    }
                )
        return Response(
            {
                "center": str(center.id),
                "nodes": graph_nodes[:limit],
                "edges": graph_edges,
                "depth": depth,
                "limit": limit,
                "truncated": len(graph_nodes) >= limit,
            }
        )


class ReadingPathListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReadingPathSerializer

    def get_queryset(self):
        queryset = ReadingPath.objects.filter(status="published").select_related(
            "primary_discipline"
        ).prefetch_related("items__node", "items__work")
        discipline = self.request.query_params.get("discipline", "").strip()
        if discipline:
            queryset = queryset.filter(primary_discipline__slug=discipline)
        return queryset.order_by("sort_order", "title")


class ReadingPathDetailView(TheorySystemFeatureMixin, generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReadingPathSerializer
    lookup_field = "slug"
    queryset = ReadingPath.objects.filter(status="published").select_related(
        "primary_discipline"
    ).prefetch_related("items__node", "items__work")


class AdminKnowledgeNodeListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeNodeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = KnowledgeNode.objects.select_related("primary_discipline").prefetch_related(
            "aliases",
            "discipline_links__discipline",
        )
        legacy_id = self.request.query_params.get("legacy_id", "").strip()
        if legacy_id:
            queryset = queryset.filter(
                legacy_mappings__legacy_model="TheorySchool",
                legacy_mappings__legacy_id=legacy_id,
            )
        return _node_filter(queryset, self.request.query_params).distinct().order_by(
            "sort_order", "canonical_name_zh"
        )


class AdminKnowledgeNodeDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeNodeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = KnowledgeNode.objects.select_related("primary_discipline").prefetch_related(
        "aliases",
        "discipline_links__discipline",
    )

    def destroy(self, request, *args, **kwargs):
        node = self.get_object()
        if request.user.role != "admin":
            return Response({"detail": "只有管理员可以下线理论节点。"}, status=403)
        node.status = "archived"
        node.published_at = None
        node.save(update_fields=["status", "published_at", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminKnowledgeNodeVersionListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = KnowledgeNodeVersionSerializer

    def get_queryset(self):
        return KnowledgeNodeVersion.objects.filter(node_id=self.kwargs["pk"]).select_related(
            "created_by"
        )


class AdminKnowledgeNodeMergePreviewView(TheorySystemFeatureMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request, pk):
        source = get_object_or_404(KnowledgeNode, pk=pk)
        return Response({"source": str(source.id), "affected": merge_preview(source)})


class AdminKnowledgeNodeMergeView(TheorySystemFeatureMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request, pk):
        target_id = request.data.get("target_node")
        if not target_id:
            return Response({"target_node": ["请选择合并目标。"]}, status=400)
        try:
            record = merge_nodes(
                pk,
                target_id,
                actor=request.user,
                change_note=request.data.get("change_note", ""),
            )
        except (KnowledgeNode.DoesNotExist, ValueError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            KnowledgeNodeMergeRecordSerializer(record, context={"request": request}).data,
            status=201,
        )


class AdminKnowledgeNodeMergeRollbackView(TheorySystemFeatureMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request, record_id):
        try:
            record = rollback_merge(record_id, actor=request.user)
        except (KnowledgeNodeMergeRecord.DoesNotExist, ValueError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(KnowledgeNodeMergeRecordSerializer(record).data)


class AdminKnowledgeRelationListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeRelationSerializer

    def get_queryset(self):
        queryset = KnowledgeRelation.objects.select_related("source_node", "target_node")
        params = self.request.query_params
        for field in ("relation_type", "direction", "status"):
            value = params.get(field, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        node = params.get("node", "").strip()
        if node:
            queryset = queryset.filter(Q(source_node_id=node) | Q(target_node_id=node))
        return queryset.order_by("-updated_at")


class AdminKnowledgeRelationDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeRelationSerializer
    queryset = KnowledgeRelation.objects.select_related("source_node", "target_node")


class AdminKnowledgeRelationVersionListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = KnowledgeRelationVersionSerializer

    def get_queryset(self):
        return KnowledgeRelationVersion.objects.filter(
            relation_id=self.kwargs["pk"]
        ).select_related("created_by")


class AdminWorkNodeRelationListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminWorkNodeRelationSerializer

    def get_queryset(self):
        queryset = WorkNodeRelation.objects.select_related("work", "node").prefetch_related(
            "evidence__file"
        )
        params = self.request.query_params
        for field in ("role", "status", "strength", "work", "node"):
            value = params.get(field, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(work__title__icontains=query)
                | Q(node__canonical_name_zh__icontains=query)
                | Q(evidence__quote__icontains=query)
            )
        return queryset.distinct().order_by("-updated_at")


class AdminWorkNodeRelationDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminWorkNodeRelationSerializer
    queryset = WorkNodeRelation.objects.select_related("work", "node").prefetch_related(
        "evidence__file"
    )


class AdminEvidenceListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = EvidenceSnippetSerializer

    def get_queryset(self):
        queryset = EvidenceSnippet.objects.select_related(
            "work", "file", "node", "work_node_relation", "knowledge_relation"
        )
        params = self.request.query_params
        for field in ("work", "file", "node", "work_node_relation", "review_status"):
            value = params.get(field, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        return queryset.order_by("-created_at")


class AdminEvidenceDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = EvidenceSnippetSerializer
    queryset = EvidenceSnippet.objects.all()


class AdminTheoryReviewTaskListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = TheoryReviewTaskSerializer

    def get_queryset(self):
        queryset = TheoryReviewTask.objects.select_related(
            "work", "file", "candidate_node", "assigned_to"
        )
        params = self.request.query_params
        for field in ("task_type", "status", "assigned_to", "candidate_node"):
            value = params.get(field, "").strip()
            if value:
                queryset = queryset.filter(**{field: value})
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(work__title__icontains=query)
                | Q(candidate_node__canonical_name_zh__icontains=query)
                | Q(suggested_node_name__icontains=query)
                | Q(evidence_text__icontains=query)
            )
        return queryset.order_by("-created_at")


class AdminTheoryReviewTaskDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = TheoryReviewTaskSerializer
    queryset = TheoryReviewTask.objects.select_related(
        "work", "file", "candidate_node", "assigned_to"
    )

    def perform_destroy(self, instance):
        if getattr(self.request.user, "role", "") != "admin":
            raise PermissionDenied("只有管理员可以删除理论审核项。")
        snapshot = {
            "task_type": instance.task_type,
            "status": instance.status,
            "work_id": str(instance.work_id or ""),
            "work_title": instance.work.title if instance.work_id else "",
            "candidate_node_id": str(instance.candidate_node_id or ""),
            "suggested_node_name": instance.suggested_node_name,
            "suggested_relation_type": instance.suggested_relation_type,
            "evidence_pages": instance.evidence_pages,
        }
        object_id = str(instance.pk)
        instance.delete()
        AuditEvent.objects.create(
            actor=self.request.user,
            action="theory_review_task_delete",
            object_type="catalog.TheoryReviewTask",
            object_id=object_id,
            before=snapshot,
            after={"deleted": True},
        )


class AdminTheoryReviewActionView(TheorySystemFeatureMixin, APIView):
    permission_classes = [IsKnowledgeReviewer]

    @staticmethod
    def _unique_slug(name: str) -> str:
        base = slugify(name, allow_unicode=False) or f"node-{uuid4().hex[:8]}"
        value = base[:180]
        suffix = 2
        while KnowledgeNode.objects.filter(slug=value).exists():
            marker = f"-{suffix}"
            value = f"{base[: 180 - len(marker)]}{marker}"
            suffix += 1
        return value

    @staticmethod
    def _create_work_followup(task, node, relation_type, actor):
        """Keep a new-node decision separate from the later work-relation review."""

        if not task.work_id:
            return
        allowed_roles = {value for value, _label in WorkNodeRelation.Role.choices}
        if relation_type not in allowed_roles:
            relation_type = WorkNodeRelation.Role.GENERAL_MENTION
        relation, _created = WorkNodeRelation.objects.update_or_create(
            work=task.work,
            node=node,
            role=relation_type,
            defaults={
                "confidence": task.confidence,
                "status": "pending",
                "source": "theory_review_new_node",
                "created_by": actor,
            },
        )
        pages = [int(value) for value in task.evidence_pages or [] if str(value).isdigit()]
        if task.file_id and pages and task.evidence_text:
            EvidenceSnippet.objects.update_or_create(
                work=task.work,
                file=task.file,
                node=node,
                work_node_relation=relation,
                page_number=min(pages),
                defaults={
                    "page_end": max(pages),
                    "quote": task.evidence_text,
                    "extraction_method": (
                        EvidenceSnippet.ExtractionMethod.OCR
                        if task.file.extraction_method == "ocr"
                        else EvidenceSnippet.ExtractionMethod.TEXT_LAYER
                    ),
                    "semantic_confidence": task.confidence,
                    "review_status": RelationReviewStatus.SUGGESTED,
                },
            )
        TheoryReviewTask.objects.update_or_create(
            task_type=TheoryReviewTask.TaskType.WORK_NODE,
            work=task.work,
            file=task.file,
            candidate_node=node,
            defaults={
                "suggested_relation_type": relation_type,
                "confidence": task.confidence,
                "evidence_pages": task.evidence_pages,
                "evidence_text": task.evidence_text,
                "status": TheoryReviewTask.TaskStatus.PENDING,
                "submitted_at": timezone.now(),
            },
        )

    @transaction.atomic
    def post(self, request, pk):
        task = get_object_or_404(TheoryReviewTask.objects.select_for_update(), pk=pk)
        action = request.data.get("action", "").strip()
        status_map = {
            "reject": TheoryReviewTask.TaskStatus.REJECTED,
            "defer": TheoryReviewTask.TaskStatus.DEFERRED,
            "insufficient": TheoryReviewTask.TaskStatus.INSUFFICIENT_EVIDENCE,
            "needs_changes": TheoryReviewTask.TaskStatus.NEEDS_CHANGES,
        }
        if action in status_map:
            task.status = status_map[action]
        elif action == "create_node":
            if task.task_type != TheoryReviewTask.TaskType.NEW_NODE:
                return Response({"action": ["只有新增节点建议可以创建草稿节点。"]}, status=400)
            name = (request.data.get("canonical_name_zh") or task.suggested_node_name).strip()
            if not name:
                return Response({"canonical_name_zh": ["请填写规范中文名。"]}, status=400)
            node_type = request.data.get("node_type") or KnowledgeNode.NodeType.THEORY_TRADITION
            allowed_types = {value for value, _label in KnowledgeNode.NodeType.choices}
            if node_type not in allowed_types:
                return Response({"node_type": ["请选择受控的节点类型。"]}, status=400)
            if KnowledgeNode.objects.filter(canonical_name_zh__iexact=name).exists():
                return Response(
                    {"canonical_name_zh": ["已经存在同名规范节点，请改为已有节点别名。"]},
                    status=400,
                )
            primary_discipline = None
            if request.data.get("primary_discipline"):
                primary_discipline = get_object_or_404(
                    Discipline,
                    pk=request.data["primary_discipline"],
                )
            node = KnowledgeNode.objects.create(
                node_type=node_type,
                canonical_name_zh=name,
                canonical_name_en=(request.data.get("canonical_name_en") or "").strip(),
                slug=self._unique_slug(name),
                primary_discipline=primary_discipline,
                status="draft",
                created_by=request.user,
            )
            if primary_discipline:
                KnowledgeNodeDiscipline.objects.create(
                    node=node,
                    discipline=primary_discipline,
                    relation_type=KnowledgeNodeDiscipline.RelationType.PRIMARY,
                    status="pending",
                )
            record_node_version(node, request.user, "从 PDF 新理论候选创建草稿")
            task.candidate_node = node
            self._create_work_followup(
                task,
                node,
                request.data.get("relation_type") or WorkNodeRelation.Role.GENERAL_MENTION,
                request.user,
            )
            task.status = TheoryReviewTask.TaskStatus.CONFIRMED
        elif action in {"alias_existing", "merge_existing"}:
            if task.task_type != TheoryReviewTask.TaskType.NEW_NODE:
                return Response({"action": ["只有新增节点建议可以归并为已有节点别名。"]}, status=400)
            if not request.data.get("candidate_node"):
                return Response({"candidate_node": ["请选择已有规范节点。"]}, status=400)
            node = get_object_or_404(KnowledgeNode, pk=request.data["candidate_node"])
            alias = task.suggested_node_name.strip()
            if alias and alias.casefold() != node.canonical_name_zh.casefold():
                normalized = " ".join(alias.casefold().split())
                conflict = KnowledgeNodeAlias.objects.filter(normalized_alias=normalized).exclude(
                    node=node
                ).select_related("node").first()
                if conflict:
                    return Response(
                        {"candidate_node": [f"该别名已属于“{conflict.node.canonical_name_zh}”。"]},
                        status=400,
                    )
                KnowledgeNodeAlias.objects.get_or_create(
                    node=node,
                    normalized_alias=normalized,
                    defaults={
                        "alias": alias,
                        "language": "zh-CN",
                        "alias_type": KnowledgeNodeAlias.AliasType.ALIAS,
                        "created_by": request.user,
                    },
                )
                record_node_version(node, request.user, f"确认 PDF 候选别名 {alias}")
            task.candidate_node = node
            self._create_work_followup(
                task,
                node,
                request.data.get("relation_type") or WorkNodeRelation.Role.GENERAL_MENTION,
                request.user,
            )
            task.status = TheoryReviewTask.TaskStatus.CONFIRMED
        elif action in {"confirm", "modify_confirm"}:
            node = task.candidate_node
            if request.data.get("candidate_node"):
                node = get_object_or_404(KnowledgeNode, pk=request.data["candidate_node"])
            if node is None:
                return Response({"candidate_node": ["确认前必须选择规范节点。"]}, status=400)
            task.candidate_node = node
            relation_type = request.data.get("relation_type") or task.suggested_relation_type
            if task.task_type == TheoryReviewTask.TaskType.WORK_NODE:
                allowed_roles = {value for value, _label in WorkNodeRelation.Role.choices}
                if relation_type not in allowed_roles:
                    return Response({"relation_type": ["请选择受控的文献关系类型。"]}, status=400)
                if not task.work_id:
                    return Response({"work": ["审核任务缺少馆藏文献。"]}, status=400)
                relation, _created = WorkNodeRelation.objects.update_or_create(
                    work=task.work,
                    node=node,
                    role=relation_type,
                    defaults={
                        "confidence": task.confidence,
                        "status": "published",
                        "source": "theory_review_task",
                        "reviewed_by": request.user,
                        "reviewed_at": timezone.now(),
                    },
                )
                pages = [int(value) for value in task.evidence_pages or [] if str(value).isdigit()]
                if task.file_id and pages and task.evidence_text:
                    EvidenceSnippet.objects.update_or_create(
                        work=task.work,
                        file=task.file,
                        node=node,
                        work_node_relation=relation,
                        page_number=min(pages),
                        defaults={
                            "page_end": max(pages),
                            "quote": task.evidence_text,
                            "extraction_method": (
                                EvidenceSnippet.ExtractionMethod.OCR
                                if task.file.extraction_method == "ocr"
                                else EvidenceSnippet.ExtractionMethod.TEXT_LAYER
                            ),
                            "semantic_confidence": task.confidence,
                            "review_status": RelationReviewStatus.APPROVED,
                            "reviewed_by": request.user,
                            "reviewed_at": timezone.now(),
                        },
                    )
            task.status = TheoryReviewTask.TaskStatus.CONFIRMED
        else:
            return Response({"action": ["未知审核操作。"]}, status=400)

        task.review_note = request.data.get("review_note", task.review_note)
        if request.data.get("assigned_to"):
            task.assigned_to_id = request.data["assigned_to"]
        task.reviewed_at = timezone.now()
        task.save()
        return Response(TheoryReviewTaskSerializer(task, context={"request": request}).data)


class AdminReadingPathListView(TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = ReadingPathSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = ReadingPath.objects.select_related("primary_discipline").prefetch_related(
            "items__node", "items__work"
        )
        status_value = self.request.query_params.get("status", "").strip()
        discipline = self.request.query_params.get("discipline", "").strip()
        query = self.request.query_params.get("q", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        if discipline:
            queryset = queryset.filter(primary_discipline__slug=discipline)
        if query:
            queryset = queryset.filter(Q(title__icontains=query) | Q(introduction__icontains=query))
        return queryset.order_by("sort_order", "title")


class AdminReadingPathDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = ReadingPathSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = ReadingPath.objects.select_related("primary_discipline").prefetch_related(
        "items__node", "items__work"
    )
