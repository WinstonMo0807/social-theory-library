import httpx
from datetime import timedelta
import mimetypes
import re
import logging
import uuid
from uuid import UUID
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from urllib.parse import urlparse

from .models import (
    Asset,
    AnonymousUsageEvent,
    Contribution,
    CoverCandidate,
    DocumentType,
    Edition,
    Page,
    PageLabelSegment,
    PageLabelStatus,
    Passage,
    PublicationState,
    ReaderRenditionPolicy,
    RelationReviewStatus,
    SearchQueryAggregate,
    ScholarProfile,
    SemanticChunk,
    SemanticIndexJob,
    SemanticIndexVersion,
    SemanticSearchFeedback,
    SiteSetting,
    TheorySchool,
    Topic,
    Work,
    WorkKnowledgeRelation,
)
from .serializers import (
    AdminScholarSerializer,
    AdminTheorySchoolSerializer,
    AdminTopicSerializer,
    CoverCandidateSerializer,
    ReaderSubmissionSettingsSerializer,
    ScholarProfileSerializer,
    SiteConfigSerializer,
    TheorySchoolSerializer,
    TopicSerializer,
    WorkCardSerializer,
    WorkDetailSerializer,
)
from .query_filters import filter_slug_or_uuid
from .services.citations import citation_bundle
from .services.covers import (
    CoverCandidateUnavailable,
    generate_cover_candidates,
    generate_recommendation_image,
    select_cover_candidate,
)
from .services.search_geometry import search_highlights
from .services.search_backend import external_passage_ids
from .services.page_labels import apply_page_label_segment, infer_page_labels
from .services.analytics import SESSION_COOKIE, record_usage_event, session_identity
from .services.semantic_search import (
    SEMANTIC_ENGINES,
    SEMANTIC_PROVIDERS,
    configure_semantic_embedder,
    current_semantic_runtime,
    record_feedback,
    semantic_model_health,
    semantic_search,
    viewer_access_statuses,
)
from .services.semantic_indexing import (
    activate_semantic_index_version,
    dispatch_semantic_version_batch,
    queue_semantic_job,
    remove_semantic_asset,
    resume_semantic_job,
    semantic_index_paused,
    set_semantic_index_paused,
    stage_semantic_index_version,
    stage_semantic_snapshot_version,
)
from .services.scoped_search import (
    SearchContext,
    SearchRequest,
    SearchService,
    SearchVisibility,
    public_work_queryset,
)
from .services.text import clean_page_label, clipboard_payload, normalize_search_text, passage_snippet
from .site_config import DEFAULT_SITE_CONFIG
from config.version import APP_VERSION
from common.permissions import CanManageSemanticIndex
from common.permissions import CanRetryJobs
from common.permissions import CanViewSemanticIndex
from common.permissions import IsCatalogEditor
from common.permissions import IsLibraryAdmin
from common.permissions import IsLibraryStaff
from common.concurrency import capacity_slot
from .services.authority_suggestions import authority_suggestions


logger = logging.getLogger(__name__)


def public_works():
    return public_work_queryset()


class AdminAuthoritySuggestionView(APIView):
    """Read-only reconciliation candidates for independent authority editors."""

    permission_classes = [IsCatalogEditor]

    def get(self, request):
        request_id = str(uuid.uuid4())
        try:
            result = authority_suggestions(
                request.query_params.get("entity_type", ""),
                request.query_params.get("q", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc), "request_id": request_id}, status=400)
        except (httpx.HTTPError, OSError, TimeoutError) as exc:
            logger.warning("authority suggestion provider unavailable request_id=%s error=%s", request_id, exc.__class__.__name__)
            return Response({"query": request.query_params.get("q", ""), "results": [], "warnings": [{"code": "provider_unavailable", "detail": "部分权威来源暂时不可用，已保留其他来源结果。"}], "request_id": request_id}, status=200)
        except Exception:
            logger.exception("authority suggestion unexpected failure request_id=%s", request_id)
            return Response({"query": request.query_params.get("q", ""), "results": [], "warnings": [{"code": "provider_error", "detail": "权威来源暂时无法读取，请稍后重试。"}], "request_id": request_id}, status=200)
        return Response(result)


class PublicWorkCoverView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, work_id):
        work = get_object_or_404(public_works(), pk=work_id)
        cover_name = work.cover.name
        if not cover_name or not work.cover.storage.exists(cover_name):
            return Response(
                {"detail": "该文献尚无公开封面。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            work.cover.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            return Response(
                {"detail": "该文献封面暂时不可用。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(
            work.cover,
            content_type="image/jpeg",
            filename=f"{work.id}-cover.jpg",
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class PublicWorkRecommendationImageView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, work_id):
        work = get_object_or_404(public_works(), pk=work_id)
        image = work.recommendation_image or work.cover
        image_name = image.name if image else ""
        if not image_name or not image.storage.exists(image_name):
            return Response(
                {"detail": "该文献尚无公开推荐图例。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            image.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            return Response(
                {"detail": "该文献推荐图例暂时不可用。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        response = FileResponse(
            image,
            content_type="image/jpeg",
            filename=f"{work.id}-recommendation.jpg",
        )
        response["Cache-Control"] = "public, max-age=86400"
        return response


class AdminWorkRecommendationImageView(APIView):
    """Preview, replace or regenerate the visual used by recommendation cards.

    A manually uploaded image is stored on ``Work.recommendation_image`` and
    therefore remains authoritative during later ingestion runs.  Removing the
    override restores the selected book cover, or allows a non-book visual to
    be generated again from its normalized PDF.
    """

    permission_classes = [IsLibraryStaff]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    max_upload_size = 12 * 1024 * 1024

    def _image(self, work):
        if work.recommendation_image:
            return work.recommendation_image, "manual_or_generated"
        if work.cover:
            return work.cover, "book_cover"
        return None, "missing"

    def _payload(self, request, work):
        image, source = self._image(work)
        image_name = image.name if image else ""
        available = bool(
            image_name
            and image.storage.exists(image_name)
        )
        return {
            "work_id": str(work.id),
            "document_type": work.document_type,
            "available": available,
            "source": source if available else "missing",
            "preview_url": request.build_absolute_uri(
                reverse("admin-work-recommendation-image", kwargs={"work_id": work.id})
            ) if available else "",
            "public_url": (
                f"{settings.PUBLIC_API_URL.rstrip('/')}"
                f"{reverse('public-work-recommendation-image', kwargs={'work_id': work.id})}"
            ) if available else "",
            "updated_at": work.updated_at,
        }

    def get(self, request, work_id):
        work = get_object_or_404(Work, pk=work_id)
        if request.query_params.get("metadata") == "1":
            return Response(self._payload(request, work))
        image, _source = self._image(work)
        image_name = image.name if image else ""
        if not image_name or not image.storage.exists(image_name):
            return Response({"detail": "该馆藏尚无可预览的推荐图例。"}, status=404)
        try:
            image.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            return Response({"detail": "推荐图例文件暂时不可用。"}, status=404)
        content_type = mimetypes.guess_type(image_name)[0] or "image/jpeg"
        response = FileResponse(image, content_type=content_type)
        response["Cache-Control"] = "private, no-store"
        return response

    def post(self, request, work_id):
        work = get_object_or_404(Work, pk=work_id)
        uploaded = request.FILES.get("image")
        action = str(request.data.get("action", "")).strip()
        previous_name = work.recommendation_image.name
        previous_storage = work.recommendation_image.storage

        if uploaded is not None:
            if uploaded.size > self.max_upload_size:
                return Response({"image": ["图片不能超过 12 MB。"]}, status=400)
            try:
                uploaded = serializers.ImageField().run_validation(uploaded)
            except serializers.ValidationError as exc:
                return Response({"image": exc.detail}, status=400)
            work.recommendation_image.save(uploaded.name, uploaded, save=False)
            work.save(update_fields=["recommendation_image", "updated_at"])
        elif action == "regenerate":
            if work.document_type == DocumentType.BOOK:
                if not work.cover:
                    return Response({"detail": "请先选择或上传图书封面。"}, status=409)
                work.recommendation_image = ""
                work.save(update_fields=["recommendation_image", "updated_at"])
            else:
                asset = (
                    Asset.objects.filter(
                        edition__work=work,
                        edition__is_primary=True,
                        kind=Asset.Kind.NORMALIZED,
                        status=Asset.Status.READY,
                        is_current=True,
                    )
                    .select_related("edition__work")
                    .first()
                )
                if asset is None:
                    return Response({"detail": "规范阅读 PDF 尚未就绪。"}, status=409)
                try:
                    generate_recommendation_image(asset, force=True)
                except CoverCandidateUnavailable as exc:
                    return Response({"detail": str(exc)}, status=409)
                work.refresh_from_db()
        else:
            return Response({"detail": "请上传图片，或指定 regenerate 操作。"}, status=400)

        current_name = work.recommendation_image.name
        if previous_name and previous_name != current_name:
            try:
                previous_storage.delete(previous_name)
            except OSError:
                # Windows may keep a preview stream open briefly.  The database
                # must still switch to the new image; the orphan can be removed
                # by normal media maintenance after the handle is released.
                pass
        return Response(self._payload(request, work))

    def delete(self, request, work_id):
        work = get_object_or_404(Work, pk=work_id)
        previous_name = work.recommendation_image.name
        previous_storage = work.recommendation_image.storage
        work.recommendation_image = ""
        work.save(update_fields=["recommendation_image", "updated_at"])
        if previous_name:
            try:
                previous_storage.delete(previous_name)
            except OSError:
                pass
        return Response(self._payload(request, work))


class AdminCoverCandidateListView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request, work_id):
        work = get_object_or_404(Work, pk=work_id)
        candidates = work.cover_candidates.select_related("asset").order_by(
            "-score",
            "page_index",
        )
        return Response(
            {
                "document_type": work.document_type,
                "eligible": work.document_type == DocumentType.BOOK,
                "results": CoverCandidateSerializer(
                    candidates,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )

    def post(self, request, work_id):
        work = get_object_or_404(Work, pk=work_id)
        if work.document_type != DocumentType.BOOK:
            return Response(
                {"detail": "封面候选只对图书启用。"},
                status=409,
            )
        asset = (
            Asset.objects.filter(
                edition__work=work,
                edition__is_primary=True,
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
            )
            .select_related("edition__work")
            .first()
        )
        if asset is None:
            return Response({"detail": "规范阅读 PDF 尚未就绪。"}, status=409)
        candidates = generate_cover_candidates(asset, force=True)
        return Response(
            {
                "document_type": work.document_type,
                "eligible": True,
                "results": CoverCandidateSerializer(
                    candidates,
                    many=True,
                    context={"request": request},
                ).data,
            }
        )


class AdminCoverCandidateSelectView(APIView):
    permission_classes = [IsLibraryStaff]

    def post(self, request, work_id, candidate_id):
        candidate = get_object_or_404(
            CoverCandidate.objects.select_related("work", "asset"),
            pk=candidate_id,
            work_id=work_id,
        )
        try:
            result = select_cover_candidate(candidate)
        except CoverCandidateUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            CoverCandidateSerializer(
                result["candidate"],
                context={"request": request},
            ).data
        )


class AdminCoverCandidateThumbnailView(APIView):
    permission_classes = [IsLibraryStaff]

    def get(self, request, work_id, candidate_id):
        candidate = get_object_or_404(
            CoverCandidate,
            pk=candidate_id,
            work_id=work_id,
        )
        thumbnail_name = candidate.thumbnail.name
        if (
            not thumbnail_name
            or not candidate.thumbnail.storage.exists(thumbnail_name)
        ):
            return Response(
                {"detail": "封面候选文件已不存在，请点击“重新分析”。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            candidate.thumbnail.open("rb")
        except (FileNotFoundError, OSError, ValueError):
            return Response(
                {"detail": "封面候选文件暂时不可用，请点击“重新分析”。"},
                status=status.HTTP_404_NOT_FOUND,
            )
        return FileResponse(
            candidate.thumbnail,
            content_type="image/jpeg",
            filename=f"cover-candidate-page-{candidate.page_index}.jpg",
        )


DOCUMENT_TYPE_ALIASES = {
    "book": "book",
    "article": "journal_article",
    "journal_article": "journal_article",
    "thesis": "thesis",
    "report": "report",
}

YEAR_FILTERS = {
    "before-1900": (None, 1899),
    "1900-1949": (1900, 1949),
    "1950-1999": (1950, 1999),
    "2000-2009": (2000, 2009),
    "2010-2019": (2010, 2019),
    "2020-now": (2020, None),
}

LANGUAGE_LABELS = {
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "zh-HK": "繁体中文",
    "en": "英文",
}


def query_values(request, name):
    values = []
    for raw_value in request.query_params.getlist(name):
        values.extend(part.strip() for part in raw_value.split(","))
    return [value for value in values if value]


def year_query(prefix, values):
    condition = Q()
    for value in values:
        start, end = YEAR_FILTERS.get(value, (None, None))
        if start is None and end is None:
            continue
        item = Q()
        if start is not None:
            item &= Q(**{f"{prefix}__gte": start})
        if end is not None:
            item &= Q(**{f"{prefix}__lte": end})
        condition |= item
    return condition


def filter_works(queryset, request):
    document_types = [
        DOCUMENT_TYPE_ALIASES[value]
        for value in query_values(request, "document_type")
        if value in DOCUMENT_TYPE_ALIASES
    ]
    if document_types:
        queryset = queryset.filter(document_type__in=document_types)
    theories = query_values(request, "theory")
    if theories:
        queryset = queryset.filter(
            knowledge_relations__theory_school__slug__in=theories,
            knowledge_relations__approved=True,
        )
    topics = query_values(request, "topic")
    if topics:
        queryset = queryset.filter(
            knowledge_relations__topic__slug__in=topics,
            knowledge_relations__approved=True,
        )
    concepts = query_values(request, "concept") or query_values(request, "tag")
    if concepts:
        queryset = queryset.filter(
            knowledge_relations__concept__slug__in=concepts,
            knowledge_relations__approved=True,
        )
    authors = query_values(request, "author")
    if authors:
        queryset = queryset.filter(
            editions__contributions__person_id__in=authors,
            editions__contributions__role=Contribution.Role.AUTHOR,
            editions__contributions__approved=True,
        )
    languages = query_values(request, "language")
    if languages:
        queryset = queryset.filter(language__in=languages)
    years = query_values(request, "year")
    if years:
        queryset = queryset.filter(year_query("editions__publication_year", years))
    access = query_values(request, "access")
    if access:
        queryset = queryset.filter(
            editions__assets__kind=Asset.Kind.NORMALIZED,
            editions__assets__status=Asset.Status.READY,
            editions__assets__is_current=True,
        )
    return queryset.distinct()


def filter_passages(queryset, request):
    document_types = [
        DOCUMENT_TYPE_ALIASES[value]
        for value in query_values(request, "document_type")
        if value in DOCUMENT_TYPE_ALIASES
    ]
    if document_types:
        queryset = queryset.filter(page__asset__edition__work__document_type__in=document_types)
    theories = query_values(request, "theory")
    if theories:
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__theory_school__slug__in=theories,
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    topics = query_values(request, "topic")
    if topics:
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__topic__slug__in=topics,
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    concepts = query_values(request, "concept") or query_values(request, "tag")
    if concepts:
        queryset = queryset.filter(
            page__asset__edition__work__knowledge_relations__concept__slug__in=concepts,
            page__asset__edition__work__knowledge_relations__approved=True,
        )
    authors = query_values(request, "author")
    if authors:
        queryset = queryset.filter(
            page__asset__edition__contributions__person_id__in=authors,
            page__asset__edition__contributions__role=Contribution.Role.AUTHOR,
            page__asset__edition__contributions__approved=True,
        )
    languages = query_values(request, "language")
    if languages:
        queryset = queryset.filter(page__asset__edition__work__language__in=languages)
    years = query_values(request, "year")
    if years:
        queryset = queryset.filter(year_query("page__asset__edition__publication_year", years))
    return queryset.distinct()


def search_facets(queryset):
    document_type_rows = (
        queryset.values("document_type")
        .annotate(count=Count("id", distinct=True))
        .order_by("document_type")
    )
    author_rows = (
        Contribution.objects.filter(
            approved=True,
            role=Contribution.Role.AUTHOR,
            edition__state=PublicationState.PUBLISHED,
            edition__is_primary=True,
            edition__work__in=queryset,
        )
        .values("person_id", "person__preferred_name")
        .annotate(count=Count("edition__work", distinct=True))
        .order_by("-count", "person__preferred_name")[:20]
    )
    language_rows = (
        queryset.values("language")
        .annotate(count=Count("id", distinct=True))
        .order_by("-count", "language")
    )
    year_counts = {
        key: queryset.filter(year_query("editions__publication_year", [key])).count()
        for key in YEAR_FILTERS
    }
    theory_rows = (
        WorkKnowledgeRelation.objects.filter(
            work__in=queryset,
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            approved=True,
            theory_school__editorial_status="published",
        )
        .values("theory_school__slug", "theory_school__name")
        .annotate(count=Count("work_id", distinct=True))
        .order_by("-count", "theory_school__name")
    )
    topic_rows = (
        WorkKnowledgeRelation.objects.filter(
            work__in=queryset,
            kind=WorkKnowledgeRelation.Kind.TOPIC,
            approved=True,
            topic__editorial_status="published",
        )
        .values("topic__slug", "topic__name")
        .annotate(count=Count("work_id", distinct=True))
        .order_by("-count", "topic__name")
    )
    concept_rows = (
        WorkKnowledgeRelation.objects.filter(
            work__in=queryset,
            kind=WorkKnowledgeRelation.Kind.CONCEPT,
            approved=True,
            concept__editorial_status="published",
        )
        .values("concept__slug", "concept__name")
        .annotate(count=Count("work_id", distinct=True))
        .order_by("-count", "concept__name")
    )
    available_count = queryset.filter(
        editions__assets__kind=Asset.Kind.NORMALIZED,
        editions__assets__status=Asset.Status.READY,
        editions__assets__is_current=True,
    ).count()
    year_labels = {
        "before-1900": "1900 年以前",
        "1900-1949": "1900—1949",
        "1950-1999": "1950—1999",
        "2000-2009": "2000—2009",
        "2010-2019": "2010—2019",
        "2020-now": "2020 年至今",
    }
    return {
        "document_types": [
            {
                "value": row["document_type"],
                "label": dict(DocumentType.choices).get(
                    row["document_type"],
                    row["document_type"],
                ),
                "count": row["count"],
            }
            for row in document_type_rows
        ],
        "authors": [
            {
                "value": str(row["person_id"]),
                "label": row["person__preferred_name"],
                "count": row["count"],
            }
            for row in author_rows
        ],
        "years": [
            {"value": key, "label": year_labels[key], "count": count}
            for key, count in year_counts.items()
            if count
        ],
        "languages": [
            {
                "value": row["language"],
                "label": LANGUAGE_LABELS.get(row["language"], row["language"] or "未标注"),
                "count": row["count"],
            }
            for row in language_rows
        ],
        "access": [
            {"value": "online", "label": "可在线阅读", "count": available_count},
            {"value": "download", "label": "可下载", "count": available_count},
        ],
        "theories": [
            {
                "value": row["theory_school__slug"],
                "label": row["theory_school__name"],
                "count": row["count"],
            }
            for row in theory_rows
        ],
        "topics": [
            {
                "value": row["topic__slug"],
                "label": row["topic__name"],
                "count": row["count"],
            }
            for row in topic_rows
        ],
        "concepts": [
            {
                "value": row["concept__slug"],
                "label": row["concept__name"],
                "count": row["count"],
            }
            for row in concept_rows
        ],
    }


def current_site_config():
    stored = SiteSetting.objects.filter(key="site_config", public=True).first()
    if not stored or not isinstance(stored.value, dict):
        return DEFAULT_SITE_CONFIG
    value = {**DEFAULT_SITE_CONFIG, **stored.value}
    value["navigation"] = {
        **DEFAULT_SITE_CONFIG["navigation"],
        **stored.value.get("navigation", {}),
    }
    value["sections"] = {
        **DEFAULT_SITE_CONFIG["sections"],
        **stored.value.get("sections", {}),
    }
    return value


class SiteConfigView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [AllowAny()]
        return [IsLibraryAdmin()]

    def get(self, request):
        return Response(current_site_config())

    def put(self, request):
        serializer = SiteConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = current_site_config()
        setting, _ = SiteSetting.objects.update_or_create(
            key="site_config",
            defaults={
                "value": serializer.validated_data,
                "public": True,
                "updated_by": request.user,
            },
        )
        from ingestion.models import AuditEvent

        AuditEvent.objects.create(
            actor=request.user,
            action="site_config_update",
            object_type="SiteSetting",
            object_id=str(setting.id),
            before=before,
            after=serializer.validated_data,
        )
        return Response(serializer.validated_data)


class SiteStatsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        published = Edition.objects.filter(
            state=PublicationState.PUBLISHED,
            is_primary=True,
        )
        last_updated = published.aggregate(value=Max("updated_at"))["value"]
        return Response(
            {
                "documents": published.count(),
                "scholars": ScholarProfile.objects.filter(
                    editorial_status="published"
                ).count(),
                "knowledge_objects": (
                    TheorySchool.objects.filter(editorial_status="published").count()
                    + Topic.objects.filter(editorial_status="published").count()
                ),
                "last_updated": last_updated,
                "last_updated_label": (
                    f"{timezone.localtime(last_updated).year} 年 "
                    f"{timezone.localtime(last_updated).month} 月"
                    if last_updated
                    else "尚未发布"
                ),
                "version": APP_VERSION,
            }
        )


class ReaderSubmissionSettingsView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        stored = SiteSetting.objects.filter(key="reader_submission_email").first()
        email = stored.value if stored and isinstance(stored.value, str) else settings.READER_SUBMISSION_EMAIL
        return Response({"email": email})

    def put(self, request):
        serializer = ReaderSubmissionSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = SiteSetting.objects.filter(key="reader_submission_email").values_list("value", flat=True).first()
        setting, _ = SiteSetting.objects.update_or_create(
            key="reader_submission_email",
            defaults={
                "value": serializer.validated_data["email"],
                "public": False,
                "updated_by": request.user,
            },
        )
        from ingestion.models import AuditEvent

        AuditEvent.objects.create(
            actor=request.user,
            action="reader_submission_email_update",
            object_type="SiteSetting",
            object_id=str(setting.id),
            before={"email": before or ""},
            after={"email": serializer.validated_data["email"]},
        )
        return Response(serializer.validated_data)


def current_ocr_runtime():
    from ingestion.models import ProcessingJob
    from ingestion.services.ocr_provider import ocr_runtime_config

    config = ocr_runtime_config()
    latest = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.OCR,
    ).order_by("-created_at").first()
    last_success = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.OCR,
        status=ProcessingJob.Status.SUCCEEDED,
    ).order_by("-finished_at").first()
    remote_configured = bool(
        config["remote_url"]
        and config["remote_model"]
        and config["remote_key_configured"]
    )
    return {
        **config,
        "nas_configured": bool(config["nas_url"]),
        "remote_configured": remote_configured,
        "remote_fallback_available": remote_configured,
        "effective_configuration": {
            "mode": config["mode"],
            "nas_url_configured": bool(config["nas_url"]),
            "remote_fallback_available": remote_configured,
            "loads_settings_per_job": True,
        },
        "restart_required": False,
        "last_success_at": last_success.finished_at if last_success else None,
        "last_job": (
            {
                "id": str(latest.id),
                "status": latest.status,
                "engine": latest.engine,
                "settings_version": latest.settings_version,
                "attempt": latest.attempt,
                "error": latest.error_message,
                "created_at": latest.created_at,
                "finished_at": latest.finished_at,
            }
            if latest
            else None
        ),
    }


class OcrRuntimeSettingsView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        return Response(current_ocr_runtime())

    def post(self, request):
        from ingestion.services.health import http_service_health

        action = str(request.data.get("action") or "").strip()
        config = current_ocr_runtime()
        if action == "test_nas":
            result = http_service_health(
                config["nas_url"],
                "/ready?deep=true",
                timeout=120,
            )
            return Response({"target": "nas", **result})
        if action == "test_remote":
            if not config["remote_configured"]:
                return Response(
                    {
                        "target": "remote",
                        "reachable": False,
                        "detail": "远程 URL、API Key 或模型配置不完整。",
                    },
                    status=409,
                )
            result = http_service_health(config["remote_url"], "/health", timeout=5)
            return Response({"target": "remote", **result})
        return Response({"action": ["请选择测试 NAS OCR 或远程 OCR。"]}, status=400)

    def put(self, request):
        mode = str(request.data.get("mode") or "").strip()
        remote_url = str(request.data.get("remote_url") or "").strip()
        remote_model = str(request.data.get("remote_model") or "").strip()
        if mode not in {"nas_preferred", "nas_only", "remote_only"}:
            return Response({"mode": ["请选择有效的 OCR 运行方式。"]}, status=400)
        if remote_url:
            parsed = urlparse(remote_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return Response({"remote_url": ["远程地址必须是有效的 HTTP 或 HTTPS 地址。"]}, status=400)
        if mode == "remote_only" and not remote_url:
            return Response({"remote_url": ["仅使用远程 OCR 时必须填写网关地址。"]}, status=400)
        before = current_ocr_runtime()
        value = {
            "mode": mode,
            "remote_url": remote_url,
            "remote_model": remote_model,
        }
        setting, _ = SiteSetting.objects.update_or_create(
            key="ocr_runtime",
            defaults={
                "value": value,
                "public": False,
                "updated_by": request.user,
            },
        )
        from ingestion.models import AuditEvent

        AuditEvent.objects.create(
            actor=request.user,
            action="ocr_runtime_update",
            object_type="SiteSetting",
            object_id=str(setting.id),
            before=before,
            after=value,
        )
        return Response(current_ocr_runtime())


class SemanticRuntimeSettingsView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        runtime = current_semantic_runtime()
        runtime["model_health"] = semantic_model_health(runtime)
        runtime["index_versions"] = [
            {
                "id": str(version.id),
                "uid": version.uid,
                "status": version.status,
                "model_repo_id": version.model_repo_id,
                "model_revision": version.model_revision,
                "dimensions": version.dimensions,
                "document_count": version.document_count,
                "created_at": version.created_at,
                "activated_at": version.activated_at,
                "error": version.error_message,
            }
            for version in SemanticIndexVersion.objects.all()[:10]
        ]
        return Response(runtime)

    def put(self, request):
        current = current_semantic_runtime()
        engine = str(request.data.get("engine") or "").strip()
        provider = str(request.data.get("provider") or "").strip()
        embedder_name = str(request.data.get("embedder_name") or "").strip()
        model = str(request.data.get("model") or "").strip()
        model_repo_id = str(request.data.get("model_repo_id") or model).strip()
        model_local_path = str(
            request.data.get("model_local_path") or settings.SEMANTIC_SEARCH_MODEL_CACHE
        ).strip()
        model_revision = str(request.data.get("model_revision") or "main").strip()
        pooling = str(request.data.get("pooling") or "useModel").strip()
        offline_mode = request.data.get("offline_mode", True)
        offline_mode = offline_mode is True or str(offline_mode).casefold() in {"1", "true", "yes"}
        dimensions_raw = request.data.get("dimensions")
        try:
            dimensions = int(dimensions_raw) if dimensions_raw not in {None, ""} else None
        except (TypeError, ValueError):
            return Response({"dimensions": ["向量维度必须是正整数。"]}, status=400)
        service_url = str(request.data.get("service_url") or "").strip()
        reranker = str(request.data.get("reranker") or "rules").strip()
        query_rewrite_raw = request.data.get("query_rewrite_enabled", False)
        query_rewrite_enabled = query_rewrite_raw is True or str(query_rewrite_raw).casefold() in {
            "1",
            "true",
            "yes",
        }
        try:
            max_results_per_work = int(request.data.get("max_results_per_work", 2))
        except (TypeError, ValueError):
            return Response({"max_results_per_work": ["同书结果上限必须是整数。"]}, status=400)
        try:
            semantic_ratio = float(request.data.get("semantic_ratio", 0.72))
        except (TypeError, ValueError):
            return Response({"semantic_ratio": ["语义占比必须是 0 到 1 之间的数字。"]}, status=400)
        if engine not in SEMANTIC_ENGINES:
            return Response({"engine": ["请选择有效的模糊检索方式。"]}, status=400)
        if provider not in SEMANTIC_PROVIDERS:
            return Response({"provider": ["请选择有效的嵌入模型来源。"]}, status=400)
        if not embedder_name or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", embedder_name):
            return Response({"embedder_name": ["嵌入器名称只能包含字母、数字、下划线和短横线。"]}, status=400)
        if not model:
            return Response({"model": ["请填写模型标识。"]}, status=400)
        revision_parts = model_revision.replace("\\", "/").split("/")
        if (
            not re.fullmatch(r"[A-Za-z0-9._/-]{1,160}", model_revision)
            or ".." in revision_parts
        ):
            return Response(
                {"model_revision": ["模型 revision 只能使用仓库分支、标签或提交哈希。"]},
                status=400,
            )
        if dimensions is not None and dimensions < 1:
            return Response({"dimensions": ["向量维度必须是正整数。"]}, status=400)
        if pooling not in {"useModel", "forceMean", "forceCls"}:
            return Response({"pooling": ["请选择模型默认、平均池化或 CLS 池化。"]}, status=400)
        if reranker != "rules":
            return Response(
                {"reranker": ["当前版本只支持已接入并可验证的内置规则重排。"]},
                status=400,
            )
        if not 0 <= semantic_ratio <= 1:
            return Response({"semantic_ratio": ["语义占比必须在 0 到 1 之间。"]}, status=400)
        if service_url:
            parsed = urlparse(service_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                return Response({"service_url": ["服务地址必须是有效的 HTTP 或 HTTPS 地址。"]}, status=400)
        if not 1 <= max_results_per_work <= 20:
            return Response({"max_results_per_work": ["同书结果上限必须在 1 至 20 之间。"]}, status=400)
        value = {
            "engine": engine,
            "provider": provider,
            "embedder_name": embedder_name,
            "model": model,
            "model_repo_id": model_repo_id,
            "model_local_path": model_local_path,
            "model_revision": model_revision,
            "dimensions": dimensions,
            "pooling": pooling,
            "offline_mode": offline_mode,
            "endpoint": service_url,
            "service_url": service_url,
            "semantic_ratio": semantic_ratio,
            "reranker": reranker or "rules",
            "query_rewrite_enabled": query_rewrite_enabled,
            "max_results_per_work": max_results_per_work,
        }
        from ingestion.models import AuditEvent
        task = None
        apply_error = ""
        model_keys = {
            "provider",
            "model_repo_id",
            "model_revision",
            "dimensions",
            "pooling",
            "embedder_name",
        }
        model_changed = any(current.get(key) != value.get(key) for key in model_keys)
        pending_configuration = None
        if engine == "meilisearch_hybrid" and model_changed:
            try:
                version = stage_semantic_index_version(value, actor=request.user)
                task = {
                    "type": "versioned_reindex",
                    "version_id": str(version.id),
                    "index_uid": version.uid,
                    "status": version.status,
                }
                apply_error = version.error_message
                pending_configuration = value
                AuditEvent.objects.create(
                    actor=request.user,
                    action="semantic_search_candidate_staged",
                    object_type="SemanticIndexVersion",
                    object_id=str(version.id),
                    before=current,
                    after={**value, "candidate_status": version.status},
                )
            except (ValueError, httpx.HTTPError, RuntimeError, TimeoutError) as exc:
                apply_error = str(exc)[:2000]
        else:
            setting, _ = SiteSetting.objects.update_or_create(
                key="semantic_search_runtime",
                defaults={
                    "value": value,
                    "public": False,
                    "updated_by": request.user,
                },
            )
            AuditEvent.objects.create(
                actor=request.user,
                action="semantic_search_runtime_update",
                object_type="SiteSetting",
                object_id=str(setting.id),
                before=current,
                after=value,
            )
            if engine == "meilisearch_hybrid":
                try:
                    task = configure_semantic_embedder(value)
                except (ValueError, httpx.HTTPError, RuntimeError, TimeoutError) as exc:
                    apply_error = str(exc)[:2000]
        response = current_semantic_runtime()
        response["task"] = task
        response["model_health"] = semantic_model_health(response)
        response["pending_configuration"] = pending_configuration
        response["pending_model_health"] = (
            semantic_model_health(value) if pending_configuration else None
        )
        response["effective"] = not bool(apply_error) and pending_configuration is None
        response["apply_error"] = apply_error
        response["restart_required"] = False
        asynchronous_apply = pending_configuration is not None
        return Response(response, status=202 if apply_error or asynchronous_apply else 200)


class AdminTheorySchoolListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTheorySchoolSerializer
    search_fields = ("name", "description", "search_aliases")
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = TheorySchool.objects.all().order_by("name")


class AdminTheorySchoolDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTheorySchoolSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = TheorySchool.objects.all()


class AdminTopicListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTopicSerializer
    search_fields = ("name", "description", "search_aliases")
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Topic.objects.all().order_by("name")


class AdminTopicDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminTopicSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = Topic.objects.all()


class AdminScholarListView(generics.ListCreateAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminScholarSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    filterset_fields = ("editorial_status",)
    search_fields = (
        "person__preferred_name",
        "person__original_name",
        "person__aliases",
    )
    queryset = ScholarProfile.objects.select_related("person").order_by(
        "person__sort_name",
        "person__preferred_name",
    )


class AdminScholarDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsLibraryStaff]
    serializer_class = AdminScholarSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = ScholarProfile.objects.select_related("person")


class WorkListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = WorkCardSerializer
    filterset_fields = ("document_type", "language")
    ordering_fields = (
        "title",
        "editions__publication_year",
        "editions__first_published_at",
        "created_at",
    )
    ordering = ("-editions__first_published_at", "title")

    def get_queryset(self):
        queryset = public_works()
        featured = self.request.query_params.get("featured")
        if featured == "true":
            queryset = queryset.filter(is_featured=True)
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        return SearchService(request=self.request).queryset(
            SearchContext.WORKS,
            query,
            base_queryset=queryset,
        )


class WorkDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = WorkDetailSerializer
    lookup_field = "editions__public_slug"

    def get_queryset(self):
        return public_works()

    def get_object(self):
        return get_object_or_404(
            self.get_queryset(),
            editions__public_slug=self.kwargs["slug"],
            editions__state=PublicationState.PUBLISHED,
        )


class TheorySchoolListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TheorySchoolSerializer

    def get_queryset(self):
        queryset = (
            TheorySchool.objects.filter(editorial_status="published")
            .annotate(
                work_count=Count(
                    "workknowledgerelation",
                    filter=Q(
                        workknowledgerelation__approved=True,
                        workknowledgerelation__work__editions__state=PublicationState.PUBLISHED,
                    ),
                    distinct=True,
                )
            )
        )
        theme = self.request.query_params.get("theme", "").strip()
        if theme:
            queryset = queryset.filter(
                Q(key_themes__icontains=theme)
                | Q(
                    workknowledgerelation__approved=True,
                    workknowledgerelation__work__knowledge_relations__topic__slug=theme,
                    workknowledgerelation__work__knowledge_relations__approved=True,
                )
                | Q(
                    workknowledgerelation__approved=True,
                    workknowledgerelation__work__knowledge_relations__topic__name__icontains=theme,
                    workknowledgerelation__work__knowledge_relations__approved=True,
                )
            )
        discipline = self.request.query_params.get("discipline", "").strip()
        if discipline:
            queryset = queryset.filter(
                discipline_relations__review_status="approved",
            )
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline_relations__discipline__slug",
                id_field="discipline_relations__discipline_id",
            )
        if self.request.query_params.get("has_works") == "true":
            queryset = queryset.filter(work_count__gt=0)
        if self.request.query_params.get("has_scholars") == "true":
            queryset = queryset.filter(
                Q(
                    personknowledgerelation__approved=True,
                    personknowledgerelation__person__scholar_profile__editorial_status="published",
                )
                | Q(
                    workknowledgerelation__approved=True,
                    workknowledgerelation__work__editions__contributions__approved=True,
                    workknowledgerelation__work__editions__contributions__person__scholar_profile__editorial_status="published",
                )
            )
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        queryset = SearchService(request=self.request).legacy_theory_queryset(
            query,
            base_queryset=queryset,
        )
        ordering = self.request.query_params.get("sort")
        if ordering == "works":
            fields = ("_search_rank", "-work_count", "name") if query else ("-work_count", "name")
            return queryset.distinct().order_by(*fields)
        fields = ("_search_rank", "name") if query else ("name",)
        return queryset.distinct().order_by(*fields)


class TheorySchoolDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = TheorySchoolSerializer
    lookup_field = "slug"

    def get_queryset(self):
        list_view = TheorySchoolListView()
        list_view.request = self.request
        return list_view.get_queryset()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = self.get_serializer(instance).data
        works = public_works().filter(
            knowledge_relations__kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            knowledge_relations__theory_school=instance,
            knowledge_relations__approved=True,
        )
        data["works"] = WorkCardSerializer(works, many=True, context={"request": request}).data
        scholars = ScholarProfile.objects.filter(
            editorial_status="published",
        ).filter(
            Q(
                person__knowledge_relations__theory_school=instance,
                person__knowledge_relations__approved=True,
            )
            | Q(
                person__contributions__approved=True,
                person__contributions__edition__state=PublicationState.PUBLISHED,
                person__contributions__edition__work__knowledge_relations__theory_school=instance,
                person__contributions__edition__work__knowledge_relations__approved=True,
            )
        ).select_related("person").distinct()
        data["scholars"] = ScholarProfileSerializer(
            scholars,
            many=True,
            context={"request": request},
        ).data
        return Response(data)


class TopicListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = TopicSerializer

    def get_queryset(self):
        queryset = Topic.objects.filter(editorial_status="published").annotate(
            work_count=Count(
                "workknowledgerelation",
                filter=Q(
                    workknowledgerelation__approved=True,
                    workknowledgerelation__work__editions__state=PublicationState.PUBLISHED,
                ),
                distinct=True,
            )
        )
        discipline = self.request.query_params.get("discipline", "").strip()
        subdiscipline = self.request.query_params.get("subdiscipline", "").strip()
        theory = self.request.query_params.get("theory", "").strip()
        if discipline:
            queryset = queryset.filter(
                discipline_relations__review_status=RelationReviewStatus.APPROVED,
            )
            queryset = filter_slug_or_uuid(
                queryset,
                discipline,
                slug_field="discipline_relations__discipline__slug",
                id_field="discipline_relations__discipline_id",
            )
        if subdiscipline:
            queryset = queryset.filter(
                subdiscipline_relations__review_status=RelationReviewStatus.APPROVED,
            )
            queryset = filter_slug_or_uuid(
                queryset,
                subdiscipline,
                slug_field="subdiscipline_relations__subdiscipline__slug",
                id_field="subdiscipline_relations__subdiscipline_id",
            )
        if theory:
            queryset = queryset.filter(
                theory_relations__review_status=RelationReviewStatus.APPROVED,
            )
            queryset = filter_slug_or_uuid(
                queryset,
                theory,
                slug_field="theory_relations__theory_school__slug",
                id_field="theory_relations__theory_school_id",
            )
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        queryset = SearchService(request=self.request).queryset(
            SearchContext.TOPICS,
            query,
            base_queryset=queryset,
        )
        if self.request.query_params.get("sort") == "works":
            fields = ("_search_rank", "-work_count", "name") if query else ("-work_count", "name")
            return queryset.distinct().order_by(*fields)
        fields = ("_search_rank", "-curation_level", "name") if query else ("-curation_level", "name")
        return queryset.distinct().order_by(*fields)


class TopicDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = TopicSerializer
    lookup_field = "slug"

    def get_queryset(self):
        list_view = TopicListView()
        list_view.request = self.request
        return list_view.get_queryset()

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = self.get_serializer(instance).data
        works = public_works().filter(
            knowledge_relations__kind=WorkKnowledgeRelation.Kind.TOPIC,
            knowledge_relations__topic=instance,
            knowledge_relations__approved=True,
        )
        data["works"] = WorkCardSerializer(works, many=True, context={"request": request}).data
        scholars = ScholarProfile.objects.filter(
            editorial_status="published",
        ).filter(
            Q(
                person__knowledge_relations__topic=instance,
                person__knowledge_relations__approved=True,
            )
            | Q(
                person__contributions__approved=True,
                person__contributions__edition__state=PublicationState.PUBLISHED,
                person__contributions__edition__work__knowledge_relations__topic=instance,
                person__contributions__edition__work__knowledge_relations__approved=True,
            )
        ).select_related("person").distinct()
        data["scholars"] = ScholarProfileSerializer(
            scholars,
            many=True,
            context={"request": request},
        ).data
        theories = (
            TheorySchool.objects.filter(
                editorial_status="published",
                workknowledgerelation__approved=True,
                workknowledgerelation__work__knowledge_relations__topic=instance,
                workknowledgerelation__work__knowledge_relations__approved=True,
            )
            .annotate(work_count=Count("workknowledgerelation__work", distinct=True))
            .distinct()
        )
        data["theories"] = TheorySchoolSerializer(
            theories,
            many=True,
            context={"request": request},
        ).data
        passage_queryset = (
            Passage.objects.filter(
                page__asset__edition__state=PublicationState.PUBLISHED,
                page__asset__kind=Asset.Kind.NORMALIZED,
                page__asset__status=Asset.Status.READY,
                page__asset__is_current=True,
                page__asset__edition__work__knowledge_relations__topic=instance,
                page__asset__edition__work__knowledge_relations__approved=True,
            )
            .select_related("page__asset__edition__work")
            .order_by("page__asset__edition", "page__index")
        )
        curation = instance.curation if isinstance(instance.curation, dict) else {}
        featured_passage_id = str(curation.get("featured_passage_id", ""))
        passages = list(passage_queryset[:12])
        passages.sort(
            key=lambda passage: (
                0 if str(passage.id) == featured_passage_id else 1,
                passage.page.index,
            )
        )
        passages = passages[:6]
        data["passages"] = [
            {
                "id": str(passage.id),
                "asset_id": str(passage.page.asset_id),
                "title": passage.page.asset.edition.work.title,
                "page_index": passage.page.index,
                "printed_label": clean_page_label(passage.page.printed_label),
                "snippet": passage_snippet(passage.text, ""),
            }
            for passage in passages
        ]
        return Response(data)


class ScholarListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ScholarProfileSerializer

    def get_queryset(self):
        query = (
            self.request.query_params.get("q", "").strip()
            or self.request.query_params.get("search", "").strip()
        )
        return SearchService(request=self.request).queryset(
            SearchContext.SCHOLARS,
            query,
        )


class ScholarDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = ScholarProfileSerializer
    lookup_field = "slug"

    def get_queryset(self):
        list_view = ScholarListView()
        list_view.request = self.request
        return list_view.get_queryset()


class GlobalSearchView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        self.throttle_scope = "exact_search_user" if self.request.user.is_authenticated else "exact_search_anon"
        return super().get_throttles()

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        requested_context = request.query_params.get("context", "").strip()
        if requested_context:
            try:
                search_request = SearchRequest.from_values(
                    query=query,
                    context=requested_context,
                    page=request.query_params.get("page", 1),
                    limit=request.query_params.get(
                        "limit",
                        request.query_params.get("page_size", 24),
                    ),
                    visibility=(
                        SearchVisibility.ADMIN
                        if request.query_params.get("visibility") == SearchVisibility.ADMIN
                        and request.user.is_authenticated
                        and (
                            request.user.is_staff
                            or getattr(request.user, "role", "")
                            in {"admin", "editor", "reviewer"}
                        )
                        else SearchVisibility.PUBLIC
                    ),
                    filters=dict(request.query_params),
                )
            except ValueError as exc:
                return Response({"context": [str(exc)]}, status=400)
            if (
                search_request.context != SearchContext.GLOBAL
                or request.query_params.get("envelope") == "1"
            ):
                return Response(SearchService(request=request).search(search_request))
        service = SearchService(request=request)
        passage_base = Passage.objects.filter(
            page__asset__edition__state=PublicationState.PUBLISHED,
            page__asset__kind=Asset.Kind.NORMALIZED,
            page__asset__status=Asset.Status.READY,
            page__asset__is_current=True,
        ).select_related("page__asset__edition__work")

        if query:
            work_base_matches = service.legacy_global_work_queryset(query)
            scholar_matches = service.legacy_global_scholar_queryset(query)
            topic_matches = service.legacy_global_topic_queryset(query)
            theory_matches = service.legacy_theory_queryset(query)
            external_result = external_passage_ids(query)
            if external_result is None:
                passage_base_matches = passage_base.filter(
                    normalized_text__icontains=normalize_search_text(query),
                )
            else:
                passage_base_matches = passage_base.filter(pk__in=external_result.ids)
        else:
            work_base_matches = public_works()
            scholar_matches = service.base_queryset(SearchContext.SCHOLARS)
            topic_matches = Topic.objects.filter(editorial_status="published")
            theory_matches = TheorySchool.objects.filter(editorial_status="published")
            passage_base_matches = passage_base.none()

        work_matches = filter_works(work_base_matches, request)
        passage_matches = filter_passages(passage_base_matches, request)
        has_work_filters = any(
            query_values(request, name)
            for name in (
                "document_type",
                "theory",
                "topic",
                "concept",
                "tag",
                "author",
                "year",
                "language",
                "access",
            )
        )
        if has_work_filters:
            related_work_ids = set(work_matches.values_list("id", flat=True))
            related_work_ids.update(
                passage_matches.values_list(
                    "page__asset__edition__work_id",
                    flat=True,
                ).distinct()
            )
            scholar_matches = scholar_matches.filter(
                person__contributions__approved=True,
                person__contributions__role=Contribution.Role.AUTHOR,
                person__contributions__edition__state=PublicationState.PUBLISHED,
                person__contributions__edition__work_id__in=related_work_ids,
            )
            topic_matches = topic_matches.filter(
                workknowledgerelation__approved=True,
                workknowledgerelation__work_id__in=related_work_ids,
            )
            theory_matches = theory_matches.filter(
                workknowledgerelation__approved=True,
                workknowledgerelation__work_id__in=related_work_ids,
            )
        scholar_matches = scholar_matches.select_related("person").distinct()
        topic_matches = topic_matches.distinct()
        theory_matches = theory_matches.distinct()

        scope = request.query_params.get("scope", "all")
        display_work_matches = work_matches
        if scope in DOCUMENT_TYPE_ALIASES:
            display_work_matches = display_work_matches.filter(
                document_type=DOCUMENT_TYPE_ALIASES[scope]
            )

        sort = request.query_params.get("sort", "relevance")
        if sort == "newest":
            display_work_matches = display_work_matches.order_by(
                "-editions__first_published_at",
                "title",
            )
        elif sort == "year":
            display_work_matches = display_work_matches.order_by(
                "-editions__publication_year",
                "title",
            )
        else:
            display_work_matches = display_work_matches.order_by("title")

        try:
            page = max(1, int(request.query_params.get("page", "1")))
        except ValueError:
            page = 1
        default_page_size = 8 if scope == "all" else 24
        try:
            page_size = min(
                50,
                max(1, int(request.query_params.get("page_size", str(default_page_size)))),
            )
        except ValueError:
            page_size = default_page_size
        start = (page - 1) * page_size
        end = start + page_size

        passage_count = passage_matches.count()
        passage_queryset = list(
            passage_matches.order_by("page__asset__edition", "page__index", "order")[start:end]
        )
        work_queryset = display_work_matches[start:end]
        scholar_queryset = scholar_matches.order_by(
            "person__sort_name",
            "person__preferred_name",
        )[start:end]
        topic_queryset = topic_matches.order_by("name")[start:end]
        theory_queryset = theory_matches.order_by("name")[start:end]

        facet_work_ids = set(work_base_matches.values_list("id", flat=True))
        facet_work_ids.update(
            passage_base_matches.values_list(
                "page__asset__edition__work_id",
                flat=True,
            ).distinct()
        )
        facet_works = public_works().filter(pk__in=facet_work_ids)

        passages = [
            {
                "id": str(passage.id),
                "work_id": str(passage.page.asset.edition.work_id),
                "edition_slug": passage.page.asset.edition.public_slug,
                "asset_id": str(passage.page.asset_id),
                "title": passage.page.asset.edition.work.title,
                "page_index": passage.page.index,
                "printed_label": clean_page_label(passage.page.printed_label),
                "snippet": passage_snippet(passage.text, query),
                "bbox": passage.bbox_union,
                "query": query,
            }
            for passage in passage_queryset
        ]
        works_data = WorkCardSerializer(work_queryset, many=True, context={"request": request}).data
        scholars_data = ScholarProfileSerializer(
            scholar_queryset,
            many=True,
            context={"request": request},
        ).data
        topics_data = TopicSerializer(topic_queryset, many=True, context={"request": request}).data
        theories_data = TheorySchoolSerializer(
            theory_queryset,
            many=True,
            context={"request": request},
        ).data
        work_count = work_matches.count()
        document_counts = {
            "books": work_matches.filter(document_type="book").count(),
            "articles": work_matches.filter(document_type="journal_article").count(),
            "theses": work_matches.filter(document_type="thesis").count(),
            "reports": work_matches.filter(document_type="report").count(),
        }
        scope_totals = {
            "book": document_counts["books"],
            "article": document_counts["articles"],
            "thesis": document_counts["theses"],
            "report": document_counts["reports"],
            "scholar": scholar_matches.count(),
            "topic": topic_matches.count(),
            "theory": theory_matches.count(),
            "fulltext": passage_count,
        }
        total_for_scope = scope_totals.get(
            scope,
            work_count
            + scholar_matches.count()
            + topic_matches.count()
            + theory_matches.count()
            + passage_count,
        )
        total_pages = max(1, (total_for_scope + page_size - 1) // page_size)
        response = Response(
            {
                "context": SearchContext.GLOBAL,
                "query": query,
                "counts": {
                    "works": work_count,
                    "scholars": scholar_matches.count(),
                    "passages": passage_count,
                    "topics": topic_matches.count(),
                    "theories": theory_matches.count(),
                    **document_counts,
                },
                "facets": search_facets(facet_works),
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total": total_for_scope,
                    "total_pages": total_pages,
                },
                "works": works_data,
                "scholars": scholars_data,
                "topics": topics_data,
                "theories": theories_data,
                "passages": passages,
            }
        )
        if not requested_context:
            response["Deprecation"] = "true"
            response["Warning"] = '299 - "Search context will become required."'
        return response


class SemanticSearchView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        self.throttle_scope = "semantic_search_user" if self.request.user.is_authenticated else "semantic_search_anon"
        return super().get_throttles()

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if len(query) < 2:
            return Response(
                {"q": ["观点检索至少需要两个字符。"]},
                status=400,
            )
        if len(query) > 1200:
            return Response(
                {"q": ["观点检索内容不能超过 1200 个字符。"]},
                status=400,
            )
        try:
            limit = min(80, max(1, int(request.query_params.get("limit", "40"))))
        except ValueError:
            limit = 40
        try:
            max_per_work = int(
                request.query_params.get(
                    "max_per_work",
                    str(settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK),
                )
            )
        except ValueError:
            max_per_work = settings.SEMANTIC_SEARCH_MAX_RESULTS_PER_WORK
        requested_work_ids = []
        for value in query_values(request, "work") or query_values(request, "work_id"):
            try:
                requested_work_ids.append(str(UUID(value)))
            except (TypeError, ValueError, AttributeError):
                continue
        filters = {
            "document_types": query_values(request, "document_type"),
            "languages": query_values(request, "language"),
            "authors": query_values(request, "author") or query_values(request, "scholar"),
            "years": query_values(request, "year"),
            "theories": query_values(request, "theory"),
            "topics": query_values(request, "topic"),
            "concepts": query_values(request, "concept") or query_values(request, "tag"),
            "access": query_values(request, "access"),
            "work_ids": requested_work_ids,
        }
        viewer_is_authenticated = bool(request.user.is_authenticated)
        viewer_is_staff = bool(
            viewer_is_authenticated
            and (
                getattr(request.user, "is_staff", False)
                or getattr(request.user, "role", "") in {"admin", "editor", "reviewer"}
            )
        )
        filters["_allowed_access_statuses"] = viewer_access_statuses(
            authenticated=viewer_is_authenticated,
            staff=viewer_is_staff,
        )
        with capacity_slot(
            "semantic-search",
            limit=settings.SEMANTIC_SEARCH_MAX_CONCURRENT,
            timeout=settings.SEMANTIC_SEARCH_TIMEOUT_SECONDS + 10,
        ) as acquired:
            if not acquired:
                response = Response(
                    {"detail": "观点检索正在处理其他请求，请稍后重试。", "retry_after": 3},
                    status=429,
                )
                response["Retry-After"] = "3"
                return response
            result = semantic_search(
                query,
                filters=filters,
                limit=limit,
                max_per_work=max(0, min(max_per_work, 20)),
                sort=(
                    request.query_params.get("sort", "relevance")
                    if request.query_params.get("sort") in {"relevance", "newest", "year"}
                    else "relevance"
                ),
                debug=bool(request.user.is_authenticated and request.user.is_staff and request.query_params.get("debug") == "1"),
                strategy=(
                    request.query_params.get("strategy", "hybrid_rerank")
                    if request.user.is_authenticated
                    and request.user.is_staff
                    and request.query_params.get("strategy")
                    in {"legacy", "keyword", "vector", "hybrid", "hybrid_rerank"}
                    else "hybrid_rerank"
                ),
                query_override=request.query_params.get("rewrite", ""),
                disable_query_rewrite=request.query_params.get("rewrite_disabled") == "1",
                search_version=(
                    request.query_params.get("version")
                    if viewer_is_staff
                    and request.query_params.get("version") in {"v1", "v2", "v2-a", "v2-b", "v2-c"}
                    else None
                ),
                search_profile=(
                    request.query_params.get("profile")
                    if viewer_is_staff
                    and request.query_params.get("profile") in {"fast", "balanced", "precision"}
                    else None
                ),
                rerank_top_k_override=(
                    min(64, max(0, int(request.query_params.get("rerank_top_k", "24"))))
                    if viewer_is_staff
                    and request.query_params.get("rerank_top_k", "").isdigit()
                    else None
                ),
            )
        result["query"] = query
        result["count"] = len(result["results"])
        result["facets"] = search_facets(filter_works(public_works(), request))
        return Response(result)


class SemanticSearchFeedbackView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        self.throttle_scope = "semantic_search_user" if self.request.user.is_authenticated else "semantic_search_anon"
        return super().get_throttles()

    def post(self, request):
        query = str(request.data.get("query") or "").strip()
        if len(query) < 2 or len(query) > 1200:
            return Response({"query": ["请提交本次观点检索的原始查询。"]}, status=400)
        relevant = request.data.get("relevant")
        if not isinstance(relevant, bool):
            return Response({"relevant": ["请选择相关或不相关。"]}, status=400)
        chunk = None
        viewer_is_authenticated = bool(request.user.is_authenticated)
        viewer_is_staff = bool(
            viewer_is_authenticated
            and (
                getattr(request.user, "is_staff", False)
                or getattr(request.user, "role", "") in {"admin", "editor", "reviewer"}
            )
        )
        allowed_access_statuses = viewer_access_statuses(
            authenticated=viewer_is_authenticated,
            staff=viewer_is_staff,
        )
        chunk_id = request.data.get("chunk_id")
        if chunk_id:
            raw_chunk_id = str(chunk_id)
            if raw_chunk_id.startswith("passage:"):
                passage_id = raw_chunk_id.removeprefix("passage:")
                passage = Passage.objects.filter(
                    pk=passage_id,
                    page__asset__edition__state=PublicationState.PUBLISHED,
                    page__asset__kind=Asset.Kind.NORMALIZED,
                    page__asset__status=Asset.Status.READY,
                    page__asset__is_current=True,
                    page__asset__access_status__in=allowed_access_statuses,
                ).first()
                if passage is None:
                    return Response({"chunk_id": ["该观点段落已不存在。"]}, status=404)
            else:
                passage_id = ""
                chunk = SemanticChunk.objects.filter(
                    pk=raw_chunk_id,
                    asset__edition__state=PublicationState.PUBLISHED,
                    asset__edition__is_primary=True,
                    asset__kind=Asset.Kind.NORMALIZED,
                    asset__status=Asset.Status.READY,
                    asset__is_current=True,
                    asset__access_status__in=allowed_access_statuses,
                ).first()
                if chunk is None:
                    return Response({"chunk_id": ["该观点段落已不存在。"]}, status=404)
        else:
            passage_id = ""
        replacement = None
        actor_identifier = ""
        if not request.user.is_authenticated:
            actor_identifier, replacement = session_identity(request)
        feedback = record_feedback(
            query=query,
            chunk=chunk,
            relevant=relevant,
            rank=request.data.get("rank", 0),
            user=request.user,
            metadata={"source": "public_search", "passage_id": passage_id},
            actor_identifier=actor_identifier,
        )
        response = Response({"id": str(feedback.id), "saved": True}, status=201)
        if replacement:
            response.set_cookie(
                SESSION_COOKIE,
                replacement,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
            )
        return response


class SemanticIndexAdminView(APIView):
    def get_permissions(self):
        if self.request.method != "POST":
            return [CanViewSemanticIndex()]
        action = str(self.request.data.get("action") or "").strip()
        if action in {"resume", "retry_failed", "rebuild_asset", "rechunk_asset", "reembed_asset"}:
            return [CanRetryJobs()]
        return [CanManageSemanticIndex()]

    def get(self, request):
        runtime = current_semantic_runtime()
        current_assets = Asset.objects.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
        chunk_counts = {
            row["index_status"]: row["count"]
            for row in SemanticChunk.objects.values("index_status").annotate(count=Count("id"))
        }
        jobs = SemanticIndexJob.objects.select_related("asset__edition__work")[:30]
        return Response(
            {
                "permissions": {
                    "can_manage": CanManageSemanticIndex().has_permission(request, self),
                },
                "runtime": runtime,
                "model_health": semantic_model_health(runtime),
                "index_versions": [
                    {
                        "id": str(version.id),
                        "uid": version.uid,
                        "status": version.status,
                        "model_repo_id": version.model_repo_id,
                        "model_revision": version.model_revision,
                        "dimensions": version.dimensions,
                        "document_count": version.document_count,
                        "expected_document_count": version.expected_document_count,
                        "validation_details": version.validation_details,
                        "created_at": version.created_at,
                        "activated_at": version.activated_at,
                        "error": version.error_message,
                    }
                    for version in SemanticIndexVersion.objects.all()[:10]
                ],
                "paused": semantic_index_paused(),
                "documents": {
                    "eligible": current_assets.count(),
                    "indexed": SemanticChunk.objects.filter(
                        asset__in=current_assets,
                        index_status=SemanticChunk.IndexStatus.READY,
                    ).values("asset_id").distinct().count(),
                    "pending": current_assets.exclude(semantic_chunks__isnull=False).count(),
                    "failed": SemanticChunk.objects.filter(
                        index_status=SemanticChunk.IndexStatus.FAILED,
                    ).values("asset_id").distinct().count(),
                },
                "chunks": chunk_counts,
                "feedback": {
                    "total": SemanticSearchFeedback.objects.count(),
                    "relevant": SemanticSearchFeedback.objects.filter(relevant=True).count(),
                    "not_relevant": SemanticSearchFeedback.objects.filter(relevant=False).count(),
                },
                "recent_jobs": [
                    {
                        "id": str(job.id),
                        "operation": job.operation,
                        "status": job.status,
                        "progress": job.progress,
                        "asset_id": str(job.asset_id) if job.asset_id else None,
                        "title": job.asset.edition.work.title if job.asset_id else "",
                        "attempts": job.attempts,
                        "model": job.model_name,
                        "chunk_version": job.chunk_version,
                        "error": job.error_message,
                        "stats": job.stats,
                        "created_at": job.created_at,
                        "finished_at": job.finished_at,
                    }
                    for job in jobs
                ],
            }
        )

    def post(self, request):
        action = str(request.data.get("action") or "").strip()
        if action == "pause":
            counts = set_semantic_index_paused(True, actor=request.user)
            return Response({"paused": True, **counts})
        if action == "resume":
            set_semantic_index_paused(False, actor=request.user)
            paused_jobs = SemanticIndexJob.objects.filter(
                status__in=[
                    SemanticIndexJob.Status.PAUSED,
                    SemanticIndexJob.Status.RUNNING,
                ],
                pause_requested_at__isnull=False,
            )
            queued = 0
            for job in paused_jobs.select_related("asset", "index_version")[:500]:
                if job.asset_id:
                    try:
                        resume_semantic_job(job, actor=request.user)
                    except ValueError:
                        continue
                    queued += 1
            for version in SemanticIndexVersion.objects.filter(
                status=SemanticIndexVersion.Status.BUILDING,
            )[:20]:
                result = dispatch_semantic_version_batch(
                    version,
                    batch_size=settings.SEMANTIC_INDEX_STAGE_BATCH_SIZE,
                )
                queued += int(result.get("queued") or 0)
            return Response({"paused": False, "queued": queued})
        if action == "stage_snapshot_version":
            try:
                version = stage_semantic_snapshot_version(
                    current_semantic_runtime(),
                    actor=request.user,
                )
            except (ValueError, httpx.HTTPError, RuntimeError, TimeoutError) as exc:
                return Response({"detail": str(exc)}, status=409)
            from ingestion.models import AuditEvent

            AuditEvent.objects.create(
                actor=request.user,
                action="semantic_snapshot_staged",
                object_type="SemanticIndexVersion",
                object_id=str(version.id),
                after={
                    "uid": version.uid,
                    "expected_document_count": version.expected_document_count,
                    "validation_details": version.validation_details,
                },
            )
            return Response(
                {
                    "queued": version.jobs.count(),
                    "version_id": str(version.id),
                    "uid": version.uid,
                    "status": version.status,
                },
                status=202,
            )
        if action == "activate_version":
            if request.data.get("confirmed") is not True:
                return Response(
                    {"confirmed": ["切换生产索引前必须明确确认。"]},
                    status=400,
                )
            version = get_object_or_404(
                SemanticIndexVersion,
                pk=request.data.get("version_id"),
            )
            previous = SemanticIndexVersion.objects.filter(
                status=SemanticIndexVersion.Status.ACTIVE,
            ).exclude(pk=version.pk).first()
            try:
                activated = activate_semantic_index_version(
                    version,
                    actor=request.user,
                )
            except (ValueError, httpx.HTTPError, RuntimeError, TimeoutError) as exc:
                return Response({"detail": str(exc)}, status=409)
            from ingestion.models import AuditEvent

            AuditEvent.objects.create(
                actor=request.user,
                action="semantic_index_activated",
                object_type="SemanticIndexVersion",
                object_id=str(activated.id),
                before={"active_uid": previous.uid if previous else ""},
                after={
                    "active_uid": activated.uid,
                    "document_count": activated.document_count,
                    "old_index_retained": True,
                },
            )
            return Response(
                {
                    "activated": True,
                    "version_id": str(activated.id),
                    "uid": activated.uid,
                    "document_count": activated.document_count,
                    "old_index_retained": True,
                }
            )
        if action in {"rebuild_asset", "rechunk_asset", "reembed_asset"}:
            asset = get_object_or_404(
                Asset.objects.select_related("edition__work"),
                pk=request.data.get("asset_id"),
                kind=Asset.Kind.NORMALIZED,
                is_current=True,
            )
            job = queue_semantic_job(asset, force=True, actor=request.user)
            return Response({"queued": True, "job_id": str(job.id)}, status=202)
        if action in {"rebuild_all", "retry_failed"}:
            assets = Asset.objects.filter(
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
            ).select_related("edition__work")
            if action == "retry_failed":
                failed_ids = SemanticChunk.objects.filter(
                    index_status=SemanticChunk.IndexStatus.FAILED,
                ).values_list("asset_id", flat=True)
                assets = assets.filter(pk__in=failed_ids)
            queued = 0
            for asset in assets[:10000]:
                queue_semantic_job(asset, force=True, actor=request.user)
                queued += 1
            return Response({"queued": queued}, status=202)
        if action == "clean_orphans":
            stale = Asset.objects.exclude(
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
                edition__state=PublicationState.PUBLISHED,
            ).filter(semantic_chunks__isnull=False).distinct()
            cleaned = 0
            for asset in stale[:10000]:
                remove_semantic_asset(str(asset.id))
                asset.semantic_chunks.all().delete()
                cleaned += 1
            return Response({"cleaned": cleaned})
        return Response({"action": ["请选择有效的语义索引操作。"]}, status=400)


class SemanticIndexTestQueryView(APIView):
    permission_classes = [IsLibraryAdmin]

    def post(self, request):
        query = str(request.data.get("query") or "").strip()
        if len(query) < 2:
            return Response({"query": ["测试查询至少需要两个字符。"]}, status=400)
        active_search_version = (
            "v2" if settings.SEMANTIC_SEARCH_V2_ENABLED else "v1"
        )
        result = semantic_search(
            query,
            filters={},
            limit=20,
            max_per_work=2,
            debug=True,
            search_version=active_search_version,
        )
        keyword = semantic_search(
            query,
            filters={},
            limit=20,
            max_per_work=2,
            debug=True,
            strategy="keyword",
            search_version=active_search_version,
        )
        vector = semantic_search(
            query,
            filters={},
            limit=20,
            max_per_work=2,
            debug=True,
            strategy="vector",
            search_version=active_search_version,
        )
        v1_result = semantic_search(
            query,
            filters={},
            limit=20,
            max_per_work=2,
            debug=True,
            search_version="v1",
        )
        v2_result = semantic_search(
            query,
            filters={},
            limit=20,
            max_per_work=2,
            debug=True,
            search_version="v2",
            search_profile="precision",
        )
        runtime = current_semantic_runtime()
        result["query"] = query
        result["count"] = len(result["results"])
        result["effective_configuration"] = {
            "semantic_ratio": runtime["semantic_ratio"],
            "embedder": runtime["embedder_name"],
            "provider": runtime["provider"],
            "model": runtime["model_repo_id"],
            "revision": runtime["model_revision"],
            "offline_mode": runtime["offline_mode"],
            "model_health": semantic_model_health(runtime),
            "active_search_version": active_search_version,
            "viewpoint_v2": {
                "enabled": settings.SEMANTIC_SEARCH_V2_ENABLED,
                "profile": settings.SEMANTIC_SEARCH_PROFILE,
                "rerank_provider": settings.SEMANTIC_SEARCH_V2_RERANK_PROVIDER,
                "rerank_model": settings.SEMANTIC_SEARCH_V2_RERANK_MODEL,
                "rerank_service_configured": bool(settings.SEMANTIC_SEARCH_V2_RERANK_URL),
            },
        }
        result["comparison"] = {
            "keyword_results": keyword["results"],
            "semantic_results": vector["results"],
            "final_results": result["results"],
            "v1_results": v1_result["results"],
            "v2_results": v2_result["results"],
            "v2_diagnostics": v2_result.get("diagnostics"),
            "latency_ms": {
                "keyword": keyword.get("timing_ms"),
                "semantic": vector.get("timing_ms"),
                "final": result.get("timing_ms"),
                "v1": v1_result.get("timing_ms"),
                "v2": v2_result.get("timing_ms"),
            },
        }
        return Response(result)


class AdminPageMappingView(APIView):
    permission_classes = [IsLibraryStaff]

    def _asset(self, asset_id):
        return get_object_or_404(
            Asset.objects.select_related("edition__work"),
            pk=asset_id,
            kind=Asset.Kind.NORMALIZED,
            is_current=True,
        )

    def get(self, request, asset_id):
        asset = self._asset(asset_id)
        try:
            page_number = max(1, int(request.query_params.get("page", "1")))
            page_size = min(100, max(1, int(request.query_params.get("page_size", "50"))))
        except ValueError:
            return Response({"page": ["分页参数必须是整数。"]}, status=400)
        queryset = asset.pages.order_by("index")
        total = queryset.count()
        start = (page_number - 1) * page_size
        pages = queryset[start : start + page_size]
        return Response(
            {
                "asset_id": str(asset.id),
                "edition_id": str(asset.edition_id),
                "title": asset.edition.work.title,
                "status": asset.edition.page_label_status,
                "page_count": asset.page_count,
                "pagination": {
                    "page": page_number,
                    "page_size": page_size,
                    "total": total,
                },
                "segments": [
                    {
                        "id": str(segment.id),
                        "start_file_page_index": segment.start_file_page_index,
                        "end_file_page_index": segment.end_file_page_index,
                        "start_label": segment.start_label,
                        "style": segment.style,
                        "source": segment.source,
                        "confidence": segment.confidence,
                    }
                    for segment in asset.page_label_segments.all()
                ],
                "pages": [
                    {
                        "id": str(page.id),
                        "file_page_index": page.index,
                        "printed_page_label": page.printed_label,
                        "source": page.label_source,
                        "confidence": page.label_confidence,
                        "is_manual": page.is_label_manual,
                        "is_anchor": page.is_label_anchor,
                        "reader_url": f"/reader/{asset.id}?page={page.index}",
                    }
                    for page in pages
                ],
            }
        )

    def post(self, request, asset_id):
        asset = self._asset(asset_id)
        action = str(request.data.get("action") or "").strip()
        if action == "analyze":
            return Response(infer_page_labels(asset))
        if action == "confirm":
            asset.edition.page_label_status = PageLabelStatus.READY
            asset.edition.save(update_fields=["page_label_status", "updated_at"])
            return Response({"status": PageLabelStatus.READY})
        if action == "set_page":
            try:
                file_page_index = int(request.data.get("file_page_index"))
            except (TypeError, ValueError):
                return Response({"file_page_index": ["PDF 页序必须是正整数。"]}, status=400)
            page = get_object_or_404(asset.pages, index=file_page_index)
            page.printed_label = str(request.data.get("printed_page_label") or "").strip()[:40]
            page.label_source = Page.LabelSource.MANUAL
            page.label_confidence = 1
            page.is_label_manual = True
            page.is_label_anchor = bool(request.data.get("is_anchor", True))
            page.save()
            asset.edition.page_label_status = PageLabelStatus.NEEDS_REVIEW
            asset.edition.save(update_fields=["page_label_status", "updated_at"])
            return Response(
                {
                    "file_page_index": page.index,
                    "printed_page_label": page.printed_label,
                    "source": page.label_source,
                }
            )
        if action == "create_segment":
            try:
                start_index = int(request.data.get("start_file_page_index"))
                end_raw = request.data.get("end_file_page_index")
                end_index = int(end_raw) if end_raw not in {None, ""} else None
            except (TypeError, ValueError):
                return Response({"detail": "分段页序必须是正整数。"}, status=400)
            if start_index < 1 or start_index > asset.page_count:
                return Response({"start_file_page_index": ["起始页超出 PDF 页数。"]}, status=400)
            if end_index is not None and (end_index < start_index or end_index > asset.page_count):
                return Response({"end_file_page_index": ["结束页超出有效范围。"]}, status=400)
            style = str(request.data.get("style") or PageLabelSegment.Style.ARABIC)
            if style not in PageLabelSegment.Style.values:
                return Response({"style": ["请选择有效的页码样式。"]}, status=400)
            with transaction.atomic():
                segment, _ = PageLabelSegment.objects.update_or_create(
                    asset=asset,
                    start_file_page_index=start_index,
                    defaults={
                        "end_file_page_index": end_index,
                        "start_label": str(request.data.get("start_label") or "").strip()[:40],
                        "style": style,
                        "source": Page.LabelSource.MANUAL,
                        "confidence": 1,
                        "created_by": request.user,
                    },
                )
                updated = apply_page_label_segment(segment)
            return Response({"segment_id": str(segment.id), "updated_pages": updated})
        return Response({"action": ["请选择分析、校对单页、建立分段或确认页码。"]}, status=400)


class AdminReaderRenditionPolicyView(APIView):
    permission_classes = [IsLibraryAdmin]

    def put(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        policy = str(request.data.get("policy") or "").strip()
        if policy not in ReaderRenditionPolicy.values:
            return Response({"policy": ["请选择自动、原始 PDF 或 OCR PDF。"]}, status=400)
        edition.reader_rendition_policy = policy
        edition.save(update_fields=["reader_rendition_policy", "updated_at"])
        validated_ocr = edition.assets.filter(
            kind=Asset.Kind.OCR_PDF,
            status=Asset.Status.READY,
            validation_status=Asset.ValidationStatus.VALID,
            is_current=True,
        ).exists()
        return Response(
            {
                "policy": policy,
                "validated_ocr_pdf_available": validated_ocr,
                "effective_rendition": (
                    Asset.Kind.OCR_PDF
                    if policy == ReaderRenditionPolicy.OCR and validated_ocr
                    else Asset.Kind.NORMALIZED
                ),
                "fallback_active": policy == ReaderRenditionPolicy.OCR and not validated_ocr,
            }
        )


class PublicUsageEventView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "public_usage_event"

    def post(self, request):
        event_type = str(request.data.get("event_type") or "").strip()
        if event_type not in AnonymousUsageEvent.EventType.values:
            return Response({"event_type": ["请选择有效的公开使用事件。"]}, status=400)
        query = str(request.data.get("query") or "").strip()
        if event_type == AnonymousUsageEvent.EventType.SEARCH_SUBMIT and not query:
            return Response({"query": ["提交检索事件时必须包含查询。"]}, status=400)
        work = None
        asset = None
        work_id = request.data.get("work_id")
        asset_id = request.data.get("asset_id")
        if work_id:
            work = public_works().filter(pk=work_id).first()
        if asset_id:
            asset = Asset.objects.filter(
                pk=asset_id,
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
                edition__state=PublicationState.PUBLISHED,
            ).select_related("edition__work").first()
            if asset and work is None:
                work = asset.edition.work
        result_count_raw = request.data.get("result_count")
        try:
            result_count = int(result_count_raw) if result_count_raw not in {None, ""} else None
        except (TypeError, ValueError):
            return Response({"result_count": ["结果数量必须是非负整数。"]}, status=400)
        if result_count is not None and result_count < 0:
            return Response({"result_count": ["结果数量必须是非负整数。"]}, status=400)
        event, replacement = record_usage_event(
            request,
            event_type=event_type,
            work=work,
            asset=asset,
            query=query,
            result_count=result_count,
            metadata={
                "source": str(request.data.get("source") or "public")[:80],
                "scope": str(request.data.get("scope") or "")[:80],
            },
        )
        response = Response(
            {"accepted": event is not None, "event_id": str(event.id) if event else None},
            status=202,
        )
        if replacement:
            response.set_cookie(
                SESSION_COOKIE,
                replacement,
                max_age=365 * 24 * 60 * 60,
                httponly=True,
                secure=not settings.DEBUG,
                samesite="Lax",
            )
        return response


class HotSearchView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        try:
            days = min(90, max(1, int(request.query_params.get("days", "30"))))
            limit = min(30, max(1, int(request.query_params.get("limit", "10"))))
        except ValueError:
            return Response({"detail": "统计天数和数量必须是整数。"}, status=400)
        since = timezone.localdate() - timedelta(days=days - 1)
        rows = (
            SearchQueryAggregate.objects.filter(
                period="day",
                period_start__gte=since,
                excluded=False,
            )
            .values("normalized_query")
            .annotate(
                search_count=Sum("search_count"),
                unique_sessions=Sum("unique_sessions"),
                click_count=Sum("click_count"),
                zero_result_count=Sum("zero_result_count"),
            )
            .filter(unique_sessions__gte=3, search_count__gte=3)
            .order_by("-search_count", "normalized_query")[:limit]
        )
        return Response(
            {
                "period_days": days,
                "results": [
                    {
                        "query": row["normalized_query"],
                        "search_count": row["search_count"],
                        "unique_sessions": row["unique_sessions"],
                        "click_count": row["click_count"],
                        "zero_result_count": row["zero_result_count"],
                    }
                    for row in rows
                ],
            }
        )


class AdminUsageAnalyticsView(APIView):
    permission_classes = [IsLibraryAdmin]

    def get(self, request):
        try:
            days = min(365, max(1, int(request.query_params.get("days", "30"))))
        except ValueError:
            return Response({"days": ["统计天数必须是整数。"]}, status=400)
        since = timezone.now() - timedelta(days=days)
        events = AnonymousUsageEvent.objects.filter(created_at__gte=since)
        counts = {
            value: events.filter(event_type=value).count()
            for value in AnonymousUsageEvent.EventType.values
        }
        sessions = events.values("session_hash").distinct().count()
        zero_result = events.filter(
            event_type=AnonymousUsageEvent.EventType.SEARCH_SUBMIT,
            result_count=0,
        ).count()
        top_works = (
            events.filter(
                event_type=AnonymousUsageEvent.EventType.READER_OPEN,
                work__isnull=False,
            )
            .values("work_id", "work__title")
            .annotate(opens=Count("id"), unique_sessions=Count("session_hash", distinct=True))
            .order_by("-opens")[:20]
        )
        aggregate_since = timezone.localdate() - timedelta(days=days - 1)
        top_queries = list(
            SearchQueryAggregate.objects.filter(
                period="day",
                period_start__gte=aggregate_since,
                excluded=False,
            )
            .values("normalized_query")
            .annotate(
                search_count=Sum("search_count"),
                unique_sessions=Sum("unique_sessions"),
                click_count=Sum("click_count"),
                zero_result_count=Sum("zero_result_count"),
            )
            .order_by("-search_count", "normalized_query")[:50]
        )
        for row in top_queries:
            row["click_through_rate"] = round(
                row["click_count"] / row["search_count"],
                4,
            ) if row["search_count"] else 0
        return Response(
            {
                "period_days": days,
                "anonymous_sessions": sessions,
                "events": counts,
                "zero_result_searches": zero_result,
                "top_works": list(top_works),
                "top_queries": top_queries,
                "privacy": {
                    "stores_ip_identity": False,
                    "links_registered_user": False,
                    "retention_days": settings.ANONYMOUS_EVENT_RETENTION_DAYS,
                },
            }
        )


class PassageFocusView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, pk):
        passage = Passage.objects.select_related("page__asset__edition__work").filter(
            pk=pk,
            page__asset__edition__state=PublicationState.PUBLISHED,
            page__asset__edition__is_primary=True,
            page__asset__kind=Asset.Kind.NORMALIZED,
            page__asset__status=Asset.Status.READY,
            page__asset__is_current=True,
        ).first()
        if passage is not None:
            return Response(
                {
                    "id": str(passage.id),
                    "asset_id": str(passage.page.asset_id),
                    "title": passage.page.asset.edition.work.title,
                    "page_index": passage.page.index,
                    "printed_label": clean_page_label(passage.page.printed_label),
                    "width": passage.page.width,
                    "height": passage.page.height,
                    "bbox": passage.bbox_union,
                    "text": passage.text,
                }
            )
        chunk = get_object_or_404(
            SemanticChunk.objects.select_related("asset__edition__work"),
            pk=pk,
            asset__edition__state=PublicationState.PUBLISHED,
            asset__edition__is_primary=True,
            asset__kind=Asset.Kind.NORMALIZED,
            asset__status=Asset.Status.READY,
            asset__is_current=True,
        )
        locator = chunk.locators[0] if chunk.locators else {}
        page = chunk.asset.pages.filter(index=chunk.page_start).first()
        return Response(
            {
                "id": str(chunk.id),
                "asset_id": str(chunk.asset_id),
                "title": chunk.asset.edition.work.title,
                "page_index": chunk.page_start,
                "printed_label": clean_page_label(locator.get("printed_label", "")),
                "width": page.width if page else 0,
                "height": page.height if page else 0,
                "bbox": locator.get("bbox", []),
                "text": chunk.original_text,
                "locators": chunk.locators,
            }
        )


class PublicAssetManifestView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, asset_id):
        asset = get_object_or_404(
            Asset.objects.select_related("edition__work"),
            pk=asset_id,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            edition__state=PublicationState.PUBLISHED,
            is_current=True,
        )
        chapter_pages = asset.pages.exclude(chapter_title="").order_by("index")
        author_profiles = ScholarProfile.objects.filter(
            editorial_status="published",
            person__contributions__edition=asset.edition,
            person__contributions__role=Contribution.Role.AUTHOR,
            person__contributions__approved=True,
        ).select_related("person").distinct()
        theories = asset.edition.work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.THEORY_SCHOOL,
            approved=True,
        ).select_related("theory_school")
        topics = asset.edition.work.knowledge_relations.filter(
            kind=WorkKnowledgeRelation.Kind.TOPIC,
            approved=True,
        ).select_related("topic")
        return Response(
            {
                "asset_id": str(asset.id),
                "edition_id": str(asset.edition_id),
                "page_count": asset.page_count,
                "publication_status": asset.edition.state,
                "ocr_status": asset.edition.ocr_status,
                "semantic_index_status": asset.edition.semantic_index_status,
                "page_label_status": asset.edition.page_label_status,
                "reader_rendition_policy": asset.edition.reader_rendition_policy,
                "work": WorkCardSerializer(
                    asset.edition.work,
                    context={"request": request},
                ).data,
                "outline": [
                    {
                        "index": page.index,
                        "file_page_index": page.index,
                        "printed_label": clean_page_label(page.printed_label),
                        "chapter_title": page.chapter_title,
                    }
                    for page in chapter_pages
                ],
                "related_scholars": [
                    {
                        "name": profile.person.preferred_name,
                        "slug": profile.slug,
                        "years": (
                            f"{profile.person.birth_year or ''}—{profile.person.death_year or ''}"
                            if profile.person.birth_year or profile.person.death_year
                            else ""
                        ),
                    }
                    for profile in author_profiles
                ],
                "related_theories": [
                    {
                        "name": relation.theory_school.name,
                        "slug": relation.theory_school.slug,
                    }
                    for relation in theories
                    if relation.theory_school_id
                ],
                "related_topics": [
                    {
                        "name": relation.topic.name,
                        "slug": relation.topic.slug,
                    }
                    for relation in topics
                    if relation.topic_id
                ],
            }
        )


class PublicPageContentView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, asset_id, page_index):
        asset = get_object_or_404(
            Asset,
            pk=asset_id,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            edition__state=PublicationState.PUBLISHED,
            is_current=True,
        )
        page = get_object_or_404(asset.pages, index=page_index)
        return Response(
            {
                "page_id": str(page.id),
                "page_index": page.index,
                "file_page_index": page.index,
                "printed_label": clean_page_label(page.printed_label),
                "citation_page_label": clean_page_label(page.printed_label) or str(page.index),
                "label_source": page.label_source,
                "label_confidence": page.label_confidence,
                "chapter_title": page.chapter_title,
                "text_source": page.text_source,
                "width": page.width,
                "height": page.height,
                "text": page.text,
                "blocks": [
                    {
                        "id": str(block.id),
                        "order": block.order,
                        "type": block.block_type,
                        "text": block.text,
                        "bbox": block.bbox,
                        "confidence": block.confidence,
                    }
                    for block in page.blocks.exclude(block_type__in=["header", "footer"])
                ],
            }
        )


class DocumentSearchView(APIView):
    permission_classes = [AllowAny]

    def get_throttles(self):
        self.throttle_scope = "exact_search_user" if self.request.user.is_authenticated else "exact_search_anon"
        return super().get_throttles()

    def get(self, request, asset_id):
        query = request.query_params.get("q", "").strip()[:500]
        asset = get_object_or_404(
            Asset,
            pk=asset_id,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            edition__state=PublicationState.PUBLISHED,
            is_current=True,
        )
        if not query:
            return Response({"query": "", "matches": []})
        external_result = external_passage_ids(query, limit=200, asset_id=str(asset.id))
        # An available Meilisearch service can still have an empty or stale
        # passages index during an upgrade/reindex.  The reader must continue
        # to search the authoritative page text in that case.
        if external_result is None or not external_result.ids:
            matches = asset.pages.filter(
                normalized_text__icontains=normalize_search_text(query),
            ).order_by("index")
            data = [
                {
                    "page_id": str(page.id),
                    "page_index": page.index,
                    "printed_label": clean_page_label(page.printed_label),
                    "snippet": passage_snippet(page.text, query),
                    "width": page.width,
                    "height": page.height,
                    "blocks": [
                        {"bbox": block.bbox, "text": block.text, "order": block.order}
                        for block in page.blocks.filter(
                            normalized_text__icontains=normalize_search_text(query)
                        )
                    ],
                }
                for page in matches[:100]
            ]
        else:
            external_ids = external_result.ids
            passages = (
                Passage.objects.filter(
                    pk__in=external_ids,
                    page__asset=asset,
                )
                .select_related("page")
            )
            passage_map = {str(passage.id): passage for passage in passages}
            ordered = [
                passage_map[passage_id]
                for passage_id in external_ids
                if passage_id in passage_map
            ]
            pages = {}
            for passage in ordered:
                page_data = pages.setdefault(
                    passage.page_id,
                    {
                        "page_id": str(passage.page_id),
                        "page_index": passage.page.index,
                        "printed_label": clean_page_label(passage.page.printed_label),
                        "snippet": passage_snippet(passage.page.text, query),
                        "width": passage.page.width,
                        "height": passage.page.height,
                        "blocks": [],
                    },
                )
                page_data["blocks"].append(
                    {
                        "bbox": passage.bbox_union,
                        "text": passage.text,
                        "order": passage.order,
                    }
                )
            data = sorted(pages.values(), key=lambda value: value["page_index"])[:100]
        highlight_map = search_highlights(asset, query, data)
        for rank, page_data in enumerate(data, start=1):
            page_data["highlights"] = highlight_map.get(page_data["page_index"], [])
            page_data["rank"] = rank
            page_data["occurrence_count"] = max(
                1,
                len(page_data["highlights"]) or len(page_data["blocks"]),
            )
        return Response({"query": query, "matches": data})


class CitationView(APIView):
    permission_classes = [AllowAny]

    def get(self, request, edition_id):
        edition = get_object_or_404(
            Edition.objects.select_related("work").prefetch_related("contributions__person"),
            pk=edition_id,
            state=PublicationState.PUBLISHED,
        )
        pdf_page_raw = request.query_params.get("pdf_page", "").strip()
        legacy_page = clean_page_label(
            request.query_params.get("page", "").strip()
        )
        page_label = legacy_page
        page_meta = {
            "pdf_page": None,
            "printed_label": legacy_page,
            "citation_label": legacy_page,
            "source": "legacy" if legacy_page else "none",
        }
        if pdf_page_raw:
            try:
                pdf_page = int(pdf_page_raw)
            except ValueError:
                return Response(
                    {"pdf_page": ["PDF 页序必须是正整数。"]},
                    status=400,
                )
            if pdf_page < 1:
                return Response(
                    {"pdf_page": ["PDF 页序必须是正整数。"]},
                    status=400,
                )
            asset = edition.assets.filter(
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
            ).first()
            if asset is None:
                return Response(
                    {"detail": "当前版本没有可用于页码映射的规范 PDF。"},
                    status=409,
                )
            page = get_object_or_404(asset.pages, index=pdf_page)
            printed_label = clean_page_label(page.printed_label)
            page_label = printed_label or str(page.index)
            page_meta = {
                "pdf_page": page.index,
                "printed_label": printed_label,
                "citation_label": page_label,
                "source": "pdf-label" if printed_label else "pdf-index",
            }
        bundle = citation_bundle(edition, page_label)
        bundle["page"] = page_meta
        return Response(bundle)


class CleanCopyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        text = request.data.get("text", "")
        if not isinstance(text, str) or not text.strip():
            return Response({"text": "", "html": "", "warnings": ["没有可清理的文字。"]}, status=400)
        payload = clipboard_payload(text)
        if len(text) > 100_000:
            payload["warnings"].append("本次内容较长，请粘贴后复核段落边界。")
        return Response(payload)
