from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_issue_views import EditorialErrorMixin
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import RecommendationIssue
from catalog.services import editorial_assistance as service
from common.permissions import CanEditMetadata
from ingestion.models import ProcessingJob


class EditorialAssistanceInput(serializers.Serializer):
    request_id = serializers.UUIDField()
    edit_version = serializers.CharField()
    operation = serializers.ChoiceField(choices=service.OPERATIONS)
    question = serializers.CharField(max_length=4000)
    references = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=40)


class EditorialAssistanceCommand(serializers.Serializer):
    action = serializers.ChoiceField(choices=["retry", "cancel", "adopt", "dismiss"])
    request_id = serializers.UUIDField(required=False)
    edit_version = serializers.CharField(required=False)
    suggestion_ids = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=40)
    edits = serializers.DictField(child=serializers.CharField(max_length=6000), required=False)
    task_token = serializers.CharField(required=False, allow_blank=True)


class EditorialSuggestionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["heading", "paragraph"])
    text = serializers.CharField()
    source_keys = serializers.ListField(child=serializers.CharField())
    gap = serializers.CharField(allow_blank=True)


class EditorialAssistanceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    issue_id = serializers.UUIDField()
    operation = serializers.ChoiceField(choices=service.OPERATIONS)
    status = serializers.CharField()
    stage = serializers.CharField()
    progress = serializers.IntegerField()
    error_code = serializers.CharField(allow_blank=True)
    error_message = serializers.CharField(allow_blank=True)
    source_available = serializers.BooleanField()
    draft_changed = serializers.BooleanField()
    can_adopt = serializers.BooleanField()
    edit_version = serializers.CharField()
    sources = serializers.ListField(child=serializers.DictField())
    suggestions = EditorialSuggestionSerializer(many=True)
    adopted_ids = serializers.ListField(child=serializers.UUIDField())
    dismissed_ids = serializers.ListField(child=serializers.UUIDField())
    question = serializers.CharField(allow_blank=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    created_by = serializers.CharField(allow_blank=True)
    task_token = serializers.CharField(allow_blank=True)
    model = serializers.DictField(allow_null=True)
    poll_after_ms = serializers.IntegerField(allow_null=True)


class EditorialAssistancePageSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = EditorialAssistanceSerializer(many=True)


class EditorialAssistanceListView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(operation_id="catalog_editorial_assistance_list", responses=EditorialAssistancePageSerializer)
    def get(self, request, issue_id):
        get_object_or_404(RecommendationIssue, pk=issue_id)
        jobs = ProcessingJob.objects.filter(job_type=service.JOB_TYPE, stats__issue_id=str(issue_id)).order_by("-created_at", "pk")
        paginator = Paginator(jobs, 24)
        page = paginator.get_page(request.query_params.get("page", 1))
        return Response({"count": paginator.count, "page": page.number, "total_pages": paginator.num_pages,
                         "results": [service.assistance_payload(job, request.user) for job in page.object_list]})

    @extend_schema(operation_id="catalog_editorial_assistance_create", request=EditorialAssistanceInput, responses={202: EditorialAssistanceSerializer})
    def post(self, request, issue_id):
        EditorialAssistanceInput(data=request.data).is_valid(raise_exception=True)
        return Response(service.assistance_payload(service.request_assistance(issue_id, request.data, request.user), request.user), status=202)


class EditorialAssistanceDetailView(EditorialErrorMixin, AdminPrivateResponseMixin, APIView):
    permission_classes = [CanEditMetadata]

    @extend_schema(operation_id="catalog_editorial_assistance_retrieve", responses=EditorialAssistanceSerializer)
    def get(self, request, issue_id, job_id):
        job = get_object_or_404(ProcessingJob, pk=job_id, job_type=service.JOB_TYPE, stats__issue_id=str(issue_id))
        return Response(service.assistance_payload(job, request.user))

    @extend_schema(operation_id="catalog_editorial_assistance_command", request=EditorialAssistanceCommand, responses=EditorialAssistanceSerializer)
    def post(self, request, issue_id, job_id):
        get_object_or_404(ProcessingJob, pk=job_id, job_type=service.JOB_TYPE, stats__issue_id=str(issue_id))
        EditorialAssistanceCommand(data=request.data).is_valid(raise_exception=True)
        return Response(service.assistance_payload(service.assistance_action(job_id, request.data, request.user), request.user))
