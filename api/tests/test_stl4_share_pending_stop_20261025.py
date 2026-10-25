"""Deferred checks for stopping unknown sharing commands without revoking applied grants."""
from datetime import timedelta
from uuid import uuid4
from cryptography.fernet import Fernet
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.models import User
from reading import reader_shares, research, share_scope
from reading.knowledge_models import KnowledgeSaveReceipt
from reading.sharing_models import ReaderShare
from reading.sharing_views import ShareCreateInput

pytestmark=pytest.mark.django_db
PATH='/api/reading/shares/receipt/'


@pytest.fixture(autouse=True)
def isolated_key(settings):
    settings.PRIVATE_DATA_ENCRYPTION_KEY=Fernet.generate_key().decode()


def client_for(user):
    client=APIClient();client.force_authenticate(user);client.credentials(HTTP_X_READER_OWNER=str(user.pk));return client


def pending(request_id):
    return {'request_id':str(request_id),'confirmed':True,'preview_hash':'0'*64,'source_kind':'research','source_id':str(uuid4()),
        'expected_version':'isolated-version','questions':['project'],'materials':[],'notes':[],'message':'', 'destination':'proposal','expires_days':30}


def test_stop_is_durable_idempotent_and_prevents_late_grant(reader_user):
    client=client_for(reader_user);identifier=uuid4();command={'request_id':str(identifier),'action':'cancel_pending'}
    stopped=client.post(PATH,command,format='json')
    assert stopped.status_code==200 and stopped.data['state']=='cancelled' and stopped.data['receipt'] is None
    assert 'no-store' in stopped['Cache-Control']
    assert client.post(PATH,command,format='json').data==stopped.data
    assert KnowledgeSaveReceipt.objects.filter(user=reader_user,request_id=identifier).count()==1
    assert client.post('/api/reading/shares/',pending(identifier),format='json').status_code==409
    assert not ReaderShare.objects.filter(user=reader_user,request_id=identifier).exists()
    assert client.get(PATH,{'request_id':str(identifier)}).status_code==409


def test_stop_returns_original_receipt_and_does_not_revoke_applied_grant(reader_user):
    client=client_for(reader_user);identifier=uuid4();body=pending(identifier)
    serializer=ShareCreateInput(data=body);serializer.is_valid(raise_exception=True)
    values=serializer.validated_data
    row=ReaderShare.objects.create(user=reader_user,request_id=identifier,source_kind='research',source_id=values['source_id'],
        destination='proposal',expires_at=timezone.now()+timedelta(days=1),data_ciphertext=research.pack({'request_fingerprint':share_scope.digest(values)}))
    result=client.post(PATH,{'request_id':str(identifier),'action':'cancel_pending'},format='json')
    assert result.status_code==200 and result.data['state']=='applied'
    assert result.data['receipt']['share']['id']==str(row.pk)
    row.refresh_from_db();assert row.revoked_at is None
    assert client.post('/api/reading/shares/',body,format='json').data['share']['id']==str(row.pk)
    assert not KnowledgeSaveReceipt.objects.filter(user=reader_user,request_id=identifier).exists()


def test_stop_is_owner_scoped_and_rejects_changed_session(reader_user,admin_user):
    identifier=uuid4();client=client_for(reader_user)
    client.credentials(HTTP_X_READER_OWNER=str(admin_user.pk))
    assert client.post(PATH,{'request_id':str(identifier),'action':'cancel_pending'},format='json').status_code==403
    client.credentials(HTTP_X_READER_OWNER=str(reader_user.pk))
    assert client.post(PATH,{'request_id':str(identifier),'action':'cancel_pending'},format='json').status_code==200
    assert not reader_shares.stopped_request(admin_user,identifier)
    User.objects.filter(pk=reader_user.pk).update(token_version=reader_user.token_version+1)
    assert client.get(PATH,{'request_id':str(identifier)}).status_code==403


def test_other_receipt_namespace_cannot_be_overwritten(reader_user):
    identifier=uuid4();client=client_for(reader_user)
    KnowledgeSaveReceipt.objects.create(user=reader_user,request_id=identifier,target_key='different-operation',fingerprint='1'*64,applied_saved=True)
    assert client.post(PATH,{'request_id':str(identifier),'action':'cancel_pending'},format='json').status_code==409
    assert KnowledgeSaveReceipt.objects.get(user=reader_user,request_id=identifier).target_key=='different-operation'
