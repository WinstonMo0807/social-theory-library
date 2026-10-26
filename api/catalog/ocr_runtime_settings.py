"""One editor for the existing OCR setting; no second runtime or credential store."""
from hashlib import sha256
import json
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from common.capabilities import capability_snapshot
from common.permissions import IsLibraryAdmin
from catalog.models import SiteSetting
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.ocr_provider import ocr_runtime_config, OCR_RUNTIME_KEY, OCR_MODEL_ID
from catalog.editorial_read import AdminPrivateResponseMixin


class OcrConfigurationConflict(APIException):
    status_code = 409
    default_detail = "OCR 配置已变化，未覆盖新配置。请重新读取并核对后保存。"


def version(config):
    return sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def editable_url(value):
    if not value:
        return True
    try:
        parsed = urlsplit(value)
        return bool(parsed.scheme in {'http', 'https'} and parsed.hostname and not parsed.username
                    and not parsed.password and not parsed.query and not parsed.fragment
                    and not any(ord(char) < 33 or char == '\\' for char in value) and parsed.port != 0)
    except ValueError:
        return False


def current_ocr_runtime():
    config = ocr_runtime_config()
    latest = ProcessingJob.objects.filter(job_type=ProcessingJob.JobType.OCR).order_by('-created_at').first()
    last_success = ProcessingJob.objects.filter(job_type=ProcessingJob.JobType.OCR, status=ProcessingJob.Status.SUCCEEDED).order_by('-finished_at').first()
    complete = bool(config['remote_url'] and config['remote_model'] and config['remote_key_configured'])
    from catalog.local_services import _origin
    return {**config, 'nas_url': _origin(config['nas_url']),
            'configuration_version': version(config),
            'remote_url': config['remote_url'] if editable_url(config['remote_url']) else '',
            'remote_url_redacted': not editable_url(config['remote_url']),
            'nas_configured': bool(config['nas_url']), 'remote_configured': complete, 'remote_fallback_available': complete,
            'effective_configuration': {'mode': config['mode'], 'nas_url_configured': bool(config['nas_url']),
                                        'remote_fallback_available': complete, 'loads_settings_per_job': True},
            'restart_required': False, 'last_success_at': last_success.finished_at if last_success else None,
            'last_job': {'id': str(latest.id), 'status': latest.status, 'engine': latest.engine,
                         'settings_version': latest.settings_version, 'attempt': latest.attempt,
                         'created_at': latest.created_at, 'finished_at': latest.finished_at} if latest else None}


class OcrRuntimeSnapshot(serializers.Serializer):
    mode = serializers.ChoiceField(choices=['nas_preferred', 'nas_only', 'remote_only'])
    remote_url = serializers.CharField(allow_blank=True)
    remote_url_redacted = serializers.BooleanField()
    remote_model = serializers.CharField(allow_blank=True)
    nas_url = serializers.CharField()
    nas_configured = serializers.BooleanField()
    remote_key_configured = serializers.BooleanField()
    remote_configured = serializers.BooleanField()
    remote_fallback_available = serializers.BooleanField()
    saved_configuration_version = serializers.CharField()
    configuration_version = serializers.CharField()
    effective_configuration = serializers.DictField()
    restart_required = serializers.BooleanField()
    last_success_at = serializers.DateTimeField(allow_null=True)
    last_job = serializers.DictField(allow_null=True)


class OcrRuntimeInput(serializers.Serializer):
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')
    mode = serializers.ChoiceField(choices=['nas_preferred', 'nas_only', 'remote_only'])
    remote_url = serializers.CharField(allow_blank=True, max_length=2048)
    remote_model = serializers.CharField(allow_blank=True, max_length=300)
    acknowledge_remote = serializers.BooleanField(default=False)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) - set(self.fields):
            raise serializers.ValidationError('仅接受当前 OCR 配置字段。')
        return super().to_internal_value(data)

    def validate_remote_url(self, value):
        if not editable_url(value):
            raise serializers.ValidationError('请使用不含账号、密码、查询参数或片段的 HTTP(S) 网关地址。密钥沿服务器原配置维护。')
        return value

    def validate_remote_model(self, value):
        if value not in {'', OCR_MODEL_ID}:
            raise serializers.ValidationError('全站统一使用 PP-OCRv6-tiny，请配置同一 RapidOCR 网关。')
        return value


class OcrProbeInput(serializers.Serializer):
    action = serializers.ChoiceField(choices=['test_nas', 'test_remote'])
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {'action', 'expected_version'}:
            raise serializers.ValidationError('仅接受检查动作与当前配置版本。')
        return super().to_internal_value(data)


class OcrFenceInput(serializers.Serializer):
    expected_version = serializers.RegexField(r'^[a-f0-9]{64}$')

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {'expected_version'}:
            raise serializers.ValidationError('仅接受尚未确认保存的原配置版本。')
        return super().to_internal_value(data)


class OcrProbeResult(serializers.Serializer):
    target = serializers.ChoiceField(choices=['nas', 'remote'])
    configured = serializers.BooleanField()
    reachable = serializers.BooleanField()
    functional = serializers.BooleanField(required=False)
    detail = serializers.CharField()


def locked_configuration(request, expected_version, *, allow_changed=False):
    if request.headers.get('X-Editor-Owner') != str(request.user.pk):
        raise PermissionDenied('请重新读取当前管理账户后操作。')
    actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if not actor or actor.token_version != request.user.token_version or capability_snapshot(actor).access_level not in {'admin', 'superadmin'}:
        raise PermissionDenied('管理会话或权限已变化。')
    acquire_entity_lock('ocr_runtime', OCR_RUNTIME_KEY)
    # The advisory lock also protects the initial setting when no row exists yet.
    list(SiteSetting.objects.select_for_update().filter(key=OCR_RUNTIME_KEY))
    config = ocr_runtime_config()
    if not allow_changed and version(config) != expected_version:
        raise OcrConfigurationConflict()
    return actor, config


class OcrRuntimeSettingsView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryAdmin]

    @extend_schema(responses=OcrRuntimeSnapshot)
    def get(self, request):
        return Response(current_ocr_runtime())

    @extend_schema(request=OcrRuntimeInput, responses=OcrRuntimeSnapshot)
    @transaction.atomic
    def put(self, request):
        serializer = OcrRuntimeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor, before = locked_configuration(request, data['expected_version'])
        value = {key: data[key] for key in ('mode', 'remote_url', 'remote_model')}
        value['remote_model'] = OCR_MODEL_ID
        if value['mode'] == 'nas_only' and not value['remote_url'] and not editable_url(before['remote_url']):
            # Turning off remote processing must not erase a hidden legacy address.
            stored = SiteSetting.objects.filter(key=OCR_RUNTIME_KEY).first()
            value['remote_url'] = stored.value.get('remote_url', '') if stored and isinstance(stored.value, dict) else ''
        effective_url = value['remote_url'] or settings.OCR_REMOTE_API_URL.strip()
        effective_model = OCR_MODEL_ID
        complete = bool(effective_url and effective_model and before['remote_key_configured'])
        if value['mode'] != 'nas_only' and not editable_url(effective_url):
            raise serializers.ValidationError({'remote_url': '现有默认地址包含隐藏凭据或参数，请填写新的无凭据地址，或先在服务器修正默认配置。'})
        if value['mode'] == 'remote_only' and not complete:
            raise serializers.ValidationError({'mode': '远程地址、模型和服务器密钥必须齐全，才能只使用远程解析。'})
        changed_remote = (value['mode'] != before['mode'] or effective_url != before['remote_url'] or effective_model != before['remote_model'])
        if value['mode'] != 'nas_only' and complete and changed_remote and not data['acknowledge_remote']:
            raise serializers.ValidationError({'acknowledge_remote': '请确认新的解析方式可能把待识别文档发送到所配置的远程服务。'})
        setting, _ = SiteSetting.objects.update_or_create(key=OCR_RUNTIME_KEY, defaults={'value': value, 'public': False, 'updated_by': actor})
        from catalog.local_services import _origin
        AuditEvent.objects.create(actor=actor, action='ocr_runtime_update', object_type='SiteSetting', object_id=str(setting.pk),
            before={'mode': before['mode'], 'remote_origin': _origin(before['remote_url']), 'version': data['expected_version']},
            after={'mode': value['mode'], 'remote_origin': _origin(effective_url), 'remote_model': effective_model,
                   'acknowledge_remote': data['acknowledge_remote'], 'version': version(ocr_runtime_config())})
        return Response(current_ocr_runtime())

    @extend_schema(request=OcrFenceInput, responses=OcrRuntimeSnapshot)
    @transaction.atomic
    def patch(self, request):
        """Fence a late CAS save without undoing any configuration already saved."""
        serializer = OcrFenceInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        expected = serializer.validated_data['expected_version']
        actor, config = locked_configuration(request, expected, allow_changed=True)
        if version(config) == expected:
            stored = SiteSetting.objects.filter(key=OCR_RUNTIME_KEY).first()
            setting, _ = SiteSetting.objects.update_or_create(key=OCR_RUNTIME_KEY,
                defaults={'value': stored.value if stored else {}, 'public': False, 'updated_by': actor})
            AuditEvent.objects.create(actor=actor, action='ocr_runtime_save_fenced', object_type='SiteSetting', object_id=str(setting.pk),
                before={'version': expected}, after={'version': version(ocr_runtime_config())})
        return Response(current_ocr_runtime())

    @extend_schema(request=OcrProbeInput, responses=OcrProbeResult)
    @transaction.atomic
    def post(self, request):
        from ingestion.services.health import http_service_health, ocr_service_health
        serializer = OcrProbeInput(data=request.data)
        serializer.is_valid(raise_exception=True)
        _, config = locked_configuration(request, serializer.validated_data['expected_version'])
        if serializer.validated_data['action'] == 'test_nas':
            return Response({'target': 'nas', **ocr_service_health(config['nas_url'], deep=True, timeout=120)})
        complete = bool(config['remote_url'] and config['remote_model'] and config['remote_key_configured'])
        if not complete or not editable_url(config['remote_url']):
            raise serializers.ValidationError('远程 URL、模型及密钥配置不完整或地址需修正。')
        return Response({'target': 'remote', **http_service_health(config['remote_url'], '/health', timeout=5)})
