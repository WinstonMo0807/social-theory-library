from __future__ import annotations

import pytest

from accounts.models import User
from catalog.models import (
    Asset,
    Contribution,
    DocumentType,
    Edition,
    EditionWorkflowDecision,
    EditorialRevision,
    PublicationState,
    TheoryReviewTask,
)
from catalog.services.admin_workflow import WORKFLOW_STEPS, build_edition_workflow
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.work_editor import save_workflow_section
from ingestion.models import (
    EntityResolutionCandidate,
    FieldLock,
    MetadataCandidate,
    UploadBatch,
    UploadItem,
)
from ingestion.services.entity_resolution_decisions import decide_entity_resolution
from ingestion.services.reconciliation import persist_resolution_candidates

from .test_resilient_publication_v260 import create_item_with_files
from .publication_fixtures import acknowledge_catalog_projections


def confirm_required_catalog_fields(edition, actor):
    from catalog.models import Person

    save_workflow_section(edition, "work", {
        "title": edition.work.title, "document_type": edition.work.document_type, "language": edition.work.language,
    }, actor=actor)
    person = Person.objects.create(preferred_name="已确认作者", sort_name="已确认作者", authority_status="verified")
    save_workflow_section(edition, "contributors", {
        "contributors": [{"person_id": person.pk, "role": "author", "order": 0}],
    }, actor=actor)
    edition.refresh_from_db()


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
    assert curation["status"] == "complete"
    assert next(row for row in curation["fields"] if row["field"] == "curation")["status"] == "not_applicable"
    decision = EditionWorkflowDecision.objects.get(
        edition=edition,
        step_key=EditionWorkflowDecision.Step.CURATION,
    )
    assert decision.decision == EditionWorkflowDecision.Decision.SKIPPED
    assert "尚未加入阅读路径" not in skipped.data["data"]["publication"]["blockers"]


@pytest.mark.django_db
def test_save_draft_does_not_confirm_lock_or_accept_candidates(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="尚未确认的书名",
    )
    item = make_item(admin_user, edition)
    candidate = MetadataCandidate.objects.create(
        upload_item=item,
        field_name="title",
        value="暂存后的书名",
        source="front_matter",
        confidence=0.91,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/work/",
        {
            "data": {
                "title": "暂存后的书名",
                "document_type": "book",
                "language": "zh-CN",
            },
            "confirm_section": False,
        },
        format="json",
    )

    assert response.status_code == 200
    work.refresh_from_db()
    candidate.refresh_from_db()
    assert work.title == "暂存后的书名"
    assert not EditionWorkflowDecision.objects.filter(
        edition=edition,
        step_key=EditionWorkflowDecision.Step.WORK,
    ).exists()
    assert not FieldLock.objects.filter(edition=edition, field_name="title").exists()
    assert candidate.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
    work_step = next(row for row in response.data["workflow"]["steps"] if row["key"] == "work")
    assert work_step["status"] != "complete"


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
def test_pending_contributor_and_optional_classification_are_advisory(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    _work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="候选不阻断人工保存",
    )
    item = make_item(admin_user, edition)
    from catalog.models import Person

    selected = Person.objects.create(
        preferred_name="人工确认作者",
        sort_name="人工确认作者",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    pending = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="另一个 OCR 候选",
        candidate_entity_type="person_draft",
        label="新建草稿：另一个 OCR 候选",
        match_score=0.35,
    )
    for index in range(9):
        EntityResolutionCandidate.objects.create(
            upload_item=item,
            target_type="person",
            source_name=f"未采用责任者候选 {index + 2}",
            candidate_entity_type="person_draft",
            label=f"新建草稿：未采用责任者候选 {index + 2}",
            match_score=0.3,
            supporting_properties={
                "contribution_role": (
                    Contribution.Role.TRANSLATOR
                    if index % 2
                    else Contribution.Role.AUTHOR
                )
            },
        )
    MetadataCandidate.objects.create(
        upload_item=item,
        field_name="authors",
        value=["批量候选甲", "批量候选乙", "批量候选丙"],
        source="front_matter_native_v1",
        confidence=0.88,
    )
    api_client.force_authenticate(admin_user)

    opened = api_client.get(f"/api/catalog/admin/intake/{item.id}/")
    assert opened.data["data"]["contributors"]["items"] == []
    person_candidates = [
        row
        for row in opened.data["candidates"]["entities"]
        if row["target_type"] == "person"
    ]
    assert len(person_candidates) == 10
    assert {row["role"] for row in person_candidates} == {
        Contribution.Role.AUTHOR,
        Contribution.Role.TRANSLATOR,
    }
    author_bundle = next(
        row
        for row in opened.data["candidates"]["metadata"]
        if row["field_name"] == "authors"
    )
    assert author_bundle["available_actions"] == ["inspect", "reject"]
    response = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/contributors/",
        {
            "data": {
                "items": [
                    {
                        "person_id": str(selected.id),
                        "role": Contribution.Role.AUTHOR,
                        "order": 0,
                    }
                ],
                "expected_updated_at": opened.data["data"]["contributors"]["expected_updated_at"],
                "expected_work_updated_at": opened.data["data"]["contributors"]["expected_work_updated_at"],
            }
        },
        format="json",
    )

    assert response.status_code == 200
    assert Contribution.objects.filter(
        edition=edition,
        person=selected,
        approved=True,
    ).exists()
    assert len(response.data["data"]["contributors"]["items"]) == 1
    assert response.data["data"]["contributors"]["items"][0]["person_id"] == str(
        selected.id
    )
    pending.refresh_from_db()
    assert pending.status == EntityResolutionCandidate.Status.PROPOSED
    contributor_step = next(
        row for row in response.data["workflow"]["steps"] if row["key"] == "contributors"
    )
    assert contributor_step["status"] == "complete"
    # Unchosen discovery candidates remain visible beside the field, but do
    # not create a review requirement for the already confirmed selection.
    assert not any(row["code"] == "contributors_unresolved" for row in contributor_step["issues"])
    assert next(row for row in contributor_step["fields"] if row["field"] == "authors")["status"] == "confirmed"
    assert len([row for row in response.data["candidates"]["entities"] if row["target_type"] == "person"]) == 10
    classification_step = next(
        row for row in response.data["workflow"]["steps"] if row["key"] == "classification"
    )
    primary_missing = next(
        row for row in classification_step["issues"] if row["code"] == "primary_discipline_missing"
    )
    assert classification_step["status"] != "blocked"
    assert primary_missing["severity"] == "warning"


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
def test_maintenance_workspace_and_mutation_stay_on_requested_edition(
    api_client,
    admin_user,
    settings,
    tmp_path,
):
    work, primary, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="多版本精确维护",
    )
    primary.publisher = "主版本出版社"
    primary.is_primary = True
    primary.save(update_fields=["publisher", "is_primary", "updated_at"])
    selected = Edition.objects.create(
        work=work,
        version_label="待维护的第二版",
        publication_year=2025,
        publisher="第二版原出版社",
        is_primary=False,
    )
    api_client.force_authenticate(admin_user)

    loaded = api_client.get(
        f"/api/catalog/admin/library/works/{work.id}/?edition={selected.id}"
    )
    assert loaded.status_code == 200
    assert loaded.data["context"]["edition_id"] == str(selected.id)

    saved = api_client.patch(
        (
            f"/api/catalog/admin/library/works/{work.id}/sections/bibliography/"
            f"?edition={selected.id}"
        ),
        {"data": {"publisher": "第二版核定出版社"}},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.data["context"]["edition_id"] == str(selected.id)
    primary.refresh_from_db()
    selected.refresh_from_db()
    assert primary.publisher == "主版本出版社"
    assert selected.publisher == "第二版核定出版社"


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
    assert next(row for row in first["steps"] if row["key"] == "work")["status"] == "blocked"
    save_workflow_section(edition, "work", {
        "title": work.title, "document_type": work.document_type, "language": work.language,
    }, actor=admin_user)
    edition.refresh_from_db()
    confirmed = build_edition_workflow(edition)
    assert next(row for row in confirmed["steps"] if row["key"] == "work")["status"] == "complete"

    save_workflow_section(edition, "work", {"subtitle": "内容已经变化"}, actor=admin_user, confirm_section=False)
    edition.refresh_from_db()
    stale = build_edition_workflow(edition)
    work_step = next(row for row in stale["steps"] if row["key"] == "work")
    assert work_step["status"] == "attention"
    assert any(row["code"] == "field_needs_review" and row["field"] == "subtitle" for row in work_step["issues"])

    normalized.validation_status = Asset.ValidationStatus.INVALID
    normalized.save(update_fields=["validation_status", "updated_at"])
    blocked = build_edition_workflow(edition)
    publication = next(row for row in blocked["steps"] if row["key"] == "publication")
    assert publication["status"] == "blocked"
    assert blocked["blockers_count"] >= 1


@pytest.mark.django_db
def test_pending_knowledge_research_is_visible_but_non_blocking(settings, tmp_path, admin_user):
    work, edition, _original, _normalized = create_item_with_files(
        settings,
        tmp_path,
        title="可选知识策展",
    )
    candidate = TheoryReviewTask.objects.create(
        task_type=TheoryReviewTask.TaskType.NEW_NODE,
        work=work,
        suggested_node_name="待判断理论",
        evidence_text="机器候选仍需人工判断。",
    )

    workflow = build_edition_workflow(edition)
    knowledge = next(row for row in workflow["steps"] if row["key"] == "knowledge")
    assert knowledge["status"] != "blocked"
    assert not any(row["code"] == "knowledge_review_pending" for row in knowledge["issues"])
    workspace = build_admin_workspace(edition, user=admin_user, mode="maintenance")
    suggestion = next(row for row in workspace["candidates"]["theory"] if row["id"] == str(candidate.pk))
    assert suggestion["status"] == "pending"
    assert suggestion["evidence"]["text"] == "机器候选仍需人工判断。"
    assert not work.node_relations.exists()


@pytest.mark.django_db
def test_workflow_queue_and_maintenance_publication_reuse_existing_rules(
    api_client,
    admin_user,
    settings,
    tmp_path,
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

    confirm_required_catalog_fields(edition, admin_user)
    before = build_edition_workflow(edition)
    assert before["publication_preflight"]["blockers"] == []
    assert before["publication_preflight"]["warnings"]

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
    assert published.data["maintenance_url"].endswith(
        f"/{work.id}?edition={edition.id}#publication"
    )
    edition.refresh_from_db()
    assert edition.state == PublicationState.PUBLISHED
    acknowledge_catalog_projections(edition)

    draft = api_client.patch(
        f"/api/catalog/admin/library/works/{work.id}/sections/work/?edition={edition.id}",
        {
            "data": {
                "title": "由最终发布动作提交的草稿题名",
                "document_type": "book",
                "language": "zh-CN",
            },
            "confirm_section": False,
        },
        format="json",
    )
    assert draft.status_code == 202
    revision_id = draft.data["editorial_revision"]["id"]
    work.refresh_from_db()
    assert work.title == "维护发布与下一项"

    rolled_back = api_client.post(
        f"/api/catalog/admin/library/works/{work.id}/publication/",
        {"confirm_warnings": False},
        format="json",
    )
    assert rolled_back.status_code == 409
    work.refresh_from_db()
    assert work.title == "维护发布与下一项"
    assert EditorialRevision.objects.get(pk=revision_id).status == EditorialRevision.Status.DRAFT

    updated = api_client.post(
        f"/api/catalog/admin/library/works/{work.id}/publication/",
        {"confirm_warnings": True},
        format="json",
    )
    assert updated.status_code == 200
    assert updated.data["published_editorial_revision"]["id"] == revision_id
    work.refresh_from_db()
    assert work.title == "由最终发布动作提交的草稿题名"
    assert (
        EditorialRevision.objects.get(pk=revision_id).status
        == EditorialRevision.Status.PUBLISHED
    )


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

    from ingestion.services.pipeline import _create_or_update_catalog

    item.refresh_from_db()
    _create_or_update_catalog(item, {
        "title": "后续 OCR 不得覆盖人工关联的作品", "document_type": "book", "language": "en",
    }, [], "")
    existing_work.refresh_from_db()
    assert existing_work.title == "同题名作品识别"
    assert existing_work.language == "zh-CN"

    after = api_client.get(f"/api/catalog/admin/intake/{item.id}/")
    assert after.data["data"]["file"]["duplicate_status"] == "existing_work"
    work_step = next(row for row in after.data["workflow"]["steps"] if row["key"] == "work")
    # Resolving identity does not implicitly confirm the linked Work's fields.
    assert work_step["status"] == "blocked"
    item.refresh_from_db()
    assert item.preflight_summary["catalog_reconciliation"]["requires_review"] is True
    confirmed = api_client.patch(
        f"/api/catalog/admin/intake/{item.id}/sections/work/",
        {"data": {"title": existing_work.title, "document_type": existing_work.document_type, "language": existing_work.language}},
        format="json",
    )
    assert confirmed.status_code == 200
    work_step = next(row for row in confirmed.data["workflow"]["steps"] if row["key"] == "work")
    assert work_step["status"] != "blocked"
