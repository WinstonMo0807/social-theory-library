"""Deferred review receipts, stale decisions and retained manual evidence."""
from uuid import uuid4
import pytest

from catalog.models import EvidenceSnippet, TheoryReviewTask, WorkNodeRelation
from catalog.theory_review_commands import review_version
from catalog.theory_system_views import AdminTheoryReviewActionView
from ingestion.models import AuditEvent
from .test_stl4_material_relation_candidates_20261024 import candidate, material
from .test_stl4_person_node_directory_20261024 import node

pytestmark = pytest.mark.django_db
ROOT = "/api/catalog/admin/theory-system/review-tasks/"


def headers(actor, key):
    return {"HTTP_X_EDITOR_OWNER":str(actor.pk), "HTTP_IDEMPOTENCY_KEY":str(key)}


def test_retired_review_replay_preserves_original_decisions(api_client, admin_user):
    task=candidate(material(),node())
    api_client.force_authenticate(admin_user)
    key=uuid4()
    for action in ["defer","defer","reject","confirm"]:
        response=api_client.post(f"{ROOT}{task.pk}/action/",{"action":action,"edit_version":review_version(task)},format="json",**headers(admin_user,key))
        assert response.status_code==409 and response.data["code"]=="legacy_academic_candidate_retired"
    task.refresh_from_db()
    assert task.status=="pending" and not AuditEvent.objects.filter(pk=key).exists()


def test_cancel_receipt_owner_readonly_and_delete_boundaries(api_client, admin_user, reader_user):
    task=candidate(material(),node()); key=uuid4()
    api_client.force_authenticate(admin_user)
    data={"action":"delete","edit_version":review_version(task)}
    receipt=f"{ROOT}commands/{key}/"
    stopped=api_client.post(receipt,{"action":"cancel_pending"},format="json",**headers(admin_user,key))
    assert stopped.status_code == 200 and stopped.data["state"] == "cancelled"
    assert api_client.post(f"{ROOT}{task.pk}/action/",data,format="json",**headers(admin_user,key)).status_code == 409
    assert TheoryReviewTask.objects.filter(pk=task.pk).exists()
    assert api_client.get(receipt,HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403
    assert api_client.post(ROOT,{},format="json").status_code == 405
    assert api_client.patch(f"{ROOT}{task.pk}/",{"status":"confirmed"},format="json").status_code == 405
    assert api_client.delete(f"{ROOT}{task.pk}/").status_code == 405
    applied=uuid4()
    result=api_client.post(f"{ROOT}{task.pk}/action/",data,format="json",**headers(admin_user,applied))
    assert result.status_code == 409 and TheoryReviewTask.objects.filter(pk=task.pk).exists()
    assert api_client.get(f"{ROOT}commands/{applied}/",HTTP_X_EDITOR_OWNER=str(admin_user.pk)).status_code == 404
    api_client.force_authenticate(reader_user)
    assert api_client.get(f"{ROOT}commands/{applied}/",HTTP_X_EDITOR_OWNER=str(reader_user.pk)).status_code == 403


def test_retired_confirmation_preserves_reviewed_relation_evidence(api_client,admin_user):
    current,file=node(),material()
    original=candidate(file,current,status="rejected")
    relation=WorkNodeRelation.objects.create(work=file.edition.work,node=current,role="general_mention",status="published",source="人工核对",reviewed_by=admin_user)
    snippet=EvidenceSnippet.objects.create(work=file.edition.work,file=file,node=current,work_node_relation=relation,page_number=2,
        quote="已人工校正的原文",review_status="approved",reviewed_by=admin_user)
    source=TheoryReviewTask.objects.create(task_type="new_node",work=file.edition.work,file=file,evidence_pages=[2],evidence_text="新的自动摘录")
    api_client.force_authenticate(admin_user)
    response=api_client.post(f"{ROOT}{source.pk}/action/",{"action":"confirm","edit_version":review_version(source)},format="json",**headers(admin_user,uuid4()))
    assert response.status_code==409
    relation.refresh_from_db();snippet.refresh_from_db();original.refresh_from_db()
    assert relation.status=="published" and relation.source=="人工核对"
    assert snippet.quote=="已人工校正的原文" and snippet.review_status=="approved"
    assert original.status=="rejected"
    assert TheoryReviewTask.objects.filter(task_type="work_node",file=file,candidate_node=current).count()==1


def test_unsupported_task_cannot_be_falsely_confirmed(api_client, admin_user):
    task=TheoryReviewTask.objects.create(task_type="node_relation",candidate_node=node())
    api_client.force_authenticate(admin_user)
    result=api_client.post(f"{ROOT}{task.pk}/action/",{"action":"confirm","edit_version":review_version(task)},format="json",**headers(admin_user,uuid4()))
    assert result.status_code == 409 and result.data["code"] == "legacy_academic_candidate_retired"
    task.refresh_from_db()
    assert task.status == "pending"


def test_aggregators_keep_decisions_in_the_versioned_original_form():
    from catalog.services.candidate_decision_protocol import attach_candidate_action_descriptors
    task_id=uuid4()
    payload=attach_candidate_action_descriptors({"id":str(task_id),"decision_url":f"/catalog/admin/theory-system/review-tasks/{task_id}/action/",
        "available_actions":["accept","reject"],"action_payloads":{"accept":{"action":"confirm"}},"evidence_count":1})
    assert payload["decision_url"] is None and payload["available_actions"] == ["inspect","review_task"]
    assert payload["action_payloads"] == {}
    navigation=payload["action_descriptors"][1]
    assert navigation["method"] == "NAVIGATE" and f"review_task={task_id}" in navigation["endpoint"]
