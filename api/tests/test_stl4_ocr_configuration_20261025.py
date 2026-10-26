"""Deferred CAS/owner/fence acceptance; no execution during implementation."""
from unittest.mock import patch
import pytest
from rest_framework.test import APIClient
from catalog.models import SiteSetting
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
PATH = '/api/catalog/admin/ocr-runtime/'


@pytest.fixture(autouse=True)
def runtime_environment(settings):
    settings.OCR_REMOTE_API_URL = ''
    settings.OCR_REMOTE_API_KEY = ''
    settings.RAPIDOCR_SERVICE_URL = 'http://ocr.invalid:8001'


def client_for(actor):
    client = APIClient(); client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client


def command(snapshot, **changes):
    return {'expected_version': snapshot['configuration_version'], 'mode': 'nas_only', 'remote_url': '', 'remote_model': '', **changes}


def test_stale_or_duplicate_save_cannot_overwrite_new_configuration(admin_user):
    client = client_for(admin_user); first = client.get(PATH)
    assert first.status_code == 200 and 'no-store' in first['Cache-Control']
    saved = client.put(PATH, command(first.data), format='json')
    assert saved.status_code == 200 and saved.data['configuration_version'] != first.data['configuration_version']
    assert client.put(PATH, command(first.data, mode='nas_preferred'), format='json').status_code == 409
    assert client.get(PATH).data['mode'] == 'nas_only'
    assert AuditEvent.objects.filter(action='ocr_runtime_update').count() == 1


def test_fence_blocks_delayed_save_and_does_not_undo_completed_save(admin_user):
    client = client_for(admin_user); first = client.get(PATH).data
    fenced = client.patch(PATH, {'expected_version': first['configuration_version']}, format='json')
    assert fenced.status_code == 200 and fenced.data['mode'] == first['mode']
    assert client.put(PATH, command(first), format='json').status_code == 409
    saved = client.put(PATH, command(fenced.data), format='json')
    assert saved.status_code == 200
    after = client.patch(PATH, {'expected_version': fenced.data['configuration_version']}, format='json')
    assert after.data['configuration_version'] == saved.data['configuration_version'] and after.data['mode'] == 'nas_only'


def test_remote_mode_requires_complete_configuration_and_explicit_change_acknowledgment(admin_user, settings):
    client = client_for(admin_user); first = client.get(PATH).data
    assert client.put(PATH, command(first, mode='remote_only'), format='json').status_code == 400
    settings.OCR_REMOTE_API_KEY = 'fixture-only-credential'
    first = client.get(PATH).data
    values = command(first, mode='remote_only', remote_url='https://gateway.invalid', remote_model='PP-OCRv6-tiny')
    assert client.put(PATH, values, format='json').status_code == 400
    values['acknowledge_remote'] = True
    result = client.put(PATH, values, format='json')
    assert result.status_code == 200 and result.data['remote_configured'] is True
    assert 'fixture-only-credential' not in str(result.data)


def test_hidden_legacy_address_is_not_echoed_or_erased_when_disabling_remote(admin_user):
    SiteSetting.objects.create(key='ocr_runtime', value={'mode': 'nas_preferred', 'remote_url': 'https://private:fixture@gateway.invalid?token=fixture'}, public=False)
    client = client_for(admin_user); first = client.get(PATH).data
    assert first['remote_url_redacted'] and first['remote_url'] == '' and 'token=fixture' not in str(first)
    result = client.put(PATH, command(first), format='json')
    assert result.status_code == 200 and result.data['mode'] == 'nas_only'
    assert 'token=fixture' in SiteSetting.objects.get(key='ocr_runtime').value['remote_url']
    assert 'token=fixture' not in str(list(AuditEvent.objects.filter(action='ocr_runtime_update').values('before','after')))


def test_reader_or_changed_owner_cannot_read_or_write_configuration(admin_user, reader_user):
    assert client_for(reader_user).get(PATH).status_code == 403
    client = client_for(admin_user); first = client.get(PATH).data
    client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert client.get(PATH).status_code == 403
    assert client.put(PATH, command(first), format='json').status_code == 403
    assert client.patch(PATH, {'expected_version': first['configuration_version']}, format='json').status_code == 403


def test_audit_failure_rolls_back_original_setting_and_get_never_probes(admin_user):
    client = client_for(admin_user)
    with patch('ingestion.services.health.ocr_service_health', side_effect=AssertionError('GET cannot load OCR')):
        first = client.get(PATH).data
    with patch('catalog.ocr_runtime_settings.AuditEvent.objects.create', side_effect=RuntimeError('audit unavailable')):
        assert client.put(PATH, command(first), format='json').status_code == 500
    assert not SiteSetting.objects.filter(key='ocr_runtime').exists()
