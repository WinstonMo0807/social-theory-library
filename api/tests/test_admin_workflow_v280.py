from __future__ import annotations

import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    Contribution,
    DocumentType,
    EditionWorkflowDecision,
    PublicationState,
)
from catalog.services.admin_workflow import WORKFLOW_STEPS, build_edition_workflow
from ingestion.models import EntityResolutionCandidate, UploadBatch, UploadItem
from ingestion.services.entity_resolution_decisions import decide_entity_resolution
from ingestion.services.reconciliation import persist_resolution_candidates

from .test_resilient_publication_v260 import create_item_with_files


def make_item(admin_user, edition, *, status=UploadItem.Status.NEEDS_REVIEW):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
    )
    return UploadItem.objects.create(
        batch=batch,
        source_filename="workflow-v280.pdf",
        status=status,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
        edition=edition,
        asset=edition.assets.filter(kind="normalized").first(),
    )


@pytest.mark.django_db
def test_workflow_order_section_confirmation_and_curation_skip(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="工作流图书",
    )
    item = make_item(admin_user, edition)
    api_client.force_authenticate(admin_user)

    opened = api_client.get(f"/api/catalog/admin/intake/{item.id}/")
    assert opened.status_code == 200
    assert [row["key"] for row in opened.data["workflow"]["steps"]] == [
        key for key, _label in WORKFLOW_STEPS
    ]
    assert opened.data["workflow"]["current_step"] == "work"
    assert opened.data["mode"] == "intake"
    assert opened.data["context"]["work_id"] == str(work.id)

    saved_work = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/work/",
        {
            "data": {
                "title": "工作流图书修订",
                "document_type": "book",
                "language": "zh-CN",
                "expected_updated_at": opened.data["data"]["work"]["expected_updated_at"],
                "expected_work_updated_at": opened.data["data"]["work"]["expected_work_updated_at"],
            }
        },
        format="json",
    )
    assert saved_work.status_code == 200
    assert saved_work.data["workflow"]["steps"][1]["status"] == "complete"
    assert saved_work.data["workflow"]["current_step"] == "bibliography"

    skipped = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/curation/",
        {"data": {"skipped": True}, "skip": True},
        format="json",
    )
    assert skipped.status_code == 200
    curation = next(
        row for row in skipped.data["workflow"]["steps"] if row["key"] == "curation"
    )
    assert curation["status"] == "skipped"
    decision = EditionWorkflowDecision.objects.get(
        edition=edition,
        step_key=EditionWorkflowDecision.Step.CURATION,
    )
    assert decision.decision == EditionWorkflowDecision.Decision.SKIPPED
    assert "尚未加入阅读路径" not in skipped.data["data"]["publication"]["blockers"]


@pytest.mark.django_db
def test_journal_bibliography_and_role_aware_contributors_save_independently(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="工作流期刊论文",
    )
    work.document_type = DocumentType.JOURNAL_ARTICLE
    work.save(update_fields=["document_type", "updated_at"])
    item = make_item(admin_user, edition)
    # A Person is an authority object, not an account.
    from catalog.models import Person

    person = Person.objects.create(
        preferred_name="工作流作者",
        sort_name="工作流作者",
        authority_status=Person.AuthorityStatus.DRAFT,
    )
    api_client.force_authenticate(admin_user)
    opened = api_client.get(f"/api/catalog/admin/intake/{item.id}/")

    bibliography = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/bibliography/",
        {
            "data": {
                "publication_year": 2026,
                "journal_title": "社会理论研究",
                "volume": "18",
                "issue": "2",
                "page_range": "33-58",
                "doi": "10.1234/workflow.2026.2",
                "expected_updated_at": opened.data["data"]["bibliography"]["expected_updated_at"],
                "expected_work_updated_at": opened.data["data"]["bibliography"]["expected_work_updated_at"],
            }
        },
        format="json",
    )
    assert bibliography.status_code == 200
    edition.refresh_from_db()
    assert edition.journal_title == "社会理论研究"
    assert edition.volume == "18"
    assert edition.issue == "2"
    assert edition.page_range == "33-58"
    assert edition.doi == "10.1234/workflow.2026.2"
    assert work.title == "工作流期刊论文"

    contributors = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/contributors/",
        {
            "data": {
                "items": [
                    {
                        "person_id": str(person.id),
                        "display_name": person.preferred_name,
                        "role": "editor",
                        "order": 0,
                    }
                ],
                "expected_updated_at": bibliography.data["data"]["contributors"]["expected_updated_at"],
                "expected_work_updated_at": bibliography.data["data"]["contributors"]["expected_work_updated_at"],
            }
        },
        format="json",
    )
    assert contributors.status_code == 200
    relation = Contribution.objects.get(edition=edition, person=person)
    assert relation.role == Contribution.Role.EDITOR
    assert relation.approved is True


@pytest.mark.django_db
def test_maintenance_mode_work_library_and_permissions(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="维护模式作品",
    )
    edition.state = PublicationState.PUBLISHED
    edition.save(update_fields=["state", "updated_at"])

    api_client.force_authenticate(admin_user)
    library = api_client.get("/api/catalog/admin/library/works/?q=维护模式")
    assert library.status_code == 200
    assert library.data["count"] == 1
    assert library.data["results"][0]["id"] == str(work.id)
    assert library.data["results"][0]["publication_state"] == "published"

    maintenance = api_client.get(f"/api/catalog/admin/library/works/{work.id}/")
    assert maintenance.status_code == 200
    assert maintenance.data["mode"] == "maintenance"
    assert maintenance.data["context"]["item_id"] is None
    assert next(
        row for row in maintenance.data["workflow"]["steps"] if row["key"] == "file"
    )["status"] == "skipped"

    reader = User.objects.create_user(
        username="workflow-reader@example.test",
        email="workflow-reader@example.test",
        password="Workflow-Reader-2026",
        role=User.Role.READER,
    )
    api_client.force_authenticate(reader)
    assert api_client.get(f"/api/catalog/admin/library/works/{work.id}/").status_code == 403
    denied = api_client.patch(
        f"/api/catalog/admin/library/works/{work.id}/sections/work/",
        {"data": {"title": "不能修改"}},
        format="json",
    )
    assert denied.status_code == 403


@pytest.mark.django_db
def test_workflow_stale_confirmation_and_publication_blocker(settings, tmp_path, admin_user):
    work, edition, _original, normalized = create_item_with_files(
        settings,
        tmp_path,
        title="确认失效与阻止项",
    )
    from catalog.services.admin_workflow import record_step_decision

    record_step_decision(edition, "work", actor=admin_user)
    first = build_edition_workflow(edition)
    assert next(row for row in first["steps"] if row["key"] == "work")["status"] == "complete"

    work.subtitle = "内容已经变化"
    work.save(update_fields=["subtitle", "updated_at"])
    stale = build_edition_workflow(edition)
    work_step = next(row for row in stale["steps"] if row["key"] == "work")
    assert work_step["status"] == "attention"
    assert any(row["code"] == "confirmation_stale" for row in work_step["issues"])

    normalized.validation_status = Asset.ValidationStatus.INVALID
    normalized.save(update_fields=["validation_status", "updated_at"])
    blocked = build_edition_workflow(edition)
    publication = next(row for row in blocked["steps"] if row["key"] == "publication")
    assert publication["status"] == "blocked"
    assert blocked["blockers_count"] >= 1


@pytest.mark.django_db
def test_workflow_queue_and_maintenance_publication_reuse_existing_rules(
    api_client,
    admin_user,
    settings,
    tmp_path,
    monkeypatch,
):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="维护发布与下一项",
    )
    item = make_item(admin_user, edition, status=UploadItem.Status.READY)
    api_client.force_authenticate(admin_user)

    queue = api_client.get("/api/catalog/admin/workflows/queue/")
    assert queue.status_code == 200
    assert any(row["item_id"] == str(item.id) for row in queue.data["recent_items"])
    assert "candidate_review_count" in queue.data

    before = build_edition_workflow(edition)
    assert before["publication_preflight"]["blockers"] == []
    assert before["publication_preflight"]["warnings"]

    monkeypatch.setattr("catalog.workflow_views.index_asset", lambda *args, **kwargs: None)
    needs_confirmation = api_client.post(
        f"/api/catalog/admin/library/works/{work.id}/publication/",
        {"confirm_warnings": False},
        format="json",
    )
    assert needs_confirmation.status_code == 409
    assert needs_confirmation.data["confirmation_required"] is True

    published = api_client.post(
        f"/api/catalog/admin/library/works/{work.id}/publication/",
        {"confirm_warnings": True, "after_publish": "stay"},
        format="json",
    )
    assert published.status_code == 200
    assert published.data["mode"] == "maintenance"
    assert published.data["maintenance_url"].endswith(f"/{work.id}#publication")
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED


@pytest.mark.django_db
def test_entity_resolution_never_downgrades_confirmed_contributor(
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="责任者确认保护",
    )
    item = make_item(admin_user, edition)
    from catalog.models import Person

    person = Person.objects.create(
        preferred_name="已确认责任者",
        sort_name="已确认责任者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    contribution = Contribution.objects.create(
        edition=edition,
        person=person,
        role=Contribution.Role.AUTHOR,
        source="manual_review",
        confidence=1,
        approved=True,
    )
    candidate = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name=person.preferred_name,
        candidate_entity_type="person",
        candidate_entity_id=str(person.id),
        label=person.preferred_name,
        match_score=1,
    )

    decide_entity_resolution(
        candidate,
        action="link_existing",
        target_type="person",
        target_id=str(person.id),
        confirm_identity=True,
        actor=admin_user,
    )

    contribution.refresh_from_db()
    assert contribution.approved is True
    assert contribution.source == "manual_review"


@pytest.mark.django_db
def test_ambiguous_work_can_be_explicitly_linked_without_leaving_workflow_blocked(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    provisional_work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="同题名作品识别",
    )
    existing_work = provisional_work.__class__.objects.create(
        title="同题名作品识别",
        document_type=DocumentType.BOOK,
        language="zh-CN",
    )
    item = make_item(admin_user, edition)
    item.preflight_summary = {
        "catalog_reconciliation": {
            "mode": "ambiguous",
            "requires_review": True,
            "conflicts": ["馆内存在同题名作品"],
        }
    }
    item.save(update_fields=["preflight_summary", "updated_at"])
    candidates = persist_resolution_candidates(
        item,
        target_type="work",
        source_name="同题名作品识别",
    )
    candidate = next(
        row for row in candidates if row.candidate_entity_id == str(existing_work.id)
    )
    api_client.force_authenticate(admin_user)

    before = api_client.get(f"/api/catalog/admin/intake/{item.id}/")
    work_step = next(row for row in before.data["workflow"]["steps"] if row["key"] == "work")
    assert work_step["status"] == "blocked"

    decided = api_client.post(
        f"/api/ingestion/items/{item.id}/entity-resolution-candidates/{candidate.id}/decision/",
        {
            "action": "link_existing",
            "target_type": "work",
            "target_id": str(existing_work.id),
        },
        format="json",
    )
    assert decided.status_code == 200
    edition.refresh_from_db()
    assert edition.work_id == existing_work.id

    after = api_client.get(f"/api/catalog/admin/intake/{item.id}/")
    work_step = next(row for row in after.data["workflow"]["steps"] if row["key"] == "work")
    assert work_step["status"] != "blocked"
