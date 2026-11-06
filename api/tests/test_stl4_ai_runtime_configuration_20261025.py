"""Deferred acceptance: profile ownership, stale writes, atomic credentials and old documents."""
from copy import deepcopy
from unittest.mock import patch

from cryptography.fernet import Fernet
import pytest
from rest_framework.test import APIClient
from accounts.models import User
from catalog.models import SiteSetting, ProviderCredentialSecret
from catalog.services.provider_secrets import set_provider_secret
from common.ai_runtime import PROFILE_SETTING_KEY, validate_profile_document, _environment_profiles
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
PATH = '/api/reading/admin/ai-runtime-profiles/'


@pytest.fixture(autouse=True)
def isolated_key(settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.AI_PROVIDER = 'none'
    settings.AI_API_KEY = ''


def client_for(actor):
    client = APIClient(); client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client


def body_for(data):
    rows = deepcopy(data['profiles'])
    for row in rows:
        for field in ('environment', 'credential_managed_here', 'credential_storage'):
            row.pop(field)
        if not data['permissions']['can_edit_sensitive_aliases']:
            row.pop('endpoint_alias'); row.pop('credential_alias')
    return {'expected_version': data['configuration_version'], 'active': deepcopy(data['active']), 'profiles': rows}


def credential_body(data):
    body = body_for(data); row = body['profiles'][0]
    row['credential_alias'] = 'isolated-model-fixture'
    body['credential'] = {'action': 'set', 'profile_key': row['key'], 'alias': row['credential_alias'], 'secret': 'isolated-runtime-fixture-value'}
    return body


def test_versions_fence_late_save_and_never_undo_completed_update(admin_user):
    client = client_for(admin_user); initial = client.get(PATH)
    assert initial.status_code == 200 and 'no-store' in initial['Cache-Control']
    fenced = client.patch(PATH, {'expected_version': initial.data['configuration_version']}, format='json', secure=True)
    assert fenced.status_code == 200
    assert client.put(PATH, body_for(initial.data), format='json', secure=True).status_code == 409
    body = body_for(fenced.data); body['profiles'][0]['temperature'] = .15
    saved = client.put(PATH, body, format='json', secure=True)
    assert saved.status_code == 200
    assert client.put(PATH, body, format='json', secure=True).status_code == 409
    observed = client.patch(PATH, {'expected_version': fenced.data['configuration_version']}, format='json', secure=True)
    assert observed.data['configuration_version'] == saved.data['configuration_version']


def test_secret_binding_is_atomic_and_no_plaintext_returns(superadmin_user):
    client = client_for(superadmin_user); body = credential_body(client.get(PATH).data)
    with patch('reading.runtime_configuration.save_runtime_profile_document', side_effect=ValueError('isolated failure')):
        result = client.put(PATH, body, format='json', secure=True)
        assert result.status_code == 500
        assert 'isolated failure' not in str(result.data)
    assert not ProviderCredentialSecret.objects.filter(alias='isolated-model-fixture').exists()
    assert not AuditEvent.objects.filter(action='provider_credential_secret_update').exists()
    result = client.put(PATH, body, format='json', secure=True)
    assert result.status_code == 200
    assert result.data['profiles'][0]['credential_storage'] == 'saved'
    assert result.data['profiles'][0]['credential_managed_here']
    assert 'isolated-runtime-fixture-value' not in str(result.data)
    assert 'isolated-runtime-fixture-value' not in str(list(AuditEvent.objects.values('before', 'after')))
    assert b'isolated-runtime-fixture-value' not in bytes(ProviderCredentialSecret.objects.get(alias='isolated-model-fixture').ciphertext)


def test_environment_shadow_and_shared_delete_are_blocked(superadmin_user, monkeypatch):
    client = client_for(superadmin_user); data = client.get(PATH).data
    body = credential_body(data)
    monkeypatch.setenv('AI_CREDENTIAL_ISOLATED_MODEL_FIXTURE', 'isolated-environment-fixture')
    assert client.put(PATH, body, format='json', secure=True).status_code == 400
    monkeypatch.delenv('AI_CREDENTIAL_ISOLATED_MODEL_FIXTURE')
    saved = client.put(PATH, body, format='json', secure=True); assert saved.status_code == 200
    bound = body_for(saved.data); bound['profiles'][1]['credential_alias'] = bound['profiles'][0]['credential_alias']
    saved = client.put(PATH, bound, format='json', secure=True); assert saved.status_code == 200
    deletion = body_for(saved.data)
    deletion['credential'] = {'action':'delete','profile_key':deletion['profiles'][0]['key'],'alias':'isolated-model-fixture','confirm_delete':True}
    assert client.put(PATH, deletion, format='json', secure=True).status_code == 400
    assert ProviderCredentialSecret.objects.filter(alias='isolated-model-fixture').exists()


def test_single_delete_disables_profile_and_preserves_environment(superadmin_user, settings):
    client = client_for(superadmin_user)
    saved = client.put(PATH, credential_body(client.get(PATH).data), format='json', secure=True)
    deletion = body_for(saved.data)
    deletion['credential'] = {'action':'delete','profile_key':deletion['profiles'][0]['key'],'alias':'isolated-model-fixture','confirm_delete':True}
    result = client.put(PATH, deletion, format='json', secure=True)
    assert result.status_code == 200 and not result.data['profiles'][0]['enabled']
    assert result.data['profiles'][0]['credential_alias'] == 'default'
    assert not ProviderCredentialSecret.objects.filter(alias='isolated-model-fixture').exists()
    assert settings.AI_API_KEY == ''


def test_admin_preserves_aliases_but_cannot_change_them_or_credentials(admin_user, superadmin_user):
    owner = client_for(superadmin_user)
    saved = owner.put(PATH, credential_body(owner.get(PATH).data), format='json', secure=True); assert saved.status_code == 200
    client = client_for(admin_user); data = client.get(PATH).data
    assert not data['credential_alias_options'] and data['profiles'][0]['credential_alias'] == ''
    body = body_for(data); body['profiles'][0]['temperature'] = .2
    result = client.put(PATH, body, format='json', secure=True); assert result.status_code == 200
    stored = SiteSetting.objects.get(key=PROFILE_SETTING_KEY).value
    assert stored['profiles'][0]['credential_alias'] == 'isolated-model-fixture'
    body = body_for(result.data); body['profiles'][0]['credential_alias'] = 'unauthorized-alias'
    assert client.put(PATH, body, format='json', secure=True).status_code == 403


def test_current_role_session_and_reader_scope_are_checked(admin_user, reader_user):
    client = client_for(admin_user); data = client.get(PATH).data
    client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert client.put(PATH, body_for(data), format='json', secure=True).status_code == 403
    client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    User.objects.filter(pk=admin_user.pk).update(role=User.Role.READER)
    assert client.put(PATH, body_for(data), format='json', secure=True).status_code == 403
    assert client.get(PATH).status_code == 403
    reader = client_for(reader_user)
    assert reader.get(PATH).status_code == 403
    assert reader.patch(PATH, {'expected_version':data['configuration_version']}, format='json', secure=True).status_code == 403


def test_old_expanded_document_over_24_profiles_can_round_trip():
    document = _environment_profiles()
    for index in range(15):
        document['profiles'].append({**document['profiles'][0], 'key':f'legacy-extra-{index}'})
    validated = validate_profile_document(document)
    assert len(validated['profiles']) > 24
    assert validate_profile_document(validated)['profiles'] == validated['profiles']


def test_unknown_fields_rejected_and_no_automatic_model_probe(superadmin_user):
    client = client_for(superadmin_user)
    with patch('reading.runtime_views.test_runtime_profile', side_effect=AssertionError('no implicit model call')):
        initial = client.get(PATH); body = body_for(initial.data)
        body['profiles'][0]['api_key'] = 'not-a-supported-field'
        assert client.put(PATH, body, format='json', secure=True).status_code == 400
        body = body_for(initial.data); body['profiles'][0]['max_input_chars'] = 24000
        assert client.put(PATH, body, format='json', secure=True).status_code == 200


def test_existing_unbound_ai_aliases_are_owner_only(superadmin_user, admin_user):
    set_provider_secret(alias='old-runtime-fixture',purpose='ai_runtime',provider_key='legacy',secret='isolated-fixture',actor=superadmin_user)
    assert 'old-runtime-fixture' in client_for(superadmin_user).get(PATH).data['credential_alias_options']
    assert not client_for(admin_user).get(PATH).data['credential_alias_options']
