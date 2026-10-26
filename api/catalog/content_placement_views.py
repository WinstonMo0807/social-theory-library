"""Protected editing, exact-revision preview, and public placement reads."""
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Case, When, Value, IntegerField, Exists, OuterRef, Subquery, F, Count
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from catalog.media_views import PublicCoverMediaSerializer
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition, KnowledgeNode, DocumentType, Contribution, WorkTopicRelation
from catalog.services import content_placements as service
from catalog.services import shared_curation
from common.permissions import CanEditMetadata, IsKnowledgeEditor


class PlacementTargetSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["work", "edition", "node", "span", "scholar", "issue"])
    id = serializers.UUIDField()
    edition_id = serializers.UUIDField(required=False)
    document_revision_id = serializers.UUIDField(required=False)


class PlacementSerializer(serializers.Serializer):
    id = serializers.UUIDField(required=False)
    area = serializers.CharField(max_length=80, required=False)
    group = serializers.CharField(max_length=240, allow_blank=True, required=False)
    position = serializers.IntegerField(min_value=0, required=False)
    target = PlacementTargetSerializer()
    reason = serializers.CharField(max_length=6000, allow_blank=True, required=False)
    local_text = serializers.CharField(max_length=6000, allow_blank=True, required=False)
    reading_target = serializers.DictField(required=False, allow_null=True)
    concept_usage = serializers.DictField(required=False, allow_null=True)
    internal_goal = serializers.CharField(max_length=1000, allow_blank=True, required=False)
    display_fields = serializers.ListField(child=serializers.ChoiceField(choices=["authors", "year", "type", "tags"]), max_length=4, required=False)
    reason_format = serializers.DictField(required=False, allow_null=True)


class PlacementGroupSerializer(serializers.Serializer):
    area = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=240, allow_blank=True)


class PlacementCommandSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=service.ACTIONS)
    request_id = serializers.UUIDField()
    expected_revision = serializers.CharField(max_length=80)
    items = PlacementSerializer(many=True, max_length=100, required=False)
    item = PlacementSerializer(required=False)
    item_id = serializers.UUIDField(required=False)
    position = serializers.IntegerField(min_value=0, max_value=100, required=False)
    area = serializers.CharField(max_length=80, required=False)
    group = serializers.CharField(max_length=240, allow_blank=True, required=False)
    patch = serializers.DictField(required=False)
    revision_id = serializers.UUIDField(required=False)
    confirmed_only = serializers.BooleanField(required=False)
    groups = PlacementGroupSerializer(many=True, max_length=100, required=False)


class PlacementReaderTargetSerializer(serializers.Serializer):
    asset_id = serializers.UUIDField()
    document_revision_id = serializers.UUIDField()
    pdf_page = serializers.IntegerField(min_value=1)


class PlacementUsageAuthorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()


class PlacementSourceSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["work", "edition", "node", "span", "scholar", "issue"])
    id = serializers.UUIDField()
    title = serializers.CharField(allow_blank=True)
    public_eligible = serializers.BooleanField()
    work_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)
    edition_label = serializers.CharField(required=False, allow_blank=True)
    reader_url = serializers.CharField(required=False, allow_blank=True)
    work_url = serializers.CharField(required=False, allow_blank=True)
    edit_url = serializers.CharField(required=False, allow_blank=True)
    source_type = serializers.CharField(required=False)
    text = serializers.CharField(required=False)
    context_before = serializers.CharField(required=False, allow_blank=True)
    context_after = serializers.CharField(required=False, allow_blank=True)
    work_title = serializers.CharField(required=False, allow_blank=True)
    asset_id = serializers.UUIDField(required=False)
    page_start = serializers.IntegerField(required=False, min_value=1)
    page_end = serializers.IntegerField(required=False, min_value=1)
    printed_label = serializers.CharField(required=False, allow_blank=True)
    document_revision_id = serializers.UUIDField(required=False, allow_null=True)
    reader_target = PlacementReaderTargetSerializer(required=False)
    usage_author = PlacementUsageAuthorSerializer(required=False, allow_null=True)
    image_url = serializers.CharField(required=False, allow_blank=True)
    publication_year = serializers.IntegerField(required=False, allow_null=True)
    authors = serializers.ListField(child=serializers.DictField(), required=False)
    document_type = serializers.CharField(required=False, allow_blank=True)
    language = serializers.CharField(required=False, allow_blank=True)
    page_count = serializers.IntegerField(required=False, allow_null=True)
    publisher = serializers.CharField(required=False, allow_blank=True)
    tags = serializers.ListField(child=serializers.CharField(), required=False)
    href = serializers.CharField(required=False, allow_blank=True)
    summary = serializers.CharField(required=False, allow_blank=True)


class PlacementResultItemSerializer(PlacementSerializer):
    id = serializers.UUIDField()
    source = PlacementSourceSerializer(allow_null=True)
    reading_target = PlacementReaderTargetSerializer(required=False, allow_null=True)


class PlacementSourceChoiceSerializer(serializers.Serializer):
    target = PlacementTargetSerializer()
    source = PlacementSourceSerializer()
    version_count = serializers.IntegerField(min_value=1, required=False)


class PlacementSourcesPageSerializer(serializers.Serializer):
    topics = serializers.ListField(child=serializers.CharField(), required=False)
    languages = serializers.ListField(child=serializers.CharField(), required=False)
    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    results = PlacementSourceChoiceSerializer(many=True)


class PlacementHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    base_revision = serializers.IntegerField()
    status = serializers.ChoiceField(choices=["draft", "published", "superseded"])
    created_at = serializers.DateTimeField()
    published_at = serializers.DateTimeField(allow_null=True)
    item_count = serializers.IntegerField()
    withdrawn = serializers.BooleanField()


class PlacementHistoryPageSerializer(PlacementSourcesPageSerializer):
    results = PlacementHistoryItemSerializer(many=True)


class PublicConceptAuthorSerializer(PlacementUsageAuthorSerializer):
    original_name = serializers.CharField(allow_blank=True)
    birth_year = serializers.IntegerField(allow_null=True)
    death_year = serializers.IntegerField(allow_null=True)
    portrait_url = serializers.CharField(allow_blank=True)
    portrait_media = PublicCoverMediaSerializer(allow_null=True, required=False)
    scholar_slug = serializers.CharField(allow_blank=True)


class PublicConceptUsageSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    term = serializers.CharField()
    language = serializers.CharField(allow_blank=True)
    usage_type = serializers.CharField()
    interpretation = serializers.CharField(allow_blank=True)
    attribution_note = serializers.CharField()
    title = serializers.CharField(allow_blank=True)
    explanatory_object = serializers.CharField(allow_blank=True)
    period = serializers.CharField(allow_blank=True)
    context = serializers.CharField(allow_blank=True)
    author = PublicConceptAuthorSerializer(allow_null=True)
    source = PlacementSourceSerializer()


class PublicConceptDetailSerializer(serializers.Serializer):
    configured = serializers.BooleanField()
    revision_id = serializers.UUIDField(allow_null=True)
    usages = PublicConceptUsageSerializer(many=True)
    unavailable_usage_count = serializers.IntegerField(min_value=0)


class PlacementReadSerializer(serializers.Serializer):
    item_states = serializers.DictField(child=serializers.ChoiceField(choices=["published", "saved_unpublished"]), required=False)
    schema_version = serializers.IntegerField()
    page_type = serializers.CharField()
    page_id = serializers.UUIDField()
    revision_id = serializers.UUIDField(allow_null=True)
    configured = serializers.BooleanField()
    items = PlacementResultItemSerializer(many=True)
    groups = PlacementGroupSerializer(many=True)
    withdrawn = serializers.BooleanField()
    expected_revision = serializers.CharField(required=False)
    is_current_revision = serializers.BooleanField(required=False)
    published_revision_id = serializers.UUIDField(required=False, allow_null=True)
    has_unpublished_changes = serializers.BooleanField(required=False)
    source_problems = serializers.ListField(child=serializers.DictField(), required=False)
    publication_blockers = serializers.ListField(child=serializers.DictField(), required=False)
    state = serializers.CharField(required=False)
    can_publish = serializers.BooleanField(required=False)
    can_withdraw = serializers.BooleanField(required=False)
    can_publish_confirmed = serializers.BooleanField(required=False)
    confirmed_publication_blockers = serializers.ListField(child=serializers.DictField(), required=False)
    impact = serializers.CharField(required=False)
    title = serializers.CharField(required=False)
    public_url = serializers.CharField(required=False)
    edit_url = serializers.CharField(required=False)
    replayed = serializers.BooleanField(required=False)
    applied_revision_id = serializers.UUIDField(required=False)
    public_detail = PublicConceptDetailSerializer(required=False)


def _page(request, rows, serialize):
    paginator = Paginator(rows, 24)
    page = paginator.get_page(request.query_params.get("page", 1))
    def url(number):
        params = request.query_params.copy()
        params["page"] = number
        return f"{request.path}?{params.urlencode()}"
    return {"count": paginator.count, "next": url(page.next_page_number()) if page.has_next() else None,
            "previous": url(page.previous_page_number()) if page.has_previous() else None,
            "results": [serialize(row) for row in page.object_list]}


class PlacementSourceQuerySerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["work", "edition", "node", "span", "scholar", "issue"], default="edition")
    q = serializers.CharField(max_length=500, allow_blank=True, required=False)
    work_id = serializers.UUIDField(required=False)
    edition_id = serializers.UUIDField(required=False)
    document_type = serializers.ChoiceField(choices=DocumentType.choices, required=False)
    topic = serializers.CharField(max_length=240, allow_blank=True, required=False)
    language = serializers.CharField(max_length=32, allow_blank=True, required=False)
    readable = serializers.ChoiceField(choices=["yes", "no"], required=False)
    sort = serializers.ChoiceField(choices=["relevance", "title", "newest", "oldest"], default="relevance")
    page = serializers.IntegerField(min_value=1, default=1)
    group_by = serializers.ChoiceField(choices=["edition", "work"], default="edition")

    def validate(self, values):
        if values["group_by"] == "work" and values["type"] not in {"work", "edition"}:
            raise serializers.ValidationError("只有馆藏作品和出版版本支持按作品归并。")
        return values


def placement_source_rows(params):
    """Search canonical catalog records; choose an exact edition before adding."""
    from catalog.services.publication_eligibility import public_editions, current_retrieval_source_q
    rows = Edition.objects.select_related("work", "active_catalog_revision", "active_catalog_revision__reader_asset")
    query = params.get("q", "").strip()
    if query:
        authors = Contribution.objects.filter(edition_id=OuterRef("pk"), approved=True).filter(
            Q(person__preferred_name__icontains=query) | Q(person__original_name__icontains=query))
        rows = rows.annotate(matches_author=Exists(authors)).filter(
            Q(work__title__icontains=query) | Q(work__original_title__icontains=query) | Q(isbn__icontains=query) | Q(doi__icontains=query) | Q(matches_author=True))
    for parameter, field in (("work_id", "work_id"), ("edition_id", "id"), ("document_type", "work__document_type"), ("language", "work__language")):
        if params.get(parameter):
            rows = rows.filter(**{field: params[parameter]})
    if params.get("topic"):
        topics = WorkTopicRelation.objects.filter(work_id=OuterRef("work_id"), review_status="approved", topic__name__icontains=params["topic"])
        rows = rows.annotate(matches_topic=Exists(topics)).filter(matches_topic=True)
    if params.get("readable"):
        readable = public_editions().filter(current_retrieval_source_q(asset_prefix="active_catalog_revision__reader_asset", access_statuses=("public", "inherit")))
        rows = rows.annotate(is_readable=Exists(readable.filter(pk=OuterRef("pk")))).filter(is_readable=params["readable"] == "yes")
    order = params.get("sort", "relevance")
    if order == "relevance" and query:
        rows = rows.annotate(match_rank=Case(When(work__title__iexact=query, then=Value(0)), When(work__title__istartswith=query, then=Value(1)), default=Value(2), output_field=IntegerField()))
        return rows.order_by("match_rank", "work__title", F("publication_year").asc(nulls_last=True), "pk")
    year = F("publication_year").desc(nulls_last=True) if order == "newest" else F("publication_year").asc(nulls_last=True)
    return rows.order_by(*([year, "work__title"] if order in {"newest", "oldest"} else ["work__title", year]), "pk")


def grouped_placement_source_rows(params):
    """Group by the real Work identity before pagination, never by title."""
    rows = placement_source_rows(params)
    representative = rows.filter(work_id=OuterRef("work_id")).values("pk")[:1]
    versions = Edition.objects.filter(work_id=OuterRef("work_id")).order_by().values("work_id").annotate(total=Count("pk"))
    return rows.annotate(representative_id=Subquery(representative), version_count=Subquery(versions.values("total")[:1])).filter(pk=F("representative_id"))


class PlacementSourcesView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(parameters=[PlacementSourceQuerySerializer], responses=PlacementSourcesPageSerializer)
    def get(self, request):
        incoming = PlacementSourceQuerySerializer(data=request.query_params)
        incoming.is_valid(raise_exception=True)
        params = incoming.validated_data
        kind = params["type"]
        query = params.get("q", "").strip()
        if kind in {"scholar", "issue"}:
            from catalog.site_layout import source_rows
            return Response(_page(request, source_rows(kind, query), lambda row: dict(zip(("target", "source"), service._source({"type": kind, "id": str(row.pk)})))))
        if kind in {"work", "edition"}:
            grouped = params["group_by"] == "work"
            rows = grouped_placement_source_rows(params) if grouped else placement_source_rows(params)
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.work_id if kind == "work" else row.pk), "edition_id": str(row.pk)})
                return {"target": reference, "source": source, **({"version_count": row.version_count} if grouped else {})}
            page = _page(request, rows, serialize)
            if grouped:
                page["topics"] = list(WorkTopicRelation.objects.filter(review_status="approved", work__editions__isnull=False).order_by("topic__name").values_list("topic__name", flat=True).distinct())
                page["languages"] = list(Edition.objects.exclude(work__language="").order_by("work__language").values_list("work__language", flat=True).distinct())
            return Response(page)
        if kind == "node":
            rows = KnowledgeNode.objects.all()
            if query:
                rows = rows.filter(Q(canonical_name_zh__icontains=query) | Q(canonical_name_en__icontains=query))
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.pk)})
                return {"target": reference, "source": source}
            return Response(_page(request, rows.order_by("canonical_name_zh", "pk"), serialize))
        if kind == "span":
            rows = shared_curation.sources("span").filter(is_stale=False)
            if query:
                rows = rows.filter(original_text__icontains=query)
            for parameter, field in (("work_id", "page__asset__edition__work_id"), ("edition_id", "page__asset__edition_id")):
                if request.query_params.get(parameter):
                    rows = rows.filter(**{field: shared_curation.identifier(request.query_params[parameter])})
            def serialize(row):
                reference, source = service._source({"type": kind, "id": str(row.pk)})
                return {"target": reference, "source": source}
            return Response(_page(request, rows.order_by("page__asset_id", "page__index", "start_offset", "pk"), serialize))
        return Response({"detail": "未知馆藏选择类型。"}, status=400)


class AdminPlacementView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(responses=PlacementReadSerializer)
    def get(self, request, page_type, page_id):
        return Response(service.read(page_type, page_id, actor=request.user, revision_id=request.query_params.get("revision")))

    @extend_schema(request=PlacementCommandSerializer, responses=PlacementReadSerializer)
    def post(self, request, page_type, page_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取编排内容。")
        incoming = PlacementCommandSerializer(data=request.data)
        incoming.is_valid(raise_exception=True)
        # Keep the original JSON: the service rejects source/body fields that
        # DRF would otherwise silently discard as unknown serializer fields.
        return Response(service.command(page_type, page_id, request.data, request.user))


class PlacementReceiptSerializer(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    revision_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    page_type = serializers.CharField()
    page_id = serializers.UUIDField()
    exists = serializers.BooleanField()


class PlacementCancelSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["cancel_pending"])


class PlacementReceiptView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @staticmethod
    def response(receipt, page_type, page_id):
        return Response(PlacementReceiptSerializer({"actor_id": str(receipt.actor_id), "request_id": receipt.request_id,
            "revision_id": receipt.after.get("revision_id"), "page_type": page_type, "page_id": page_id,
            "state": "cancelled" if receipt.after.get("operation") == "cancelled" else "applied",
            "exists": service.PAGES[page_type][0].objects.filter(pk=page_id).exists()}).data)

    @extend_schema(responses=PlacementReceiptSerializer)
    def get(self, request, page_type, page_id, request_id):
        from ingestion.models import AuditEvent
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取原请求。")
        service.authorize(request.user, page_type)
        receipt = get_object_or_404(AuditEvent, action="content_placement.command", object_type=service.KIND,
            object_id=str(service.target_id(page_type, page_id)), request_id=str(request_id), actor=request.user)
        return self.response(receipt, page_type, page_id)

    @extend_schema(request=PlacementCancelSerializer, responses=PlacementReceiptSerializer)
    @transaction.atomic
    def post(self, request, page_type, page_id, request_id):
        from accounts.models import User
        from ingestion.models import AuditEvent
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取原请求。")
        if not isinstance(request.data, dict) or request.data != {"action": "cancel_pending"}:
            return Response({"detail": "只接受停止未确认请求。"}, status=400)
        # Share the exact actor lock with command(): either the original finishes,
        # or this durable receipt prevents it from writing if it arrives later.
        actor = get_object_or_404(User.objects.select_for_update(), pk=request.user.pk, is_active=True)
        if actor.token_version != request.user.token_version:
            raise PermissionDenied("账户会话已变化，请重新核对编辑身份。")
        service.authorize(actor, page_type)
        key = str(service.target_id(page_type, page_id))
        receipt = AuditEvent.objects.filter(action="content_placement.command", object_type=service.KIND,
            object_id=key, request_id=str(request_id), actor=actor).first()
        if receipt is None:
            service.parent_object(page_type, page_id, lock=True, actor=actor)
            receipt = AuditEvent.objects.create(actor=actor, action="content_placement.command", object_type=service.KIND,
                object_id=key, request_id=str(request_id), before={},
                after={"operation": "cancelled", "revision_id": None, "fingerprint": ""})
        return self.response(receipt, page_type, page_id)


class PlacementHistoryView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor | CanEditMetadata]

    @extend_schema(responses=PlacementHistoryPageSerializer)
    def get(self, request, page_type, page_id):
        service.authorize(request.user, page_type)
        parent = service.parent_object(page_type, page_id, actor=request.user)
        rows = service.revisions(page_type, parent.pk)
        return Response(_page(request, rows, lambda row: {
            "id": str(row.pk), "revision": row.revision, "base_revision": row.base_revision,
            "status": row.status, "created_at": row.created_at, "published_at": row.published_at,
            "item_count": len(row.materialized_preview.get("items", [])),
            "withdrawn": row.materialized_preview.get("withdrawn", False),
        }))


class PublicPlacementView(EditorialErrorMixin, APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PlacementReadSerializer)
    def get(self, request, page_type, page_id):
        # Anonymous requests cannot select a draft or a historical publication.
        return Response(service.read(page_type, page_id, public=True))
