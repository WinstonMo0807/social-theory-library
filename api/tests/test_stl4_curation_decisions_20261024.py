"""Deferred M07 acceptance; authored but not executed during development."""
from uuid import uuid4
import pytest
from catalog.models import Discipline, EnrichmentCandidate
from catalog.services.curation_decisions import decision_version
from catalog.services.field_assistant.curation import _identity, _merge, _enrichment
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


def context(client, actor):
    client.force_authenticate(actor); client.credentials(HTTP_X_EDITOR_OWNER=str(actor.pk))
    target = Discipline.objects.create(name="待核对的合成学科")
    candidate = EnrichmentCandidate.objects.create(target_type="discipline", target_id=target.pk,
        field_name="foreign_name", candidate_kind="factual", proposed_value="Synthetic field", current_value="",
        fingerprint=uuid4().hex, conflict_group="foreign_name", policy_version="deferred-fixture", extraction_version="fixture")
    path = f"/api/catalog/admin/curation/discipline/{target.pk}/field-decisions/"
    body = {"request_id":str(uuid4()), "expected_version":decision_version("discipline", target, "foreign_name"),
        "field_name":"foreign_name", "source_type":"enrichment", "source_id":str(candidate.pk), "action":"reject", "reason":"来源身份尚未确认"}
    return target,candidate,path,body


def test_replay_and_stop_return_original_decision_without_changing_the_target(api_client, admin_user):
    target,candidate,path,body=context(api_client,admin_user)
    first=api_client.post(path,body,format="json")
    assert first.status_code==200,first.data
    assert api_client.post(path,body,format="json").data==first.data
    assert api_client.get(f"{path}commands/{body['request_id']}/").data==first.data
    assert api_client.post(f"{path}commands/{body['request_id']}/",{"action":"cancel_pending"},format="json").data==first.data
    assert AuditEvent.objects.filter(action="curation_assistant.command",request_id=body["request_id"]).count()==1
    target.refresh_from_db();candidate.refresh_from_db()
    assert target.foreign_name=="" and candidate.status=="rejected"
    assert api_client.post(path,{**body,"reason":"不能用原编号改写理由"},format="json").status_code==409


def test_stop_fences_late_write_and_version_change_preserves_pending_candidate(api_client, admin_user):
    target,candidate,path,body=context(api_client,admin_user)
    assert api_client.post(f"{path}commands/{body['request_id']}/",{"action":"cancel_pending"},format="json").data["state"]=="cancelled"
    assert api_client.post(path,body,format="json").status_code==409
    body["request_id"]=str(uuid4());target.foreign_name="人工填写";target.save()
    assert api_client.post(path,body,format="json").status_code==409
    candidate.refresh_from_db();assert candidate.status=="pending"


def test_cross_target_wrong_owner_and_reader_cannot_decide_or_read_receipt(api_client, admin_user, reader_user):
    target,candidate,path,body=context(api_client,admin_user)
    other=Discipline.objects.create(name="另一学科")
    assert api_client.post(path.replace(str(target.pk),str(other.pk)),body,format="json").status_code==404
    api_client.credentials(HTTP_X_EDITOR_OWNER=str(reader_user.pk))
    assert api_client.post(path,body,format="json").status_code==403
    api_client.force_authenticate(reader_user)
    assert api_client.get(f"{path}commands/{body['request_id']}/").status_code==403
    candidate.refresh_from_db();assert candidate.status=="pending"


def test_same_named_records_and_same_values_are_not_one_identity(api_client, admin_user):
    _,candidate,_,_=context(api_client,admin_user)
    other=EnrichmentCandidate.objects.create(target_type=candidate.target_type,target_id=candidate.target_id,
        field_name=candidate.field_name,candidate_kind="factual",proposed_value=candidate.proposed_value,
        fingerprint=uuid4().hex,conflict_group="foreign_name",policy_version="deferred-fixture",extraction_version="fixture")
    rows=[_identity({"id":str(uuid4()),"label":"同名人物"},local=True),_identity({"id":str(uuid4()),"label":"同名人物"},local=True),_enrichment(candidate),_enrichment(other)]
    assert len(_merge(rows))==4
