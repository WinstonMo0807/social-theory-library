from uuid import UUID

from django.core.paginator import Paginator, EmptyPage
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiParameter
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import TheoryTimelineEvent, TimelineMergeRecord
from catalog.scholar_commands import PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.services.timeline_merge import merge_preview, merge_events, rollback_preview, rollback_merge
from catalog.services.editorial_revision import EditorialRevisionError
from common.permissions import IsKnowledgeEditor, CanMergeAuthority


class PairInput(serializers.Serializer):
    source_id = serializers.UUIDField()
    target_id = serializers.UUIDField()


class MergeInput(PairInput):
    fingerprint = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()


class RollbackInput(serializers.Serializer):
    fingerprint = serializers.RegexField(r"^[a-f0-9]{64}$")
    confirmed = serializers.BooleanField()


class MergeEventSummary(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    event_type = serializers.CharField()
    date_label = serializers.CharField()
    start_year = serializers.IntegerField(allow_null=True)
    end_year = serializers.IntegerField(allow_null=True)
    start_date = serializers.DateField(allow_null=True)
    end_date = serializers.DateField(allow_null=True)
    date_precision = serializers.CharField()
    review_status = serializers.CharField()
    source = serializers.CharField()
    description = serializers.CharField()
    editor_url = serializers.CharField()


class TimelineMergePreview(serializers.Serializer):
    source = MergeEventSummary()
    target = MergeEventSummary()
    fingerprint = serializers.CharField()
    can_merge = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())
    source_count = serializers.IntegerField()
    relation_count = serializers.IntegerField()
    placement_count = serializers.IntegerField()
    will_be_public = serializers.BooleanField()
    rule = serializers.CharField()


class TimelineRollbackState(serializers.Serializer):
    fingerprint = serializers.CharField()
    can_rollback = serializers.BooleanField()
    blockers = serializers.ListField(child=serializers.CharField())


class TimelineMergeReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    timeline_merge_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class TimelineMergeResult(serializers.ModelSerializer):
    source_title = serializers.CharField(source="source.title")
    target_title = serializers.CharField(source="target.title")
    rollback = serializers.SerializerMethodField()
    save_receipt = TimelineMergeReceipt(required=False)

    class Meta:
        model = TimelineMergeRecord
        fields = ("id", "source", "target", "source_title", "target_title", "created_at", "rolled_back_at", "rollback", "save_receipt")

    @extend_schema_field(TimelineRollbackState)
    def get_rollback(self, record):
        return rollback_preview(record)


class TimelineMergeHistoryRow(TimelineMergeResult):
    class Meta(TimelineMergeResult.Meta):
        fields = ("id", "source", "target", "source_title", "target_title", "created_at", "rolled_back_at")


class MergeRows(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    pages = serializers.IntegerField()
    results = TimelineMergeHistoryRow(many=True)


class MergePrivateView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsKnowledgeEditor]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("账户已变化，请重新读取事件归并。")


class TimelineMergePreviewView(MergePrivateView):
    @extend_schema(request=PairInput, responses=TimelineMergePreview)
    def post(self, request):
        data = PairInput(data=request.data)
        data.is_valid(raise_exception=True)
        source = get_object_or_404(TheoryTimelineEvent, pk=data.validated_data["source_id"])
        target = get_object_or_404(TheoryTimelineEvent, pk=data.validated_data["target_id"])
        return Response(TimelineMergePreview(merge_preview(source, target)).data)


class TimelineMergeView(MergePrivateView):
    permission_classes = [CanMergeAuthority]

    @extend_schema(request=MergeInput, responses=TimelineMergeResult)
    def post(self, request):
        data = MergeInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            request_id = UUID(request.headers.get("Idempotency-Key", ""))
        except (ValueError, TypeError):
            raise ValidationError("归并需要固定请求编号，请重新核对原请求。") from None
        try:
            record = merge_events(actor=request.user, request_id=request_id, **data.validated_data)
        except EditorialRevisionError as error:
            raise ValidationError(str(error)) from error
        result = TimelineMergeResult(record).data
        result["save_receipt"] = command_receipt(request.user, request_id, action="timeline_merge", model=TimelineMergeRecord, identity="timeline_merge_id")
        return Response(result)


class TimelineMergeRecordView(MergePrivateView):
    def get_permissions(self):
        return [CanMergeAuthority()] if self.request.method == "POST" else super().get_permissions()

    @extend_schema(operation_id="timeline_merge_record_read", responses=TimelineMergeResult)
    def get(self, request, pk):
        return Response(TimelineMergeResult(get_object_or_404(TimelineMergeRecord.objects.select_related("source", "target"), pk=pk)).data)

    @extend_schema(request=RollbackInput, responses=TimelineMergeResult)
    def post(self, request, pk):
        data = RollbackInput(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            record = rollback_merge(pk, actor=request.user, **data.validated_data)
        except EditorialRevisionError as error:
            raise ValidationError(str(error)) from error
        return Response(TimelineMergeResult(record).data)


class TimelineMergeHistoryView(MergePrivateView):
    @extend_schema(operation_id="timeline_merge_history_list", parameters=[OpenApiParameter("page", int)], responses=MergeRows)
    def get(self, request, pk):
        get_object_or_404(TheoryTimelineEvent, pk=pk)
        number = serializers.IntegerField(min_value=1).run_validation(request.query_params.get("page", 1))
        rows = TimelineMergeRecord.objects.filter(Q(source_id=pk) | Q(target_id=pk)).select_related("source", "target").order_by("-created_at", "pk")
        pages = Paginator(rows, 12)
        try:
            page = pages.page(number)
        except EmptyPage:
            raise ValidationError("记录页已变化，请回到第一页。") from None
        return Response(MergeRows({"count": pages.count, "page": page.number, "pages": pages.num_pages, "results": page.object_list}).data)


class TimelineMergeReceiptView(MergePrivateView):
    @extend_schema(responses=TimelineMergeReceipt)
    def get(self, request, request_id):
        return Response(TimelineMergeReceipt(command_receipt(request.user, request_id, action="timeline_merge", model=TimelineMergeRecord, identity="timeline_merge_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=TimelineMergeReceipt)
    def post(self, request, request_id):
        return Response(TimelineMergeReceipt(stop_pending_save(request, request_id, action="timeline_merge", model=TimelineMergeRecord, identity="timeline_merge_id", lock="timeline_merge_request")).data)
