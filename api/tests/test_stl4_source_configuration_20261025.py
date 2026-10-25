"""Deferred source/secret atomicity and account-scope acceptance definitions."""
from unittest.mock import patch

from cryptography.fernet import Fernet
import pytest
from rest_framework.test import APIClient

from catalog.models import SiteSetting, ProviderCredentialSecret
from catalog.services.research_sources import REGISTRY_SETTING_KEY
from catalog.services.provider_secrets import set_provider_secret
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
PATH = '/api/catalog/admin/research-sources/'


@pytest.fixture(autouse=True)
def isolated_key(settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()


def client_for(actor):
    client = APIClient(); client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client


def change(data, *, enabled=False):
    return {'expected_version': data['configuration_version'], 'adapters': [{'key': 'crossref', 'enabled': enabled}]}


def test_duplicate_or_stale_save_cannot_overwrite_and_fence_does_not_undo(admin_user):
    client = client_for(admin_user); initial = client.get(PATH)
    assert initial.status_code == 200 and 'no-store' in initial['Cache-Control']
    fenced = client.patch(PATH, {'expected_version': initial.data['configuration_version']}, format='json')
    assert fenced.status_code == 200
    assert client.put(PATH, change(initial.data), format='json').status_code == 409
    saved = client.put(PATH, change(fenced.data), format='json')
    assert saved.status_code == 200
    assert client.put(PATH, change(fenced.data, enabled=True), format='json').status_code == 409
    again = client.patch(PATH, {'expected_version': fenced.data['configuration_version']}, format='json')
    assert again.data['configuration_version'] == saved.data['configuration_version']
    assert not next(row for row in again.data['adapters'] if row['key'] == 'crossref')['enabled']


def credential_body(data):
    return {'expected_version': data['configuration_version'], 'adapters': [{'key': 'openalex', 'enabled': False, 'credential_alias': 'fixture-openalex'}],
            'credential': {'source_key': 'openalex', 'action': 'set', 'alias': 'fixture-openalex', 'secret': 'isolated-fixture-value'}}


def test_secret_and_binding_are_atomic_and_never_return_plaintext(superadmin_user):
    client = client_for(superadmin_user); data = client.get(PATH).data
    body = credential_body(data)
    result = client.put(PATH, body, format='json')
    assert result.status_code == 200
    assert 'isolated-fixture-value' not in str(result.data)
    assert 'isolated-fixture-value' not in str(list(AuditEvent.objects.values('before', 'after')))
    assert b'isolated-fixture-value' not in bytes(ProviderCredentialSecret.objects.get(alias='fixture-openalex').ciphertext)
    row = next(item for item in result.data['adapters'] if item['key'] == 'openalex')
    assert row['credential_alias'] == 'fixture-openalex' and row['credential_managed_here'] and not row['enabled']


def test_invalid_registry_change_rolls_back_credential_write(superadmin_user):
    client = client_for(superadmin_user); body = credential_body(client.get(PATH).data)
    body['adapters'][0]['endpoint_alias'] = 'unsupported-fixed-endpoint'
    result = client.put(PATH, body, format='json')
    assert result.status_code == 400
    assert not ProviderCredentialSecret.objects.filter(alias='fixture-openalex').exists()
    assert not AuditEvent.objects.filter(action='provider_credential_secret_update').exists()


def test_shared_or_other_purpose_alias_cannot_be_deleted_from_one_source(superadmin_user):
    set_provider_secret(alias='shared-fixture', purpose='research_source', provider_key='openalex', secret='isolated-fixture-value', actor=superadmin_user)
    SiteSetting.objects.create(key=REGISTRY_SETTING_KEY, value={'adapters': {'openalex': {'enabled': True, 'credential_alias': 'shared-fixture'},
        'google_books': {'enabled': True, 'credential_alias': 'shared-fixture'}}}, public=False)
    client = client_for(superadmin_user); data = client.get(PATH).data
    body = {'expected_version': data['configuration_version'], 'adapters': [{'key': 'openalex'}],
            'credential': {'source_key': 'openalex', 'action': 'delete', 'alias': 'shared-fixture', 'confirm_delete': True}}
    assert client.put(PATH, body, format='json').status_code == 400
    assert ProviderCredentialSecret.objects.filter(alias='shared-fixture').exists()


def test_ordinary_admin_cannot_change_secrets_and_wrong_owner_cannot_save(admin_user, superadmin_user):
    client = client_for(admin_user); data = client.get(PATH).data
    assert client.put(PATH, credential_body(data), format='json').status_code == 403
    client.credentials(HTTP_X_EDITOR_OWNER=str(superadmin_user.pk))
    assert client.put(PATH, change(data), format='json').status_code == 403
    assert not ProviderCredentialSecret.objects.exists()


def test_explicit_check_does_not_echo_upstream_secret_message(admin_user):
    client = client_for(admin_user); data = client.get(PATH).data
    with patch('catalog.services.research_sources.test_research_source', return_value={'status': 'healthy', 'functional': True, 'productive': False, 'detail': 'private upstream fixture'}):
        result = client.post(PATH, {'expected_version': data['configuration_version'], 'source_key': 'crossref', 'action': 'test'}, format='json')
    assert result.status_code == 200 and result.data['functional'] and not result.data['productive']
    assert 'private upstream fixture' not in str(result.data)


def test_reader_cannot_read_registry_or_fence_configurations(reader_user):
    client = client_for(reader_user)
    assert client.get(PATH).status_code == 403
    assert client.patch(PATH, {'expected_version': 'a' * 64}, format='json').status_code == 403


def test_unbound_existing_credential_is_selectable_without_returning_secret(superadmin_user, admin_user):
    set_provider_secret(alias='old-unbound', purpose='research_source', provider_key='openalex', secret='isolated-old-value', actor=superadmin_user)
    owner_data = client_for(superadmin_user).get(PATH).data
    row = next(item for item in owner_data['adapters'] if item['key'] == 'openalex')
    assert 'old-unbound' in row['credential_alias_options'] and 'isolated-old-value' not in str(owner_data)
    ordinary_data = client_for(admin_user).get(PATH).data
    assert all(not item['credential_alias_options'] and not item['credential_alias'] for item in ordinary_data['adapters'])
