from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import ReadingPath
from catalog.reading_path_serializers import PublicReadingPathSerializer
from catalog.scholar_commands import PendingSaveStopSerializer, stop_pending_save
from catalog.services import path_route_candidates as service
from catalog.services.reading_paths import ReadingPathStructureError
from common.permissions import IsKnowledgeEditor


class RouteCandidateSummary(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    summary = serializers.CharField()
    status = serializers.CharField()
    created_at = serializers.DateTimeField()
    stages_count = serializers.IntegerField()
    items_count = serializers.IntegerField()
    method = serializers.CharField()
    gaps = serializers.ListField(child=serializers.CharField())
    edit_version = serializers.CharField()
    audience = serializers.CharField(allow_blank=True)
    learning_goal = serializers.CharField(allow_blank=True)
    review_note = serializers.CharField(allow_blank=True)


class RouteCandidateDetail(RouteCandidateSummary):
    blockers = serializers.ListField(child=serializers.CharField())
    can_adopt = serializers.BooleanField()
    candidate_version = serializers.CharField()
    preview = PublicReadingPathSerializer(allow_null=True)
    moves = serializers.ListField(child=serializers.DictField())


class RouteCandidatePage(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    results = RouteCandidateSummary(many=True)


class RouteCommandInput(serializers.Serializer):
    operation = serializers.ChoiceField(choices=["generate", "adopt", "dismiss"])
    edit_version = serializers.CharField(max_length=128)
    candidate_id = serializers.UUIDField(required=False)
    candidate_version = serializers.CharField(max_length=128, required=False)

    def validate(self, values):
        if set(self.initial_data) - set(self.fields):
            raise ValidationError("只接受本次候选与原路线版本。")
        if values["operation"] == "generate" and (values.get("candidate_id") or values.get("candidate_version")):
            raise ValidationError("重新生成不携带其他候选。")
        if values["operation"] != "generate" and not (values.get("candidate_id") and values.get("candidate_version")):
            raise ValidationError("请重新读取候选详情再决定。")
        return values


class RouteReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    path_route_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class RouteCommandResult(serializers.Serializer):
    path_id = serializers.UUIDField()
    save_receipt = RouteReceipt()


class RouteListView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(operation_id="reading_path_route_candidates_list", responses=RouteCandidatePage)
    def get(self, request, path_id):
        path = get_object_or_404(ReadingPath, pk=path_id)
        paginator = Paginator(service.candidates_for(path.pk), 12)
        page = paginator.get_page(request.query_params.get("page", 1))
        return Response(RouteCandidatePage({"count": paginator.count, "page": page.number, "total_pages": paginator.num_pages,
            "results": [service.candidate_payload(row, path, request, details=False) for row in page.object_list]}).data)

    @extend_schema(operation_id="reading_path_route_candidates_command", request=RouteCommandInput, responses=RouteCommandResult)
    def post(self, request, path_id):
        incoming = RouteCommandInput(data=request.data); incoming.is_valid(raise_exception=True)
        try:
            result = service.command(path_id, incoming.validated_data, request)
        except ReadingPathStructureError as error:
            raise ValidationError(str(error)) from error
        return Response(RouteCommandResult(result).data)


class RouteDetailView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(operation_id="reading_path_route_candidate_detail", responses=RouteCandidateDetail)
    def get(self, request, path_id, candidate_id):
        path = get_object_or_404(ReadingPath, pk=path_id)
        candidate = get_object_or_404(service.candidates_for(path_id), pk=candidate_id)
        return Response(RouteCandidateDetail(service.candidate_payload(candidate, path, request)).data)


class RouteReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    @extend_schema(responses=RouteReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("账户已变化，请重新打开路线。")
        return Response(RouteReceipt(service.route_receipt(request.user, request_id)).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=RouteReceipt)
    def post(self, request, request_id):
        return Response(RouteReceipt(stop_pending_save(request, request_id, action=service.ACTION,
            model=ReadingPath, identity="path_route_id", lock=service.LOCK)).data)
