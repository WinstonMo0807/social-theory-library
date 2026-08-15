import pytest

from accounts.models import User
from catalog.models import (
    Contribution,
    DocumentType,
    Edition,
    OrganizationAuthority,
    OrganizationContribution,
    Person,
    PublicationState,
    Work,
)
from ingestion.models import AuditEvent, DecisionLog, EntityResolutionCandidate, UploadBatch, UploadItem
from ingestion.services.reconciliation import persist_resolution_candidates


pytestmark = pytest.mark.django_db


def make_item(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="待审作品")
    edition = Edition.objects.create(work=work, state=PublicationState.DRAFT)
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="candidate.pdf",
    )


def make_editor():
    return User.objects.create_user(
        username="cataloger@example.org",
        email="cataloger@example.org",
        role=User.Role.EDITOR,
        password="Cataloger-Secure-2026",
    )


def decision_url(item, candidate):
    return (
        f"/api/ingestion/items/{item.id}/entity-resolution-candidates/"
        f"{candidate.id}/decision/"
    )


def revert_url(item, decision):
    return f"/api/ingestion/items/{item.id}/entity-resolution-decisions/{decision.id}/revert/"


def test_editor_can_explicitly_link_same_name_person_and_decision_is_idempotent(
    api_client,
    admin_user,
):
    item = make_item(admin_user)
    person = Person.objects.create(
        preferred_name="王明",
        sort_name="王明",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    candidates = persist_resolution_candidates(
        item,
        target_type="person",
        source_name="王明",
    )
    candidate = next(row for row in candidates if row.candidate_entity_id == str(person.id))
    editor = make_editor()
    api_client.force_authenticate(editor)

    response = api_client.post(
        decision_url(item, candidate),
        {
            "action": "link_existing",
            "target_type": "person",
            "target_id": str(person.id),
            "confirm_identity": True,
            "reason": "已核对生卒年与作品责任者",
        },
        format="json",
    )

    assert response.status_code == 200
    assert response.data["candidate"]["status"] == EntityResolutionCandidate.Status.LINKED
    assert response.data["idempotent"] is False
    contribution = Contribution.objects.get(edition=item.edition, person=person)
    assert contribution.approved is False
    assert contribution.source == "entity_resolution"
    assert DecisionLog.objects.filter(
        resolution_candidate=candidate,
        action="link_existing",
        actor=editor,
    ).count() == 1
    assert AuditEvent.objects.filter(
        object_type="EntityResolutionCandidate",
        object_id=str(candidate.id),
        action="entity_resolution_link_existing",
    ).count() == 1
    assert all(row["status"] != EntityResolutionCandidate.Status.PROPOSED for row in response.data["group"])

    repeated = api_client.post(
        decision_url(item, candidate),
        {
            "action": "link_existing",
            "target_type": "person",
            "target_id": str(person.id),
            "confirm_identity": True,
        },
        format="json",
    )
    assert repeated.status_code == 200
    assert repeated.data["idempotent"] is True
    assert DecisionLog.objects.filter(resolution_candidate=candidate).count() == 1
    assert AuditEvent.objects.filter(object_id=str(candidate.id)).count() == 1


def test_same_name_person_link_requires_explicit_identity_confirmation(
    api_client,
    admin_user,
):
    item = make_item(admin_user)
    person = Person.objects.create(preferred_name="李平", sort_name="李平")
    candidate = next(
        row
        for row in persist_resolution_candidates(item, target_type="person", source_name="李平")
        if row.candidate_entity_id == str(person.id)
    )
    api_client.force_authenticate(make_editor())

    response = api_client.post(
        decision_url(item, candidate),
        {
            "action": "link_existing",
            "target_type": "person",
            "target_id": str(person.id),
        },
        format="json",
    )

    assert response.status_code == 409
    assert "明确确认" in response.data["detail"]
    candidate.refresh_from_db()
    assert candidate.status == EntityResolutionCandidate.Status.PROPOSED
    assert not Contribution.objects.filter(edition=item.edition, person=person).exists()


def test_create_person_draft_never_creates_public_scholar_profile(api_client, admin_user):
    item = make_item(admin_user)
    candidate = next(
        row
        for row in persist_resolution_candidates(item, target_type="person", source_name="新责任者")
        if row.candidate_entity_type == "person_draft"
    )
    api_client.force_authenticate(make_editor())

    response = api_client.post(
        decision_url(item, candidate),
        {
            "action": "create_draft",
            "target_type": "person",
            "reason": "馆内没有可靠匹配",
        },
        format="json",
    )

    assert response.status_code == 200
    candidate.refresh_from_db()
    person = Person.objects.get(pk=candidate.candidate_entity_id)
    assert person.authority_status == Person.AuthorityStatus.DRAFT
    assert not hasattr(person, "scholar_profile")
    assert candidate.status == EntityResolutionCandidate.Status.CREATE_DRAFT


def test_reviewer_cannot_change_catalog_entity_resolution(api_client, admin_user):
    item = make_item(admin_user)
    candidate = next(
        row
        for row in persist_resolution_candidates(item, target_type="person", source_name="未解析作者")
        if row.candidate_entity_type == "person_draft"
    )
    reviewer = User.objects.create_user(
        username="reviewer@example.org",
        email="reviewer@example.org",
        role=User.Role.REVIEWER,
        password="Reviewer-Secure-2026",
    )
    api_client.force_authenticate(reviewer)

    response = api_client.post(
        decision_url(item, candidate),
        {"action": "keep_unresolved", "target_type": "person"},
        format="json",
    )

    assert response.status_code == 403
    candidate.refresh_from_db()
    assert candidate.status == EntityResolutionCandidate.Status.PROPOSED


def test_editor_can_revert_unpublished_person_link_and_restore_review_group(
    api_client,
    admin_user,
):
    item = make_item(admin_user)
    person = Person.objects.create(
        preferred_name="可撤销作者",
        sort_name="可撤销作者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    group = persist_resolution_candidates(
        item,
        target_type="person",
        source_name="可撤销作者",
    )
    candidate = next(row for row in group if row.candidate_entity_id == str(person.id))
    editor = make_editor()
    api_client.force_authenticate(editor)
    decided = api_client.post(
        decision_url(item, candidate),
        {
            "action": "link_existing",
            "target_type": "person",
            "target_id": str(person.id),
            "confirm_identity": True,
        },
        format="json",
    )
    assert decided.status_code == 200
    decision = DecisionLog.objects.get(resolution_candidate=candidate, action="link_existing")

    reverted = api_client.post(
        revert_url(item, decision),
        {"reason": "复核后确认并非同一人物"},
        format="json",
    )

    assert reverted.status_code == 200
    assert reverted.data["candidate"]["status"] == EntityResolutionCandidate.Status.PROPOSED
    assert reverted.data["review_task_status"] == "pending"
    assert not Contribution.objects.filter(edition=item.edition, person=person).exists()
    assert all(row["status"] == EntityResolutionCandidate.Status.PROPOSED for row in reverted.data["group"])
    decision.refresh_from_db()
    assert decision.reverted_by_id == editor.id
    assert decision.reversal.reverts_decision_id == decision.id

    repeated = api_client.post(
        revert_url(item, decision),
        {"reason": "重复提交同一撤销请求"},
        format="json",
    )
    assert repeated.status_code == 200
    assert repeated.data["idempotent"] is True


def test_reverting_created_person_archives_draft_instead_of_deleting_it(api_client, admin_user):
    item = make_item(admin_user)
    candidate = next(
        row
        for row in persist_resolution_candidates(item, target_type="person", source_name="临时责任者")
        if row.candidate_entity_type == "person_draft"
    )
    editor = make_editor()
    api_client.force_authenticate(editor)
    response = api_client.post(
        decision_url(item, candidate),
        {"action": "create_draft", "target_type": "person"},
        format="json",
    )
    assert response.status_code == 200
    candidate.refresh_from_db()
    person_id = candidate.candidate_entity_id
    decision = DecisionLog.objects.get(resolution_candidate=candidate, action="create_draft")

    response = api_client.post(
        revert_url(item, decision),
        {"reason": "发现责任者名称来自 OCR 误识别"},
        format="json",
    )

    assert response.status_code == 200
    person = Person.objects.get(pk=person_id)
    assert person.authority_status == Person.AuthorityStatus.ARCHIVED
    assert not Contribution.objects.filter(person=person).exists()


def test_published_item_blocks_direct_entity_decision_revert(api_client, admin_user):
    item = make_item(admin_user)
    person = Person.objects.create(preferred_name="发布作者", sort_name="发布作者")
    candidate = next(
        row
        for row in persist_resolution_candidates(item, target_type="person", source_name="发布作者")
        if row.candidate_entity_id == str(person.id)
    )
    editor = make_editor()
    api_client.force_authenticate(editor)
    assert api_client.post(
        decision_url(item, candidate),
        {
            "action": "link_existing",
            "target_type": "person",
            "target_id": str(person.id),
            "confirm_identity": True,
        },
        format="json",
    ).status_code == 200
    decision = DecisionLog.objects.get(resolution_candidate=candidate, action="link_existing")
    item.edition.state = PublicationState.PUBLISHED
    item.edition.save(update_fields=["state", "updated_at"])

    response = api_client.post(
        revert_url(item, decision),
        {"reason": "尝试直接改动已发布版本"},
        format="json",
    )

    assert response.status_code == 409
    assert "已发布" in response.data["detail"]


def test_organization_candidate_creates_draft_role_and_can_be_reverted(api_client, admin_user):
    item = make_item(admin_user)
    candidate = next(
        row
        for row in persist_resolution_candidates(
            item,
            target_type="organization",
            source_name="中国社会科学院社会学研究所",
            supporting_properties={
                "organization_role": OrganizationContribution.Role.REPORT_ISSUER,
                "organization_type": OrganizationAuthority.OrganizationType.RESEARCH_INSTITUTE,
            },
        )
        if row.candidate_entity_type == "organization_draft"
    )
    editor = make_editor()
    api_client.force_authenticate(editor)

    response = api_client.post(
        decision_url(item, candidate),
        {"action": "create_draft", "target_type": "organization"},
        format="json",
    )

    assert response.status_code == 200
    candidate.refresh_from_db()
    organization = OrganizationAuthority.objects.get(pk=candidate.candidate_entity_id)
    assert organization.authority_status == OrganizationAuthority.AuthorityStatus.DRAFT
    relation = OrganizationContribution.objects.get(
        edition=item.edition,
        organization=organization,
    )
    assert relation.role == OrganizationContribution.Role.REPORT_ISSUER
    assert relation.approved is False

    decision = DecisionLog.objects.get(resolution_candidate=candidate, action="create_draft")
    response = api_client.post(
        revert_url(item, decision),
        {"reason": "机构名称来自错误的报告页眉"},
        format="json",
    )
    assert response.status_code == 200
    organization.refresh_from_db()
    assert organization.authority_status == OrganizationAuthority.AuthorityStatus.ARCHIVED
    assert not organization.contributions.exists()
