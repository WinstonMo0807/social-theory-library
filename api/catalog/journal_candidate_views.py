from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiTypes
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanEditMetadata
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Edition
from catalog.services.document_outline import OutlineConflict
from catalog.services.journal_candidates import directory
from catalog.workspace_receipt_views import actor_for


class JournalCandidateQuery(serializers.Serializer):
    asset_id = serializers.UUIDField(required=False)
    page = serializers.IntegerField(min_value=1, max_value=400, default=1)


class JournalContentsCandidatesView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(parameters=[JournalCandidateQuery], responses=OpenApiTypes.OBJECT)
    def get(self, request, edition_id):
        actor = actor_for(request)
        query = JournalCandidateQuery(data=request.query_params); query.is_valid(raise_exception=True)
        edition = get_object_or_404(Edition.objects.select_related("work"), pk=edition_id)
        try:
            return Response(directory(edition, actor, **query.validated_data))
        except OutlineConflict as error:
            return Response({"detail":str(error), "code":"journal_source_changed"}, status=409)
