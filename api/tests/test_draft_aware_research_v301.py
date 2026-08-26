from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from catalog.models import (
    DocumentType,
    Edition,
    EnrichmentCandidate,
    PublicationState,
    ResearchRun,
    Work,
)
from catalog.services.research.context import build_research_context
from catalog.services.research.contracts import (
    RESEARCH_CONTRACTS,
    WORKFLOW_FIELDS,
    contract_payload,
)
from catalog.services.research.diagnostics import ResearchDiagnostics
from catalog.services.research.orchestrator import ResearchOrchestrator
from catalog.services.research.planner import ResearchPlanner
from catalog.services.work_editor import save_workflow_section
from ingestion.models import EntityResolutionCandidate, UploadBatch, UploadItem


pytestmark = pytest.mark.django_db


def _workspace(admin_user, *, title="数据库旧题名"):
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title=title,
        language="zh-CN",
        first_publication_date=date(1978, 1, 1),
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.DRAFT,
        publication_year=2024,
        publisher="旧版本出版社",
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="draft-aware-research.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )
    return work, edition, item


def _empty_discovery():
    return SimpleNamespace(
        discover=lambda request: {
            "entity_type": request.entity_type,
            "field": request.field,
            "query": request.query,
            "results": [],
            "warnings": [],
            "providers_attempted": ["local"],
            "status": "healthy",
        }
    )


def test_field_research_contract_covers_product_editable_fields():
    required = {
        "work": {
            "title", "subtitle", "original_title", "canonical_title", "abstract",
            "language", "original_language", "first_publication_date",
        },
        "bibliography": {
            "edition_statement", "publication_date", "publisher", "publication_place",
            "isbn10", "isbn13", "series",
        },
        "contributors": {"authors", "translators", "other_contributors"},
        "classification": {
            "primary_discipline", "related_disciplines", "subdisciplines",
        },
        "knowledge": {"theories", "concepts", "topics", "debates"},
        "curation": {
            "core_viewpoints", "major_criticisms", "major_responses",
            "reading_path_placements", "recommendation_reason",
        },
    }

    for step, fields in required.items():
        assert fields <= set(WORKFLOW_FIELDS[step])
        for field_name in fields:
            payload = contract_payload(RESEARCH_CONTRACTS.get(step, field_name))
            assert payload["scope"]
            assert payload["trigger_inputs"]
            assert payload["local_catalog_sources"]
            assert payload["document_ocr_sources"]
            assert payload["research_task_profile"]
            assert payload["output_schema"]
            assert payload["accept_policy"]
            assert payload["stale_policy"] == "invalidate_on_trigger_change"
            assert payload["no_reliable_candidate"]["reason"]


def test_title_draft_replans_required_fields_with_new_value(admin_user):
    _work, edition, item = _workspace(admin_user)
    context = build_research_context(
        edition,
        item=item,
        active_step="work",
        draft_data={"work": {"title": "草稿中的新题名"}},
        changed_fields=["work.title"],
        draft_session_id="workbench-session-1",
    )

    planned_context, tasks = ResearchPlanner().plan(
        context,
        include_background=False,
    )
    by_field = {(row.step, row.field): row for row in tasks}
    required = {
        ("work", "original_title"),
        ("work", "language"),
        ("work", "first_publication_date"),
        ("work", "abstract"),
        ("bibliography", "version_label"),
        ("bibliography", "publication_date"),
        ("bibliography", "publisher"),
        ("bibliography", "isbn13"),
        ("contributors", "contributors"),
    }

    assert required <= set(by_field)
    assert all(by_field[key].query == "草稿中的新题名" for key in required)
    assert planned_context.draft_session_id == "workbench-session-1"
    assert planned_context.draft_hash
    assert planned_context.trigger_input_values["work.title"] == "草稿中的新题名"
    assert planned_context.trigger_input_hash
    assert planned_context.canonical_revision["work"] == 0
    assert planned_context.canonical_revision["work_updated_at"]


def test_new_draft_supersedes_overlapping_run_and_ignores_late_execution(admin_user):
    _work, edition, item = _workspace(admin_user)
    orchestrator = ResearchOrchestrator(entity_discovery=_empty_discovery())
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        first, _ = orchestrator.prepare(
            edition,
            item=item,
            active_step="work",
            draft_data={"work": {"title": "第一版未保存题名"}},
            changed_fields=["work.title"],
            draft_session_id="same-browser-editor",
            actor=admin_user,
            dispatch=False,
        )
        candidate = EntityResolutionCandidate.objects.create(
            upload_item=item,
            target_type="person",
            source_name="旧作者候选",
            candidate_entity_type="person_draft",
            label="旧作者候选",
            supporting_properties={
                "research_run_id": str(first.id),
                "research_context_fingerprint": first.context_fingerprint,
                "is_current_context": True,
            },
        )
        enrichment_candidate = EnrichmentCandidate.objects.create(
            target_type=EnrichmentCandidate.TargetType.WORK,
            target_id=edition.work_id,
            field_name="title",
            candidate_kind=EnrichmentCandidate.CandidateKind.FACTUAL,
            proposed_value="第一版候选题名",
            request_context={
                "research_run_id": str(first.id),
                "research_context_fingerprint": first.context_fingerprint,
                "research_draft_session_id": first.draft_session_id,
                "research_draft_hash": first.draft_hash,
                "research_trigger_input_hash": first.trigger_input_hash,
                "is_current_context": True,
            },
            conflict_group="draft-aware-title",
            policy_version="test-policy-v1",
            extraction_version="test-extraction-v1",
            fingerprint="9" * 64,
        )
        second, created = orchestrator.prepare(
            edition,
            item=item,
            active_step="work",
            draft_data={"work": {"title": "第二版未保存题名"}},
            changed_fields=["work.title"],
            draft_session_id="same-browser-editor",
            actor=admin_user,
            dispatch=False,
        )

    first.refresh_from_db()
    candidate.refresh_from_db()
    enrichment_candidate.refresh_from_db()
    assert created is True
    assert second.id != first.id
    assert first.status == ResearchRun.Status.SUPERSEDED
    assert first.is_current is False
    assert first.superseded_by_id == second.id
    assert candidate.status == EntityResolutionCandidate.Status.STALE
    assert candidate.supporting_properties["is_current_context"] is False
    assert enrichment_candidate.status == EnrichmentCandidate.Status.SUPERSEDED
    assert enrichment_candidate.request_context["is_current_context"] is False
    assert enrichment_candidate.request_context["stale_reason"]
    assert second.draft_hash != first.draft_hash
    assert second.trigger_input_values["work.title"] == "第二版未保存题名"

    enrichment = Mock(return_value=[])
    orchestrator._run_enrichment = enrichment
    ignored = orchestrator.execute(str(first.id))
    assert ignored.status == ResearchRun.Status.SUPERSEDED
    enrichment.assert_not_called()


def test_first_v301_draft_supersedes_legacy_run_without_session(admin_user):
    _work, edition, item = _workspace(admin_user)
    orchestrator = ResearchOrchestrator(entity_discovery=_empty_discovery())
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        legacy, _ = orchestrator.prepare(
            edition,
            item=item,
            active_step="work",
            draft_data={"work": {"title": "3.0.0 旧题名"}},
            changed_fields=["work.title"],
            draft_session_id="temporary-session",
            actor=admin_user,
            dispatch=False,
        )
        legacy.draft_session_id = ""
        legacy.canonical_revision = {}
        legacy.trigger_input_hash = ""
        legacy.plan = [
            {
                key: value
                for key, value in row.items()
                if key != "trigger_input_values"
            }
            for row in legacy.plan
        ]
        legacy.save(
            update_fields=[
                "draft_session_id",
                "canonical_revision",
                "trigger_input_hash",
                "plan",
                "updated_at",
            ]
        )
        candidate = EntityResolutionCandidate.objects.create(
            upload_item=item,
            target_type="person",
            source_name="3.0.0 旧作者",
            candidate_entity_type="person_draft",
            label="3.0.0 旧作者",
            supporting_properties={
                "research_run_id": str(legacy.id),
                "is_current_context": True,
            },
        )

        current, _ = orchestrator.prepare(
            edition,
            item=item,
            active_step="work",
            draft_data={"work": {"title": "3.0.1 新题名"}},
            changed_fields=["work.title"],
            draft_session_id="current-browser-session",
            actor=admin_user,
            dispatch=False,
        )

    legacy.refresh_from_db()
    candidate.refresh_from_db()
    assert legacy.status == ResearchRun.Status.SUPERSEDED
    assert legacy.superseded_by_id == current.id
    assert candidate.status == EntityResolutionCandidate.Status.STALE
    assert candidate.supporting_properties["is_current_context"] is False


def test_unrelated_draft_run_remains_current(admin_user):
    _work, edition, item = _workspace(admin_user)
    orchestrator = ResearchOrchestrator(entity_discovery=_empty_discovery())
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        contributor_run, _ = orchestrator.prepare(
            edition,
            item=item,
            active_step="contributors",
            draft_data={
                "contributors": {"items": [{"display_name": "草稿作者"}]},
            },
            changed_fields=["contributors.items.0.display_name"],
            draft_session_id="same-browser-editor",
            actor=admin_user,
            dispatch=False,
        )
        publisher_run, _ = orchestrator.prepare(
            edition,
            item=item,
            active_step="bibliography",
            draft_data={"bibliography": {"publisher": "草稿出版社"}},
            changed_fields=["bibliography.publisher"],
            draft_session_id="same-browser-editor",
            actor=admin_user,
            dispatch=False,
        )

    contributor_run.refresh_from_db()
    publisher_run.refresh_from_db()
    assert contributor_run.is_current is True
    assert publisher_run.is_current is True
    assert contributor_run.status == ResearchRun.Status.QUEUED
    assert publisher_run.status == ResearchRun.Status.QUEUED


def test_prepare_refreshes_local_results_after_stale_candidates_are_hidden(admin_user):
    _work, edition, item = _workspace(admin_user)
    orchestrator = ResearchOrchestrator(entity_discovery=_empty_discovery())
    stale = {"suggestions": [{"id": "candidate-from-old-draft"}], "errors": []}
    current = {"suggestions": [], "errors": []}
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        side_effect=[stale, current],
    ):
        run, created = orchestrator.prepare(
            edition,
            item=item,
            active_step="work",
            draft_data={"work": {"title": "新题名"}},
            changed_fields=["work.title"],
            draft_session_id="refresh-local-results",
            actor=admin_user,
            dispatch=False,
        )

    assert created is True
    assert run.local_results["workflow"] == current


def test_enrichment_executes_all_affected_fields_in_bounded_batches(admin_user):
    _work, edition, item = _workspace(admin_user)
    context = build_research_context(
        edition,
        item=item,
        active_step="bibliography",
        draft_data={"work": {"title": "批量研究题名"}},
        changed_fields=["work.title"],
        draft_session_id="enrichment-batches",
    )
    fields = [
        "version_label", "publication_date", "publication_year", "publisher",
        "publication_place", "isbn", "isbn10", "isbn13", "series", "extent",
        "responsibility_statement", "journal_title", "doi",
    ]
    tasks = [
        {"step": "bibliography", "field": field_name, "query": "批量研究题名"}
        for field_name in fields
    ]
    service = SimpleNamespace(
        enrich=Mock(return_value=SimpleNamespace(candidates=[], errors=[]))
    )
    diagnostics = ResearchDiagnostics(
        context_revision=context.fingerprint,
        active_step=context.active_step,
        changed_fields=list(context.changed_fields),
    )

    ResearchOrchestrator(enrichment_service=service)._run_enrichment(
        run=SimpleNamespace(id="00000000-0000-0000-0000-000000000001"),
        context=context,
        tasks=tasks,
        mode="structured",
        actor=admin_user,
        diagnostics=diagnostics,
    )

    assert service.enrich.call_count == 2
    requested = [
        field_name
        for call in service.enrich.call_args_list
        for field_name in call.args[0].field_names
    ]
    assert requested == fields
    assert all(len(call.args[0].field_names) <= 12 for call in service.enrich.call_args_list)


def test_work_and_edition_publication_dates_remain_distinct(admin_user):
    work, edition, _item = _workspace(admin_user)

    save_workflow_section(
        edition,
        "bibliography",
        {"publication_date": date(2025, 6, 30), "publisher": "新版本出版社"},
        actor=admin_user,
    )

    work.refresh_from_db()
    edition.refresh_from_db()
    assert work.first_publication_date == date(1978, 1, 1)
    assert edition.publication_date == date(2025, 6, 30)
    assert edition.publication_year == 2025
    assert edition.citation_data["issued"]["date-parts"] == [[2025, 6, 30]]


def test_field_outcome_explains_when_no_reliable_candidate_exists():
    outcomes = ResearchOrchestrator._field_outcomes(
        [
            {
                "step": "work",
                "field": "abstract",
                "context_fingerprint": "draft-context",
                "no_reliable_candidate_reason": "PDF 中没有可定位摘要。",
            }
        ],
        {"enrichment": [], "entities": [], "editorial_evidence": []},
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert {
        "field": outcome["field"],
        "status": outcome["status"],
        "reason": outcome["reason"],
        "context_fingerprint": outcome["context_fingerprint"],
    } == {
        "field": "work.abstract",
        "status": "no_reliable_candidate",
        "reason": "PDF 中没有可定位摘要。",
        "context_fingerprint": "draft-context",
    }
    assert outcome["producer_capability"]["field"] == "abstract"
    assert outcome["producer_capability"]["state"] == "productive"
    assert outcome["producer_capability"]["channels"]["pdf_native"]["state"] == "productive"
