from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from common.permissions import CanRunBackup
from .backup_checks import check_state, queue_check
from .models import BackupJob


class BackupCheckInputSerializer(serializers.Serializer):
    operation = serializers.ChoiceField(choices=['verify', 'restore_rehearsal'])
    expected_checksum = serializers.RegexField(r'^[0-9a-f]{64}$')
    request_key = serializers.UUIDField()
    confirm_isolated = serializers.BooleanField(default=False)

    def validate(self, data):
        if data['operation'] == 'restore_rehearsal' and not data['confirm_isolated']:
            raise serializers.ValidationError('请明确确认在新的空白隔离测试库中恢复。')
        return data


class BackupCheckRecordSerializer(serializers.Serializer):
    operation = serializers.CharField()
    request_key = serializers.UUIDField()
    status = serializers.ChoiceField(choices=['queued', 'running', 'completed', 'failed'])
    requested_at = serializers.DateTimeField()
    started_at = serializers.DateTimeField(allow_null=True)
    checked_at = serializers.DateTimeField(allow_null=True)
    archive_checksum = serializers.CharField()
    error_message = serializers.CharField(allow_blank=True)
    result = serializers.JSONField()


class BackupCheckHistorySerializer(serializers.Serializer):
    count = serializers.IntegerField()
    page = serializers.IntegerField()
    next_page = serializers.IntegerField(allow_null=True)
    previous_page = serializers.IntegerField(allow_null=True)
    results = BackupCheckRecordSerializer(many=True)


class BackupCheckStateSerializer(serializers.Serializer):
    backup_id = serializers.UUIDField()
    verification = BackupCheckRecordSerializer(allow_null=True)
    rehearsal = BackupCheckRecordSerializer(allow_null=True)
    history = BackupCheckHistorySerializer()
    replay = serializers.BooleanField()


class BackupCheckView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRunBackup]

    @extend_schema(parameters=[OpenApiParameter('page', int)], responses=BackupCheckStateSerializer)
    def get(self, request, pk):
        page = serializers.IntegerField(min_value=1).run_validation(request.query_params.get('page', 1))
        return Response(check_state(get_object_or_404(BackupJob, pk=pk), page))

    @extend_schema(request=BackupCheckInputSerializer, responses={200: BackupCheckStateSerializer, 202: BackupCheckStateSerializer})
    def post(self, request, pk):
        job = get_object_or_404(BackupJob, pk=pk)
        serializer = BackupCheckInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = queue_check(job.pk, request.user, serializer.validated_data)
        return Response(result, status=200 if result['replay'] else 202)
