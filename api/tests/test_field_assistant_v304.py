from __future__ import annotations

import pytest

from catalog.models import (
    CatalogFieldDecision,
    Contribution,
    KnowledgePublicationEvent,
    Person,
    PublicationBundleItem,
)
from catalog.services.field_assistant import (
    FieldAssistantRequest,
    FieldAssistantService,
)
from ingestion.models import (
    EntityResolutionCandidate,
    MetadataCandidate,
    UploadBatch,
    UploadItem,
)

from .test_resilient_publication_v260 import create_item_with_files


def _upload_item(admin_user, edition):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        source_filename="field-assistant-v304.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
        edition=edition,
        asset=edition.assets.filter(kind="normalized").first(),
    )


@pytest.mark.django_db
def test_author_lookup_aggregates_sources_and_adoption_writes_confirmed_draft(
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="质的研究方法与社会科学研究",
    )
    item = _upload_item(admin_user, edition)
    person = Person.objects.create(
        preferred_name="陈向明",
        sort_name="陈向明",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    entity_candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="陈向明",
        candidate_entity_type="person",
        candidate_entity_id=str(person.pk),
        label="陈向明",
        match_score=0.91,
        match_reasons=["版权页姓名与馆内学者一致"],
        supporting_properties={"contribution_role": Contribution.Role.AUTHOR},
    )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="authors",
        value=["陈向明"],
        source="front_matter_native_v1",
        confidence=0.88,
    )

    service = FieldAssistantService()
    result = service.lookup(
        FieldAssistantRequest(
            object_type="edition",
            object_id=edition.pk,
            field_name="author",
            query="陈向明",
        )
    ).as_dict()

    assert len(result["results"]) == 1
    suggestion = result["results"][0]
    assert suggestion["label"] == "陈向明"
    assert suggestion["source_count"] == 3
    assert suggestion["status_label"] == "建议采用"
    assert "confidence" not in suggestion
    assert "score" not in suggestion

    saved = service.adopt(
        edition_id=edition.pk,
        field_name="author",
        source_type=suggestion["action"]["source_type"],
        source_id=suggestion["action"]["source_id"],
        actor=admin_user,
    )

    assert saved["saved"] is True
    assert Contribution.objects.filter(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    ).exists()
    decision = CatalogFieldDecision.objects.get(edition=edition, field_name="authors")
    assert decision.status == CatalogFieldDecision.Status.CONFIRMED
    entity_candidate.refresh_from_db()
    assert entity_candidate.status == EntityResolutionCandidate.Status.LINKED
    assert not KnowledgePublicationEvent.objects.exists()


@pytest.mark.django_db
def test_adoption_is_atomic_when_field_decision_fails(
    admin_user,
    settings,
    tmp_path,
    monkeypatch,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="事务回滚测试",
    )
    item = _upload_item(admin_user, edition)
    person = Person.objects.create(
        preferred_name="待回滚作者",
        sort_name="待回滚作者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name=person.preferred_name,
        candidate_entity_type="person",
        candidate_entity_id=str(person.pk),
        label=person.preferred_name,
        supporting_properties={"contribution_role": Contribution.Role.AUTHOR},
    )

    def fail_decision(*args, **kwargs):
        raise RuntimeError("forced field decision failure")

    monkeypatch.setattr(
        "catalog.services.field_assistant.service.record_edition_field_decision",
        fail_decision,
    )
    with pytest.raises(RuntimeError, match="forced field decision failure"):
        FieldAssistantService().adopt(
            edition_id=edition.pk,
            field_name="author",
            source_type="entity_resolution",
            source_id=candidate.pk,
            actor=admin_user,
        )

    candidate.refresh_from_db()
    assert candidate.status == EntityResolutionCandidate.Status.PROPOSED
    assert not Contribution.objects.filter(edition=edition, person=person).exists()


@pytest.mark.django_db
def test_rejected_person_candidate_is_feedback_only(
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="拒绝候选测试",
    )
    item = _upload_item(admin_user, edition)
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="错误人物",
        candidate_entity_type="person_draft",
        label="错误人物",
        supporting_properties={"contribution_role": Contribution.Role.AUTHOR},
    )

    result = FieldAssistantService().reject(
        edition_id=edition.pk,
        field_name="author",
        source_type="entity_resolution",
        source_id=candidate.pk,
        actor=admin_user,
        reason="不是此人",
    )

    candidate.refresh_from_db()
    assert result["rejected"] is True
    assert candidate.status == EntityResolutionCandidate.Status.REJECTED
    assert not Contribution.objects.filter(edition=edition).exists()
    assert not CatalogFieldDecision.objects.filter(edition=edition).exists()
    assert not KnowledgePublicationEvent.objects.exists()


@pytest.mark.django_db
def test_inline_person_creation_is_linked_but_remains_draft_until_publication(
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="新建学者测试",
    )

    created = FieldAssistantService().create_and_link(
        edition_id=edition.pk,
        field_name="author",
        label="馆内尚无学者",
        actor=admin_user,
        details={"original_name": "New Scholar"},
    )

    person = Person.objects.get(pk=created["entity"]["id"])
    assert person.authority_status == Person.AuthorityStatus.DRAFT
    assert person.scholar_profile.editorial_status == "draft"
    assert Contribution.objects.filter(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        approved=True,
    ).exists()
    assert PublicationBundleItem.objects.filter(
        bundle_id=created["bundle_id"],
        object_type="person",
        object_id=person.pk,
        action=PublicationBundleItem.Action.CREATE,
    ).exists()
    assert not KnowledgePublicationEvent.objects.exists()


@pytest.mark.django_db
def test_inline_creation_requires_duplicate_confirmation(
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="重复实体测试",
    )
    Person.objects.create(
        preferred_name="社会资本研究者",
        sort_name="社会资本研究者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )

    with pytest.raises(ValueError, match="馆内已有相近对象"):
        FieldAssistantService().create_and_link(
            edition_id=edition.pk,
            field_name="author",
            label="社会资本研究者",
            actor=admin_user,
        )

    assert Person.objects.filter(preferred_name="社会资本研究者").count() == 1


@pytest.mark.django_db
def test_field_assistant_api_requires_editor_and_adopts_author(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized_asset = create_item_with_files(
        settings,
        tmp_path,
        title="字段助手接口测试",
    )
    item = _upload_item(admin_user, edition)
    person = Person.objects.create(
        preferred_name="接口作者",
        sort_name="接口作者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name=person.preferred_name,
        candidate_entity_type="person",
        candidate_entity_id=str(person.pk),
        label=person.preferred_name,
        supporting_properties={"contribution_role": Contribution.Role.AUTHOR},
    )
    payload = {
        "object_type": "edition",
        "object_id": str(edition.pk),
        "field_name": "author",
        "query": person.preferred_name,
    }

    denied = api_client.post("/api/catalog/admin/field-assistant/lookup/", payload, format="json")
    assert denied.status_code in {401, 403}

    api_client.force_authenticate(admin_user)
    lookup = api_client.post("/api/catalog/admin/field-assistant/lookup/", payload, format="json")
    assert lookup.status_code == 200
    assert len(lookup.data["results"]) == 1
    assert "confidence" not in lookup.data["results"][0]

    adopted = api_client.post(
        "/api/catalog/admin/field-assistant/adopt/",
        {
            "edition_id": str(edition.pk),
            "field_name": "author",
            "source_type": "entity_resolution",
            "source_id": str(candidate.pk),
        },
        format="json",
    )
    assert adopted.status_code == 200
    assert adopted.data["saved"] is True
    assert Contribution.objects.filter(edition=edition, person=person, approved=True).exists()
