"""Deferred legacy credential API acceptance; never use real credentials or providers."""
from cryptography.fernet import Fernet
import pytest
from rest_framework.test import APIClient
from accounts.models import User
from catalog.models import ProviderCredentialSecret, SiteSetting
from catalog.services.provider_secrets import set_provider_secret
from .test_stl4_ai_runtime_configuration_20261025 import body_for

pytestmark = pytest.mark.django_db
PATH = '/api/catalog/admin/provider-secrets/'


@pytest.fixture(autouse=True)
def isolated_key(settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY=Fernet.generate_key().decode()
    settings.AI_PROVIDER='none'
    settings.AI_API_KEY=''


def client_for(actor):
    client=APIClient();client.force_authenticate(actor);client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk));return client


def command(version, **changes):
    return {'expected_version':version,'action':'set','alias':'legacy-fixture','purpose':'ai_runtime','provider_key':'legacy-profile','secret':'isolated-legacy-fixture',**changes}


def test_owner_version_fences_unknown_write_without_repeating(superadmin_user):
    client=client_for(superadmin_user);initial=client.get(PATH)
    assert initial.status_code==200 and 'no-store' in initial['Cache-Control']
    version=initial.data['configuration_version']
    fenced=client.patch(PATH,{'expected_version':version},format='json');assert fenced.status_code==200
    assert client.post(PATH,command(version),format='json').status_code==409
    saved=client.post(PATH,command(fenced.data['configuration_version']),format='json');assert saved.status_code==200
    assert client.post(PATH,command(fenced.data['configuration_version']),format='json').status_code==409
    assert 'isolated-legacy-fixture' not in str(saved.data)
    again=client.patch(PATH,{'expected_version':fenced.data['configuration_version']},format='json')
    assert again.data['configuration_version']==saved.data['configuration_version']


def test_bound_alias_requires_original_service_editor(superadmin_user):
    client=client_for(superadmin_user)
    created=client.post(PATH,command(client.get(PATH).data['configuration_version']),format='json');assert created.status_code==200
    runtime='/api/reading/admin/ai-runtime-profiles/'
    body=body_for(client.get(runtime).data);body['profiles'][0]['credential_alias']='legacy-fixture'
    assert client.put(runtime,body,format='json').status_code==200
    current=client.get(PATH).data
    row=next(row for row in current['secrets'] if row['alias']=='legacy-fixture')
    assert row['bindings'] and not row['can_edit_here']
    assert client.post(PATH,command(current['configuration_version']),format='json').status_code==400
    assert client.post(PATH,{'expected_version':current['configuration_version'],'action':'delete','alias':'legacy-fixture','confirm_delete':True},format='json').status_code==400
    assert ProviderCredentialSecret.objects.filter(alias='legacy-fixture').exists()


def test_unbound_delete_needs_confirmation_and_cannot_change_purpose(superadmin_user):
    client=client_for(superadmin_user)
    created=client.post(PATH,command(client.get(PATH).data['configuration_version']),format='json')
    version=created.data['configuration_version']
    assert client.post(PATH,command(version,purpose='research_source',provider_key='openalex'),format='json').status_code==400
    deletion={'expected_version':version,'action':'delete','alias':'legacy-fixture'}
    assert client.post(PATH,deletion,format='json').status_code==400
    assert ProviderCredentialSecret.objects.filter(alias='legacy-fixture').exists()
    assert client.post(PATH,{**deletion,'confirm_delete':True},format='json').status_code==200
    assert not ProviderCredentialSecret.objects.filter(alias='legacy-fixture').exists()


def test_inventory_pages_all_aliases_without_returning_upstream_text(superadmin_user):
    for index in range(51):
        set_provider_secret(alias=f'fixture-{index:03}',purpose='ai_runtime',provider_key='legacy-profile',secret='isolated-value',actor=superadmin_user)
    ProviderCredentialSecret.objects.update(last_test_status='unsafe-upstream-secret',last_test_message='unsafe-upstream-url')
    client=client_for(superadmin_user);first=client.get(PATH);second=client.get(PATH+'?page=2')
    assert len(first.data['secrets'])==50 and first.data['has_next']
    assert len(second.data['secrets'])==1 and not second.data['has_next']
    assert first.data['summary']['configured']==51
    assert first.data['configuration_version']==second.data['configuration_version']
    assert not ({row['alias'] for row in first.data['secrets']} & {row['alias'] for row in second.data['secrets']})
    assert 'unsafe-upstream' not in str(first.data)+str(second.data)


def test_only_current_owner_can_manage_inventory(superadmin_user,admin_user,reader_user):
    for actor in (admin_user,reader_user):
        client=client_for(actor)
        assert client.get(PATH).status_code==403
        assert client.post(PATH,command('0'*64),format='json').status_code==403
        assert client.patch(PATH,{'expected_version':'0'*64},format='json').status_code==403
    client=client_for(superadmin_user);version=client.get(PATH).data['configuration_version']
    client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert client.post(PATH,command(version),format='json').status_code==403
    client.credentials(HTTP_X_EDITOR_OWNER=str(superadmin_user.pk))
    User.objects.filter(pk=superadmin_user.pk).update(token_version=superadmin_user.token_version+1)
    assert client.get(PATH).status_code==403


def test_environment_shadow_is_rejected(superadmin_user,monkeypatch):
    client=client_for(superadmin_user);version=client.get(PATH).data['configuration_version']
    monkeypatch.setenv('AI_CREDENTIAL_LEGACY_FIXTURE','isolated-environment')
    assert client.post(PATH,command(version),format='json').status_code==400
    assert not ProviderCredentialSecret.objects.filter(alias='legacy-fixture').exists()


def test_invalid_binding_document_is_not_treated_as_no_references(superadmin_user):
    client=client_for(superadmin_user);version=client.get(PATH).data['configuration_version']
    SiteSetting.objects.create(key='research_source_registry',value={'adapters':[]},public=False)
    assert client.get(PATH).status_code==400
    assert client.post(PATH,command(version),format='json').status_code==400
    assert not ProviderCredentialSecret.objects.filter(alias='legacy-fixture').exists()
