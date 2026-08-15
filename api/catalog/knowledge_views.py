from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsLibraryStaff

from .models import (
    AboutPageBlock,
    Discipline,
    PublicationState,
    RecommendationOverride,
    RecommendationPolicy,
    RecommendationSnapshot,
    RelationReviewStatus,
    ScholarProfile,
    Subdiscipline,
    TheoryDisciplineRelation,
    TheoryHierarchyRelation,
    TheoryRelation,
    TheorySchool,
    TheorySubdisciplineRelation,
    TheoryTimelineEvent,
    Topic,
    TopicDisciplineRelation,
    TopicSubdisciplineRelation,
    TopicTheoryRelation,
    Work,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkSubdisciplineRelation,
)
from .serializers import (
    AboutPageBlockSerializer,
    AdminDisciplineSerializer,
    AdminRecommendationOverrideSerializer,
    AdminSubdisciplineSerializer,
    AdminTheoryDisciplineRelationSerializer,
    AdminTheoryHierarchyRelationSerializer,
    AdminTheoryRelationSerializer,
    AdminTheorySubdisciplineRelationSerializer,
    AdminTheoryTimelineEventSerializer,
    AdminTopicDisciplineRelationSerializer,
    AdminTopicSubdisciplineRelationSerializer,
    AdminTopicTheoryRelationSerializer,
    AdminWorkDisciplineRelationSerializer,
    AdminWorkSubdisciplineRelationSerializer,
    AdminWorkTheoryRelationSerializer,
    DisciplineSerializer,
    RecommendationPolicySerializer,
    SubdisciplineSerializer,
    TheoryTimelineEventSerializer,
)
from .query_filters import filter_slug_or_uuid
from .services.recommendations import (
    PLACEMENT_TARGETS,
    current_recommendations,
    ensure_default_policies,
    generate_snapshot,
)


class DisciplineListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DisciplineSerializer

    def get_queryset(self):
        queryset = Discipline.objects.filter(editorial_status="published")
        query = self.request.query_params.get("q", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(foreign_name__icontains=query)
                | Q(description__icontains=query)
                | Q(search_aliases__icontains=query)
            )
        return queryset.order_by("sort_order", "name")


class DisciplineDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = DisciplineSerializer
    lookup_field = "slug"
    queryset = Discipline.objects.filter(editorial_status="published")


class SubdisciplineListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubdisciplineSerializer

    def get_queryset(self):
        queryset = Subdiscipline.objects.filter(editorial_status="published").select_related(
            "discipline",
            "parent",
        )
        query = self.request.query_params.get("q", "").strip()
        discipline = self.request.query_params.get("discipline", "").strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(foreign_name__icontains=query)
                | Q(description__icontains=query)
                | Q(research_object__icontains=query)
            )
        if discipline:
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline__slug",
                id_field="discipline_id",
            )
        return queryset.order_by("discipline__sort_order", "name")


class SubdisciplineDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = SubdisciplineSerializer
    lookup_field = "slug"
    queryset = Subdiscipline.objects.filter(editorial_status="published").select_related(
        "discipline",
        "parent",
    )


class KnowledgeMatrixView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        disciplines = Discipline.objects.filter(editorial_status="published").order_by("sort_order", "name")
        return Response(
            {
                "disciplines": DisciplineSerializer(disciplines, many=True, context={"request": request}).data,
                "entry_modes": [
                    {
                        "key": "theory",
                        "title": "按理论传统进入",
                        "description": "从经典理论到当代流派，沿思想脉络进入理解。",
                        "href": "/theory-schools?mode=traditions",
                    },
                    {
                        "key": "subdiscipline",
                        "title": "按子学科进入",
                        "description": "聚焦具体领域，发现细分知识脉络。",
                        "href": "/subdisciplines",
                    },
                    {
                        "key": "topic",
                        "title": "按研究主题进入",
                        "description": "从研究领域与核心概念出发，连接相关理论、学者与原文。",
                        "href": "/topics",
                    },
                ],
                "counts": {
                    "disciplines": disciplines.count(),
                    "theories": TheorySchool.objects.filter(editorial_status="published").count(),
                    "subdisciplines": Subdiscipline.objects.filter(editorial_status="published").count(),
                    "topics": Topic.objects.filter(editorial_status="published").count(),
                },
            }
        )


class TheoryTimelineListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TheoryTimelineEventSerializer

    def get_queryset(self):
        queryset = TheoryTimelineEvent.objects.filter(
            review_status=RelationReviewStatus.APPROVED,
        ).select_related(
            "discipline",
            "theory_school",
            "subdiscipline",
            "scholar__person",
            "work",
        )
        discipline = self.request.query_params.get("discipline", "").strip()
        theory = self.request.query_params.get("theory", "").strip()
        orientation = self.request.query_params.get("orientation", "").strip()
        if discipline:
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline__slug",
                id_field="discipline_id",
            )
        if theory:
            queryset = filter_slug_or_uuid(
                queryset,
                theory,
                slug_field="theory_school__slug",
                id_field="theory_school_id",
            )
        if orientation:
            queryset = queryset.filter(orientation=orientation)
        return queryset.order_by("start_year", "display_order", "title")


class TheoryGraphView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        discipline = request.query_params.get("discipline", "").strip()
        theories = TheorySchool.objects.filter(editorial_status="published")
        if discipline:
            theories = theories.filter(
                discipline_relations__review_status=RelationReviewStatus.APPROVED,
                discipline_relations__discipline__slug=discipline,
            )
        theories = list(theories.distinct().order_by("name"))
        theory_ids = [item.id for item in theories]
        nodes = [
            {
                "id": str(theory.id),
                "slug": theory.slug,
                "name": theory.name,
                "foreign_name": theory.foreign_name,
                "entity_level": theory.entity_level,
                "symbol": theory.symbol,
                "curation_level": theory.curation_level,
            }
            for theory in theories
        ]
        edges = [
            {
                "id": str(relation.id),
                "source": str(relation.source_theory_id),
                "target": str(relation.target_theory_id),
                "relation_type": relation.relation_type,
                "strength": relation.strength,
                "evidence_page": relation.evidence_page,
                "evidence_text": relation.evidence_text,
            }
            for relation in TheoryRelation.objects.filter(
                review_status=RelationReviewStatus.APPROVED,
                source_theory_id__in=theory_ids,
                target_theory_id__in=theory_ids,
            )
        ]
        edges.extend(
            {
                "id": str(relation.id),
                "source": str(relation.parent_id),
                "target": str(relation.child_id),
                "relation_type": "hierarchy",
                "strength": "high",
                "evidence_text": relation.evidence_text,
            }
            for relation in TheoryHierarchyRelation.objects.filter(
                review_status=RelationReviewStatus.APPROVED,
                parent_id__in=theory_ids,
                child_id__in=theory_ids,
            )
        )
        return Response({"nodes": nodes, "edges": edges})


class RecommendationListView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        snapshots = current_recommendations()
        policies = []
        for placement, snapshot in snapshots.items():
            policy = snapshot.policy
            policy.resolved_snapshot = snapshot
            policies.append(policy)
        return Response(
            {
                "shared_for_all_readers": True,
                "rotation_days": 3,
                "placements": {
                    policy.placement: RecommendationPolicySerializer(
                        policy,
                        context={"request": request},
                    ).data
                    for policy in policies
                },
            }
        )


class AboutPageBlockListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = AboutPageBlockSerializer
    queryset = AboutPageBlock.objects.filter(visible=True).order_by("sort_order", "created_at")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        if isinstance(response.data, dict):
            response.data["configured"] = AboutPageBlock.objects.exists()
        return response


class AdminDisciplineListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminDisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Discipline.objects.all().order_by("sort_order", "name")


class AdminDisciplineDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminDisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Discipline.objects.all()


class AdminSubdisciplineListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminSubdisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        queryset = Subdiscipline.objects.select_related("discipline", "parent")
        discipline = self.request.query_params.get("discipline", "").strip()
        if discipline:
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline__slug",
                id_field="discipline_id",
            )
        return queryset.order_by("discipline__sort_order", "name")


class AdminSubdisciplineDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminSubdisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Subdiscipline.objects.select_related("discipline", "parent")


class AdminTheoryTimelineListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTheoryTimelineEventSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    def get_queryset(self):
        queryset = TheoryTimelineEvent.objects.select_related(
            "discipline",
            "theory_school",
            "subdiscipline",
            "scholar__person",
            "work",
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
        review_status = params.get("review_status", "").strip()
        has_collection = params.get("has_collection", "").strip().lower()
        query = params.get("q", "").strip()
        if discipline:
            queryset = queryset.filter(
                Q(discipline_id=discipline)
                | Q(normalized_relations__discipline_id=discipline)
                | Q(normalized_relations__node__primary_discipline_id=discipline)
            )
        if node:
            queryset = queryset.filter(normalized_relations__node_id=node)
        if event_type:
            queryset = queryset.filter(event_type=event_type)
        if review_status:
            queryset = queryset.filter(review_status=review_status)
        if has_collection in {"1", "true", "yes"}:
            queryset = queryset.filter(
                Q(work__isnull=False) | Q(normalized_relations__work__isnull=False)
            )
        if query:
            queryset = queryset.filter(
                Q(title__icontains=query)
                | Q(description__icontains=query)
                | Q(source__icontains=query)
                | Q(normalized_relations__node__canonical_name_zh__icontains=query)
            )
        return queryset.distinct().order_by("start_year", "display_order", "title")

    def perform_create(self, serializer):
        review_status = serializer.validated_data.get("review_status")
        serializer.save(
            reviewed_by=self.request.user if review_status == RelationReviewStatus.APPROVED else None,
            reviewed_at=timezone.now() if review_status == RelationReviewStatus.APPROVED else None,
        )


class AdminTheoryTimelineDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTheoryTimelineEventSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = TheoryTimelineEvent.objects.prefetch_related(
        "normalized_relations__node",
        "normalized_relations__discipline",
        "normalized_relations__scholar__person",
        "normalized_relations__work",
    )

    def perform_update(self, serializer):
        review_status = serializer.validated_data.get("review_status", serializer.instance.review_status)
        serializer.save(
            reviewed_by=self.request.user if review_status == RelationReviewStatus.APPROVED else serializer.instance.reviewed_by,
            reviewed_at=timezone.now() if review_status == RelationReviewStatus.APPROVED else serializer.instance.reviewed_at,
        )


class AdminRecommendationListView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request):
        policies = ensure_default_policies()
        for policy in policies:
            policy.resolved_snapshot = policy.snapshots.filter(is_current=True).first()
        return Response(RecommendationPolicySerializer(policies, many=True, context={"request": request}).data)


class AdminRecommendationPolicyView(APIView):
    permission_classes = [IsLibraryStaff]

    def put(self, request, placement):
        policy = get_object_or_404(RecommendationPolicy, placement=placement)
        serializer = RecommendationPolicySerializer(policy, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        policy = serializer.save(updated_by=request.user)
        return Response(RecommendationPolicySerializer(policy, context={"request": request}).data)


def _resolve_manual_target(target_type, identifier):
    mapping = {
        "work": Work,
        "theory_school": TheorySchool,
        "topic": Topic,
        "scholar": ScholarProfile,
    }
    model = mapping.get(target_type)
    if model is None:
        return None
    queryset = model.objects.all()
    if model is Work:
        queryset = queryset.filter(editions__state=PublicationState.PUBLISHED).distinct()
    else:
        queryset = queryset.filter(editorial_status="published")
    try:
        return queryset.filter(pk=identifier).first()
    except (DjangoValidationError, TypeError, ValueError):
        return None


class AdminRecommendationRefreshView(APIView):
    permission_classes = [IsLibraryStaff]

    def post(self, request, placement):
        policy = get_object_or_404(RecommendationPolicy, placement=placement)
        raw_items = request.data.get("items")
        selected = None
        if raw_items is not None:
            if not isinstance(raw_items, list):
                return Response({"items": ["人工推荐项目必须是列表。"]}, status=400)
            if len(raw_items) > policy.item_count:
                return Response({"items": [f"人工推荐最多只能选择 {policy.item_count} 项。"]}, status=400)
            selected = []
            expected_type = PLACEMENT_TARGETS.get(policy.placement)
            seen = set()
            for row in raw_items:
                if not isinstance(row, dict) or row.get("target_type") != expected_type:
                    return Response({"items": ["推荐对象类型与展示位置不一致。"]}, status=400)
                key = (row.get("target_type"), str(row.get("id", "")))
                if key in seen:
                    return Response({"items": ["人工推荐不能包含重复对象。"]}, status=400)
                seen.add(key)
                target = _resolve_manual_target(row.get("target_type"), row.get("id"))
                if target is None:
                    return Response({"items": ["推荐对象不存在或尚未公开。"]}, status=400)
                selected.append(target)
        source = (
            RecommendationSnapshot.Source.MANUAL
            if raw_items is not None
            else RecommendationSnapshot.Source.AUTOMATIC
        )
        snapshot = generate_snapshot(
            policy,
            actor=request.user,
            selected_targets=selected,
            source=source,
        )
        policy.resolved_snapshot = snapshot
        return Response(RecommendationPolicySerializer(policy, context={"request": request}).data)


class AdminRecommendationOverrideListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminRecommendationOverrideSerializer

    def get_queryset(self):
        queryset = RecommendationOverride.objects.select_related(
            "policy",
            "work",
            "theory_school",
            "topic",
            "scholar__person",
        )
        placement = self.request.query_params.get("placement", "").strip()
        if placement:
            queryset = queryset.filter(policy__placement=placement)
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class AdminRecommendationOverrideDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminRecommendationOverrideSerializer
    queryset = RecommendationOverride.objects.all()


class AdminAboutPageBlockListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AboutPageBlockSerializer
    queryset = AboutPageBlock.objects.all().order_by("sort_order", "created_at")

    def perform_create(self, serializer):
        serializer.save(updated_by=self.request.user)


class AdminAboutPageBlockDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AboutPageBlockSerializer
    queryset = AboutPageBlock.objects.all()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)


RELATION_RESOURCES = {
    "theory-disciplines": (TheoryDisciplineRelation, AdminTheoryDisciplineRelationSerializer),
    "theory-subdisciplines": (TheorySubdisciplineRelation, AdminTheorySubdisciplineRelationSerializer),
    "theory-hierarchy": (TheoryHierarchyRelation, AdminTheoryHierarchyRelationSerializer),
    "theory-relations": (TheoryRelation, AdminTheoryRelationSerializer),
    "topic-disciplines": (TopicDisciplineRelation, AdminTopicDisciplineRelationSerializer),
    "topic-theories": (TopicTheoryRelation, AdminTopicTheoryRelationSerializer),
    "topic-subdisciplines": (TopicSubdisciplineRelation, AdminTopicSubdisciplineRelationSerializer),
    "work-disciplines": (WorkDisciplineRelation, AdminWorkDisciplineRelationSerializer),
    "work-subdisciplines": (WorkSubdisciplineRelation, AdminWorkSubdisciplineRelationSerializer),
    "work-theories": (WorkKnowledgeRelation, AdminWorkTheoryRelationSerializer),
}


class AdminKnowledgeRelationListCreateView(APIView):
    permission_classes = [IsLibraryStaff]

    def _resource(self, kind):
        resource = RELATION_RESOURCES.get(kind)
        if resource is None:
            return None
        return resource

    def get(self, request, kind):
        resource = self._resource(kind)
        if resource is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        model, serializer_class = resource
        queryset = model.objects.all().order_by("-updated_at")
        for name, value in request.query_params.items():
            if name in {field.name for field in model._meta.fields} and value:
                queryset = queryset.filter(**{name: value})
        return Response(serializer_class(queryset[:500], many=True, context={"request": request}).data)

    def post(self, request, kind):
        resource = self._resource(kind)
        if resource is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        _model, serializer_class = resource
        payload = request.data.copy()
        if kind == "work-theories":
            payload["kind"] = WorkKnowledgeRelation.Kind.THEORY_SCHOOL
        serializer = serializer_class(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class AdminKnowledgeRelationDetailView(APIView):
    permission_classes = [IsLibraryStaff]

    def _object(self, kind, pk):
        resource = RELATION_RESOURCES.get(kind)
        if resource is None:
            return None, None, None
        model, serializer_class = resource
        return model, serializer_class, get_object_or_404(model, pk=pk)

    def patch(self, request, kind, pk):
        _model, serializer_class, instance = self._object(kind, pk)
        if instance is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        serializer = serializer_class(instance, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, kind, pk):
        _model, _serializer_class, instance = self._object(kind, pk)
        if instance is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
