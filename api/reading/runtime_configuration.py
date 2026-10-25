"""Versioned edits of the existing AI profile document and encrypted credentials."""
from hashlib import sha256
import json
import os
from uuid import uuid4

from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from accounts.models import User
from accounts.ownership import is_library_owner
from catalog.models import SiteSetting, ProviderCredentialSecret
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from catalog.services.provider_secrets import set_provider_secret, delete_provider_secret
from common.capabilities import Capability, has_capability
from common.ai_runtime import PROFILE_SETTING_KEY, current_profile_document, validate_profile_document, resolve_endpoint, resolve_credential
from ingestion.models import AuditEvent
from .runtime_profiles import runtime_profile_payload, save_runtime_profile_document


class RuntimeConfigurationConflict(APIException):
    status_code = 409
    default_detail = '模型配置或凭据已变化，未覆盖新值。请重新读取并核对后保存。'


def validated_document():
    try:
        return validate_profile_document(current_profile_document())
    except ValueError as exc:
        raise ValidationError('原模型配置格式无效，已保留原值；请维护者核对配置记录后修复。') from exc


def configuration_version():
    stored = SiteSetting.objects.filter(key=PROFILE_SETTING_KEY).values('value', 'updated_at').first()
    document = validated_document()
    credentials = list(ProviderCredentialSecret.objects.order_by('pk').values_list('pk', 'updated_at'))
    environment = [(row['key'], resolve_endpoint(row['endpoint_alias']),
        sha256(resolve_credential(row['credential_alias']).encode()).hexdigest()) for row in document['profiles']]
    return sha256(json.dumps([stored, document, credentials, environment], cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def credential_environment(alias):
    from django.conf import settings
    return bool(getattr(settings, 'AI_API_KEY', '')) if alias == 'default' else bool(os.getenv('AI_CREDENTIAL_' + alias.upper().replace('-', '_'), ''))


def snapshot(actor):
    validated_document()  # Invalid stored rows must not leak arbitrary fields or become editable defaults.
    result = runtime_profile_payload()
    result['configuration_version'] = configuration_version()
    owner = is_library_owner(actor)
    result['permissions'] = {'can_edit_profiles': True, 'can_edit_sensitive_aliases': owner, 'can_remove_profiles': owner}
    aliases = list(ProviderCredentialSecret.objects.filter(purpose='ai_runtime').exclude(alias='default')
        .order_by('alias').values_list('alias', flat=True)[:51]) if owner else []
    result['credential_alias_options'] = aliases[:50]
    result['more_credential_aliases'] = len(aliases) > 50
    for row in result['profiles']:
        alias = row['credential_alias']
        saved = ProviderCredentialSecret.objects.filter(alias=alias, purpose='ai_runtime').exists()
        environment = credential_environment(alias)
        row['credential_storage'] = 'environment' if environment else 'saved' if saved and alias != 'default' else 'absent'
        row['credential_managed_here'] = bool(owner and saved and alias != 'default' and not environment)
        if not owner:
            row['endpoint_alias'] = ''
            row['credential_alias'] = ''
    return result


def locked_actor(request, expected='', *, read=False, allow_changed=False):
    if not read and request.headers.get('X-Editor-Owner') != str(request.user.pk):
        raise PermissionDenied('请重新读取当前管理账户后操作。')
    actor = User.objects.select_for_update().filter(pk=request.user.pk, is_active=True).first()
    if not actor or actor.token_version != request.user.token_version or not has_capability(actor, Capability.MANAGE_AI):
        raise PermissionDenied('管理会话或模型配置权限已变化。')
    # Same order as source configuration and legacy credential writers; no second credential store.
    acquire_entity_lock('provider_configuration', 'research_source_registry')
    list(SiteSetting.objects.select_for_update().filter(key=PROFILE_SETTING_KEY))
    if not read and not allow_changed and configuration_version() != expected:
        raise RuntimeConfigurationConflict()
    return actor


def save(actor, values, *, request_id=''):
    before = validated_document()
    previous = {row['key']: row for row in before['profiles']}
    updates = {'active': values['active'], 'profiles': [dict(row) for row in values['profiles']]}
    owner = is_library_owner(actor)
    if not owner:
        if set(previous) != {row['key'] for row in updates['profiles']}:
            raise PermissionDenied('只有馆长可以增加或删除模型配置档。')
        for row in updates['profiles']:
            old = previous[row['key']]
            if row['capability'] != old['capability'] or any(row.get(field) not in (None, '', old[field]) for field in ('endpoint_alias', 'credential_alias')):
                raise PermissionDenied('只有馆长可以更改配置用途和敏感别名。')
            row.update(endpoint_alias=old['endpoint_alias'], credential_alias=old['credential_alias'])
    try:
        updated = validate_profile_document(updates)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    credential = values.get('credential')
    if credential:
        if not owner:
            raise PermissionDenied('只有馆长可以修改服务器凭据。')
        apply_credential(actor, credential, updated, before, request_id=request_id)
    # A saved alias from another purpose must never be accidentally treated as an AI key.
    for row in updated['profiles']:
        if ProviderCredentialSecret.objects.filter(alias=row['credential_alias']).exclude(purpose='ai_runtime').exists():
            raise ValidationError('凭据别名属于其他用途，请使用模型服务的独立别名。')
    save_runtime_profile_document(updated, actor=actor, request_id=request_id)
    return snapshot(actor)


def apply_credential(actor, command, document, before, *, request_id):
    key, alias = command['profile_key'], command['alias']
    target = next((row for row in document['profiles'] if row['key'] == key), None)
    original = next((row for row in before['profiles'] if row['key'] == key), None)
    if not target or target['credential_alias'] != alias:
        raise ValidationError('凭据操作必须与本次配置档的绑定别名一致。')
    if alias == 'default' or credential_environment(alias):
        raise ValidationError('该别名由部署环境管理。请使用独立新别名，避免保存后仍使用旧环境凭据。')
    if any(row['key'] != key and row['credential_alias'] == alias for row in before['profiles'] + document['profiles']):
        raise ValidationError('该凭据仍被其他模型配置档引用，请先选择独立别名。')
    existing = ProviderCredentialSecret.objects.select_for_update().filter(alias=alias).first()
    if existing and existing.purpose != 'ai_runtime':
        raise ValidationError('此别名属于其他用途，不能从模型配置覆盖或删除。')
    if command['action'] == 'set':
        set_provider_secret(alias=alias, purpose='ai_runtime', provider_key=key, secret=command['secret'], actor=actor, request_id=request_id)
    else:
        if not command.get('confirm_delete'):
            raise ValidationError('请确认删除已保存凭据并停用此配置档。')
        if not existing or not original or original['credential_alias'] != alias:
            raise RuntimeConfigurationConflict('当前配置档没有这份可删除的加密凭据。')
        delete_provider_secret(alias=alias, actor=actor, request_id=request_id)
        target.update(enabled=False, credential_alias='default')


def fence(actor, expected):
    if configuration_version() != expected:
        return
    stored = SiteSetting.objects.filter(key=PROFILE_SETTING_KEY).first()
    value = stored.value if stored else validated_document()
    row, _ = SiteSetting.objects.update_or_create(key=PROFILE_SETTING_KEY, defaults={
        'value': {**value, '_save_fence': str(uuid4())}, 'public': False, 'updated_by': actor})
    AuditEvent.objects.create(actor=actor, action='ai_runtime_save_fenced', object_type='SiteSetting', object_id=str(row.pk),
        before={'version': expected}, after={'version': configuration_version()})
