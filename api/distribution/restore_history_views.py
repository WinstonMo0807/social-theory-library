from django.core import signing
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import CanRunBackup
from catalog.editorial_read import AdminPrivateResponseMixin
from .models import BackupJob
from .restore_history import NAME, report_window
from .storage_workspace import StorageConflict
from .storage_views import RestoreReport

CURSOR_SALT = 'stl-restore-history-cursor-v1'


class RestoreHistoryQuery(serializers.Serializer):
    cursor = serializers.CharField(max_length=2048, required=False)
    backup_id = serializers.UUIDField(required=False)

    def to_internal_value(self, data):
        if set(data) - set(self.fields) or any(len(data.getlist(key)) != 1 for key in data):
            raise serializers.ValidationError('恢复记录筛选包含未知或重复参数。')
        return super().to_internal_value(data)


class RestoreHistoryRecord(RestoreReport):
    id = serializers.CharField()


class RestoreHistoryPage(serializers.Serializer):
    as_of = serializers.DateTimeField()
    source_status = serializers.ChoiceField(choices=['available', 'missing', 'unavailable'])
    candidate_count = serializers.IntegerField()
    inspected_count = serializers.IntegerField()
    unverified_count = serializers.IntegerField()
    filtered_count = serializers.IntegerField()
    directory_errors = serializers.IntegerField()
    results = RestoreHistoryRecord(many=True)
    next_cursor = serializers.CharField(allow_blank=True)
    notice = serializers.CharField()


class RestoreHistoryView(AdminPrivateResponseMixin, APIView):
    permission_classes = [CanRunBackup]

    @extend_schema(parameters=[RestoreHistoryQuery], responses=RestoreHistoryPage)
    def get(self, request):
        query = RestoreHistoryQuery(data=request.query_params)
        query.is_valid(raise_exception=True)
        values = query.validated_data
        checksum, backup_id = None, str(values.get('backup_id') or '')
        if backup_id:
            backup = BackupJob.objects.filter(pk=backup_id).first()
            if not backup:
                raise NotFound('备份记录不存在。')
            if not backup.checksum:
                raise serializers.ValidationError('此备份尚无归档身份，不能匹配恢复报告。')
            checksum = backup.checksum
        after, as_of, source_identity = '', timezone.now(), ''
        if values.get('cursor'):
            try:
                cursor = signing.loads(values['cursor'], salt=CURSOR_SALT, max_age=86400)
                if not isinstance(cursor, dict) or cursor.get('owner') != str(request.user.pk) or cursor.get('backup_id') != backup_id or cursor.get('checksum') != checksum:
                    raise ValueError('Cursor scope differs')
                after, as_of, source_identity = cursor['after'], parse_datetime(cursor['as_of']), cursor['source_identity']
                if not isinstance(after, str) or not NAME.fullmatch(after) or not as_of or timezone.is_naive(as_of) or as_of > timezone.now():
                    raise ValueError('Invalid cursor')
            except (signing.BadSignature, ValueError, TypeError, KeyError) as error:
                raise serializers.ValidationError('分页记录已失效，请返回最新记录重新读取。') from error
        page = report_window(after=after, as_of=as_of, checksum=checksum)
        if source_identity and page['source_status'] == 'available' and page['source_identity'] != source_identity:
            raise StorageConflict('备份挂载或恢复记录目录已变化，请重新读取最新记录。')
        page['next_cursor'] = signing.dumps({'owner': str(request.user.pk), 'backup_id': backup_id, 'checksum': checksum,
            'after': page['next_after'], 'as_of': as_of.isoformat(), 'source_identity': page['source_identity']}, salt=CURSOR_SALT) if page['next_after'] else ''
        return Response(RestoreHistoryPage(page).data)
