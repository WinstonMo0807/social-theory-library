"""Private preview routes, separate from report mutations and original downloads."""
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import document_preview
from .models import CitationAudit
from .research_views import PrivateResponses


class PreviewCommand(serializers.Serializer):
    action = serializers.ChoiceField(choices=["generate", "cancel"])
    request_id = serializers.UUIDField()
    expected_preview_revision = serializers.IntegerField(min_value=0)
    source_generation = serializers.IntegerField(min_value=1)


class PreviewStatus(serializers.Serializer):
    audit_id = serializers.UUIDField(read_only=True)
    audit_revision = serializers.IntegerField(read_only=True)
    content_hash = serializers.CharField(read_only=True)
    source_generation = serializers.IntegerField(read_only=True)
    manuscript_revision = serializers.IntegerField(read_only=True)
    preview_revision = serializers.IntegerField(read_only=True)
    preview_generation = serializers.IntegerField(read_only=True)
    status = serializers.CharField(read_only=True)
    enabled = serializers.BooleanField(read_only=True)
    page_count = serializers.IntegerField(read_only=True, allow_null=True)
    converter_version = serializers.CharField(read_only=True, allow_null=True)
    fonts_version = serializers.CharField(read_only=True, allow_null=True)
    poll_after_ms = serializers.IntegerField(read_only=True, allow_null=True)
    notice = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True, allow_blank=True)


class CitationPreviewView(PrivateResponses, APIView):
    permission_classes = [IsAuthenticated]
    purpose = "manuscript"

    def record(self, user, pk):
        record = CitationAudit.objects.filter(user=user, pk=pk, purpose=self.purpose).defer("original_ciphertext", "preview_ciphertext").first()
        if record is None:
            raise NotFound("私人稿件不存在或不可访问。")
        return record

    @extend_schema(parameters=[OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER)], responses=PreviewStatus)
    def get(self, request, pk):
        return Response(document_preview.status(self.record(request.user, pk)))

    @extend_schema(parameters=[OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER)], request=PreviewCommand, responses={202: PreviewStatus})
    def post(self, request, pk):
        schema = PreviewCommand(data=request.data)
        schema.is_valid(raise_exception=True)
        record = document_preview.command(request.user, pk, self.purpose, schema.validated_data)
        record.refresh_from_db(fields=["preview_state", "generation", "revision"])
        return Response(document_preview.status(record), status=202)


class CitationPreviewFileView(CitationPreviewView):
    @extend_schema(parameters=[OpenApiParameter("generation", int, required=True), OpenApiParameter("X-Reader-Owner", str, location=OpenApiParameter.HEADER)], responses={(200, "application/pdf"): OpenApiTypes.BINARY})
    def get(self, request, pk):
        schema = serializers.IntegerField(min_value=1)
        generation = schema.run_validation(request.query_params.get("generation"))
        record = self.record(request.user, pk)
        response = HttpResponse(document_preview.document(record, generation), content_type="application/pdf")
        response["Content-Disposition"] = 'inline; filename="manuscript-preview.pdf"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    # File route is read-only even though it shares object lookup with the status route.
    http_method_names = ["get", "head", "options"]
