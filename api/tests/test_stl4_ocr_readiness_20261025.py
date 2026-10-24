"""Deferred checks: no network, database or model invocation."""
from io import BytesIO
from urllib.error import HTTPError, URLError
from unittest.mock import Mock, patch

import pytest

from catalog.local_services import _check
from catalog.services.system_health import _ocr_probe, ProbeResult
from ingestion.services.health import ocr_service_health


class Reply(BytesIO):
    status = 200


@pytest.mark.parametrize('body,ready', [
    (b'{"available":true,"runtime_verified":true}', True),
    (b'{"available":true,"runtime_verified":false}', False),
    (b'{"available":true}', False),
    (b'{"available":1,"runtime_verified":true}', False),
    (b'not json', False), (b'"' + b'a' * 65537 + b'"', False),
])
def test_normal_ocr_probe_requires_current_runtime_evidence(body, ready):
    with patch('ingestion.services.health.urlopen', return_value=Reply(body)) as call:
        result = ocr_service_health('http://ocr.invalid')
    assert call.call_args.args[0].full_url == 'http://ocr.invalid/ready'
    assert result['reachable'] is True and result['functional'] is ready
    assert set(result) == {'configured', 'reachable', 'functional', 'detail'}


def test_http_not_ready_and_network_failure_are_distinct_and_safe():
    error = HTTPError('http://ocr.invalid', 503, 'not ready', {}, BytesIO(b'private model path'))
    with patch('ingestion.services.health.urlopen', side_effect=error):
        result = ocr_service_health('http://ocr.invalid')
    assert result['reachable'] is True and result['functional'] is False
    assert 'private' not in str(result)
    with patch('ingestion.services.health.urlopen', side_effect=URLError('connection refused')):
        assert ocr_service_health('http://ocr.invalid')['reachable'] is False
    with patch('ingestion.services.health.urlopen', side_effect=AssertionError('no request')):
        assert ocr_service_health('')['configured'] is False


def test_historical_success_cannot_make_current_ocr_ready():
    jobs = Mock()
    jobs.filter.return_value.order_by.return_value.first.return_value = Mock()
    with patch('catalog.services.system_health.ocr_runtime_config', return_value={'nas_url': 'http://ocr.invalid'}), \
         patch('catalog.services.system_health.ocr_service_health', return_value={'reachable': True, 'functional': False}), \
         patch('catalog.services.system_health.ProcessingJob.objects', jobs):
        result = _ocr_probe()
    assert result.reachable is True and result.functional is False and result.productive is True
    assert result.error_code == 'ocr_not_ready'
    probe = Mock(runner=Mock(return_value=ProbeResult(True, True, False, True, 'unready')))
    with patch('catalog.services.system_health.HEALTH_CHECKS', {'ocr': probe}):
        assert _check({'id': 'ocr'})[0] == 'partial'


def test_only_explicit_deep_probe_uses_the_existing_model_probe():
    with patch('ingestion.services.health.urlopen', return_value=Reply(b'{"available":true,"runtime_verified":true}')) as call:
        ocr_service_health('http://ocr.invalid', deep=True, timeout=120)
    assert call.call_args.args[0].full_url == 'http://ocr.invalid/ready?deep=true'
    assert call.call_args.kwargs['timeout'] == 120
