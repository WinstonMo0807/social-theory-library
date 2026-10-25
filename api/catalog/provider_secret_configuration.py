"""Compatibility endpoint: only unbound credentials may be changed independently."""
from hashlib import sha256
import json
from uuid import uuid4
from django.core.serializers.json import DjangoJSONEncoder
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError
from accounts.models import User
from accounts.ownership import is_library_owner
from common.ai_runtime import PROFILE_SETTING_KEY, current_profile_document, validate_profile_document
from common.capabilities import Capability, has_capability
from catalog.models import ProviderCredentialSecret, SiteSetting
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from catalog.services.research_sources import SOURCE_SPECS, REGISTRY_SETTING_KEY
from catalog.services.provider_secrets import provider_secret_registry_payload, set_provider_secret, delete_provider_secret
from ingestion.models import AuditEvent

FENCE_KEY = 'provider_credentials_save_fence'


class CredentialConfigurationConflict(APIException):
    status_code = 409
    default_detail = '凭据或绑定已变化，请重新读取。未覆盖或删除任何凭据。'


def bindings():
    result = {}
    source = SiteSetting.objects.filter(key=REGISTRY_SETTING_KEY).first()
    document = source.value if source else {}
    if not isinstance(document, dict) or not isinstance(document.get('adapters', {}), dict):
        raise ValidationError('来源配置格式无效，暂不能确定凭据引用；请先核对原配置。')
    adapters = document.get('adapters', {})
    for spec in SOURCE_SPECS:
        configured = adapters.get(spec.key, {})
        if not isinstance(configured, dict):
            raise ValidationError('来源配置格式无效，暂不能确定凭据引用；请先核对原配置。')
        alias = str(configured.get('credential_alias') or '').strip().casefold()
        if alias:
            result.setdefault(alias, []).append({'kind':'research_source','key':spec.key,'url':f'/admin/settings?service=metadata-{spec.key}'})
    try:
        saved = SiteSetting.objects.filter(key=PROFILE_SETTING_KEY).first()
        profiles = validate_profile_document(saved.value if saved else current_profile_document())['profiles']
    except ValueError as exc:
        raise ValidationError('模型配置格式无效，暂不能确定凭据引用；原记录保留，请先核对模型配置。') from exc
    for profile in profiles:
        alias = profile['credential_alias']
        if alias != 'default':  # The AI default alias resolves only to deployment environment values.
            result.setdefault(alias, []).append({'kind':'ai_runtime','key':profile['key'],'url':f'/admin/processing/settings#ai'})
    return result


def configuration_version():
    credentials = list(ProviderCredentialSecret.objects.order_by('pk').values_list('pk','alias','purpose','provider_key','updated_at'))
    settings = list(SiteSetting.objects.filter(key__in=[REGISTRY_SETTING_KEY, PROFILE_SETTING_KEY, FENCE_KEY]).order_by('key').values('key','value','updated_at'))
    return sha256(json.dumps([credentials, settings, bindings()],cls=DjangoJSONEncoder,sort_keys=True).encode()).hexdigest()


def locked_actor(request, expected='', *, read=False, allow_changed=False):
    if not read and request.headers.get('X-Editor-Owner') != str(request.user.pk):
        raise PermissionDenied('请重新读取当前馆长账户后操作。')
    actor = User.objects.select_for_update().filter(pk=request.user.pk,is_active=True).first()
    if not actor or actor.token_version != request.user.token_version or not is_library_owner(actor) or not has_capability(actor,Capability.MANAGE_AI_PROVIDERS):
        raise PermissionDenied('馆长会话或敏感配置权限已变化。')
    acquire_entity_lock('provider_configuration','research_source_registry')
    if not read and not allow_changed and configuration_version() != expected:
        raise CredentialConfigurationConflict()
    return actor


def snapshot(*, page=1):
    result = provider_secret_registry_payload(page=page)
    references = bindings()
    for row in result['secrets']:
        row['bindings'] = references.get(row['alias'],[])
        row['can_edit_here'] = not row['bindings']
    result['configuration_version'] = configuration_version()
    return result


def save(actor, command, *, request_id=''):
    alias = command['alias']
    if bindings().get(alias):
        raise ValidationError('此凭据已绑定服务，请从对应来源或模型配置同时修改，避免影响其他配置。')
    existing = ProviderCredentialSecret.objects.select_for_update().filter(alias=alias).first()
    if command['action'] == 'delete':
        if not command.get('confirm_delete'):
            raise ValidationError('删除未绑定凭据需要明确确认。')
        if not existing:
            raise CredentialConfigurationConflict('此凭据已不存在，未再次执行删除。')
        delete_provider_secret(alias=alias,actor=actor,request_id=request_id)
    else:
        from reading.runtime_configuration import credential_environment
        if command['purpose'] == 'ai_runtime' and (alias == 'default' or credential_environment(alias)):
            raise ValidationError('此模型别名由环境管理，请选独立别名，避免保存后仍使用旧环境凭据。')
        if existing and (existing.purpose != command['purpose'] or existing.provider_key != command['provider_key']):
            raise ValidationError('已有别名的用途或服务不一致，请使用独立别名。')
        set_provider_secret(alias=alias,purpose=command['purpose'],provider_key=command['provider_key'],secret=command['secret'],actor=actor,request_id=request_id)
    return snapshot()


def fence(actor, expected):
    if configuration_version() != expected:
        return
    row,_ = SiteSetting.objects.update_or_create(key=FENCE_KEY,defaults={'value':{'nonce':str(uuid4())},'public':False,'updated_by':actor})
    AuditEvent.objects.create(actor=actor,action='provider_credential_save_fenced',object_type='SiteSetting',object_id=str(row.pk),before={'version':expected},after={'version':configuration_version()})
