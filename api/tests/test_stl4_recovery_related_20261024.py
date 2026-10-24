"""Deferred acceptance definitions; intentionally not executed during development."""
from uuid import uuid4
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import Work, Edition, RecycleEntry
from catalog.recycle_workspace import detail
from catalog.services.recycle import recycle_object
from ingestion.models import AuditEvent


@pytest.mark.django_db
def test_paged_dependencies_history_and_private_boundaries(admin_user, reader_user):
    work=Work.objects.create(title="关联页原作品")
    Edition.objects.bulk_create([Edition(work=work,version_label=str(index)) for index in range(25)])
    stamp=timezone.now()
    AuditEvent.objects.bulk_create([AuditEvent(actor=admin_user,action="example.change",object_type="catalog.work",
        object_id=work.pk.hex if index%2 else str(work.pk),after={"private_note":"不返回正文"}) for index in range(35)])
    client=APIClient();client.force_authenticate(admin_user)
    base=f"/api/catalog/admin/recycle/work/{work.pk}/related/"
    first=client.get(base,{"relation":"reverse:edition:work"})
    assert first.status_code==200 and first.data["count"]==25 and len(first.data["dependencies"])==20
    second=client.get(base,{"relation":"reverse:edition:work","page":2})
    assert len(second.data["dependencies"])==5
    assert not {row["object_id"] for row in first.data["dependencies"]}&{row["object_id"] for row in second.data["dependencies"]}
    assert all(row["destination"].startswith(f"/admin/library/works/{work.pk}?edition=") for row in second.data["dependencies"])
    history=client.get(base,{"category":"history"})
    assert history.data["count"]==35 and len(history.data["history"])==20
    assert "private_note" not in str(history.data) and "不返回正文" not in str(history.data)
    assert client.get(base,{"category":"history","as_of":stamp.isoformat()}).data["count"]==0
    assert client.get(base+"?page=1&page=2").status_code==400
    assert client.get(base,{"relation":"reader_notes"}).status_code==400
    assert client.get(base,{"page":900}).status_code==400
    client.force_authenticate(reader_user)
    assert client.get(base).status_code==403


@pytest.mark.django_db
def test_same_name_requires_explicit_preserve_identity_and_fresh_preview(admin_user):
    original=Work.objects.create(title="同名作品")
    peer=Work.objects.create(title="同名作品")
    entry=recycle_object(original,actor=admin_user,kind="work",name=original.title)
    client=APIClient();client.force_authenticate(admin_user)
    base="/api/catalog/admin/recycle/";headers={"HTTP_X_EDITOR_OWNER":str(admin_user.pk)}
    preview=detail("work",original.pk,admin_user,check_files=True)
    assert preview["names"]["count"]==1 and preview["destination"]==f"/admin/library/works/{original.pk}"
    command={"kind":"work","object_id":str(original.pk),"request_id":str(uuid4()),"confirmed":True,"expected_version":preview["version"]}
    assert client.post(base,command,format="json",**headers).status_code==409
    peer.title="修改后的独立作品";peer.save()
    assert client.post(base,{**command,"keep_separate":True},format="json",**headers).status_code==409
    peer.title="同名作品";peer.save()
    command.update(expected_version=detail("work",original.pk,admin_user,check_files=True)["version"],keep_separate=True)
    response=client.post(base,command,format="json",**headers)
    assert response.status_code==200 and response.data["restored"] and not response.data["public_restored"]
    peer.refresh_from_db()
    assert peer.title=="同名作品" and Work.objects.filter(pk__in=[original.pk,peer.pk]).count()==2
    assert RecycleEntry.objects.get(pk=entry.pk).restored_at is not None
    assert client.post(base,command,format="json",**headers).data==response.data
