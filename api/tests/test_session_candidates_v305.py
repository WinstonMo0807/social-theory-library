import pytest

from catalog.models import CatalogFieldDecision, CatalogingSession, Contribution, KnowledgePublicationEvent, Person
from catalog.services.cataloging_sessions import open_cataloging_session
from catalog.services.field_assistant import FieldAssistantError, FieldAssistantRequest, FieldAssistantService
from catalog.services.research.context import build_research_context
from catalog.services.research.orchestrator import ResearchOrchestrator
from ingestion.models import DecisionLog, EntityResolutionCandidate, UploadItem
from ingestion.services.entity_resolution_decisions import decide_entity_resolution, revert_entity_resolution_decision


pytestmark = pytest.mark.django_db


def session(admin_user):
    return open_cataloging_session(actor=admin_user, source_type="manual", title="手工编目的作品")[0]


def candidate(session, name="人工核对的人物", **kwargs):
    return EntityResolutionCandidate.objects.create(
        cataloging_session=session, target_type="person", source_name=name, label=name,
        candidate_entity_type="person_draft", supporting_properties={"contribution_role": "author"}, **kwargs,
    )


def test_session_candidate_uses_field_assistant_without_upload(admin_user):
    active = session(admin_user)
    row = candidate(active)
    service = FieldAssistantService()
    lookup = service.lookup(FieldAssistantRequest(object_type="edition", object_id=active.edition_id, field_name="author"))
    assert lookup.results[0]["action"]["source_id"] == str(row.pk)
    assert not Person.objects.exists()
    saved = service.adopt(edition_id=active.edition_id, field_name="author", source_type="entity_resolution", source_id=row.pk, actor=admin_user)
    assert saved["saved"]
    row.refresh_from_db()
    assert row.status == "create_draft"
    assert Contribution.objects.filter(edition_id=active.edition_id, approved=True).count() == 1
    assert CatalogFieldDecision.objects.get(edition_id=active.edition_id, field_name="authors").status == "confirmed"
    assert Person.objects.get(pk=row.candidate_entity_id).authority_status == "draft"
    assert not UploadItem.objects.exists()
    assert not KnowledgePublicationEvent.objects.exists()
    service.adopt(edition_id=active.edition_id, field_name="author", source_type="entity_resolution", source_id=row.pk, actor=admin_user)
    assert Person.objects.count() == 1
    assert Contribution.objects.filter(edition_id=active.edition_id).count() == 1


def test_other_session_same_name_is_not_rejected(admin_user):
    first, second = session(admin_user), session(admin_user)
    chosen, other = candidate(first), candidate(second)
    decide_entity_resolution(chosen, action="create_draft", target_type="person", actor=admin_user)
    other.refresh_from_db()
    assert other.status == "proposed"
    assert not Contribution.objects.filter(edition=second.edition).exists()


def test_same_person_different_role_is_not_a_rejected_sibling(admin_user):
    active = session(admin_user)
    author, translator = candidate(active), candidate(active)
    translator.supporting_properties = {"contribution_role": "translator"}
    translator.save()
    decide_entity_resolution(author, action="create_draft", target_type="person", actor=admin_user)
    translator.refresh_from_db()
    assert translator.status == "proposed"


def test_cross_edition_field_adoption_is_rejected(admin_user):
    first, second = session(admin_user), session(admin_user)
    row = candidate(first)
    with pytest.raises(FieldAssistantError, match="不属于"):
        FieldAssistantService().adopt(edition_id=second.edition_id, field_name="author", source_type="entity_resolution", source_id=row.pk, actor=admin_user)
    assert not Person.objects.exists()


def test_session_decision_reversal_uses_same_audited_service(admin_user):
    active = session(admin_user)
    row = candidate(active)
    decided = decide_entity_resolution(row, action="create_draft", target_type="person", actor=admin_user)
    repeated = decide_entity_resolution(decided.candidate, action="create_draft", target_type="person", actor=admin_user)
    assert repeated.idempotent
    log = DecisionLog.objects.get(resolution_candidate=row, reverts_decision__isnull=True)
    result = revert_entity_resolution_decision(log, actor=admin_user, reason="人工撤销")
    assert result.candidate.status == "proposed"
    assert not Contribution.objects.filter(edition=active.edition).exists()
    assert not UploadItem.objects.exists()


def test_closed_session_candidate_cannot_be_adopted(admin_user):
    active = session(admin_user)
    row = candidate(active)
    CatalogingSession.objects.filter(pk=active.pk).update(status="abandoned")
    with pytest.raises(FieldAssistantError, match="不能修改"):
        FieldAssistantService().adopt(edition_id=active.edition_id, field_name="author", source_type="entity_resolution", source_id=row.pk, actor=admin_user)
    assert not Person.objects.exists()


def test_manual_research_results_persist_and_reuse_candidates(admin_user):
    active = session(admin_user)
    context = build_research_context(active.edition, active_step="contributors")
    group = {"entity_type": "person", "field": "contributors.authors", "results": [{
        "id": "authority-example", "label": "外部人物资料", "candidate_group": "authority",
        "provider": "authority-fixture", "evidence_status": "external_evidence", "available_actions": ["create_draft"],
    }]}
    ResearchOrchestrator._persist_intake_entity_candidates(context=context, item=None, groups=[group], actor=admin_user)
    ResearchOrchestrator._persist_intake_entity_candidates(context=context, item=None, groups=[group], actor=admin_user)
    row = EntityResolutionCandidate.objects.get(cataloging_session=active)
    assert row.status == "proposed"
    assert group["results"][0]["review_candidate_id"] == str(row.pk)
    assert f"cataloging-sessions/{active.pk}/" in group["results"][0]["decision_url"]
    assert not UploadItem.objects.exists()
    assert not Person.objects.exists()


def test_session_candidate_endpoint_rejects_wrong_session(api_client, admin_user):
    first, second = session(admin_user), session(admin_user)
    row = candidate(first)
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/cataloging-sessions/{second.pk}/candidates/{row.pk}/decision/"
    response = api_client.post(url, {"action": "create_draft", "target_type": "person"}, format="json")
    assert response.status_code == 404
    url = f"/api/catalog/admin/cataloging-sessions/{first.pk}/candidates/{row.pk}/decision/"
    response = api_client.post(url, {"action": "create_draft", "target_type": "person"}, format="json")
    assert response.status_code == 200
    assert response["Cache-Control"] == "private, no-store"
