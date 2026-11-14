"""Public homepage composition over the existing publication boundaries."""
import logging

from django.db.models import Count, Q
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_serializers import RecommendationIssueSerializer
from catalog.models import RelationReviewStatus, Topic
from catalog.serializers import (
    ScholarProfileSerializer, SiteConfigSerializer, TopicSerializer, WorkCardSerializer,
)
from catalog.services.analytics import public_hot_searches
from catalog.services.editorial_issues import issue_payload, published_issues
from catalog.services.recommendations import current_recommendations
from catalog.services.scoped_search import public_scholar_queryset, public_work_queryset
from catalog.views import current_site_config
from catalog.site_layout import HomeLayoutPreviewSerializer, public_layout


logger = logging.getLogger(__name__)


class HomeSectionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["ready", "empty", "unavailable"])
    source = serializers.CharField()
    count = serializers.IntegerField(allow_null=True)
    message = serializers.CharField(allow_blank=True)


class HomeSectionsSerializer(serializers.Serializer):
    home_layout = HomeSectionSerializer()
    works = HomeSectionSerializer()
    random_works = HomeSectionSerializer()
    scholars = HomeSectionSerializer()
    topics = HomeSectionSerializer()
    issues = HomeSectionSerializer()
    hot_searches = HomeSectionSerializer()
    config = HomeSectionSerializer()


class HomeResponseSerializer(serializers.Serializer):
    home_layout = HomeLayoutPreviewSerializer(allow_null=True)
    schema_version = serializers.CharField()
    visibility = serializers.ChoiceField(choices=["public"])
    status = serializers.ChoiceField(choices=["ready", "empty", "partial", "unavailable"])
    config = SiteConfigSerializer(allow_null=True)
    works = WorkCardSerializer(many=True)
    random_works = WorkCardSerializer(many=True)
    scholars = ScholarProfileSerializer(many=True)
    topics = TopicSerializer(many=True)
    issues = RecommendationIssueSerializer(many=True)
    issue = RecommendationIssueSerializer(allow_null=True)
    issue_count = serializers.IntegerField(allow_null=True)
    hot_searches = serializers.ListField(child=serializers.CharField())
    sections = HomeSectionsSerializer()


def _collection(queryset, serializer, snapshot, target_field, limit, *, supplement=False, context=None):
    """Recheck current visibility even when a recommendation snapshot is older."""
    selected = []
    if snapshot is not None:
        identifiers = [getattr(item, f"{target_field}_id") for item in snapshot.items.all()]
        by_id = {row.pk: row for row in queryset.filter(pk__in=filter(None, identifiers))}
        selected = list(dict.fromkeys(by_id[value] for value in identifiers if value in by_id))[:limit]
    source = "recommendation_snapshot" if selected else "published_catalog"
    if not selected or supplement:
        selected.extend(queryset.exclude(pk__in=[row.pk for row in selected])[:limit - len(selected)])
    # No request/user context: public cards must not gain staff-only file access.
    return list(serializer(selected, many=True, context=context or {}).data), source


def _home_issues():
    queryset = published_issues().order_by("-effective_display_from", "-created_at", "id")
    return [issue_payload(row, public=True) for row in queryset[:4]], queryset.count()


class HomeView(APIView):
    permission_classes = [AllowAny]
    # This endpoint intentionally has identical data for staff, readers and guests.
    authentication_classes = []

    @extend_schema(operation_id="catalog_home", responses={200: HomeResponseSerializer, 503: HomeResponseSerializer})
    def get(self, request):
        payload = {
            "schema_version": "4.0", "visibility": "public", "status": "empty",
            "config": None, "works": [], "random_works": [], "scholars": [],
            "topics": [], "issues": [], "issue": None, "issue_count": None,
            "hot_searches": [], "sections": {}, "home_layout": None,
        }
        snapshots = None
        # Only identical public work cards within this response are reused.
        # The next GET creates a fresh map and rechecks publication/withdrawal.
        public_context = {"_public_work_cards": {}}

        def recommended(placement):
            nonlocal snapshots
            if snapshots is None:
                # Public GETs must not create policies or publish a new snapshot.
                snapshots = current_recommendations(read_only=True)
            return snapshots.get(placement)

        def works(placement, limit):
            return _collection(
                public_work_queryset().order_by("-editions__first_published_at", "id"),
                WorkCardSerializer, recommended(placement), "work", limit,
                context=public_context,
            )

        def scholars():
            return _collection(
                public_scholar_queryset().order_by("person__preferred_name", "id"),
                ScholarProfileSerializer, recommended("home_scholars"), "scholar", 6,
                supplement=True, context=public_context,
            )

        def topics():
            queryset = Topic.objects.filter(editorial_status="published").prefetch_related(
                "knowledge_node_links__node",
            ).annotate(work_count=Count(
                "work_relations__work", distinct=True,
                filter=Q(
                    work_relations__review_status=RelationReviewStatus.APPROVED,
                    work_relations__work__in=public_work_queryset(),
                ),
            )).order_by("name", "id")
            return _collection(queryset, TopicSerializer, recommended("home_topics"), "topic", 5, context=public_context)

        loaders = {
            "home_layout": (lambda: (public_layout(), "published_site_revision"), "首页编排"),
            "works": (lambda: works("home_featured", 12), "馆藏内容"),
            "random_works": (lambda: works("home_random", 4), "推荐馆藏"),
            "scholars": (scholars, "学者内容"),
            "topics": (topics, "主题内容"),
            "issues": (_home_issues, "特别策划"),
            "hot_searches": (lambda: (
                [row["query"] for row in public_hot_searches()["results"]], "anonymous_aggregate",
            ), "热门搜索"),
            "config": (lambda: (current_site_config(), "published_site_config"), "网站介绍"),
        }
        for key, (load, label) in loaders.items():
            try:
                data, source = load()
                if key == "issues":
                    payload["issue_count"] = source
                    payload["issue"] = data[0] if data else None
                    source = "published_issue_revision"
                payload[key] = data
                count = 1 if key == "config" else sum(len(rows or []) for rows in data.values()) if key == "home_layout" else len(data)
                payload["sections"][key] = {
                    "status": "ready" if count else "empty", "source": source,
                    "count": count, "message": "" if count else f"暂无公开的{label}。",
                }
            except Exception:
                # A failed region is explicitly unavailable, never an empty success.
                logger.exception("Homepage section unavailable: %s", key)
                payload["sections"][key] = {
                    "status": "unavailable", "source": "unavailable", "count": None,
                    "message": f"{label}暂时无法加载，请稍后重试。",
                }
        failed = sum(section["status"] == "unavailable" for section in payload["sections"].values())
        has_content = any(section["count"] for key, section in payload["sections"].items() if key != "config")
        payload["status"] = (
            "unavailable" if failed == len(loaders) else "partial" if failed
            else "ready" if has_content else "empty"
        )
        return Response(payload, status=503 if payload["status"] == "unavailable" else 200,
                        headers={"Cache-Control": "no-store"})
