"""Service-check recovery acceptance; intentionally not run in development."""
from uuid import uuid4
from unittest.mock import patch
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import HealthCheckRun
from ingestion.models import AuditEvent

pytestmark=pytest.mark.django_db


def client_for(actor):
    client=APIClient();client.force_authenticate(actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return client


def test_cancel_fences_late_service_request_without_connecting(admin_user):
    client=client_for(admin_user);identifier=uuid4()
    receipt=f"/api/catalog/admin/local-services/receipts/{identifier}/"
    with patch('catalog.local_services._check',side_effect=AssertionError('No service calls')):
        assert client.get(receipt).status_code==404
        response=client.post(receipt,{"action":"cancel_pending"},format='json')
        assert response.status_code==200 and response.data['state']=='cancelled'
        values={"request_id":str(identifier),"service_id":"ocr","configuration_version":"a"*64}
        assert client.post('/api/catalog/admin/local-services/check/',values,format='json').status_code==409
        assert client.get(receipt).data['state']=='cancelled'
        assert client.post(receipt,{"action":"cancel_pending"},format='json').data==response.data
        assert client.post(receipt,{"action":"cancel_pending","force":True},format='json').status_code==400
    assert not HealthCheckRun.objects.filter(pk=identifier).exists()
    assert AuditEvent.objects.filter(action='local-service.cancelled',request_id=str(identifier)).count()==1


def test_prior_result_is_read_without_current_configuration_or_service_call(admin_user,reader_user):
    identifier=uuid4()
    HealthCheckRun.objects.create(pk=identifier,probe_key='local-services:removed-provider',capability='metadata',status='failed',source='manual',
        started_at=timezone.now(),completed_at=timezone.now(),initiated_by=admin_user,
        details={"service_status":"quota_exhausted","configuration_version":"b"*64,"safe_detail":"原检查记录","raw_response":"不返回"})
    client=client_for(admin_user);receipt=f"/api/catalog/admin/local-services/receipts/{identifier}/"
    with patch('catalog.local_services._check',side_effect=AssertionError('No service calls')),patch('catalog.local_services.service_definitions',side_effect=AssertionError('No configuration reads')):
        response=client.get(receipt)
        assert response.status_code==200 and response.data['state']=='applied'
        assert response.data['observation']['service_id']=='removed-provider'
        assert 'raw_response' not in str(response.data) and '不返回' not in str(response.data)
        assert client.post(receipt,{"action":"cancel_pending"},format='json').data==response.data
    assert not AuditEvent.objects.filter(action='local-service.cancelled',request_id=str(identifier)).exists()
    assert client_for(reader_user).get(receipt).status_code==403
    HealthCheckRun.objects.filter(pk=identifier).update(initiated_by=reader_user)
    assert client.get(receipt).status_code==409
    client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert client.get(receipt).status_code==403
