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

from common.capabilities import Capability, has_capability
from common.permissions import (
    CanMergeAuthority,
    CanRunSystemRecovery,
    IsKnowledgeEditor,
    IsKnowledgeReviewer,
)
from ingestion.models import AuditEvent

from .editorial_read import AdminEditorialDraftReadMixin

from .models import (
    Asset,
    Discipline,
    CanonicalObjectRevision,
    EditorialRevision,
    EvidenceSnippet,
    KnowledgeNode,
    KnowledgeNodeAlias,
    KnowledgeNodeDiscipline,
    KnowledgeNodeSubdiscipline,
    KnowledgeNodeTopic,
    KnowledgeNodeMergeRecord,
    KnowledgeNodeVersion,
    KnowledgeRelation,
    KnowledgeRelationVersion,
    Page,
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
from .services.scoped_search import SearchContext, SearchService
from .services.semantic_search import viewer_access_statuses
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
        authenticated = bool(request.user.is_authenticated)
        staff = bool(
            authenticated
            and (
                request.user.is_staff
                or getattr(request.user, "role", "") in {"admin", "editor", "reviewer"}
            )
        )
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
                file__access_status__in=viewer_access_statuses(
                    authenticated=authenticated,
                    staff=staff,
                ),
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
    published_subdisciplines = KnowledgeNodeSubdiscipline.objects.filter(
        status="published"
    ).select_related("subdiscipline__discipline")
    published_topics = KnowledgeNodeTopic.objects.filter(status="published").select_related(
        "topic"
    )
    return KnowledgeNode.objects.filter(status="published").select_related(
        "primary_discipline"
    ).prefetch_related(
        "aliases",
        Prefetch("discipline_links", queryset=published_links),
        Prefetch("subdiscipline_links", queryset=published_subdisciplines),
        Prefetch("topic_links", queryset=published_topics),
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
        queryset = SearchService().apply_query(
            queryset,
            SearchContext.THEORIES,
            query,
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


def _published_work_node_relation_requires_revision(work=None):
    return Response(
        {
            "detail": (
                "已发布作品的知识关系必须通过 Workbench 编辑草稿修改，"
                "确认发布前不会影响公网。"
            ),
            "code": "published_work_relation_requires_revision",
            "work_id": str(work.id) if work is not None else None,
            "replacement": (
                f"/admin/library/works/{work.id}#knowledge"
                if work is not None
                else "/admin/library"
            ),
        },
        status=status.HTTP_409_CONFLICT,
    )


def _node_alias_revision_from_review_task(task, node, alias, actor):
    from catalog.services.editorial_revision import create_editorial_revision, editorial_target_snapshot

    latest = EditorialRevision.objects.select_for_update().filter(
        target_type="knowledge_node", target_id=node.pk, status="draft",
    ).order_by("-revision").first()
    current = CanonicalObjectRevision.objects.filter(
        object_type="knowledge_node", object_id=node.pk,
    ).values_list("current_revision", flat=True).first() or 0
    if latest is not None and latest.base_revision != current:
        raise ValueError("正式理论内容已经变化，请先更新编辑草稿。")
    snapshot = editorial_target_snapshot(target_type="knowledge_node", target=node)
    patch = dict(latest.patch or {}) if latest is not None else {}
    aliases = list(patch.get("aliases", snapshot.get("aliases", [])))
    normalized = " ".join(alias.casefold().split())
    if not any(" ".join(str(row.get("alias", "")).casefold().split()) == normalized for row in aliases):
        aliases.append({"alias": alias, "language": "zh-CN", "alias_type": "alias",
                        "source_kind": KnowledgeNodeAlias.SourceKind.PDF_EVIDENCE, "is_verified": True})
    patch["aliases"] = aliases
    revision = create_editorial_revision(
        target_type="knowledge_node", target_id=node.pk, patch=patch, actor=actor,
        idempotency_key=f"theory-review-task:{task.id}:node-alias",
        change_note="采用本书中的理论别名，等待正式发布",
    )
    if latest is not None and latest.pk != revision.pk:
        latest.status = EditorialRevision.Status.SUPERSEDED
        latest.save(update_fields=["status", "updated_at"])
    return revision


def _work_relation_revision_from_review_task(task, node, relation_type, actor):
    from catalog.services.editorial_revision import (
        create_editorial_revision,
        editorial_target_snapshot,
    )

    snapshot = editorial_target_snapshot(target_type="work", target=task.work)
    knowledge = dict(snapshot["knowledge"])
    rows = [dict(row) for row in knowledge.get("nodes", [])]
    key = (str(node.id), relation_type)
    pages = [
        int(value)
        for value in task.evidence_pages or []
        if str(value).isdigit()
    ]
    candidate_row = {
        "id": str(node.id),
        "role": relation_type,
        "strength": "medium",
        "is_primary": False,
        "evidence_asset": str(task.file_id) if task.file_id and pages and task.evidence_text else None,
        "evidence_page": min(pages) if pages and task.evidence_text else None,
        "evidence_page_end": max(pages) if pages and task.evidence_text else None,
        "evidence_printed_label": "",
        "evidence_text": task.evidence_text if pages else "",
    }
    replaced = False
    for index, row in enumerate(rows):
        if (str(row.get("id")), str(row.get("role"))) == key:
            rows[index] = candidate_row
            replaced = True
            break
    if not replaced:
        rows.append(candidate_row)
    knowledge["nodes"] = rows
    if knowledge == snapshot["knowledge"]:
        return None
    return create_editorial_revision(
        target_type="work",
        target_id=task.work_id,
        patch={"knowledge": knowledge},
        actor=actor,
        idempotency_key=f"theory-review-task:{task.id}:work-relation",
        change_note="采用理论关系候选，待单人确认发布",
    )


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


class KnowledgeNodeListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = KnowledgeNodeListSerializer

    def get_queryset(self):
        queryset = _node_filter(_published_node_queryset(), self.request.query_params)
        if self.request.query_params.get("q", "").strip():
            return queryset.order_by("_search_rank", "sort_order", "canonical_name_zh")
        return queryset.order_by("sort_order", "canonical_name_zh")


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
            person__authority_status="verified",
            person__scholar_profile__editorial_status="published",
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
                person__authority_status="verified",
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
        ).prefetch_related("stages", "items__stage", "items__node", "items__work")
        discipline = self.request.query_params.get("discipline", "").strip()
        if discipline:
            queryset = queryset.filter(primary_discipline__slug=discipline)
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        return SearchService(request=self.request).queryset(
            SearchContext.READING_PATHS,
            query,
            base_queryset=queryset,
        )


class ReadingPathDetailView(TheorySystemFeatureMixin, generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ReadingPathSerializer
    lookup_field = "slug"
    queryset = ReadingPath.objects.filter(status="published").select_related(
        "primary_discipline"
    ).prefetch_related("stages", "items__stage", "items__node", "items__work")


class AdminKnowledgeNodeListView(AdminEditorialDraftReadMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    editorial_target_type = "knowledge_node"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeNodeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = KnowledgeNode.objects.select_related("primary_discipline").prefetch_related(
            "aliases",
            "discipline_links__discipline",
            "subdiscipline_links__subdiscipline__discipline",
            "topic_links__topic",
        )
        legacy_id = self.request.query_params.get("legacy_id", "").strip()
        if legacy_id:
            queryset = queryset.filter(
                legacy_mappings__legacy_model="TheorySchool",
                legacy_mappings__legacy_id=legacy_id,
            )
        queryset = _node_filter(queryset, self.request.query_params).distinct()
        if self.request.query_params.get("q", "").strip():
            return queryset.order_by("_search_rank", "sort_order", "canonical_name_zh")
        return queryset.order_by("sort_order", "canonical_name_zh")


class AdminKnowledgeNodeDetailView(
    AdminEditorialDraftReadMixin,
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    editorial_target_type = "knowledge_node"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeNodeSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = KnowledgeNode.objects.select_related("primary_discipline").prefetch_related(
        "aliases",
        "discipline_links__discipline",
        "subdiscipline_links__subdiscipline__discipline",
        "topic_links__topic",
    )

    def update(self, request, *args, **kwargs):
        node = self.get_object()
        if node.status != "published":
            return super().update(request, *args, **kwargs)

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(node, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        if "cover_asset" in values:
            return Response(
                {
                    "detail": "已发布节点的主视觉暂不能绕过编辑草稿直接替换。请先发布文字草稿，再单独处理主视觉版本。",
                    "code": "published_binary_requires_revision",
                },
                status=status.HTTP_409_CONFLICT,
            )
        aliases = values.get("aliases")
        if aliases is not None:
            values["aliases"] = [dict(row) for row in aliases]
        links = values.get("discipline_links")
        if links is not None:
            values["discipline_links"] = [
                {
                    "discipline_id": str(row["discipline"].id),
                    "relation_type": row.get("relation_type", "related"),
                    "discipline_specific_summary": row.get(
                        "discipline_specific_summary", ""
                    ),
                    "sort_order": row.get("sort_order", 0),
                    "status": row.get("status", "pending"),
                }
                for row in links
            ]
        subdiscipline_links = values.get("subdiscipline_links")
        if subdiscipline_links is not None:
            values["subdiscipline_links"] = [
                {
                    "subdiscipline_id": str(row["subdiscipline"].id),
                    "is_primary": row.get("is_primary", False),
                    "relation_role": row.get("relation_role", ""),
                    "source": row.get("source", ""),
                    "confidence": row.get("confidence", 0),
                    "sort_order": row.get("sort_order", 0),
                    "status": row.get("status", "pending"),
                }
                for row in subdiscipline_links
            ]
        topic_links = values.get("topic_links")
        if topic_links is not None:
            values["topic_links"] = [
                {
                    "topic_id": str(row["topic"].id),
                    "relation_label": row.get("relation_label", ""),
                    "source": row.get("source", ""),
                    "confidence": row.get("confidence", 0),
                    "sort_order": row.get("sort_order", 0),
                    "status": row.get("status", "pending"),
                }
                for row in topic_links
            ]
        from catalog.services.editorial_revision import (
            EditorialRevisionError,
            changed_editorial_patch,
            create_editorial_revision,
            editorial_idempotency_key,
            serialize_editorial_revision,
        )

        try:
            patch = changed_editorial_patch(
                target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                target=node,
                patch=values,
            )
            if not patch:
                return Response(self._draft_read_rows([node])[0])
            current_revision = (
                CanonicalObjectRevision.objects.filter(
                    object_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                    object_id=node.id,
                )
                .values_list("current_revision", flat=True)
                .first()
                or 0
            )
            revision = create_editorial_revision(
                target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                target_id=node.id,
                patch=patch,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
                or editorial_idempotency_key(
                    target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                    target_id=node.id,
                    base_revision=current_revision,
                    patch=patch,
                ),
                change_note=str(request.data.get("change_note") or "知识工作室编辑草稿"),
            )
        except EditorialRevisionError as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(self._draft_read_rows([node])[0], status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        node = self.get_object()
        if not has_capability(request.user, Capability.PUBLISH_AUTHORITY):
            return Response({"detail": "只有管理员可以下线理论节点。"}, status=403)
        if node.status != "published":
            return super().destroy(request, *args, **kwargs)
        from catalog.services.editorial_revision import (
            EditorialRevisionError,
            create_editorial_revision,
            editorial_idempotency_key,
            serialize_editorial_revision,
        )

        patch = {"status": "archived"}
        current_revision = (
            CanonicalObjectRevision.objects.filter(
                object_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                object_id=node.id,
            )
            .values_list("current_revision", flat=True)
            .first()
            or 0
        )
        try:
            revision = create_editorial_revision(
                target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                target_id=node.id,
                patch=patch,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
                or editorial_idempotency_key(
                    target_type=EditorialRevision.TargetType.KNOWLEDGE_NODE,
                    target_id=node.id,
                    base_revision=current_revision,
                    patch=patch,
                ),
                change_note=str(request.data.get("change_note") or "下线已发布知识节点"),
            )
        except EditorialRevisionError as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"editorial_revision": serialize_editorial_revision(revision)},
            status=status.HTTP_202_ACCEPTED,
        )


class AdminKnowledgeNodeVersionListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = KnowledgeNodeVersionSerializer

    def get_queryset(self):
        return KnowledgeNodeVersion.objects.filter(node_id=self.kwargs["pk"]).select_related(
            "created_by"
        )


class AdminKnowledgeNodeMergePreviewView(TheorySystemFeatureMixin, APIView):
    permission_classes = [CanMergeAuthority]

    def get(self, request, pk):
        source = get_object_or_404(KnowledgeNode, pk=pk)
        return Response({"source": str(source.id), "affected": merge_preview(source)})


class AdminKnowledgeNodeMergeView(TheorySystemFeatureMixin, APIView):
    permission_classes = [CanMergeAuthority]

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
    permission_classes = [CanRunSystemRecovery]

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

    def destroy(self, request, *args, **kwargs):
        relation = self.get_object()
        if relation.status == "published":
            return Response(
                {
                    "detail": "已发布知识关系不能硬删除，请先把状态改为 archived。",
                    "code": "published_relation_requires_withdrawal",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


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

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        work = serializer.validated_data["work"]
        if work.editions.filter(state=PublicationState.PUBLISHED).exists():
            return _published_work_node_relation_requires_revision(work)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED,
            headers=headers,
        )


class AdminWorkNodeRelationDetailView(
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminWorkNodeRelationSerializer
    queryset = WorkNodeRelation.objects.select_related("work", "node").prefetch_related(
        "evidence__file"
    )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        requested_work = serializer.validated_data.get("work", instance.work)
        if (
            instance.work.editions.filter(
                state=PublicationState.PUBLISHED
            ).exists()
            or requested_work.editions.filter(
                state=PublicationState.PUBLISHED
            ).exists()
        ):
            blocked_work = (
                instance.work
                if instance.work.editions.filter(
                    state=PublicationState.PUBLISHED
                ).exists()
                else requested_work
            )
            return _published_work_node_relation_requires_revision(blocked_work)
        self.perform_update(serializer)
        if getattr(instance, "_prefetched_objects_cache", None):
            instance._prefetched_objects_cache = {}
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.work.editions.filter(
            state=PublicationState.PUBLISHED
        ).exists():
            return _published_work_node_relation_requires_revision(instance.work)
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
        pending_revision = None
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
            node = get_object_or_404(KnowledgeNode.objects.select_for_update(), pk=request.data["candidate_node"])
            if node.status == "archived":
                return Response({"candidate_node": ["该理论节点已经下线，请选择其他节点。"]}, status=409)
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
                if node.status == "published":
                    try:
                        pending_revision = _node_alias_revision_from_review_task(task, node, alias, request.user)
                    except ValueError as exc:
                        return Response({"detail": str(exc), "code": "editorial_revision_error"}, status=409)
                else:
                    KnowledgeNodeAlias.objects.get_or_create(
                        node=node, normalized_alias=normalized,
                        defaults={"alias": alias, "language": "zh-CN",
                                  "alias_type": KnowledgeNodeAlias.AliasType.ALIAS,
                                  "source_kind": KnowledgeNodeAlias.SourceKind.PDF_EVIDENCE,
                                  "is_verified": True, "created_by": request.user},
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
                pages = [int(value) for value in task.evidence_pages or [] if str(value).isdigit()]
                if task.work.editions.filter(
                    state=PublicationState.PUBLISHED
                ).exists():
                    try:
                        pending_revision = _work_relation_revision_from_review_task(
                            task,
                            node,
                            relation_type,
                            request.user,
                        )
                    except ValueError as exc:
                        return Response(
                            {
                                "detail": str(exc),
                                "code": "editorial_revision_error",
                            },
                            status=status.HTTP_409_CONFLICT,
                        )
                else:
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
        payload = dict(
            TheoryReviewTaskSerializer(task, context={"request": request}).data
        )
        if pending_revision is not None:
            from catalog.services.editorial_revision import (
                serialize_editorial_revision,
            )

            payload["editorial_revision"] = serialize_editorial_revision(
                pending_revision
            )
        return Response(payload)


class AdminReadingPathListView(AdminEditorialDraftReadMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    editorial_target_type = "reading_path"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = ReadingPathSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = ReadingPath.objects.select_related("primary_discipline").prefetch_related(
            "stages", "items__stage", "items__node", "items__work"
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

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_unpublished_items"] = True
        return context


class AdminReadingPathDetailView(
    AdminEditorialDraftReadMixin,
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    editorial_target_type = "reading_path"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = ReadingPathSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = ReadingPath.objects.select_related("primary_discipline").prefetch_related(
        "stages", "items__stage", "items__node", "items__work"
    )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_unpublished_items"] = True
        return context

    def update(self, request, *args, **kwargs):
        path = self.get_object()
        if path.status != "published":
            return super().update(request, *args, **kwargs)
        if "cover_asset" in request.data:
            return Response(
                {
                    "detail": "已发布阅读路径的封面尚不支持进入 JSON 编辑草稿。",
                    "code": "published_binary_requires_revision",
                },
                status=status.HTTP_409_CONFLICT,
            )
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(path, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
        expected_updated_at = values.pop("expected_updated_at", None)
        if expected_updated_at is not None and path.updated_at != expected_updated_at:
            return Response(
                {
                    "detail": "阅读路径已被其他编辑更新，请刷新后重试。",
                    "code": "editorial_revision_conflict",
                },
                status=status.HTTP_409_CONFLICT,
            )
        items = values.pop("items", None)
        stage_groups = values.pop("stage_groups", None)
        from catalog.services.editorial_revision import (
            EditorialRevisionError,
            changed_editorial_patch,
            create_editorial_revision,
            editorial_idempotency_key,
            serialize_editorial_revision,
        )
        from catalog.services.reading_paths import (
            ReadingPathStructureError,
            stage_groups_from_items,
        )

        try:
            if stage_groups is not None:
                values["stage_groups"] = stage_groups
            elif items is not None:
                values["stage_groups"] = stage_groups_from_items(path, items)
            patch = changed_editorial_patch(
                target_type=EditorialRevision.TargetType.READING_PATH,
                target=path,
                patch=values,
            )
            if not patch:
                return Response(self._draft_read_rows([path])[0])
            current_revision = (
                CanonicalObjectRevision.objects.filter(
                    object_type=EditorialRevision.TargetType.READING_PATH,
                    object_id=path.id,
                )
                .values_list("current_revision", flat=True)
                .first()
                or 0
            )
            revision = create_editorial_revision(
                target_type=EditorialRevision.TargetType.READING_PATH,
                target_id=path.id,
                patch=patch,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
                or editorial_idempotency_key(
                    target_type=EditorialRevision.TargetType.READING_PATH,
                    target_id=path.id,
                    base_revision=current_revision,
                    patch=patch,
                ),
                change_note=str(
                    request.data.get("change_note") or "阅读路径编辑草稿"
                ),
            )
        except (EditorialRevisionError, ReadingPathStructureError) as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._draft_read_rows([path])[0], status=status.HTTP_202_ACCEPTED)

    def destroy(self, request, *args, **kwargs):
        path = self.get_object()
        if path.status != "published":
            return super().destroy(request, *args, **kwargs)
        if not has_capability(request.user, Capability.PUBLISH_AUTHORITY):
            raise PermissionDenied("删除已发布阅读路径需要 authority 发布权限。")
        from catalog.services.editorial_revision import (
            EditorialRevisionError,
            create_editorial_revision,
            editorial_idempotency_key,
            serialize_editorial_revision,
        )

        patch = {"status": "archived"}
        current_revision = (
            CanonicalObjectRevision.objects.filter(
                object_type=EditorialRevision.TargetType.READING_PATH,
                object_id=path.id,
            )
            .values_list("current_revision", flat=True)
            .first()
            or 0
        )
        try:
            revision = create_editorial_revision(
                target_type=EditorialRevision.TargetType.READING_PATH,
                target_id=path.id,
                patch=patch,
                actor=request.user,
                idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
                or editorial_idempotency_key(
                    target_type=EditorialRevision.TargetType.READING_PATH,
                    target_id=path.id,
                    base_revision=current_revision,
                    patch=patch,
                ),
                change_note=str(
                    request.data.get("change_note") or "下线已发布阅读路径"
                ),
            )
        except EditorialRevisionError as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {"editorial_revision": serialize_editorial_revision(revision)},
            status=status.HTTP_202_ACCEPTED,
        )

    def perform_destroy(self, instance):
        if instance.status == "published" and not has_capability(
            self.request.user,
            Capability.PUBLISH_AUTHORITY,
        ):
            raise PermissionDenied("删除已发布阅读路径需要 authority 发布权限。")
        return super().perform_destroy(instance)
