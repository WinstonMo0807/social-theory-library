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
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.editorial_issue_serializers import IssuePublicationReviewSerializer, SitePublishSerializer
from catalog.models import EditorialRevision, RecommendationIssue, RecommendationIssueItem, MediaRendition, SiteSetting
from catalog.services import editorial_issues as service
from common.permissions import CanAccessBackOffice, CanEditMetadata, CanPublishAuthority, IsLibraryAdmin
from catalog.editorial_issue_serializers import (RecommendationIssueSerializer, RecommendationIssueCollectionSerializer,
    AdminRecommendationIssueCollectionSerializer, EditorialPublishSerializer, PlannedItemLinkSerializer, SiteContentSerializer, SavedIssueListSerializer,
    PublicEditorialDirectorySerializer, SaveIssueListCommandSerializer)


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
    paginator = Paginator(queryset.order_by("-effective_display_from" if public else "-updated_at", "-created_at", "id"), 12)
    page = paginator.get_page(request.query_params.get("page", 1))
    def page_url(number):
        params = request.query_params.copy()
        params["page"] = number
        return f"{request.path}?{params.urlencode()}"
    current = service.published_issues().order_by("-effective_display_from", "-created_at").first()
    return {"count": paginator.count, "page": page.number, "page_size": paginator.per_page, "pages": paginator.num_pages, "next": page_url(page.next_page_number()) if page.has_next() else None,
            "previous": page_url(page.previous_page_number()) if page.has_previous() else None,
            "results": [service.issue_payload(row, public=public) for row in page.object_list],
            "current": service.issue_payload(current, public=True) if current else None}


class PublicIssueListView(APIView):
    permission_classes = [AllowAny]
    @extend_schema(operation_id="catalog_recommendation_issues_list", responses=PolymorphicProxySerializer(
        component_name="RecommendationIssueListing", serializers=[RecommendationIssueCollectionSerializer, PublicEditorialDirectorySerializer], resource_type_field_name=None),
        parameters=[OpenApiParameter(key, type=str) for key in ("view", "q", "topic", "kind", "curator", "year_from", "year_to", "sort", "page", "page_size")])
    def get(self, request):
        if request.query_params.get("view") == "directory":
            from catalog.services.public_editorial import public_directory
            return Response(public_directory(request.query_params))
        return Response(collection(request, service.published_issues(), public=True))


class PublicIssueDetailView(APIView):
    permission_classes = [AllowAny]
    @extend_schema(responses=RecommendationIssueSerializer)
    def get(self, request, slug):
        from catalog.services.public_editorial import article_context
        issue = get_object_or_404(service.published_issues(), slug=slug)
        return Response(article_context(issue, service.issue_payload(issue, public=True)))


from reading.research_views import PrivateResponses


class SaveIssueReadingListView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter("request_id", str, required=True), OpenApiParameter("public_revision_id", str, required=True),
        OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)], responses=SavedIssueListSerializer)
    def get(self, request, slug):
        from reading.source_follow_views import require_owner
        from reading.issue_lists import state
        require_owner(request)
        data = SaveIssueListCommandSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        return Response(state(request.user, slug, data.validated_data["public_revision_id"], data.validated_data["request_id"]))

    @extend_schema(request=SaveIssueListCommandSerializer, responses=SavedIssueListSerializer,
        parameters=[OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER, required=True)])
    def post(self, request, slug):
        from reading.source_follow_views import require_owner
        from reading.issue_lists import save
        require_owner(request)
        data = SaveIssueListCommandSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(save(request.user, slug, data.validated_data))


class EditorialErrorMixin:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        # A tab may outlive a cookie/account switch. Never apply its command as
        # the newly logged-in editor, even if both accounts can edit this issue.
        owner = request.headers.get("X-Editor-Owner")
        if owner is not None and owner != str(request.user.pk):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("登录账户已变化，请重新读取当前账户的工作。")

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
    @extend_schema(operation_id="catalog_admin_recommendation_issues_list", responses=AdminRecommendationIssueCollectionSerializer,
        parameters=[OpenApiParameter("scope", enum=["all", "mine", "unassigned", "draft", "published", "scheduled"]), OpenApiParameter("q"), OpenApiParameter("page", type=int)])
    def get(self, request):
        from catalog.services.curation_projects import visible_issues
        issues = visible_issues(request.user).select_related("active_revision", "scheduled_revision")
        if request.query_params.get("unassigned") == "1": issues = issues.filter(project__isnull=True)
        if request.query_params.get("mine") == "1": issues = issues.filter(created_by=request.user)
        upcoming = issues.filter(scheduled_revision__status="published", scheduled_for__gt=timezone.now())
        drafts = EditorialRevision.objects.filter(target_type="recommendation_issue", target_id=OuterRef("pk"), status="draft")
        from rest_framework import serializers
        scope = serializers.ChoiceField(choices=["all", "mine", "unassigned", "draft", "published", "scheduled"]).run_validation(request.query_params.get("scope", "all"))
        filtered = issues
        if scope == "mine": filtered = filtered.filter(created_by=request.user)
        elif scope == "unassigned": filtered = filtered.filter(project__isnull=True)
        elif scope == "draft": filtered = filtered.filter(Exists(drafts))
        elif scope == "published": filtered = filtered.filter(pk__in=service.published_issues().values("pk"))
        elif scope == "scheduled": filtered = upcoming
        payload = collection(request, filtered)
        public_ids = set(str(value) for value in service.published_issues().filter(pk__in=[row["id"] for row in payload["results"]]).values_list("pk", flat=True))
        for item in payload["results"]: item["is_public"] = str(item["id"]) in public_ids
        # Dashboard metrics describe the inventory, independently of a search
        # or page. A published issue can also have a draft or a future revision.
        payload["summary"] = {"total": issues.count(), "published": service.published_issues().filter(pk__in=issues.values("pk")).count(),
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
    @extend_schema(responses=RecommendationIssueSerializer, parameters=[OpenApiParameter("revision", type=str), OpenApiParameter("request_id", type=str)])
    def get(self, request, issue_id):
        from catalog.services.shared_curation import identifier
        from rest_framework.exceptions import ValidationError
        issue = get_object_or_404(RecommendationIssue, pk=issue_id)
        if request.query_params.get("revision") and request.query_params.get("request_id"):
            raise ValidationError("请选择历史版本或保存回执之一。")
        revision = get_object_or_404(EditorialRevision, pk=identifier(request.query_params["revision"]), target_type="recommendation_issue", target_id=issue.pk) if request.query_params.get("revision") else None
        if request.query_params.get("request_id"):
            issue._save_receipt = service.issue_save_receipt(issue, str(identifier(request.query_params["request_id"])), request.user)
        payload = service.issue_payload(issue, revision=revision)
        if revision:
            payload.update(viewed_revision_id=str(revision.pk), viewed_revision=revision.revision)
        if request.query_params.get("request_id") and not issue._save_receipt:
            payload["request_found"] = False
        return Response(payload)
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
    http_method_names = ["get", "post", "head", "options"]

    def get_permissions(self):
        return [CanEditMetadata()] if self.request.method == "POST" else [CanAccessBackOffice()]

    @extend_schema(responses=PolymorphicProxySerializer(component_name="IssuePreviewResponse", serializers=[RecommendationIssueSerializer, IssuePublicationReviewSerializer], resource_type_field_name=None), parameters=[OpenApiParameter("review", type=bool), OpenApiParameter("edit_version", type=str)])
    def get(self, request, issue_id):
        if request.query_params.get("review") != "true":
            return super().get(request, issue_id)
        from catalog.services.issue_publication_review import review
        issue = get_object_or_404(RecommendationIssue, pk=issue_id)
        if request.query_params.get("edit_version"):
            service._check_version("recommendation_issue", issue.pk, request.query_params["edit_version"])
        return Response(review(issue, request.user))

    @extend_schema(request=RecommendationIssueSerializer, responses=RecommendationIssueSerializer)
    def post(self, request, issue_id):
        from copy import deepcopy
        from types import SimpleNamespace
        from catalog.services.shared_curation import identifier
        issue = get_object_or_404(RecommendationIssue, pk=issue_id)
        payload = service.issue_draft_payload(issue)
        retained = payload
        if request.data.get("restore_revision_id"):
            retained = get_object_or_404(EditorialRevision, pk=identifier(request.data["restore_revision_id"]), target_type="recommendation_issue", target_id=issue.pk).materialized_preview
        payload["body_blocks"] = service._body(request.data.get("body_blocks", []), retained=retained.get("body_blocks", []))
        # Re-resolve sources/media through the exact renderer used for saved
        # drafts. This projection creates no revision, item or publication.
        preview = SimpleNamespace(materialized_preview=deepcopy(payload), published_at=issue.published_at)
        return Response(service.issue_payload(issue, revision=preview))


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
        from catalog.site_commands import execute
        return Response(execute(request))


class AdminSitePublishView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]
    @extend_schema(request=SitePublishSerializer, responses=SiteContentSerializer)
    def post(self, request):
        from catalog.site_commands import execute
        return Response(execute(request, publishing=True))


class AdminSitePreviewView(AdminSiteContentView):
    http_method_names = ["get", "head", "options"]


class PublicEditorialMediaView(APIView):
    permission_classes = [AllowAny]
    def get(self, request, rendition_id):
        from django.http import Http404
        key = str(rendition_id)
        from catalog.services.public_editorial import published_media_usage
        published = published_media_usage(key)
        published = published or SiteSetting.objects.filter(key="site_config", public=True, value__home_hero_rendition_id=key).exists()
        if not published:
            from catalog.site_layout import public_cover_used
            published = public_cover_used(key)
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


class AdminIssueItemCoverView(AdminPrivateResponseMixin, IssueItemCoverView):
    permission_classes = [CanAccessBackOffice]
    admin_preview = True
