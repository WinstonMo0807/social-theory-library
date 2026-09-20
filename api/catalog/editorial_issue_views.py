"""Issue articles and fixed site templates, with protected draft previews."""
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import EditorialRevision, RecommendationIssue, RecommendationIssueItem, MediaRendition, SiteSetting
from catalog.services import editorial_issues as service
from common.permissions import CanAccessBackOffice, CanEditMetadata, CanPublishAuthority, IsLibraryAdmin
from catalog.editorial_issue_serializers import (RecommendationIssueSerializer, RecommendationIssueCollectionSerializer,
    AdminRecommendationIssueCollectionSerializer, EditorialPublishSerializer, PlannedItemLinkSerializer, SiteContentSerializer, SavedIssueListSerializer)


def collection(request, queryset, *, public=False):
    query = request.query_params.get("q", "").strip()
    if query:
        # Public searches only consult the already published snapshot.
        if public:
            due = Q(scheduled_revision__status="published", scheduled_for__lte=timezone.now())
            queryset = queryset.filter((due & Q(scheduled_revision__materialized_preview__title__icontains=query)) |
                                       (~due & Q(active_revision__materialized_preview__title__icontains=query)))
        else:
            queryset = queryset.filter(title__icontains=query)
    paginator = Paginator(queryset.order_by("-effective_display_from" if public else "-created_at", "-created_at", "id"), 12)
    page = paginator.get_page(request.query_params.get("page", 1))
    def page_url(number):
        params = request.query_params.copy()
        params["page"] = number
        return f"{request.path}?{params.urlencode()}"
    current = service.published_issues().order_by("-effective_display_from", "-created_at").first()
    return {"count": paginator.count, "next": page_url(page.next_page_number()) if page.has_next() else None,
            "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
            "results": [service.issue_payload(row, public=public) for row in page.object_list],
            "current": service.issue_payload(current, public=True) if current else None}


class PublicIssueListView(APIView):
    permission_classes = [AllowAny]
    @extend_schema(operation_id="catalog_recommendation_issues_list", responses=RecommendationIssueCollectionSerializer)
    def get(self, request):
        return Response(collection(request, service.published_issues(), public=True))


class PublicIssueDetailView(APIView):
    permission_classes = [AllowAny]
    @extend_schema(responses=RecommendationIssueSerializer)
    def get(self, request, slug):
        return Response(service.issue_payload(get_object_or_404(service.published_issues(), slug=slug), public=True))


class SaveIssueReadingListView(APIView):
    permission_classes = [IsAuthenticated]
    @extend_schema(request=None, responses=SavedIssueListSerializer)
    @transaction.atomic
    def post(self, request, slug):
        from django.contrib.auth import get_user_model
        from reading.models import ReadingList, ReadingListItem
        issue = get_object_or_404(service.published_issues(), slug=slug)
        payload = service.issue_payload(issue, public=True)
        # Serialize concurrent retries for this user; no other reader's list is read.
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        marker = f"书库推荐 /recommendations/{issue.slug}"
        reading_list = ReadingList.objects.filter(user=request.user, description=marker).first()
        if reading_list is None:
            reading_list = ReadingList.objects.create(user=request.user, title=payload["title"][:240], description=marker)
        for position, item in enumerate(payload["items"]):
            if item.get("available_work_id"):
                ReadingListItem.objects.get_or_create(reading_list=reading_list, work_id=item["available_work_id"], defaults={"order": position})
        return Response({"id": str(reading_list.pk), "title": reading_list.title, "item_count": reading_list.items.count(),
                         "planned_count": sum(row["status"] == "planned" for row in payload["items"])})


class EditorialErrorMixin:
    def handle_exception(self, exc):
        from django.core.exceptions import ValidationError as ModelValidationError
        if isinstance(exc, service.EditConflict):
            return Response({"code": "editorial_conflict", "detail": str(exc)}, status=409)
        if isinstance(exc, ModelValidationError):
            return Response({"code": "invalid_editorial_data", "detail": "对象标识或内容格式无效，请核对后重试。"}, status=400)
        return super().handle_exception(exc)


class AdminIssueListView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]
    @extend_schema(operation_id="catalog_admin_recommendation_issues_list", responses=AdminRecommendationIssueCollectionSerializer)
    def get(self, request):
        issues = RecommendationIssue.objects.select_related("active_revision", "scheduled_revision")
        upcoming = issues.filter(scheduled_revision__status="published", scheduled_for__gt=timezone.now())
        drafts = EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=OuterRef("pk"), status="draft")
        payload = collection(request, issues)
        # Dashboard metrics describe the inventory, independently of a search
        # or page. A published issue can also have a draft or a future revision.
        payload["summary"] = {"total": issues.count(), "published": service.published_issues().count(),
                              "drafts": issues.filter(Exists(drafts)).count(), "scheduled": upcoming.count()}
        payload["upcoming"] = [service.issue_payload(row, revision=row.scheduled_revision)
                               for row in upcoming.order_by("scheduled_for", "id")[:3]]
        return Response(payload)
    @extend_schema(request=RecommendationIssueSerializer, responses={201: RecommendationIssueSerializer})
    def post(self, request):
        return Response(service.issue_payload(service.create_issue(request.data, request.user)), status=201)


class AdminIssueDetailView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "PUT" else [CanAccessBackOffice()]
    @extend_schema(responses=RecommendationIssueSerializer)
    def get(self, request, issue_id):
        return Response(service.issue_payload(get_object_or_404(RecommendationIssue, pk=issue_id)))
    @extend_schema(request=RecommendationIssueSerializer, responses=RecommendationIssueSerializer)
    def put(self, request, issue_id):
        get_object_or_404(RecommendationIssue, pk=issue_id)
        return Response(service.issue_payload(service.save_issue(issue_id, request.data, request.user)))


class AdminIssuePublishView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanPublishAuthority]
    @extend_schema(request=EditorialPublishSerializer, responses=RecommendationIssueSerializer)
    def post(self, request, issue_id):
        get_object_or_404(RecommendationIssue, pk=issue_id)
        return Response(service.issue_payload(service.publish_issue(issue_id, request.data.get("edit_version"), request.user)))


class AdminIssuePreviewView(AdminIssueDetailView):
    http_method_names = ["get", "head", "options"]


class AdminIssueLinkView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]
    @extend_schema(request=PlannedItemLinkSerializer, responses=RecommendationIssueSerializer)
    def post(self, request, issue_id, item_id):
        get_object_or_404(RecommendationIssueItem, pk=item_id, issue_id=issue_id)
        return Response(service.issue_payload(service.link_planned_item(issue_id, item_id, request.data, request.user)))


class AdminSiteContentView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]
    @extend_schema(responses=SiteContentSerializer)
    def get(self, request):
        return Response(service.site_payload())
    @extend_schema(request=SiteContentSerializer, responses=SiteContentSerializer)
    def put(self, request):
        return Response(service.save_site(request.data, request.user))


class AdminSitePublishView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]
    @extend_schema(request=EditorialPublishSerializer, responses=SiteContentSerializer)
    def post(self, request):
        return Response(service.publish_site(request.data.get("edit_version"), request.user))


class AdminSitePreviewView(AdminSiteContentView):
    http_method_names = ["get", "head", "options"]


class PublicEditorialMediaView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, rendition_id):
        from django.http import Http404
        key = str(rendition_id)
        published = service.published_issues().filter(Q(active_revision__materialized_preview__cover_rendition_id=key) |
            Q(scheduled_for__lte=timezone.now(), scheduled_revision__materialized_preview__cover_rendition_id=key)).exists()
        published = published or SiteSetting.objects.filter(key="site_config", public=True, value__home_hero_rendition_id=key).exists()
        if not published:
            raise Http404
        row = get_object_or_404(MediaRendition, pk=rendition_id)
        try:
            response = FileResponse(row.file.open("rb"), content_type="image/webp")
        except OSError:
            return Response({"detail": "图片暂时无法读取。"}, status=503)
        response["X-Content-Type-Options"] = "nosniff"
        response["ETag"] = f'"{row.checksum}"'
        return response


class IssueItemCoverView(APIView):
    permission_classes = [AllowAny]
    admin_preview = False

    def get(self, request, item_id, slug=None, issue_id=None):
        from django.http import Http404
        from catalog.models import Work
        from pathlib import PurePosixPath
        import mimetypes
        issue = get_object_or_404(RecommendationIssue, pk=issue_id) if self.admin_preview else get_object_or_404(service.published_issues(), slug=slug)
        payload = service.issue_payload(issue, public=not self.admin_preview, include_cover_storage=True)
        item = next((row for row in payload["items"] if row["id"] == str(item_id)), None)
        if not item or not item.get("available_edition_id"):
            raise Http404
        if item.get("cover_rendition_id"):
            rendition = get_object_or_404(MediaRendition, pk=item["cover_rendition_id"])
            try:
                response = FileResponse(rendition.file.open("rb"), content_type="image/webp")
            except OSError:
                return Response({"detail": "封面暂时无法读取。"}, status=503)
            response["ETag"] = f'"{rendition.checksum}"'
        else:
            filename = str(item.get("cover_path") or "")
            if not filename or ".." in PurePosixPath(filename).parts or filename.startswith("/") or "\\" in filename:
                raise Http404
            try:
                response = FileResponse(Work._meta.get_field("cover").storage.open(filename, "rb"), content_type=mimetypes.guess_type(filename)[0] or "image/jpeg")
            except OSError:
                return Response({"detail": "封面暂时无法读取。"}, status=503)
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store" if self.admin_preview else "public, max-age=300"
        return response


class AdminIssueItemCoverView(IssueItemCoverView):
    permission_classes = [CanAccessBackOffice]
    admin_preview = True
