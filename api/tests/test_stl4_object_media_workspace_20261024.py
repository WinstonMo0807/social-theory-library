"""Deferred M08 acceptance. No browser, image processing or tests run in development."""
from uuid import uuid4
import pytest
from catalog.models import EditorialRevision, KnowledgeNode, MediaRendition, Person, ScholarProfile
from catalog.services.media import ingest_image
from ingestion.models import AuditEvent
from tests.test_media_v305 import picture

pytestmark=pytest.mark.django_db


@pytest.fixture(params=["scholar_profile","knowledge_node"])
def media_context(request,settings,tmp_path,api_client,admin_user):
    settings.MEDIA_ROOT=tmp_path;settings.THEORY_SYSTEM_ENABLED=True
    kind=request.param
    if kind=="scholar_profile":
        person=Person.objects.create(preferred_name="合成肖像对象")
        target=ScholarProfile.objects.create(person=person,slug="synthetic-portrait",editorial_status="published")
    else:
        target=KnowledgeNode.objects.create(canonical_name_zh="合成理论对象",slug="synthetic-media-node",node_type="concept",status="published")
    media,_=ingest_image(picture(size=(800,1000)),actor=admin_user,metadata={"alt_text":"原图说明"})
    api_client.force_authenticate(admin_user);api_client.credentials(HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    path=f"/api/catalog/admin/media-objects/{kind}/{target.pk}/"
    state=api_client.get(path)
    assert state.status_code==200,state.data
    body={"request_id":str(uuid4()),"expected_version":state.data["version"],"action":"save","slot":state.data["slot"],"media_id":str(media.pk),
        "transform":{"x":0.1,"y":0.1,"width":0.8,"height":0.8,"rotation":90},
        "metadata":{"alt_text":"本次选图说明","source_label":"合成材料","source_url":"","rights":"","license":"","credit":""}}
    return kind,target,media,path,body


def test_crop_replay_and_history_restore_keep_original_and_public_choice(media_context,api_client):
    kind,target,media,path,body=media_context
    original=media.file.read();media.file.close()
    first=api_client.post(path,body,format="json");assert first.status_code==200,first.data
    assert api_client.post(path,body,format="json").data==first.data
    assert AuditEvent.objects.filter(action="media.object_workspace.command",request_id=body["request_id"]).count()==1
    state=api_client.get(path).data
    assert state["current"]["metadata"]["alt_text"]=="本次选图说明"
    assert state["history"]["count"]==1 and state["has_unpublished_changes"]
    revision_id=state["current"]["id"]
    media.refresh_from_db();assert media.alt_text=="原图说明"
    assert media.file.read()==original;media.file.close()
    target.refresh_from_db()
    assert not (target.person.portrait_rendition_id if kind=="scholar_profile" else target.cover_rendition_id)
    clear={"request_id":str(uuid4()),"expected_version":state["version"],"slot":body["slot"],"action":"clear"}
    assert api_client.post(path,clear,format="json").status_code==200
    state=api_client.get(path).data
    restored={"request_id":str(uuid4()),"expected_version":state["version"],"slot":body["slot"],"action":"restore","rendition_id":revision_id}
    assert api_client.post(path,restored,format="json").status_code==200
    assert api_client.get(path).data["current"]["id"]==revision_id
    assert MediaRendition.objects.filter(media=media).count()==3
    assert EditorialRevision.objects.filter(target_type=kind,target_id=target.pk,status="draft").count()==1


def test_stopped_changed_scope_and_reader_cannot_write(media_context,api_client,reader_user):
    _,_,media,path,body=media_context
    command=f"{path}commands/{body['request_id']}/"
    assert api_client.post(command,{"action":"cancel_pending"},format="json").data["state"]=="cancelled"
    assert api_client.post(path,body,format="json").status_code==409
    other={**body,"request_id":str(uuid4()),"slot":"hero" if body["slot"]=="portrait" else "portrait"}
    assert api_client.post(path,other,format="json").status_code==409
    assert not media.renditions.exists()
    api_client.force_authenticate(reader_user);api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.get(command).status_code==403
    assert api_client.post(path,{**body,"request_id":str(uuid4())},format="json").status_code==403


def test_preparing_legacy_image_does_not_select_or_publish_it(media_context,api_client):
    kind,target,_,path,body=media_context
    file=target.person.portrait if kind=="scholar_profile" else target.cover_asset
    file.save("legacy.png",picture(),save=True)
    original=file.read();file.close()
    state=api_client.get(path).data
    command={"request_id":str(uuid4()),"expected_version":state["version"],"slot":body["slot"],"action":"legacy"}
    first=api_client.post(path,command,format="json")
    assert first.status_code==200 and first.data["media"],first.data
    assert api_client.post(path,command,format="json").data==first.data
    assert not EditorialRevision.objects.filter(target_type=kind,target_id=target.pk).exists()
    assert api_client.get(path).data["current"] is None
    assert file.read()==original;file.close()
