"""Atomic edits over the original registry and encrypted credential service."""
from hashlib import sha256
import json
from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from accounts.models import User
from accounts.ownership import is_library_owner
from common.capabilities import Capability, has_capability
from catalog.models import SiteSetting, ProviderCredentialSecret
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from catalog.services import research_sources as sources
from catalog.services.provider_secrets import set_provider_secret, delete_provider_secret, normalize_secret_alias
from ingestion.models import AuditEvent


class SourceConfigurationConflict(APIException):
    status_code = 409
    default_detail = '来源或凭据配置已变化，未覆盖新值。请重新读取并核对后保存。'


def configuration_version():
    stored = SiteSetting.objects.filter(key=sources.REGISTRY_SETTING_KEY).values('value', 'updated_at').first()
    credentials = list(ProviderCredentialSecret.objects.order_by('pk').values_list('pk', 'updated_at'))
    effective = [(spec.key, sources.source_configuration(spec.key), sources.resolve_source_endpoint(spec.key)) for spec in sources.SOURCE_SPECS]
    return sha256(json.dumps([stored, credentials, effective], cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def snapshot(actor):
    result = sources.research_source_registry_payload(user=actor)
    result['configuration_version'] = configuration_version()
    owner = is_library_owner(actor)
    for row in result['adapters']:
        config = sources.source_configuration(row['key'])
        row['endpoint_alias'] = config['endpoint_alias'] if owner else ''
        row['credential_alias'] = config['credential_alias'] if owner else ''
        row['credential_last_test_message'] = ''  # Never echo upstream credential messages.
        aliases = list(ProviderCredentialSecret.objects.filter(purpose='research_source', provider_key=row['key'])
            .order_by('alias').values_list('alias', flat=True)[:51]) if owner else []
        row['credential_alias_options'] = aliases[:50]
        row['more_credential_aliases'] = len(aliases) > 50
        row['credential_managed_here'] = bool(config['credential_alias'] and ProviderCredentialSecret.objects.filter(
            alias=config['credential_alias'], purpose='research_source', provider_key=row['key']).exists()) if owner else False
    return result


def locked_actor(request, expected, *, allow_changed=False, read=False):
    if not read and request.headers.get('X-Editor-Owner') != str(request.user.pk):
        raise PermissionDenied('请重新读取当前管理账户后操作。')
    actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    capability = Capability.VIEW_SYSTEM_STATUS if read else Capability.CONFIGURE_PROVIDERS
    if not actor or actor.token_version != request.user.token_version or not has_capability(actor, capability):
        raise PermissionDenied('管理会话或来源配置权限已变化。')
    acquire_entity_lock('provider_configuration', sources.REGISTRY_SETTING_KEY)
    list(SiteSetting.objects.select_for_update().filter(key=sources.REGISTRY_SETTING_KEY))
    if not read and not allow_changed and configuration_version() != expected:
        raise SourceConfigurationConflict()
    return actor


def apply_credential(actor, credential, updates):
    if not is_library_owner(actor):
        raise PermissionDenied('只有馆长可以修改服务器凭据。')
    key = credential['source_key']
    if len(updates) != 1 or updates[0]['key'] != key:
        raise ValidationError('凭据与来源必须在同一次保存中对应同一来源。')
    spec = sources.SOURCE_SPEC_BY_KEY.get(key)
    if not spec or not (spec.credential_required or spec.credential_setting):
        raise ValidationError('当前来源没有可管理的凭据。')
    alias = normalize_secret_alias(credential.get('alias'))
    if updates[0].get('credential_alias', alias) != alias:
        raise ValidationError('凭据操作与来源绑定别名不一致，未更改任何配置。')
    used_by = [other.key for other in sources.SOURCE_SPECS if other.key != key and sources.source_configuration(other.key)['credential_alias'] == alias]
    if used_by:
        raise ValidationError('该别名仍被其他来源使用，请选择独立别名，或先解除其他绑定。')
    existing = ProviderCredentialSecret.objects.select_for_update().filter(alias=alias).first()
    if existing and (existing.purpose != 'research_source' or existing.provider_key != key):
        raise ValidationError('此别名属于另一用途或服务，不能从当前来源覆盖或删除。')
    if credential['action'] == 'set':
        set_provider_secret(alias=alias, purpose='research_source', provider_key=key, secret=credential['secret'], actor=actor)
        updates[0]['credential_alias'] = alias
    else:
        if not credential.get('confirm_delete'):
            raise ValidationError('请明确确认删除已保存凭据并停用此来源。')
        if not existing or sources.source_configuration(key)['credential_alias'] != alias:
            raise SourceConfigurationConflict('当前来源没有这份可删除的服务器凭据，环境凭据不在此处删除。')
        delete_provider_secret(alias=alias, actor=actor)
        updates[0].update(credential_alias='', enabled=False)


def fence(actor, expected):
    if configuration_version() != expected:
        return
    stored = SiteSetting.objects.filter(key=sources.REGISTRY_SETTING_KEY).first()
    row, _ = SiteSetting.objects.update_or_create(key=sources.REGISTRY_SETTING_KEY,
        defaults={'value': {**(stored.value if stored and isinstance(stored.value, dict) else {}), '_save_fence': str(uuid4())}, 'public': False, 'updated_by': actor})
    AuditEvent.objects.create(actor=actor, action='research_source_save_fenced', object_type='SiteSetting', object_id=str(row.pk),
        before={'version': expected}, after={'version': configuration_version()})
