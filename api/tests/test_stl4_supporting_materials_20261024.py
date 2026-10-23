"""Deferred supporting-material acceptance; no tests run in the development phase."""
from uuid import uuid4
import pytest
from catalog.models import Edition, Work, EditionSupportingMaterial
from catalog.supporting_material_views import version

pytestmark=pytest.mark.django_db


def setup(client, actor):
    client.force_authenticate(actor); client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    edition=Edition.objects.create(work=Work.objects.create(title="补充材料的独立版本"),publication_mode="bibliographic")
    return edition,f"/api/catalog/admin/editions/{edition.pk}/supporting-materials/"


def command(edition,**extra):
    return {"request_id":str(uuid4()),"expected_version":version(edition),"action":"create",
            "fields":{"kind":"note","title":"编目核对","note":"仅管理核对的补充说明","url":""},**extra}


def test_create_replay_archive_restore_preserves_original(api_client,admin_user):
    edition,path=setup(api_client,admin_user);body=command(edition)
    first=api_client.post(path,body,format="json");assert first.status_code==200,first.data
    assert api_client.post(path,body,format="json").data==first.data
    row=EditionSupportingMaterial.objects.get(edition=edition)
    archived={key:value for key,value in command(edition,action="archive",material_id=str(row.pk)).items() if key!="fields"}
    assert api_client.post(path,archived,format="json").status_code==200
    row.refresh_from_db();assert row.archived and row.note==body["fields"]["note"]
    assert api_client.get(path).data["count"]==0
    assert api_client.get(path+"?archived=true").data["count"]==1
    restore={**archived,"request_id":str(uuid4()),"expected_version":version(edition),"action":"restore"}
    assert api_client.post(path,restore,format="json").status_code==200
    edition.refresh_from_db();assert edition.state=="draft" and edition.active_catalog_revision_id is None


def test_stopped_late_write_and_stale_version_rejected(api_client,admin_user):
    edition,path=setup(api_client,admin_user);body=command(edition)
    assert api_client.post(f"{path}commands/{body['request_id']}/",{"action":"cancel_pending"},format="json").status_code==200
    assert api_client.post(path,body,format="json").status_code==409
    body=command(edition);other=command(edition)
    assert api_client.post(path,body,format="json").status_code==200
    assert api_client.post(path,other,format="json").status_code==409
    assert EditionSupportingMaterial.objects.filter(edition=edition).count()==1


def test_reader_and_cross_edition_record_isolation(api_client,admin_user,reader_user):
    edition,path=setup(api_client,admin_user)
    result=api_client.post(path,command(edition),format="json").data
    other=Edition.objects.create(work=edition.work,publication_mode="bibliographic")
    payload=command(other,action="update",material_id=result["result"]["id"])
    assert api_client.post(f"/api/catalog/admin/editions/{other.pk}/supporting-materials/",payload,format="json").status_code==404
    api_client.force_authenticate(reader_user);api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(path).status_code==403


@pytest.mark.parametrize("url",["javascript:alert(1)","https://user:password@example.org/file","file:///private/file","ftp://example.org/file"])
def test_unsafe_or_credential_links_rejected(api_client,admin_user,url):
    edition,path=setup(api_client,admin_user)
    assert api_client.post(path,command(edition,fields={"kind":"link","title":"链接","url":url,"note":""}),format="json").status_code==400
    assert not EditionSupportingMaterial.objects.filter(edition=edition).exists()
