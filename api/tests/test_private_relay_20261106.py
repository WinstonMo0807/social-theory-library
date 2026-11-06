from dataclasses import replace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from rest_framework.test import APIClient

from catalog.models import SiteSetting, ProviderCredentialSecret
from common.ai_endpoints import public_endpoint
from common.ai_runtime import AICapability, resolve_endpoint
from ingestion.models import AuditEvent
from ingestion.services.ai_client import current_ai_configuration, AIClient
from tests.test_stl4_ai_runtime_configuration_20261025 import body_for, client_for, PATH

pytestmark = pytest.mark.django_db


def test_owner_configures_private_relay_atomically_without_disclosing_credentials(superadmin_user, admin_user, reader_user, settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY = Fernet.generate_key().decode()
    settings.AI_PROVIDER = 'none'
    settings.AI_BASE_URL = ''
    settings.AI_API_KEY = ''
    client = client_for(superadmin_user)
    initial = client.get(PATH).data
    body = body_for(initial)
    row = next(row for row in body['profiles'] if row['capability'] == AICapability.PRIVATE_RESEARCH)
    row.update(enabled=True, provider='openai_compatible', model='relay-deepseek-fixture', credential_alias='private-relay-fixture')
    url = 'https://relay.example.test/api/v1'
    secret = 'isolated-not-a-real-key'
    body['endpoint'] = {'profile_key': row['key'], 'base_url': url}
    body['credential'] = {'profile_key': row['key'], 'alias': row['credential_alias'], 'action': 'set', 'secret': secret}
    with patch('catalog.services.field_enrichment.web._resolve_addresses', return_value={'93.184.216.34'}), patch('httpx.Client.send', side_effect=AssertionError('save must not call relay')):
        assert client.put(PATH, body, format='json', secure=False).status_code == 400
        assert client_for(admin_user).put(PATH, body, format='json', secure=True).status_code == 403
        result = client.put(PATH, body, format='json', secure=True)
    assert result.status_code == 200, result.data
    assert 'no-store' in result['Cache-Control']
    assert url not in str(result.data) and secret not in str(result.data)
    assert secret not in str(list(AuditEvent.objects.values('before', 'after')))
    assert url not in str(list(SiteSetting.objects.values('value')))
    assert secret.encode() not in bytes(ProviderCredentialSecret.objects.get(alias='private-relay-fixture').ciphertext)
    config = current_ai_configuration(AICapability.PRIVATE_RESEARCH)
    assert config.base_url == url[:-3] and config.public_endpoint and config.api_key == secret
    assert not current_ai_configuration(AICapability.LIBRARY_QA).enabled
    assert client_for(reader_user).get(PATH).status_code == 403
    assert APIClient().get(PATH).status_code in {401, 403}
    assert client.put(PATH, body, format='json', secure=True).status_code == 409


def test_relay_rejects_private_network_and_json_mode_is_bounded(settings):
    for url in ['http://example.com', 'https://127.0.0.1', 'https://192.168.5.6', 'https://example.com?key=secret']:
        with pytest.raises(Exception):
            public_endpoint(url)
    settings.AI_PROVIDER = 'none'
    config = replace(current_ai_configuration(AICapability.PRIVATE_RESEARCH), provider='openai_compatible', base_url='https://relay.example.test', model='fixture')
    payload, endpoint = AIClient(config)._request_payload(model='fixture', messages=[{'role':'system','content':'Use provided evidence.'}], schema={'type':'object','properties':{'note':{'type':'string'}}}, task='private_check')
    assert payload['response_format'] == {'type':'json_object'}
    assert 'JSON Schema' in payload['messages'][0]['content'] and 'note' in payload['messages'][0]['content']
    assert payload['max_tokens'] == config.max_output_tokens
    assert endpoint == 'https://relay.example.test/v1/chat/completions'
