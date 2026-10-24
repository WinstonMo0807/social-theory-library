from __future__ import annotations

from catalog.node_editor_views import NodeCommandMixin, KnowledgeRelationCommandMixin
from catalog.relation_editorial_views import relations_for_node
from catalog.theory_review_commands import TheoryReviewCommandMixin, TheoryReviewInput

from uuid import UUID, uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, F, Prefetch, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import generics, serializers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError as APIValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from .public_response_serializers import ReaderFocusSerializer

from common.capabilities import Capability, has_capability
from common.permissions import (
    CanMergeAuthority,
    CanRunSystemRecovery,
    IsKnowledgeEditor,
    IsKnowledgeReviewer,
)
from ingestion.models import AuditEvent

from .editorial_read import AdminEditorialDraftReadMixin, AdminPrivateResponseMixin
from .relation_editorial_views import StagedRelationEditorMixin

from .models import (
    Asset,
    Contribution,
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
    ScholarProfile,
    Subdiscipline,
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
from .services.publication_eligibility import active_catalog_snapshot, public_editions
from .services.semantic_search import viewer_access_statuses
from .theory_serializers import (
    AdminKnowledgeNodeSerializer,
    AdminReadingPathSerializer,
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
    NormalizedTimelineDetailSerializer,
    NormalizedTimelinePageSerializer,
    ReadingPathSerializer,
    TheoryReviewTaskSerializer,
    TheoryReviewResultSerializer,
    WorkNodeRelationSerializer,
    compact_work,
    _public_evidence_queryset,
)
from .theory_public_schema import TheorySystemOverviewSerializer
from .graph_serializers import PublicTheoryGraphSerializer


class TheorySystemFeatureMixin:
    def initial(self, request, *args, **kwargs):
        if not settings.THEORY_SYSTEM_ENABLED:
            raise NotFound("新版理论知识系统当前未启用。")
        return super().initial(request, *args, **kwargs)


class PublicEvidenceFocusView(TheorySystemFeatureMixin, APIView):
    """Return a reviewed evidence locator for the existing PDF reader."""

    permission_classes = [AllowAny]

    @extend_schema(responses=ReaderFocusSerializer)
    def get(self, request, pk):
        evidence = get_object_or_404(
            _public_evidence_queryset({"request": request}).select_related("node").filter(
                Q(node__isnull=False) | Q(work_node_relation__isnull=False)
                | Q(knowledge_relation__isnull=False),
                pk=pk,
                file__edition__active_catalog_revision__document_revision__asset_id=F("file_id"),
            ).distinct(),
        )
        page = get_object_or_404(Page, asset=evidence.file, index=evidence.page_number)
        raw_box = evidence.bounding_box or {}
        bbox = raw_box.get("rect", []) if isinstance(raw_box, dict) else raw_box
        return Response(
            {
                "id": str(evidence.id),
                "asset_id": str(evidence.file_id),
                "document_revision_id": str(evidence.file.edition.active_catalog_revision.document_revision_id),
                "text_source": page.text_source,
                "title": str((active_catalog_snapshot(evidence.file.edition).get("work") or {}).get("title") or ""),
                "page_index": evidence.page_number,
                "printed_label": evidence.printed_page_label or page.printed_label,
                "width": page.width,
                "height": page.height,
                "bbox": bbox if isinstance(bbox, list) else [],
                # Historical hand-selected evidence does not record units.
                "geometry": {}, "normalized_bbox": [], "geometry_status": "unknown",
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
        discipline_query = Q(primary_discipline__slug=discipline, primary_discipline__editorial_status="published") | Q(
            discipline_links__discipline__slug=discipline,
            discipline_links__discipline__editorial_status="published",
            discipline_links__status="published",
        )
        if _is_uuid(discipline):
            discipline_query |= Q(primary_discipline_id=discipline, primary_discipline__editorial_status="published") | Q(
                discipline_links__discipline_id=discipline,
                discipline_links__discipline__editorial_status="published",
                discipline_links__status="published",
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
    return Work.objects.filter(pk__in=public_editions().values("work_id"))


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

    @extend_schema(responses=TheorySystemOverviewSerializer)
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
                work_id__in=public_editions().values("work_id"),
            ).values("work_id").distinct()
            counts = {
                "theory_traditions": nodes.filter(node_type="theory_tradition").count(),
                "subdisciplines": Subdiscipline.objects.filter(
                    discipline=discipline, editorial_status="published",
                ).count(),
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
                work_id__in=public_editions().values("work_id"),
            )
            .select_related("work", "node")
            .order_by("-reviewed_at", "-updated_at")[:6]
        )
        from .models import RecommendationPolicy
        from .services.canonical_identity import CanonicalIdentityError, mapped_node_for_legacy
        from .services.recommendations import current_snapshot
        policy = RecommendationPolicy.objects.filter(placement="home_theories", enabled=True).first()
        snapshot = current_snapshot(policy) if policy else None
        featured_ids = []
        for item in snapshot.items.filter(theory_school__editorial_status="published").order_by("position", "created_at") if snapshot else []:
            if not item.theory_school_id:
                continue
            try:
                node = mapped_node_for_legacy("TheorySchool", item.theory_school_id)
            except CanonicalIdentityError:
                continue
            if node.status == "published" and node.pk not in featured_ids:
                featured_ids.append(node.pk)
        by_id = {node.pk: node for node in _published_node_queryset().filter(pk__in=featured_ids)}
        featured_nodes = [by_id[identifier] for identifier in featured_ids if identifier in by_id]
        return Response(
            {
                "disciplines": discipline_rows,
                "featured_nodes": KnowledgeNodeListSerializer(featured_nodes, many=True, context={"request": request}).data,
                "browse": {
                    "theory_traditions": _published_node_queryset()
                    .filter(node_type="theory_tradition")
                    .count(),
                    "subdisciplines": Subdiscipline.objects.filter(editorial_status="published").count(),
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
        if self.request.query_params.get("has_works", "").strip().lower() in {"1", "true", "yes"}:
            queryset = queryset.filter(pk__in=WorkNodeRelation.objects.filter(
                status="published", work_id__in=public_editions().values("work_id"),
            ).values("node_id"))
        sort = self.request.query_params.get("sort", "")
        if sort and sort not in {"name", "updated"}:
            raise APIValidationError({"sort": "未知理论目录排序方式。"})
        if sort == "updated":
            return queryset.order_by("-updated_at", "pk")
        if sort == "name":
            return queryset.order_by("canonical_name_zh", "pk")
        if self.request.query_params.get("q", "").strip():
            return queryset.order_by("_search_rank", "sort_order", "canonical_name_zh", "pk")
        return queryset.order_by("sort_order", "canonical_name_zh", "pk")


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
        return Response(self.public_payload(request, discipline))

    @staticmethod
    def public_payload(request, discipline):
        """Shared public projection; protected previews supply an in-memory draft parent."""
        nodes = _published_node_queryset().filter(
            Q(primary_discipline=discipline)
            | Q(discipline_links__discipline=discipline, discipline_links__status="published")
        ).distinct()
        node_type = request.query_params.get("type", "theory_tradition") if request else "theory_tradition"
        displayed = nodes.filter(node_type=node_type).order_by("sort_order", "canonical_name_zh")
        work_ids = WorkNodeRelation.objects.filter(
            node__in=nodes,
            status="published",
            work_id__in=public_editions().values("work_id"),
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
            "subdisciplines": Subdiscipline.objects.filter(
                discipline=discipline, editorial_status="published",
            ).count(),
            "debates": nodes.filter(node_type="debate").count(),
            "scholars": scholar_ids.count(),
            "works": work_ids.count(),
        }
        return {
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


class NormalizedTimelineListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = NormalizedTimelineEventSerializer
    pagination_class = None

    def get_queryset(self):
        from .services.timeline_publication import ordered, scoped_events
        if getattr(self, "swagger_fake_view", False):
            return TheoryTimelineEvent.objects.none()
        rows, sort, _selected = scoped_events(self.request.query_params)
        return ordered(rows, sort)

    @extend_schema(
        responses=NormalizedTimelinePageSerializer,
        parameters=[
            *[OpenApiParameter(key, str) for key in ("discipline", "node", "q", "related_to", "focus")],
            *[OpenApiParameter(key, str, many=True, description="重复参数或逗号分隔，组内OR；最多30项。")
              for key in ("topic", "author", "event_type")],
            OpenApiParameter("sort", str, enum=["asc", "desc"]),
            OpenApiParameter("year_from", int), OpenApiParameter("year_to", int),
            OpenApiParameter("year", str, description="年份组或undated；不改变全筛选集的year_groups。"),
            OpenApiParameter("page", int), OpenApiParameter("has_collection", bool),
        ],
    )
    def get(self, request, *args, **kwargs):
        from django.core.paginator import InvalidPage, Paginator
        from rest_framework.utils.urls import remove_query_param, replace_query_param
        from .services.timeline_publication import aggregates, focus_page, integer, ordered, scoped_events
        params = request.query_params
        scope, sort, selections = scoped_events(params)
        summary = aggregates(scope)
        group = params.get("year", "").strip()
        rows = scope.filter(timeline_year__isnull=True) if group == "undated" else scope
        if group and group != "undated":
            rows = rows.filter(timeline_year=integer(params, "year"))
        rows = ordered(rows, sort)
        focus = params.get("focus", "").strip()
        selected_id = None
        if focus:
            page_number, selected_id = focus_page(rows, focus, sort, 24)
        else:
            raw_page = params.get("page", "1")
            try:
                page_number = int(raw_page) if raw_page.isascii() and raw_page.isdigit() else 0
            except ValueError:
                page_number = 0
            if page_number < 1:
                raise APIValidationError({"page": "页码须为正整数。"})
        paginator = Paginator(rows, 24)
        try:
            page = paginator.page(page_number)
        except InvalidPage:
            raise NotFound("此事件页不存在，请返回第一页重新查看。")
        base_url = remove_query_param(request.build_absolute_uri(), "focus")
        return Response({
            "count": paginator.count,
            "next": replace_query_param(base_url, "page", page.next_page_number()) if page.has_next() else None,
            "previous": replace_query_param(base_url, "page", page.previous_page_number()) if page.has_previous() else None,
            "results": self.get_serializer(page.object_list, many=True).data,
            "page": page.number, "page_size": 24, "total_pages": paginator.num_pages,
            "focus_id": selected_id, **summary, **selections,
        })


class NormalizedTimelineDetailView(NormalizedTimelineListView):
    """Stable event links reuse the public timeline's visibility and serializer."""
    serializer_class = NormalizedTimelineDetailSerializer

    @extend_schema(operation_id="theory_system_timeline_detail", responses=NormalizedTimelineDetailSerializer)
    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from catalog.services.timeline_merge import resolved_event_id
        return Response(self.get_serializer(get_object_or_404(self.get_queryset(), pk=resolved_event_id(pk))).data)


class LocalTheoryGraphView(TheorySystemFeatureMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicTheoryGraphSerializer, parameters=[
        OpenApiParameter("center_kind", str, enum=["knowledge_node", "scholar", "topic", "subdiscipline"]),
        OpenApiParameter("center", str, description="中心实体 UUID 或已公开 slug；学者使用档案身份。"),
        OpenApiParameter("depth", int, enum=[1, 2, 3]),
        OpenApiParameter("limit", int, description="最多120个节点。"),
        OpenApiParameter("edge_limit", int, description="最多300条已确认关系。"),
        OpenApiParameter("node_type", str, many=True),
        OpenApiParameter("relation_type", str, many=True),
        OpenApiParameter("discipline", str),
        OpenApiParameter("start_year", int), OpenApiParameter("end_year", int),
        OpenApiParameter("has_collection", bool),
        OpenApiParameter("include_candidates", bool, description="仅同时具备证据查看和知识编辑权限；候选与正式关系分开。"),
        OpenApiParameter("selected_node", str, description="kind:UUID；必须在当前子图中。"),
        OpenApiParameter("works_page", int),
    ])
    def get(self, request):
        from .services.theory_graph import build_public_graph
        response = Response(build_public_graph(request.query_params, request=request))
        response["Cache-Control"] = "private, no-store"
        response["Vary"] = "Cookie, Authorization"
        return response


class ReadingPathListView(TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [AllowAny]
    from catalog.reading_path_serializers import PublicReadingPathSerializer
    serializer_class = PublicReadingPathSerializer

    def get_queryset(self):
        from uuid import UUID
        from catalog.reading_path_serializers import ReadingPathQuery
        schema = ReadingPathQuery(data=self.request.query_params)
        schema.is_valid(raise_exception=True)
        values = schema.validated_data
        queryset = ReadingPath.objects.filter(status="published").select_related("primary_discipline")
        for parameter, relation, status_field in (("discipline", "primary_discipline", "editorial_status"),
                ("topic", "topics", "editorial_status"), ("node", "items__node", "status")):
            value = values.get(parameter)
            if value:
                try:
                    identifier = UUID(value)
                except ValueError:
                    identifier = None
                queryset = queryset.filter(**{relation + ("__pk" if identifier else "__slug"): identifier or value,
                    relation + "__" + status_field: "published"}).distinct()
        if values.get("difficulty"):
            queryset = queryset.filter(difficulty=values["difficulty"])
        query = values.get("q") or values.get("search") or ""
        return SearchService(request=self.request).queryset(SearchContext.READING_PATHS, query, base_queryset=queryset)

    @extend_schema(parameters=[
        OpenApiParameter("q", str), OpenApiParameter("search", str),
        OpenApiParameter("discipline", str, description="已公开学科UUID或slug"),
        OpenApiParameter("topic", str, description="已公开主题UUID或slug"),
        OpenApiParameter("node", str, description="已公开知识节点UUID或slug"),
        OpenApiParameter("difficulty", str, enum=["beginner", "intermediate", "advanced"]),
        OpenApiParameter("page", int),
    ])
    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response


class ReadingPathDetailView(TheorySystemFeatureMixin, generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    from catalog.reading_path_serializers import PublicReadingPathSerializer
    serializer_class = PublicReadingPathSerializer
    lookup_field = "slug"
    queryset = ReadingPath.objects.filter(status="published")

    @extend_schema(parameters=[OpenApiParameter("revision", str, description="本路径正式发布修订UUID；旧记录为legacy摘要"),
        OpenApiParameter("compare_to", str, description="同一路径的较早正式公开修订，返回安全版本差异")])
    def retrieve(self, request, *args, **kwargs):
        from catalog.reading_path_serializers import ReadingPathQuery
        from catalog.services.public_reading_paths import public_reading_path_snapshot, diff_reading_path_snapshots
        schema = ReadingPathQuery(data=request.query_params)
        schema.is_valid(raise_exception=True)
        values = schema.validated_data
        path = self.get_object()
        payload = public_reading_path_snapshot(path.pk, revision=values.get("revision"), request=request)
        if values.get("compare_to"):
            previous = public_reading_path_snapshot(path.pk, revision=values["compare_to"], request=request)
            payload["diff"] = diff_reading_path_snapshots(previous, payload)
        response = Response(self.get_serializer(payload).data)
        response["Cache-Control"] = "no-store"
        return response


class AdminKnowledgeNodeListView(NodeCommandMixin, AdminEditorialDraftReadMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    http_method_names = ["get", "post", "head", "options"]
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
    NodeCommandMixin,
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
        if "cover_asset" in request.data:
            if set(request.data) != {"cover_asset"} or "cover_asset" not in request.FILES:
                return Response({"detail": "请单独上传图片，清除请使用媒体选择。"}, status=400)
            from catalog.services.knowledge_media import stage_legacy_image_upload
            try:
                stage_legacy_image_upload(node, request.FILES["cover_asset"], actor=request.user)
            except (ValueError, ValidationError) as error:
                return Response({"detail": str(error), "code": "image_selection_failed"}, status=409)
            return Response(self._draft_read_rows([node])[0], status=202)
        if node.status != "published" and not EditorialRevision.objects.filter(target_type="knowledge_node", target_id=node.pk, status="draft").exists():
            return super().update(request, *args, **kwargs)

        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(node, data=request.data, partial=partial,
            context={**self.get_serializer_context(), "defer_authority_publication": True})
        serializer.is_valid(raise_exception=True)
        values = dict(serializer.validated_data)
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
            from catalog.services.editorial_drafts import save_object_editorial_patch
            revision = save_object_editorial_patch("knowledge_node", node.pk, values, actor=request.user,
                                                   request_key=request.headers.get("Idempotency-Key", ""),
                                                   change_note=str(request.data.get("change_note") or "知识工作室编辑草稿"))
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


class AdminKnowledgeNodeVersionListView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = KnowledgeNodeVersionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return KnowledgeNodeVersion.objects.none()
        return KnowledgeNodeVersion.objects.filter(node_id=self.kwargs["pk"]).select_related(
            "created_by"
        )


class AdminKnowledgeNodeMergePreviewView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
    permission_classes = [CanMergeAuthority]

    def get(self, request, pk):
        source = get_object_or_404(KnowledgeNode, pk=pk)
        return Response({"source": str(source.id), "affected": merge_preview(source)})


class AdminKnowledgeNodeMergeView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
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


class AdminKnowledgeNodeMergeRollbackView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
    permission_classes = [CanRunSystemRecovery]

    def post(self, request, record_id):
        try:
            record = rollback_merge(record_id, actor=request.user)
        except (KnowledgeNodeMergeRecord.DoesNotExist, ValueError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(KnowledgeNodeMergeRecordSerializer(record).data)


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("node", str, description="当前正式或草稿关联的节点编号。")]))
class AdminKnowledgeRelationListView(KnowledgeRelationCommandMixin, StagedRelationEditorMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    http_method_names = ["get", "post", "head", "options"]
    editorial_target_type = "knowledge_relation"
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
            queryset = relations_for_node(queryset, node)
        query = params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(source_node__canonical_name_zh__icontains=query)
                | Q(target_node__canonical_name_zh__icontains=query)
                | Q(description__icontains=query)
                | Q(evidence_source__icontains=query)
            )
        return queryset.order_by("-updated_at", "pk")


@extend_schema_view(get=extend_schema(parameters=[OpenApiParameter("node", str, description="可选节点范围，包含正式及草稿端点。")]))
class AdminKnowledgeRelationDetailView(
    KnowledgeRelationCommandMixin,
    StagedRelationEditorMixin,
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    editorial_target_type = "knowledge_relation"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminKnowledgeRelationSerializer
    queryset = KnowledgeRelation.objects.select_related("source_node", "target_node")

    def get_queryset(self):
        rows = super().get_queryset()
        node = self.request.query_params.get("node")
        return relations_for_node(rows, node) if node else rows

    def destroy(self, request, *args, **kwargs):
        relation = self.get_object()
        if relation.status == "published":
            return Response(
                {
                    "detail": "已公开的关系不能删除。请选择下线，保存后再确认发布。",
                    "code": "published_relation_requires_withdrawal",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)


class AdminKnowledgeRelationVersionListView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = KnowledgeRelationVersionSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return KnowledgeRelationVersion.objects.none()
        return KnowledgeRelationVersion.objects.filter(
            relation_id=self.kwargs["pk"]
        ).select_related("created_by")


class AdminWorkNodeRelationListView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
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
    AdminPrivateResponseMixin,
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


class AdminEvidenceListView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = EvidenceSnippetSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "include_unpublished_items": True}

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
    AdminPrivateResponseMixin,
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = EvidenceSnippetSerializer
    queryset = EvidenceSnippet.objects.all()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "include_unpublished_items": True}


class TheoryReviewPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 24

    def get_page_size(self, request):
        return serializers.IntegerField(min_value=1, max_value=24).run_validation(request.query_params.get("page_size", 24))


@extend_schema_view(get=extend_schema(parameters=[
    *[OpenApiParameter(name, type=UUID) for name in ("work", "file", "candidate_node", "scholar")],
    OpenApiParameter("review_only", type=bool), OpenApiParameter("page_size", type=int),
]))
class AdminTheoryReviewTaskListView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.ListAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = TheoryReviewTaskSerializer
    pagination_class = TheoryReviewPagination

    def get_queryset(self):
        queryset = TheoryReviewTask.objects.select_related(
            "work", "file", "candidate_node", "assigned_to"
        )
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        params = self.request.query_params
        for field in ("work", "file", "candidate_node"):
            value = params.get(field, "").strip()
            if value:
                try:
                    identifier = UUID(value)
                except ValueError as exc:
                    raise APIValidationError({field: "材料来源编号无效，请从原处理任务重新打开。"}) from exc
                queryset = queryset.filter(**{field: identifier})
        if scholar_id := params.get("scholar", "").strip():
            scholar_id = serializers.UUIDField().run_validation(scholar_id)
            scholar = get_object_or_404(ScholarProfile, pk=scholar_id)
            editions = Contribution.objects.filter(person_id=scholar.person_id, approved=True).values("edition_id")
            queryset = queryset.filter(file__edition_id__in=editions, work_id=F("file__edition__work_id"))
        if serializers.BooleanField().run_validation(params.get("review_only", False)):
            queryset = queryset.filter(status__in=["pending", "needs_changes", "deferred", "insufficient_evidence"])
        for field in ("task_type", "status", "assigned_to"):
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
        return queryset.order_by("-created_at", "pk")


class AdminTheoryReviewTaskDetailView(AdminPrivateResponseMixin, TheorySystemFeatureMixin, generics.RetrieveAPIView):
    permission_classes = [IsKnowledgeEditor]
    serializer_class = TheoryReviewTaskSerializer
    queryset = TheoryReviewTask.objects.select_related("work", "file", "candidate_node", "assigned_to")


class AdminTheoryReviewActionView(TheoryReviewCommandMixin, AdminPrivateResponseMixin, TheorySystemFeatureMixin, APIView):
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
        get_object_or_404(Work.objects.select_for_update(), pk=task.work_id)
        allowed_roles = {value for value, _label in WorkNodeRelation.Role.choices}
        if relation_type not in allowed_roles:
            relation_type = WorkNodeRelation.Role.GENERAL_MENTION
        relation, _created = WorkNodeRelation.objects.get_or_create(
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
            EvidenceSnippet.objects.get_or_create(
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
        # An alias decision must not reset an existing human review or evidence.
        if not TheoryReviewTask.objects.filter(task_type=TheoryReviewTask.TaskType.WORK_NODE,
                work=task.work, file=task.file, candidate_node=node).exists():
            TheoryReviewTask.objects.create(task_type=TheoryReviewTask.TaskType.WORK_NODE,
                work=task.work, file=task.file, candidate_node=node,
                suggested_relation_type=relation_type, confidence=task.confidence,
                evidence_pages=task.evidence_pages, evidence_text=task.evidence_text,
                status=TheoryReviewTask.TaskStatus.PENDING, submitted_at=timezone.now())

    @extend_schema(request=TheoryReviewInput, responses=TheoryReviewResultSerializer)
    def post(self, request, pk):
        return self.review_command(request, pk, lambda: self._apply_decision(request, pk))

    @transaction.atomic
    def _apply_decision(self, request, pk):
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


from catalog.path_editor_views import PathCommandMixin


class AdminReadingPathListView(PathCommandMixin, AdminEditorialDraftReadMixin, TheorySystemFeatureMixin, generics.ListCreateAPIView):
    editorial_target_type = "reading_path"
    http_method_names = ["get", "post", "head", "options"]
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminReadingPathSerializer
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
        return queryset.order_by("sort_order", "title", "pk")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["include_unpublished_items"] = True
        return context


class AdminReadingPathDetailView(
    PathCommandMixin,
    AdminEditorialDraftReadMixin,
    TheorySystemFeatureMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    editorial_target_type = "reading_path"
    permission_classes = [IsKnowledgeEditor]
    serializer_class = AdminReadingPathSerializer
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
        if "cover_asset" in request.data:
            from rest_framework import serializers
            expected = serializers.DateTimeField(required=False).run_validation(request.data["expected_updated_at"]) if "expected_updated_at" in request.data else None
            if expected is not None and path.updated_at != expected:
                return Response({"detail": "阅读路径已变化，请重新读取。"}, status=409)
            if set(request.data) - {"cover_asset", "expected_updated_at"} or "cover_asset" not in request.FILES:
                return Response({"detail": "请单独上传图片，清除请使用媒体选择。"}, status=400)
            from catalog.services.knowledge_media import stage_legacy_image_upload
            try:
                stage_legacy_image_upload(path, request.FILES["cover_asset"], actor=request.user)
            except (ValueError, ValidationError) as error:
                return Response({"detail": str(error), "code": "image_selection_failed"}, status=409)
            return Response(self._draft_read_rows([path])[0], status=202)
        if path.status != "published" and request.data.get("status") != "published" and not EditorialRevision.objects.filter(target_type="reading_path", target_id=path.pk, status="draft").exists():
            return super().update(request, *args, **kwargs)
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
            from catalog.services.editorial_drafts import save_object_editorial_patch
            revision = save_object_editorial_patch("reading_path", path.pk, values, actor=request.user,
                                                   request_key=request.headers.get("Idempotency-Key", ""),
                                                   change_note=str(request.data.get("change_note") or "阅读路径编辑草稿"))
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
