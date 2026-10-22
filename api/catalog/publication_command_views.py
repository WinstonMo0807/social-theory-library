from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, PolymorphicProxySerializer, extend_schema
from django.core.paginator import InvalidPage
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.views import APIView

from catalog.cataloging_serializers import ApiErrorSerializer
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition
from catalog.services.publication_commands import PublicationCommandError, prepare_revision, publication_history, rollback_revision
from common.permissions import CanAccessBackOffice, CanPublishWork
from catalog.edition_file_workspace_serializers import FileImpactOutput


class PublicationReadView(AdminPrivateResponseMixin, APIView):
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        owner = request.headers.get("X-Editor-Owner")
        if owner is not None and owner != str(request.user.pk):
            raise PermissionDenied("登录账户已变化，请重新读取发布记录。")


class PublicationFieldDiffSerializer(serializers.Serializer):
    field = serializers.CharField()
    label = serializers.CharField()
    change = serializers.ChoiceField(choices=["unchanged", "added", "removed", "changed"])
    before = serializers.JSONField(allow_null=True)
    after = serializers.JSONField(allow_null=True)
    before_display = serializers.CharField(allow_blank=True)
    after_display = serializers.CharField(allow_blank=True)


class PublicationPreparationSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    active_revision_id = serializers.UUIDField(allow_null=True)
    fingerprint = serializers.CharField()
    changes = PublicationFieldDiffSerializer(many=True)
    blocking = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    background_processing = serializers.ListField(child=serializers.CharField())
    can_publish = serializers.BooleanField()


class PublicationPrepareView(PublicationReadView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=PublicationPreparationSerializer)
    def get(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        return Response(prepare_revision(edition))


class PublicationRollbackSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    request_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, allow_blank=False)
    expected_version = serializers.CharField(max_length=64, required=False)


class PublicationRollbackResultSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    source_revision_id = serializers.UUIDField()
    status = serializers.CharField()


class PublicationHistoryItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    title = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    activated_at = serializers.DateTimeField(allow_null=True)
    is_current = serializers.BooleanField()
    can_rollback = serializers.BooleanField()


class PublicationDeskRevisionSerializer(PublicationHistoryItemSerializer):
    created_at = serializers.DateTimeField()
    created_by = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    changed_fields = serializers.ListField(child=serializers.CharField())


class PublicationDeskHistorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = PublicationDeskRevisionSerializer(many=True)


class PublicationDeskSelectedSerializer(serializers.Serializer):
    revision = PublicationDeskRevisionSerializer()
    changes = PublicationFieldDiffSerializer(many=True)
    notice = serializers.CharField()


class PublicationDeskImpactSerializer(serializers.Serializer):
    title = serializers.CharField()
    detail = serializers.CharField()
    href = serializers.CharField(allow_blank=True)


class PublicationDeskEventSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    revision = serializers.IntegerField()
    action = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    processed_at = serializers.DateTimeField(allow_null=True)
    actor = serializers.CharField(allow_blank=True)
    detail = serializers.CharField()


class PublicationReviewRelationItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    label = serializers.CharField()
    change = serializers.ChoiceField(choices=["unchanged", "added", "removed"])


class PublicationReviewRelationSerializer(serializers.Serializer):
    title = serializers.CharField()
    field = serializers.CharField()
    count = serializers.IntegerField()
    items = PublicationReviewRelationItemSerializer(many=True)


class PublicationReviewCheckSerializer(serializers.Serializer):
    key = serializers.CharField()
    title = serializers.CharField()
    state = serializers.ChoiceField(choices=["notice", "ready", "warning"])
    detail = serializers.CharField()
    href = serializers.CharField()


class PublicationReviewSerializer(serializers.Serializer):
    current = PublicationDeskRevisionSerializer(allow_null=True)
    saved_at = serializers.DateTimeField()
    saved_by = serializers.CharField(allow_blank=True)
    note = serializers.CharField(allow_blank=True)
    page_count_before = serializers.IntegerField(allow_null=True)
    page_count_after = serializers.IntegerField(allow_null=True)
    relations = PublicationReviewRelationSerializer(many=True)
    checks = PublicationReviewCheckSerializer(many=True)


class PublicationDeskSerializer(serializers.Serializer):
    edition_id = serializers.UUIDField()
    work_id = serializers.UUIDField()
    version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    title = serializers.CharField()
    authors = serializers.CharField(allow_blank=True)
    publication = serializers.DictField()
    preparation = PublicationPreparationSerializer()
    history = PublicationDeskHistorySerializer()
    selected = PublicationDeskSelectedSerializer(allow_null=True)
    impacts = PublicationDeskImpactSerializer(many=True)
    dependencies = FileImpactOutput()
    events = PublicationDeskEventSerializer(many=True)
    events_limited = serializers.BooleanField()
    workbench_url = serializers.CharField()
    preview_url = serializers.CharField()
    notice = serializers.CharField()
    review = PublicationReviewSerializer(allow_null=True)


class PublicationHistoryView(PublicationReadView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(parameters=[OpenApiParameter("view", type=str, enum=["desk", "review"]), OpenApiParameter("page", type=int), OpenApiParameter("impact_page", type=int), OpenApiParameter("revision", type=str)], responses=PolymorphicProxySerializer(component_name="PublicationHistoryResponse", serializers=[PublicationHistoryItemSerializer(many=True), PublicationDeskSerializer], resource_type_field_name=None, many=False))
    def get(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        if request.query_params.get("view") not in {"desk", "review"}:
            return Response(publication_history(edition))
        from catalog.services.publication_desk import desk
        try:
            page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
            impact_page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("impact_page", 1))
            revision = serializers.UUIDField().run_validation(request.query_params["revision"]) if request.query_params.get("revision") else None
            return Response(desk(edition, page=page, impact_page=impact_page, selected_revision=revision, include_review=request.query_params.get("view") == "review"))
        except InvalidPage:
            raise ValidationError("历史页码不存在，请返回第一页。")
        except PublicationCommandError as error:
            return Response({"detail": str(error), "code": "publication.changed"}, status=409)


class PublicationRollbackView(PublicationReadView):
    permission_classes = [CanPublishWork]

    @extend_schema(request=PublicationRollbackSerializer, responses={202: PublicationRollbackResultSerializer, 409: ApiErrorSerializer})
    def post(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        serializer = PublicationRollbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        get_object_or_404(edition.catalog_revisions, pk=data["revision_id"])
        try:
            event = rollback_revision(edition, data["revision_id"], actor=request.user,
                                      idempotency_key=f"rollback:{edition.pk}:{data['request_key']}", reason=data["reason"], expected_version=data.get("expected_version", ""))
        except PublicationCommandError as error:
            return Response({"code": "publication.rollback_blocked", "detail": str(error)}, status=409)
        return Response({"event_id": str(event.pk), "source_revision_id": str(data["revision_id"]), "status": "publishing"}, status=202)
