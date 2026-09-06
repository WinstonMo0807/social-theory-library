from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.cataloging_serializers import ApiErrorSerializer
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition
from catalog.services.publication_commands import PublicationCommandError, prepare_revision, publication_history, rollback_revision
from common.permissions import CanAccessBackOffice, CanPublishWork


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


class PublicationPrepareView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=PublicationPreparationSerializer)
    def get(self, request, edition_id):
        edition = get_object_or_404(Edition, pk=edition_id)
        return Response(prepare_revision(edition))


class PublicationRollbackSerializer(serializers.Serializer):
    revision_id = serializers.UUIDField()
    request_key = serializers.UUIDField()
    reason = serializers.CharField(max_length=1000, allow_blank=False)


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


class PublicationHistoryView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=PublicationHistoryItemSerializer(many=True))
    def get(self, request, edition_id):
        return Response(publication_history(get_object_or_404(Edition, pk=edition_id)))


class PublicationRollbackView(AdminPrivateResponseMixin, APIView):
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
                                      idempotency_key=f"rollback:{edition.pk}:{data['request_key']}", reason=data["reason"])
        except PublicationCommandError as error:
            return Response({"code": "publication.rollback_blocked", "detail": str(error)}, status=409)
        return Response({"event_id": str(event.pk), "source_revision_id": str(data["revision_id"]), "status": "publishing"}, status=202)
