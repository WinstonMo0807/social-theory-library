"""Owner-managed API origins. Values stay encrypted and never enter snapshots."""
from hashlib import sha256
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import InvalidToken
from django.db import DatabaseError

from catalog.services.field_enrichment.web import WebFetchError, _validated_public_target


def endpoint_alias(profile_key):
    return 'managed-' + sha256(profile_key.encode()).hexdigest()[:24]


def saved_endpoint(alias):
    from catalog.models import SiteSetting
    from reading.services import decrypt_private_text
    try:
        value = SiteSetting.objects.filter(key=f'ai_endpoint_{alias}', public=False).values_list('value', flat=True).first()
        return decrypt_private_text(value['ciphertext'].encode()) if isinstance(value, dict) else ''
    except (DatabaseError, RuntimeError, InvalidToken, ValueError, TypeError, KeyError):
        return ''


def public_endpoint(value):
    """A relay is HTTPS/public only; internal model addresses remain deployment settings."""
    parsed = urlsplit(str(value).strip())
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError('中转接口须为 HTTPS 地址，不包含账号、密钥或查询参数。')
    url, addresses = _validated_public_target(str(value).strip())
    url = url.rstrip('/')
    if url.endswith('/chat/completions') or url.endswith('/responses'):
        raise ValueError('请填写 API Base URL，不要填写具体请求接口。')
    if url.endswith('/v1'):
        url = url[:-3]
    return url, addresses


def save_endpoint(actor, profile_key, value, *, request_id=''):
    from catalog.models import SiteSetting
    from reading.services import encrypt_private_text
    from ingestion.models import AuditEvent
    url, _ = public_endpoint(value)
    alias = endpoint_alias(profile_key)
    row, _ = SiteSetting.objects.update_or_create(key=f'ai_endpoint_{alias}', defaults={
        'value': {'ciphertext': bytes(encrypt_private_text(url)).decode()}, 'public': False, 'updated_by': actor})
    AuditEvent.objects.create(actor=actor, action='ai_endpoint_update', object_type='SiteSetting',
        object_id=str(row.pk), before={}, after={'profile_key': profile_key, 'configured': True}, request_id=request_id)
    return alias


class PublicAITransport(httpx.HTTPTransport):
    """Resolve once, reject private addresses and keep TLS/Host on the approved origin."""
    def __init__(self, base_url):
        from ingestion.services.ai_client import AIServiceUnavailable
        try:
            _, addresses = public_endpoint(base_url)
        except (ValueError, WebFetchError) as exc:
            raise AIServiceUnavailable('模型接口地址不可用，请管理员核对。') from exc
        self._address, self._origin = addresses[0], httpx.URL(base_url)
        super().__init__(trust_env=False, verify=True)

    def handle_request(self, request):
        from ingestion.services.ai_client import AIServiceUnavailable
        if (request.url.scheme, request.url.host, request.url.port) != (
                self._origin.scheme, self._origin.host, self._origin.port):
            raise AIServiceUnavailable('模型请求不能跳转到其他服务。')
        request.headers['Host'] = self._origin.netloc.decode('ascii')
        request.extensions['sni_hostname'] = self._origin.host
        request.url = request.url.copy_with(host=self._address)
        return super().handle_request(request)
