"""Deferred M07 acceptance; these cases are not executed during development."""
from uuid import uuid4
import pytest
from catalog.models import Edition, Work, Person
from catalog.services.workspace_edits import workspace_edit_version
from ingestion.models import AuditEvent, FieldLock, MetadataCandidate
from tests.test_workspace_edits_v306 import setup_workspace

pytestmark=pytest.mark.django_db


def context(client, actor):
    edition, _, _=setup_workspace(client, actor)
    client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    return edition, f"/api/catalog/admin/editions/{edition.pk}/field-decisions/"


def data(edition, action="create", **payload):
    return {"request_id":str(uuid4()),"expected_version":workspace_edit_version(edition),"action":action,"field_name":"author",
            "payload":payload or {"label":"恢复请求中的人物","defer_link":True,"allow_possible_duplicate":False}}


def test_create_replay_and_receipt_return_same_identity(api_client, admin_user):
    edition,path=context(api_client,admin_user)
    body=data(edition)
    first=api_client.post(path,body,format="json")
    assert first.status_code==200,first.data
    identity=first.data["result"]["entity"]["id"]
    assert api_client.post(path,body,format="json").data["result"]["entity"]["id"]==identity
    result=api_client.get(f"{path}commands/{body['request_id']}/")
    assert result.status_code==200 and result.data["edition_id"]==str(edition.pk)
    assert result.data["result"]["entity"]["id"]==identity
    assert Person.objects.filter(preferred_name="恢复请求中的人物").count()==1
    assert not edition.contributions.exists()
    stopped=api_client.post(f"{path}commands/{body['request_id']}/",{"action":"cancel_pending"},format="json")
    assert stopped.data["state"]=="applied"


def test_stopped_request_and_changed_book_do_not_create(api_client, admin_user):
    edition,path=context(api_client,admin_user)
    body=data(edition)
    stop=api_client.post(f"{path}commands/{body['request_id']}/",{"action":"cancel_pending"},format="json")
    assert stop.status_code==200 and stop.data["state"]=="cancelled"
    assert api_client.post(path,body,format="json").status_code==409
    body=data(edition)
    FieldLock.objects.create(edition=edition,field_name="title",locked_by=admin_user,locked_value=edition.work.title)
    assert api_client.post(path,body,format="json").status_code==409
    assert not Person.objects.filter(preferred_name="恢复请求中的人物").exists()


def test_reject_once_and_actor_receipt_isolation(api_client, admin_user, reader_user):
    edition,path=context(api_client,admin_user)
    candidate=MetadataCandidate.objects.create(cataloging_session=edition.cataloging_sessions.first(),field_name="title",value="不采用的题名",source="pdf_metadata")
    body={**data(edition,"reject",source_type="metadata",source_id=str(candidate.pk),reason="来源版本不符"),"field_name":"title"}
    first=api_client.post(path,body,format="json")
    assert first.status_code==200,first.data
    assert api_client.post(path,body,format="json").data==first.data
    assert AuditEvent.objects.filter(action="field_assistant.command",request_id=body["request_id"]).count()==1
    api_client.force_authenticate(reader_user);api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(f"{path}commands/{body['request_id']}/").status_code==403


def test_changed_payload_cannot_reuse_create_receipt(api_client, admin_user):
    edition,path=context(api_client,admin_user)
    body=data(edition)
    assert api_client.post(path,body,format="json").status_code==200
    body["payload"]["label"]="不能借旧编号建立另一人物"
    assert api_client.post(path,body,format="json").status_code==409
    assert not Person.objects.filter(preferred_name=body["payload"]["label"]).exists()
