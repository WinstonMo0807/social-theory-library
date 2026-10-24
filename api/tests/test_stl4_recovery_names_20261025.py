"""Recovery-name acceptance definitions, not run during development."""
from uuid import uuid4
import pytest
from rest_framework.test import APIClient
from catalog.models import Work, Edition, EditorialRevision, RecycleEntry
from catalog.recycle_workspace import detail
from catalog.services.recycle import recycle_object
from catalog.services.editorial_revision import create_editorial_revision
from ingestion.models import AuditEvent, FieldLock


def setup_pair(admin_user):
    source=Work.objects.create(title="同名但独立的作品")
    peer=Work.objects.create(title=source.title)
    edition=Edition.objects.create(work=source,version_label="原保留版本")
    entry=recycle_object(source,actor=admin_user,kind="work",name=source.title)
    return source,peer,edition,entry


def command(source,actor,target="restored",new_name="明确区分的新标题"):
    preview=detail("work",source.pk,actor,check_files=True)
    row=preview if target=="restored" else preview["names"]["results"][0]
    return {"request_id":str(uuid4()),"kind":"work","object_id":str(source.pk),"confirmed":True,"expected_version":preview["version"],
        "rename":{"target":target,"object_id":row["object_id"],"expected_version":row["rename"]["version"],"new_name":new_name}}


def send(actor,values):
    client=APIClient();client.force_authenticate(actor)
    return client.post("/api/catalog/admin/recycle/",values,format="json",HTTP_X_EDITOR_OWNER=str(actor.pk))


@pytest.mark.django_db
@pytest.mark.parametrize("target",["restored","existing"])
def test_explicit_rename_preserves_both_identities_and_receipt(admin_user,target):
    source,peer,edition,entry=setup_pair(admin_user)
    values=command(source,admin_user,target)
    response=send(admin_user,values)
    assert response.status_code==200 and response.data["public_restored"] is False
    source.refresh_from_db();peer.refresh_from_db();edition.refresh_from_db();entry.refresh_from_db()
    assert source.title==("明确区分的新标题" if target=="restored" else "同名但独立的作品")
    assert peer.title==("明确区分的新标题" if target=="existing" else "同名但独立的作品")
    assert edition.work_id==source.pk and edition.state!="published" and entry.restored_at
    assert send(admin_user,values).data==response.data
    assert AuditEvent.objects.filter(action="recovery.renamed",request_id=values["request_id"]).count()==1
    revision=EditorialRevision.objects.get(idempotency_key=f"recovery-name:{values['request_id']}")
    assert revision.patch=={"title":"明确区分的新标题"}


@pytest.mark.django_db
def test_existing_draft_or_public_state_blocks_without_restoring(admin_user):
    source,peer,_,entry=setup_pair(admin_user)
    values=command(source,admin_user,"existing")
    draft=create_editorial_revision(target_type="work",target_id=peer.pk,patch={"title":"未完成的人工编辑"},actor=admin_user,idempotency_key=f"prior:{uuid4()}")
    assert send(admin_user,values).status_code==409
    draft.refresh_from_db();entry.refresh_from_db();peer.refresh_from_db()
    assert draft.status=="draft" and entry.restored_at is None and peer.title==source.title
    assert not detail("work",source.pk,admin_user)["names"]["results"][0]["rename"]["allowed"]
    draft.status="superseded";draft.save()
    Edition.objects.create(work=peer,state="published")
    assert not detail("work",source.pk,admin_user)["names"]["results"][0]["rename"]["allowed"]
    assert send(admin_user,command(source,admin_user,"existing")).status_code==409
    entry.refresh_from_db();assert entry.restored_at is None


@pytest.mark.django_db
def test_rename_target_scope_and_failure_rollback(admin_user,reader_user):
    source,peer,_,entry=setup_pair(admin_user)
    other=Work.objects.create(title="另一身份")
    invalid=command(source,admin_user,"existing");invalid["rename"]["object_id"]=str(other.pk)
    assert send(admin_user,invalid).status_code==409
    assert send(admin_user,command(source,admin_user,new_name=other.title)).status_code==409
    invalid=command(source,admin_user);invalid["rename"]["patch"]={"state":"published"}
    assert send(admin_user,invalid).status_code==400
    invalid=command(source,admin_user);invalid["keep_separate"]=True
    assert send(admin_user,invalid).status_code==400
    assert send(reader_user,command(source,admin_user)).status_code==403
    entry.refresh_from_db();source.refresh_from_db();peer.refresh_from_db()
    assert entry.restored_at is None and source.title==peer.title
    assert not AuditEvent.objects.filter(action="recovery.renamed",object_id=str(source.pk)).exists()


@pytest.mark.django_db
def test_locked_work_title_and_later_draft_are_preserved(admin_user):
    source,_,edition,entry=setup_pair(admin_user)
    values=command(source,admin_user)
    lock=FieldLock.objects.create(edition=edition,field_name="title",locked_by=admin_user,locked_value=source.title,reason="已人工确认")
    assert send(admin_user,values).status_code==409
    entry.refresh_from_db();lock.refresh_from_db()
    assert entry.restored_at is None and lock.locked_value==source.title
    assert detail("work",source.pk,admin_user)["rename"]["allowed"] is False
