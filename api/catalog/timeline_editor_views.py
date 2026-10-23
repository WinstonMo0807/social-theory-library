from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanAccessBackOffice
from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import TheoryTimelineEvent
from catalog.scholar_commands import ScholarCommandMixin, PendingSaveStopSerializer, command_receipt, stop_pending_save
from catalog.timeline_editor import similar_timeline_events


class TimelineCommandMixin(ScholarCommandMixin):
    save_action = "timeline_editor_save"
    save_model = TheoryTimelineEvent
    save_identity = "timeline_id"
    save_salt = "stl4-timeline-editor"
    save_lock = "timeline_editor_request"
    save_label = "时间线事件"


class TimelineSaveReceipt(serializers.Serializer):
    actor_id = serializers.CharField()
    request_id = serializers.UUIDField()
    timeline_id = serializers.UUIDField(allow_null=True)
    state = serializers.ChoiceField(choices=["applied", "cancelled"])
    saved_version = serializers.CharField()
    exists = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class TimelineSaveReceiptView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(responses=TimelineSaveReceipt)
    def get(self, request, request_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("请重新核对当前编辑账户。")
        return Response(TimelineSaveReceipt(command_receipt(request.user, request_id,
            action="timeline_editor_save", model=TheoryTimelineEvent, identity="timeline_id")).data)

    @extend_schema(request=PendingSaveStopSerializer, responses=TimelineSaveReceipt)
    def post(self, request, request_id):
        return Response(TimelineSaveReceipt(stop_pending_save(request, request_id,
            action="timeline_editor_save", model=TheoryTimelineEvent, identity="timeline_id", lock="timeline_editor_request")).data)


class TimelineSimilarInput(serializers.Serializer):
    title = serializers.CharField(max_length=300, required=False, allow_blank=True)
    event_type = serializers.ChoiceField(choices=TheoryTimelineEvent.EventType.choices, required=False)
    work = serializers.UUIDField(allow_null=True, required=False)
    scholar = serializers.UUIDField(allow_null=True, required=False)
    exclude = serializers.UUIDField(allow_null=True, required=False)
    start_year = serializers.IntegerField(min_value=-32768, max_value=32767, allow_null=True, required=False)


class TimelineSimilarRow(serializers.ModelSerializer):
    class Meta:
        model = TheoryTimelineEvent
        fields = ("id", "title", "event_type", "start_year", "end_year", "date_label", "review_status")


class TimelineSimilarResult(serializers.Serializer):
    count = serializers.IntegerField()
    truncated = serializers.BooleanField()
    results = TimelineSimilarRow(many=True)


class TimelineSimilarView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanAccessBackOffice]

    @extend_schema(request=TimelineSimilarInput, responses=TimelineSimilarResult)
    def post(self, request):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk):
            raise PermissionDenied("编辑账户已变化，请重新读取事件。")
        incoming = TimelineSimilarInput(data=request.data)
        if not isinstance(request.data, dict) or set(request.data) - set(incoming.fields):
            raise ValidationError("只接受事件身份和发生年份。")
        incoming.is_valid(raise_exception=True)
        rows = similar_timeline_events(incoming.validated_data)
        count = rows.count()
        return Response(TimelineSimilarResult({"count": count, "truncated": count > 50, "results": rows[:50]}).data)
