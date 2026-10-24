"""Deferred acceptance: cancellation and lookup do not replay original recovery."""
from uuid import uuid4
import pytest
from rest_framework.test import APIClient
from accounts.models import User
from catalog.models import Work,RecycleEntry
from catalog.recycle_workspace import detail
from catalog.services.recycle import recycle_object


@pytest.mark.django_db
def test_cancel_before_late_restore_and_receipt_after_redelete(admin_user,reader_user):
    work=Work.objects.create(title="回执保留的原作品")
    entry=recycle_object(work,actor=admin_user,kind="work",name=work.title)
    client=APIClient();client.force_authenticate(admin_user)
    base="/api/catalog/admin/recycle/";headers={"HTTP_X_EDITOR_OWNER":str(admin_user.pk)}
    command={"request_id":str(uuid4()),"kind":"work","object_id":str(work.pk),"confirmed":True,
        "expected_version":detail("work",work.pk,admin_user,check_files=True)["version"]}
    endpoint=f"{base}receipts/{command['request_id']}/"
    assert client.get(endpoint,**headers).status_code==404
    assert RecycleEntry.objects.get(pk=entry.pk).restored_at is None
    assert client.post(endpoint,{"action":"cancel_pending","kind":"work"},format="json",**headers).status_code==400
    cancelled=client.post(endpoint,{"action":"cancel_pending"},format="json",**headers)
    assert cancelled.status_code==200 and cancelled.data["state"]=="cancelled"
    assert client.post(base,command,format="json",**headers).status_code==409
    assert RecycleEntry.objects.get(pk=entry.pk).restored_at is None
    command["request_id"]=str(uuid4())
    restored=client.post(base,command,format="json",**headers)
    assert restored.status_code==200 and restored.data["restored"]
    work.refresh_from_db();again=recycle_object(work,actor=admin_user,kind="work",name=work.title)
    endpoint=f"{base}receipts/{command['request_id']}/"
    receipt=client.get(endpoint,**headers)
    assert receipt.status_code==200 and receipt.data["state"]=="applied" and receipt.data["result"]==restored.data
    assert client.post(endpoint,{"action":"cancel_pending"},format="json",**headers).data==receipt.data
    assert client.post(base,command,format="json",**headers).data==restored.data
    assert RecycleEntry.objects.get(pk=again.pk).restored_at is None
    other=User.objects.create_user(username="another-recovery-editor",role="admin")
    client.force_authenticate(other)
    assert client.get(endpoint,HTTP_X_EDITOR_OWNER=str(other.pk)).status_code==409
    client.force_authenticate(reader_user)
    assert client.get(endpoint,HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code==403
