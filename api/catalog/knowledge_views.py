from __future__ import annotations

from hashlib import sha256
import json
from uuid import UUID
from django.core import signing

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff

from .editorial_read import AdminEditorialDraftReadMixin
from .relation_editorial_views import StagedRelationEditorMixin

from .models import (
    AboutPageBlock,
    Discipline,
    EditorialRevision,
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
from .services.scoped_search import SearchContext, SearchService


class DisciplineListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = DisciplineSerializer

    def get_queryset(self):
        queryset = Discipline.objects.filter(editorial_status="published")
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        return SearchService(request=self.request).queryset(
            SearchContext.DISCIPLINES,
            query,
            base_queryset=queryset,
        )


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
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        discipline = self.request.query_params.get("discipline", "").strip()
        if discipline:
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline__slug",
                id_field="discipline_id",
            )
        return SearchService(request=self.request).queryset(
            SearchContext.SUBDISCIPLINES,
            query,
            base_queryset=queryset,
        )


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


class _CanonicalTaxonomyMutationMixin:
    canonical_object_type = ""

    @transaction.atomic
    def perform_create(self, serializer):
        target = serializer.save()
        if target.editorial_status == "published":
            from .services.canonical_mutations import record_admin_canonical_change

            record_admin_canonical_change(
                object_type=self.canonical_object_type,
                target=target,
                change_kind="publish",
                changed_fields=serializer.validated_data.keys(),
                actor=self.request.user,
                request_idempotency_key=self.request.headers.get(
                    "Idempotency-Key", ""
                ),
            )

    @transaction.atomic
    def perform_update(self, serializer):
        previous_status = serializer.instance.editorial_status
        target = serializer.save()
        if target.editorial_status in {"published", "archived"}:
            from .services.canonical_mutations import record_admin_canonical_change

            if target.editorial_status == "archived":
                change_kind = "withdraw"
            elif previous_status != "published":
                change_kind = "publish"
            else:
                change_kind = "update"
            record_admin_canonical_change(
                object_type=self.canonical_object_type,
                target=target,
                change_kind=change_kind,
                changed_fields=serializer.validated_data.keys(),
                actor=self.request.user,
                request_idempotency_key=self.request.headers.get(
                    "Idempotency-Key", ""
                ),
            )

    def destroy(self, request, *args, **kwargs):
        target = self.get_object()
        if target.editorial_status == "published":
            return Response(
                {
                    "detail": "已发布规范对象不能硬删除，请先改为 archived。",
                    "code": "published_authority_requires_withdrawal",
                },
                status=status.HTTP_409_CONFLICT,
            )
        if not has_capability(
            request.user,
            Capability.DESTRUCTIVE_MAINTENANCE,
        ):
            return Response(
                {"detail": "只有 System Owner 可以永久删除规范对象。"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)


def _stage_taxonomy_image(view, request, target):
    from .services.knowledge_media import stage_legacy_image_upload

    if set(request.data) - {"hero_image"}:
        return Response({"detail": "请先保存文字资料，再单独保存图片。未修改资料。"}, status=400)
    serializer = view.get_serializer(target, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    try:
        stage_legacy_image_upload(target, serializer.validated_data["hero_image"], actor=request.user)
    except (ValueError, DjangoValidationError) as error:
        return Response({"detail": str(error), "code": "image_selection_failed"}, status=400)
    return Response(view._draft_read_rows([target])[0], status=202)


class AdminDisciplineListView(
    AdminEditorialDraftReadMixin,
    _CanonicalTaxonomyMutationMixin,
    generics.ListCreateAPIView,
):
    canonical_object_type = "discipline"
    editorial_target_type = "discipline"
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminDisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Discipline.objects.all().order_by("sort_order", "name", "pk")


class AdminDisciplineDetailView(
    AdminEditorialDraftReadMixin,
    _CanonicalTaxonomyMutationMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    canonical_object_type = "discipline"
    editorial_target_type = "discipline"
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminDisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Discipline.objects.all()

    def update(self, request, *args, **kwargs):
        discipline = self.get_object()
        if "hero_image" in request.data:
            return _stage_taxonomy_image(self, request, discipline)
        if discipline.editorial_status != "published" and not EditorialRevision.objects.filter(target_type="discipline", target_id=discipline.pk, status="draft").exists():
            return super().update(request, *args, **kwargs)
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            discipline,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        from .services.editorial_drafts import save_object_editorial_patch
        from .services.editorial_revision import EditorialRevisionError

        try:
            revision = save_object_editorial_patch(
                "discipline", discipline.pk, dict(serializer.validated_data), actor=request.user,
                request_key=str(request.headers.get("Idempotency-Key") or "").strip(),
                change_note=str(request.data.get("change_note") or "学科编辑草稿"),
            )
        except EditorialRevisionError as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._draft_read_rows([discipline])[0], status=202 if revision else 200)


class AdminSubdisciplineListView(
    AdminEditorialDraftReadMixin,
    _CanonicalTaxonomyMutationMixin,
    generics.ListCreateAPIView,
):
    canonical_object_type = "subdiscipline"
    editorial_target_type = "subdiscipline"
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
        return queryset.order_by("discipline__sort_order", "name", "pk")


class AdminSubdisciplineDetailView(
    AdminEditorialDraftReadMixin,
    _CanonicalTaxonomyMutationMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    canonical_object_type = "subdiscipline"
    editorial_target_type = "subdiscipline"
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminSubdisciplineSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Subdiscipline.objects.select_related("discipline", "parent")

    def update(self, request, *args, **kwargs):
        subdiscipline = self.get_object()
        if "hero_image" in request.data:
            return _stage_taxonomy_image(self, request, subdiscipline)
        if subdiscipline.editorial_status != "published" and not EditorialRevision.objects.filter(target_type="subdiscipline", target_id=subdiscipline.pk, status="draft").exists():
            return super().update(request, *args, **kwargs)
        partial = kwargs.pop("partial", False)
        serializer = self.get_serializer(
            subdiscipline,
            data=request.data,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        from .services.editorial_drafts import save_object_editorial_patch
        from .services.editorial_revision import EditorialRevisionError

        try:
            revision = save_object_editorial_patch(
                "subdiscipline", subdiscipline.pk, dict(serializer.validated_data), actor=request.user,
                request_key=str(request.headers.get("Idempotency-Key") or "").strip(),
                change_note=str(request.data.get("change_note") or "子学科编辑草稿"),
            )
        except EditorialRevisionError as error:
            return Response(
                {"detail": str(error), "code": "editorial_revision_error"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self._draft_read_rows([subdiscipline])[0], status=202 if revision else 200)

    def destroy(self, request, *args, **kwargs):
        subdiscipline = self.get_object()
        if subdiscipline.editorial_status != "published":
            return super().destroy(request, *args, **kwargs)
        from .models import CanonicalObjectRevision, EditorialRevision
        from .services.editorial_revision import (
            EditorialRevisionError,
            create_editorial_revision,
            editorial_idempotency_key,
            serialize_editorial_revision,
        )

        patch = {"editorial_status": "archived"}
        current_revision = (
            CanonicalObjectRevision.objects.filter(
                object_type=EditorialRevision.TargetType.SUBDISCIPLINE,
                object_id=subdiscipline.id,
            )
            .values_list("current_revision", flat=True)
            .first()
            or 0
        )
        try:
            revision = create_editorial_revision(
                target_type=EditorialRevision.TargetType.SUBDISCIPLINE,
                target_id=subdiscipline.id,
                patch=patch,
                actor=request.user,
                idempotency_key=str(
                    request.headers.get("Idempotency-Key") or ""
                ).strip()
                or editorial_idempotency_key(
                    target_type=EditorialRevision.TargetType.SUBDISCIPLINE,
                    target_id=subdiscipline.id,
                    base_revision=current_revision,
                    patch=patch,
                ),
                change_note=str(
                    request.data.get("change_note") or "下线已发布子学科"
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


class AdminTheoryTimelineListView(StagedRelationEditorMixin, generics.ListCreateAPIView):
    editorial_target_type = "timeline_event"
    public_status_field = "review_status"
    public_status_value = "approved"
    draft_status_value = "suggested"
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
        return queryset.distinct().order_by("start_year", "display_order", "title", "pk")

    def perform_create(self, serializer):
        return super().perform_create(serializer)


class AdminTheoryTimelineDetailView(StagedRelationEditorMixin, generics.RetrieveUpdateDestroyAPIView):
    editorial_target_type = "timeline_event"
    public_status_field = "review_status"
    public_status_value = "approved"
    draft_status_value = "suggested"
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTheoryTimelineEventSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = TheoryTimelineEvent.objects.prefetch_related(
        "normalized_relations__node",
        "normalized_relations__discipline",
        "normalized_relations__scholar__person",
        "normalized_relations__work",
    )

    def destroy(self, request, *args, **kwargs):
        event = self.get_object()
        if event.review_status == RelationReviewStatus.APPROVED:
            return Response(
                {
                    "detail": "已公开的时间线事件不能删除。请选择下线，保存后再确认发布。",
                    "code": "published_timeline_requires_withdrawal",
                },
                status=status.HTTP_409_CONFLICT,
            )
        return super().destroy(request, *args, **kwargs)

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
        from catalog.services.publication_eligibility import public_edition_q
        queryset = queryset.filter(public_edition_q(prefix="editions"), editions__is_primary=True).distinct()
    elif model is ScholarProfile:
        from catalog.services.scoped_search import public_scholar_queryset
        queryset = public_scholar_queryset()
    else:
        queryset = queryset.filter(editorial_status="published")
    try:
        return queryset.filter(pk=identifier).first()
    except (DjangoValidationError, TypeError, ValueError):
        return None


class AdminRecommendationPreviewView(APIView):
    permission_classes = [IsLibraryStaff]

    @transaction.atomic
    def post(self, request, placement):
        from .services.recommendations import select_recommendation_targets, _target_key

        policy = get_object_or_404(RecommendationPolicy.objects.select_for_update(), placement=placement)
        raw = request.data.get("items")
        selected = None
        if raw is not None:
            if not isinstance(raw, list) or len(raw) > policy.item_count:
                return Response({"detail": "推荐数量不符合当前位置要求。"}, status=400)
            selected = []
            for row in raw:
                if not isinstance(row, dict) or row.get("target_type") != PLACEMENT_TARGETS.get(placement):
                    return Response({"detail": "推荐内容类型不正确。"}, status=400)
                target = _resolve_manual_target(row["target_type"], row.get("id"))
                if target is None or target in selected:
                    return Response({"detail": "推荐内容重复、不存在或尚未公开。"}, status=400)
                selected.append(target)
        targets, _seed, _manual = select_recommendation_targets(policy, selected_targets=selected)
        current = policy.snapshots.filter(is_current=True).first()
        items = [{"target_type": _target_key(target)[0], "id": str(target.pk)} for target in targets]
        payload = {"placement": placement, "actor": str(request.user.pk), "items": items,
                   "expected_updated_at": policy.updated_at.isoformat(), "expected_snapshot_id": str(current.pk) if current else None,
                   "source": "manual" if raw is not None else "automatic"}
        return Response({**payload, "preview_token": signing.dumps(payload, salt="recommendation-preview-v306", compress=True),
                         "expected_updated_at": RecommendationPolicySerializer().fields["updated_at"].to_representation(policy.updated_at),
                         "items": [{**row, "name": getattr(target, "title", getattr(target, "name", "")) or (target.person.preferred_name if isinstance(target, ScholarProfile) else "未命名内容")} for row, target in zip(items, targets)],
                         "expires_in_seconds": 900, "public_unchanged": True}, headers={"Cache-Control": "private, no-store"})


class AdminRecommendationRefreshView(APIView):
    permission_classes = [IsLibraryStaff]

    @transaction.atomic
    def post(self, request, placement):
        from ingestion.models import AuditEvent

        # Serialize competing refreshes on the existing policy. A receipt uses
        # the existing audit log, not a second publication/success marker.
        policy = get_object_or_404(RecommendationPolicy.objects.select_for_update(), placement=placement)
        raw_items = request.data.get("items")
        try:
            request_key = str(UUID(str(request.data.get("request_key", ""))))
            expected_updated_at = parse_datetime(str(request.data.get("expected_updated_at", "")))
        except (TypeError, ValueError):
            return Response({"detail": "请刷新推荐页面并重新确认发布。未修改当前推荐。"}, status=400)
        if request.data.get("confirm") is not True or expected_updated_at is None or "expected_snapshot_id" not in request.data:
            return Response({"detail": "请刷新推荐页面并明确确认发布。未修改当前推荐。"}, status=400)
        fingerprint = sha256(json.dumps({
            "items": raw_items,
            "preview_token": request.data.get("preview_token", ""),
            "expected_snapshot_id": request.data["expected_snapshot_id"],
            "expected_updated_at": expected_updated_at.isoformat(),
        }, sort_keys=True).encode()).hexdigest()
        receipt = AuditEvent.objects.filter(
            action="catalog.recommendations_published", object_type="catalog.RecommendationPolicy",
            object_id=str(policy.pk), after__request_key=request_key,
        ).first()
        if receipt:
            if receipt.actor_id != request.user.pk or receipt.before.get("fingerprint") != fingerprint:
                return Response({"detail": "此请求编号已用于其他选择。请刷新后重新确认。"}, status=409)
            return self._result(request, policy, receipt, replayed=True)
        current = policy.snapshots.filter(is_current=True).first()
        current_id = str(current.pk) if current else None
        if request.data["expected_snapshot_id"] != current_id or expected_updated_at != policy.updated_at:
            return Response({"detail": "推荐或更新规则已被其他操作修改。请刷新核对，再决定是否发布。"}, status=409)
        preview = None
        if request.data.get("preview_token"):
            try:
                preview = signing.loads(request.data["preview_token"], salt="recommendation-preview-v306", max_age=900)
                if preview["placement"] != placement or preview["actor"] != str(request.user.pk) or preview["expected_updated_at"] != policy.updated_at.isoformat() or preview["expected_snapshot_id"] != current_id:
                    raise ValueError("preview context changed")
                raw_items = preview["items"]
            except (signing.BadSignature, ValueError, KeyError, TypeError):
                return Response({"detail": "预览已过期或条件已改变，请重新预览。当前公开推荐未改变。"}, status=409)
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
            if (preview["source"] == "manual" if preview else raw_items is not None)
            else RecommendationSnapshot.Source.AUTOMATIC
        )
        try:
            snapshot = generate_snapshot(policy, actor=request.user, selected_targets=selected, source=source, previewed=preview is not None)
        except ValueError as error:
            return Response({"detail": str(error)}, status=409)
        receipt = AuditEvent.objects.create(
            actor=request.user, object_type="catalog.RecommendationPolicy", object_id=str(policy.pk),
            action="catalog.recommendations_published",
            before={"fingerprint": fingerprint, "snapshot_id": current_id},
            after={"request_key": request_key, "snapshot_id": str(snapshot.pk), "placement": placement,
                   "source": source, "selected_items": raw_items},
        )
        policy.refresh_from_db()
        return self._result(request, policy, receipt, replayed=False)

    def _result(self, request, policy, receipt, *, replayed):
        # Replaying an accepted request reports today's result; it must never
        # make an old recommendation current again after a later edit.
        current = policy.snapshots.filter(is_current=True).first()
        policy.resolved_snapshot = current
        data = dict(RecommendationPolicySerializer(policy, context={"request": request}).data)
        data.update({
            "command_accepted": True, "replayed": replayed,
            "accepted_snapshot_id": receipt.after["snapshot_id"], "audit_id": str(receipt.pk),
            "publication_effective": bool(policy.enabled and current and str(current.pk) == receipt.after["snapshot_id"]
                                          and current.starts_at <= timezone.now() < current.expires_at),
        })
        return Response(data)


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

    def post(self, request, *args, **kwargs):
        return Response({"code": "site_editorial_required", "detail": "请在网站与关于书库中保存草稿并发布。", "replacement": "/api/catalog/admin/site-content/"}, status=409)


class AdminAboutPageBlockDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AboutPageBlockSerializer
    queryset = AboutPageBlock.objects.all()

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def update(self, request, *args, **kwargs):
        return Response({"code": "site_editorial_required", "detail": "请在网站与关于书库中保存草稿并发布。", "replacement": "/api/catalog/admin/site-content/"}, status=409)

    def destroy(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)


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


LEGACY_THEORY_RELATION_KINDS = {
    "theory-disciplines",
    "theory-subdisciplines",
    "theory-hierarchy",
    "theory-relations",
    "topic-theories",
    "work-theories",
}


def _legacy_work_theory_write_retired():
    return Response(
        {
            "detail": (
                "work-theories 的 legacy 写入已经退役。请改用 "
                "/api/catalog/admin/theory-system/work-relations/ 写入 WorkNodeRelation。"
            ),
            "code": "legacy_work_theory_write_retired",
            "replacement": "/api/catalog/admin/theory-system/work-relations/",
        },
        status=status.HTTP_409_CONFLICT,
    )


def _legacy_theory_relation_write_retired(kind: str):
    replacement = (
        "/api/catalog/admin/theory-system/relations/"
        if kind in {"theory-hierarchy", "theory-relations"}
        else "/api/catalog/admin/theory-system/nodes/"
    )
    return Response(
        {
            "detail": (
                f"{kind} 只保留迁移期读取，不能继续写入 TheorySchool 关系。"
                "请在 Knowledge Studio 使用规范 KnowledgeNode 关系。"
            ),
            "code": "legacy_theory_relation_write_retired",
            "replacement": replacement,
        },
        status=status.HTTP_409_CONFLICT,
    )


TOPIC_RELATION_FIELDS = {
    "topic-disciplines": (
        "discipline_relations",
        "discipline",
        "discipline_id",
    ),
    "topic-theories": (
        "theory_relations",
        "theory_school",
        "theory_school_id",
    ),
    "topic-subdisciplines": (
        "subdiscipline_relations",
        "subdiscipline",
        "subdiscipline_id",
    ),
}
WORK_RELATION_KINDS = {"work-disciplines", "work-subdisciplines"}


def _work_has_published_edition(work: Work | None) -> bool:
    return bool(
        work
        and work.editions.filter(state=PublicationState.PUBLISHED).exists()
    )


def _published_work_relation_requires_revision():
    return Response(
        {
            "detail": "已发布作品的知识关系必须先建立编辑草稿。",
            "code": "editorial_revision_required",
            "replacement": "/api/catalog/admin/workflow/maintenance/",
        },
        status=status.HTTP_409_CONFLICT,
    )


def _topic_relation_row(kind, *, instance=None, values=None) -> dict:
    field_name, relation_field, id_field = TOPIC_RELATION_FIELDS[kind]
    del field_name
    values = values or {}
    relation_target = values.get(
        relation_field,
        getattr(instance, relation_field, None),
    )
    row = {
        id_field: str(relation_target.pk),
        "review_status": str(
            values.get(
                "review_status",
                getattr(instance, "review_status", RelationReviewStatus.SUGGESTED),
            )
        ),
    }
    if kind == "topic-disciplines":
        row["is_primary"] = bool(
            values.get("is_primary", getattr(instance, "is_primary", False))
        )
    else:
        row["relation_label"] = str(
            values.get(
                "relation_label",
                getattr(instance, "relation_label", ""),
            )
            or ""
        )
    return row


def _draft_topic_relation_revision(
    request,
    *,
    topic: Topic,
    kind: str,
    rows: list[dict],
    change_note: str,
):
    from .models import CanonicalObjectRevision, EditorialRevision
    from .services.editorial_revision import (
        create_editorial_revision,
        editorial_idempotency_key,
        serialize_editorial_revision,
    )

    field_name = TOPIC_RELATION_FIELDS[kind][0]
    patch = {field_name: rows}
    current_revision = (
        CanonicalObjectRevision.objects.filter(
            object_type=EditorialRevision.TargetType.TOPIC,
            object_id=topic.id,
        )
        .values_list("current_revision", flat=True)
        .first()
        or 0
    )
    revision = create_editorial_revision(
        target_type=EditorialRevision.TargetType.TOPIC,
        target_id=topic.id,
        patch=patch,
        actor=request.user,
        idempotency_key=str(request.headers.get("Idempotency-Key") or "").strip()
        or editorial_idempotency_key(
            target_type=EditorialRevision.TargetType.TOPIC,
            target_id=topic.id,
            base_revision=current_revision,
            patch=patch,
        ),
        change_note=change_note,
    )
    return Response(
        {
            "topic_id": str(topic.id),
            "relation_kind": kind,
            "draft_relations": revision.patch[field_name],
            "editorial_revision": serialize_editorial_revision(revision),
        },
        status=status.HTTP_202_ACCEPTED,
    )


def _topic_relation_rows(topic: Topic, kind: str) -> list[dict]:
    from .services.editorial_revision import topic_relation_snapshot

    field_name = TOPIC_RELATION_FIELDS[kind][0]
    return topic_relation_snapshot(topic)[field_name]


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
        if kind in LEGACY_THEORY_RELATION_KINDS:
            if kind == "work-theories":
                return _legacy_work_theory_write_retired()
            return _legacy_theory_relation_write_retired(kind)
        _model, serializer_class = resource
        payload = request.data.copy()
        serializer = serializer_class(data=payload, context={"request": request})
        serializer.is_valid(raise_exception=True)
        if kind in WORK_RELATION_KINDS and _work_has_published_edition(
            serializer.validated_data.get("work")
        ):
            return _published_work_relation_requires_revision()
        if kind in TOPIC_RELATION_FIELDS:
            topic = serializer.validated_data["topic"]
            if topic.editorial_status == "published":
                from .services.editorial_revision import EditorialRevisionError

                rows = _topic_relation_rows(topic, kind)
                rows.append(
                    _topic_relation_row(kind, values=serializer.validated_data)
                )
                try:
                    return _draft_topic_relation_revision(
                        request,
                        topic=topic,
                        kind=kind,
                        rows=rows,
                        change_note="已发布主题新增知识关系草稿",
                    )
                except EditorialRevisionError as error:
                    return Response(
                        {"detail": str(error), "code": "editorial_revision_error"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
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
        if kind in LEGACY_THEORY_RELATION_KINDS:
            if kind == "work-theories":
                return _legacy_work_theory_write_retired()
            return _legacy_theory_relation_write_retired(kind)
        _model, serializer_class, instance = self._object(kind, pk)
        if instance is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        serializer = serializer_class(instance, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        if kind in WORK_RELATION_KINDS:
            current_work = instance.work
            requested_work = serializer.validated_data.get("work", current_work)
            if _work_has_published_edition(
                current_work
            ) or _work_has_published_edition(requested_work):
                return _published_work_relation_requires_revision()
        if kind in TOPIC_RELATION_FIELDS:
            topic = instance.topic
            requested_topic = serializer.validated_data.get("topic", topic)
            if requested_topic.pk != topic.pk:
                return Response(
                    {
                        "detail": "主题关系不能在更新时改挂到另一主题，请分别删除和新建。",
                        "code": "topic_relation_reparent_not_supported",
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            if topic.editorial_status == "published":
                from .services.editorial_revision import EditorialRevisionError

                field_name, _relation_field, id_field = TOPIC_RELATION_FIELDS[kind]
                rows = _topic_relation_rows(topic, kind)
                current_id = str(getattr(instance, id_field))
                replacement = _topic_relation_row(
                    kind,
                    instance=instance,
                    values=serializer.validated_data,
                )
                rows = [
                    replacement if str(row[id_field]) == current_id else row
                    for row in rows
                ]
                try:
                    return _draft_topic_relation_revision(
                        request,
                        topic=topic,
                        kind=kind,
                        rows=rows,
                        change_note=f"已发布主题调整 {field_name} 草稿",
                    )
                except EditorialRevisionError as error:
                    return Response(
                        {"detail": str(error), "code": "editorial_revision_error"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, kind, pk):
        if kind in LEGACY_THEORY_RELATION_KINDS:
            if kind == "work-theories":
                return _legacy_work_theory_write_retired()
            return _legacy_theory_relation_write_retired(kind)
        _model, _serializer_class, instance = self._object(kind, pk)
        if instance is None:
            return Response({"detail": "未知关系类型。"}, status=404)
        if kind in WORK_RELATION_KINDS and _work_has_published_edition(instance.work):
            return _published_work_relation_requires_revision()
        if kind in TOPIC_RELATION_FIELDS and instance.topic.editorial_status == "published":
            from .services.editorial_revision import EditorialRevisionError

            _field_name, _relation_field, id_field = TOPIC_RELATION_FIELDS[kind]
            rows = [
                row
                for row in _topic_relation_rows(instance.topic, kind)
                if str(row[id_field]) != str(getattr(instance, id_field))
            ]
            try:
                return _draft_topic_relation_revision(
                    request,
                    topic=instance.topic,
                    kind=kind,
                    rows=rows,
                    change_note="已发布主题移除知识关系草稿",
                )
            except EditorialRevisionError as error:
                return Response(
                    {"detail": str(error), "code": "editorial_revision_error"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
