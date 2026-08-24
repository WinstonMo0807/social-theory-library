from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from billiard.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from accounts.models import User
from catalog.models import (
    Contribution,
    DocumentType,
    Edition,
    HealthCheckRun,
    HealthIncident,
    OrganizationAuthority,
    Person,
    PublicationState,
    PublisherAuthority,
    ReadingPath,
    RecoveryAction,
    ResearchRun,
    ScholarProfile,
    TheorySchool,
    Topic,
    Work,
)
from catalog.services.admin_workspace import build_admin_workspace
from catalog.services.field_enrichment.types import SearchResult
from catalog.services.field_enrichment.web import WebSearchError
from catalog.services.research.context import build_research_context
from catalog.services.research.contracts import (
    RESEARCH_CONTRACTS,
    ResearchImplementation,
    validate_contract_coverage,
)
from catalog.services.research.entity_discovery import (
    EntityDiscoveryRequest,
    UniversalEntityDiscovery,
)
from catalog.services.research.diagnostics import ResearchDiagnostics
from catalog.services.research.orchestrator import ResearchOrchestrator
from catalog.services.research.planner import ResearchPlanner
from catalog.services.research.recovery import (
    CeleryOwnershipSnapshot,
    cancel_research_run,
    celery_research_ownership_snapshot,
    recover_orphaned_research_run,
    recover_stale_research_runs,
)
from catalog.services.system_health import (
    HEALTH_CHECKS,
    HealthProbe,
    ProbeResult,
    _research_productive_probe,
    execute_recovery,
    functional_health_snapshot,
    request_recovery,
    run_health_probe,
)
from catalog.tasks import execute_research_run
from ingestion.models import (
    AuditEvent,
    DecisionLog,
    EntityResolutionCandidate,
    FieldLock,
    UploadBatch,
    UploadItem,
)
from ingestion.services.entity_resolution_decisions import (
    ResolutionDecisionError,
    available_resolution_actions,
    decide_entity_resolution,
)


pytestmark = pytest.mark.django_db


def _edition(
    *,
    title: str = "馆藏研究测试",
    state: str = PublicationState.DRAFT,
    slug: str | None = None,
    document_type: str = DocumentType.BOOK,
    journal_title: str = "",
):
    work = Work.objects.create(
        document_type=document_type,
        title=title,
        language="zh-CN",
        abstract="这是一条用于研究规划和候选发现的馆藏摘要。",
    )
    edition = Edition.objects.create(
        work=work,
        state=state,
        public_slug=slug,
        publication_year=2026,
        publisher="原始出版社",
        journal_title=journal_title,
    )
    return work, edition


def _context(edition: Edition, *, step: str = "contributors", draft=None, changed=None):
    return build_research_context(
        edition,
        active_step=step,
        draft_data=draft or {},
        changed_fields=changed or [],
    )


def _item(admin_user, edition: Edition) -> UploadItem:
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="research-entity-decision.pdf",
        status=UploadItem.Status.NEEDS_REVIEW,
        workflow_state=UploadItem.WorkflowState.NEEDS_REVIEW,
    )


def _queued_research_run(admin_user, *, title: str = "ResearchRun 恢复测试") -> ResearchRun:
    _work, edition = _edition(title=title)
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        run, _created = ResearchOrchestrator().prepare(
            edition,
            active_step="contributors",
            draft_data={
                "contributors": {
                    "items": [{"display_name": f"{title} Contributor"}],
                }
            },
            actor=admin_user,
            dispatch=False,
        )
    return run


def _editor() -> User:
    return User.objects.create_user(
        username=f"v292-editor-{uuid4()}@example.org",
        email=f"v292-editor-{uuid4()}@example.org",
        role=User.Role.EDITOR,
        password="V292-Editor-Secure-Password",
    )


def _reviewer() -> User:
    return User.objects.create_user(
        username=f"v292-reviewer-{uuid4()}@example.org",
        email=f"v292-reviewer-{uuid4()}@example.org",
        role=User.Role.REVIEWER,
        password="V292-Reviewer-Secure-Password",
    )


def _discovery_payload(
    *,
    candidate_id: str,
    query: str,
    group: str = "authority",
    entity_type: str = "person",
    field: str = "contributors.contributors",
):
    return {
        "version": "universal-entity-discovery-v1",
        "entity_type": entity_type,
        "field": field,
        "query": query,
        "context_fingerprint": "test-context",
        "groups": [{"key": group, "label": group, "count": 1}],
        "results": [
            {
                "id": candidate_id,
                "kind": "entity_discovery",
                "entity_type": entity_type,
                "entity_id": None,
                "label": query,
                "primary_name": query,
                "secondary_identity": "外部研究候选",
                "entity_status": "external_candidate" if group != "unresolved" else "unresolved",
                "candidate_group": group,
                "source": "Wikidata" if group == "authority" else group,
                "provider": "wikidata" if group == "authority" else group,
                "match_reasons": ["名称匹配"],
                "conflicts": ["仍需人工确认"],
                "external_ids": {"wikidata": "Q-v292"} if group == "authority" else {},
                "metadata": {"aliases": [query]},
                "evidence": [],
                "evidence_count": 0,
                "evidence_status": "structured_evidence" if group == "authority" else "none",
                "source_url": "https://www.wikidata.org/wiki/Q-v292" if group == "authority" else "",
                "source_record_id": "",
                "available_actions": ["inspect", "create_draft", "keep_unresolved", "reject"],
                "human_confirmation_required": True,
                "confidence": 0.84,
            }
        ],
        "warnings": [],
        "status": "healthy",
        "providers_attempted": ["local", "authority"],
        "multiple_candidates": True,
    }


def _entity_decision_request(
    *,
    item: UploadItem,
    candidate_id: str,
    query: str,
    action: str,
):
    return {
        "item_id": str(item.id),
        "candidate_id": candidate_id,
        "entity_type": "person",
        "field": "contributors.contributors",
        "query": query,
        "step": "contributors",
        "draft": {"contributors": {"items": [{"display_name": query}]}},
        "changed_fields": ["contributors.items.0.display_name"],
        "action": action,
        "reason": "2.9.2 定向测试中的人工决定",
    }


def _local_only_discovery(edition: Edition, *, entity_type: str, query: str):
    return UniversalEntityDiscovery().discover(
        EntityDiscoveryRequest(
            entity_type=entity_type,
            field=f"test.{entity_type}",
            query=query,
            context=_context(edition),
            include_external=False,
            include_web=False,
        )
    )


def test_research_context_preserves_unsaved_draft_and_fingerprint_without_mutation():
    work, edition = _edition(title="数据库中的题名")
    draft = {
        "work": {"title": "尚未保存的题名", "abstract": "尚未保存的摘要"},
        "contributors": {"items": [{"display_name": "George Herbert Mead", "role": "author"}]},
    }

    context = _context(
        edition,
        step="contributors",
        draft=draft,
        changed=["contributors.items.0.display_name"],
    )
    repeated = _context(
        edition,
        step="contributors",
        draft=draft,
        changed=["contributors.items.0.display_name"],
    )

    assert context.persisted_data["work"]["title"] == "数据库中的题名"
    assert context.draft_value("work", "title") == "尚未保存的题名"
    assert context.draft_data == draft
    assert context.unresolved_entities == [
        {
            "entity_type": "person",
            "label": "George Herbert Mead",
            "draft_path": "contributors.items",
        }
    ]
    assert context.changed_fields == ("contributors.items.0.display_name",)
    assert context.fingerprint == repeated.fingerprint
    work.refresh_from_db()
    edition.refresh_from_db()
    assert work.title == "数据库中的题名"
    assert edition.publisher == "原始出版社"


def test_planner_replans_only_affected_dependencies_and_uses_person_input_name():
    _work, edition = _edition()
    contributor_context = _context(
        edition,
        step="contributors",
        draft={"contributors": {"items": [{"display_name": "George Herbert Mead"}]}},
        changed=["contributors.items.0.display_name"],
    )

    _planned_context, contributor_tasks = ResearchPlanner().plan(contributor_context)

    assert [(row.step, row.field) for row in contributor_tasks] == [
        ("contributors", "contributors")
    ]
    assert contributor_tasks[0].query == "George Herbert Mead"

    initial_context = _context(
        edition,
        step="contributors",
        draft={"contributors": {"items": []}},
    )
    _initial_context, initial_tasks = ResearchPlanner().plan(
        initial_context,
        include_background=False,
    )
    assert initial_tasks
    assert {row.step for row in initial_tasks} == {"contributors"}

    doi_context = _context(
        edition,
        step="bibliography",
        draft={"bibliography": {"doi": "10.1000/example"}},
        changed=["bibliography.doi"],
    )
    _planned_context, doi_tasks = ResearchPlanner().plan(doi_context)

    assert doi_tasks
    assert {row.step for row in doi_tasks} == {"bibliography"}
    doi_task = next(row for row in doi_tasks if row.field == "doi")
    assert doi_task.query == "10.1000/example"
    assert all(row.changed_fields == ("bibliography.doi",) for row in doi_tasks)


def test_contract_registry_covers_every_declared_field_and_runtime_implementation():
    coverage = validate_contract_coverage()
    runtime = ResearchOrchestrator._validate_runtime_contracts()

    assert coverage["healthy"] is True
    assert coverage["missing"] == []
    assert coverage["invalid"] == []
    assert runtime["healthy"] is True
    assert runtime["missing_implementations"] == []
    assert {
        "work",
        "bibliography",
        "contributors",
        "classification",
        "knowledge",
        "reader",
        "curation",
        "publication",
    } <= {row.step for row in RESEARCH_CONTRACTS.all()}
    assert all(
        row.implementation != ResearchImplementation.STATUS_ONLY
        for row in RESEARCH_CONTRACTS.all()
        if row.research_enabled
    )


def test_entity_discovery_supports_multiple_local_entity_types():
    _work, edition = _edition(
        title="社会分工论",
        document_type=DocumentType.JOURNAL_ARTICLE,
        journal_title="社会理论研究",
    )
    Person.objects.create(
        preferred_name="George Herbert Mead",
        original_name="George H. Mead",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    TheorySchool.objects.create(
        name="Symbolic Interactionism",
        slug="symbolic-interactionism-v292",
        editorial_status="published",
    )
    Topic.objects.create(
        name="Social Interaction",
        slug="social-interaction-v292",
        editorial_status="published",
    )
    OrganizationAuthority.objects.create(
        preferred_name="University of Chicago",
        organization_type=OrganizationAuthority.OrganizationType.UNIVERSITY,
        authority_status=OrganizationAuthority.AuthorityStatus.VERIFIED,
    )
    PublisherAuthority.objects.create(canonical_name="University of Chicago Press")
    ReadingPath.objects.create(
        title="Chicago Sociology Reading Path",
        slug="chicago-sociology-reading-path-v292",
        status="published",
    )

    cases = {
        "person": "George Herbert Mead",
        "work": "社会分工论",
        "theory": "Symbolic Interactionism",
        "topic": "Social Interaction",
        "organization": "University of Chicago",
        "publisher": "University of Chicago Press",
        "journal": "社会理论研究",
        "reading_path": "Chicago Sociology Reading Path",
    }
    for entity_type, query in cases.items():
        payload = _local_only_discovery(edition, entity_type=entity_type, query=query)
        local = [row for row in payload["results"] if row["candidate_group"] in {"local", "local_draft"}]
        assert local, entity_type
        assert local[0]["entity_type"] == entity_type
        assert any(row["candidate_group"] == "unresolved" for row in payload["results"])
        assert payload["multiple_candidates"] is True


def test_entity_discovery_groups_local_authority_web_and_keeps_multiple_candidates(monkeypatch):
    _work, edition = _edition()
    person = Person.objects.create(
        preferred_name="George Herbert Mead",
        original_name="George H. Mead",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.authority_suggestions",
        lambda entity_type, query: {
            "results": [
                {
                    "id": "Q192521",
                    "label": "George Herbert Mead",
                    "description": "American philosopher and sociologist",
                    "provider": "wikidata",
                    "source": "Wikidata",
                    "source_url": "https://www.wikidata.org/wiki/Q192521",
                    "source_record_id": str(uuid4()),
                    "external_ids": {"wikidata": "Q192521"},
                    "match_reasons": ["权威名称匹配"],
                    "conflicts": ["仍需核对出生年份"],
                },
                {
                    "id": "viaf-39381270",
                    "label": "Mead, George Herbert",
                    "description": "1863-1931",
                    "provider": "viaf",
                    "source": "VIAF",
                    "source_url": "https://viaf.org/viaf/39381270/",
                    "source_record_id": str(uuid4()),
                    "external_ids": {"viaf": "39381270"},
                    "match_reasons": ["标准名匹配"],
                    "conflicts": [],
                },
            ],
            "warnings": [],
        },
    )

    class SearchAdapter:
        def search(self, query, *, limit):
            assert query == "George Herbert Mead"
            return [
                SearchResult(
                    url="https://plato.stanford.edu/entries/mead/",
                    title="George Herbert Mead",
                    snippet="A research lead only.",
                    provider="searxng",
                    source_class="scholarly_encyclopedia",
                )
            ], None

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.configured_web_search_adapter",
        lambda: SearchAdapter(),
    )
    before = Person.objects.get(pk=person.pk)
    payload = UniversalEntityDiscovery().discover(
        EntityDiscoveryRequest(
            entity_type="person",
            field="contributors.contributors",
            query="George Herbert Mead",
            context=_context(edition),
        )
    )

    groups = {row["candidate_group"] for row in payload["results"]}
    assert {"local", "authority", "external_web", "unresolved"} <= groups
    assert payload["status"] == "healthy"
    assert payload["multiple_candidates"] is True
    assert {"local", "authority", "searxng"} <= set(payload["providers_attempted"])
    assert all(row["human_confirmation_required"] is True for row in payload["results"])
    assert all(
        row["evidence_status"] == "lead_only"
        for row in payload["results"]
        if row["candidate_group"] == "external_web"
    )
    after = Person.objects.get(pk=person.pk)
    assert after.preferred_name == before.preferred_name
    assert after.authority_status == before.authority_status
    assert Person.objects.count() == 1


def test_entity_discovery_keeps_same_name_candidates_with_distinct_authority_ids(monkeypatch):
    _work, edition = _edition(title="Authority identity deduplication")
    authority_rows = [
        {
            "id": "viaf-111",
            "label": "Alex Smith",
            "provider": "viaf",
            "source": "VIAF",
            "source_url": "https://viaf.org/viaf/111/",
            "external_ids": {"viaf": "111"},
        },
        {
            "id": "viaf-222",
            "label": "Alex Smith",
            "provider": "viaf",
            "source": "VIAF",
            "source_url": "https://viaf.org/viaf/222/",
            "external_ids": {"viaf": "222"},
        },
        {
            "id": "wikidata-Q111",
            "label": "Alex Smith",
            "provider": "wikidata",
            "source": "Wikidata",
            "source_url": "https://www.wikidata.org/wiki/Q111",
            "external_ids": {"wikidata": "Q111"},
        },
        {
            "id": "wikidata-Q222",
            "label": "Alex Smith",
            "provider": "wikidata",
            "source": "Wikidata",
            "source_url": "https://www.wikidata.org/wiki/Q222",
            "external_ids": {"wikidata": "Q222"},
        },
        {
            "id": "wikidata-Q111-duplicate",
            "label": "Alex Smith",
            "provider": "wikidata",
            "source": "Wikidata",
            "source_url": "https://www.wikidata.org/wiki/Q111?duplicate=1",
            "external_ids": {"wikidata": "Q111"},
        },
    ]
    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.authority_suggestions",
        lambda entity_type, query: {"results": authority_rows, "warnings": []},
    )

    payload = UniversalEntityDiscovery().discover(
        EntityDiscoveryRequest(
            entity_type="person",
            field="contributors.contributors",
            query="Alex Smith",
            context=_context(edition),
            include_web=False,
        )
    )

    authority = [row for row in payload["results"] if row["candidate_group"] == "authority"]
    assert len(authority) == 4
    assert {(row["provider"], tuple(row["external_ids"].items())) for row in authority} == {
        ("viaf", (("viaf", "111"),)),
        ("viaf", (("viaf", "222"),)),
        ("wikidata", (("wikidata", "Q111"),)),
        ("wikidata", (("wikidata", "Q222"),)),
    }


def test_entity_discovery_keeps_same_name_web_candidates_with_distinct_urls(monkeypatch):
    _work, edition = _edition(title="Web identity deduplication")
    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.authority_suggestions",
        lambda entity_type, query: {"results": [], "warnings": []},
    )

    class SearchAdapter:
        def search(self, query, *, limit):
            return [
                SearchResult(
                    url="https://example.org/people/alex-smith-one",
                    title="Alex Smith",
                    snippet="First person with this name.",
                    provider="searxng",
                    source_class="general_web",
                ),
                SearchResult(
                    url="https://example.org/people/alex-smith-two",
                    title="Alex Smith",
                    snippet="Second person with this name.",
                    provider="searxng",
                    source_class="general_web",
                ),
                SearchResult(
                    url="https://example.org/people/alex-smith-one",
                    title="Alex Smith",
                    snippet="Duplicate result for the first person.",
                    provider="searxng",
                    source_class="general_web",
                ),
            ], None

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.configured_web_search_adapter",
        lambda: SearchAdapter(),
    )

    payload = UniversalEntityDiscovery().discover(
        EntityDiscoveryRequest(
            entity_type="person",
            field="contributors.contributors",
            query="Alex Smith",
            context=_context(edition),
        )
    )

    web = [row for row in payload["results"] if row["candidate_group"] == "external_web"]
    assert len(web) == 2
    assert {row["source_url"] for row in web} == {
        "https://example.org/people/alex-smith-one",
        "https://example.org/people/alex-smith-two",
    }


def test_entity_discovery_degrades_to_local_candidates_when_external_sources_fail(monkeypatch):
    _work, edition = _edition()
    Person.objects.create(
        preferred_name="George Herbert Mead",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )

    def fail_authority(*args, **kwargs):
        raise RuntimeError("authority offline")

    class FailedSearchAdapter:
        def search(self, query, *, limit):
            raise WebSearchError("searxng_unavailable", "search offline")

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.authority_suggestions",
        fail_authority,
    )
    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.configured_web_search_adapter",
        lambda: FailedSearchAdapter(),
    )
    payload = UniversalEntityDiscovery().discover(
        EntityDiscoveryRequest(
            entity_type="person",
            field="contributors.contributors",
            query="George Herbert Mead",
            context=_context(edition),
        )
    )

    assert payload["status"] == "degraded"
    assert any(row["candidate_group"] == "local" for row in payload["results"])
    assert {row["code"] for row in payload["warnings"]} == {
        "authority_unavailable",
        "searxng_unavailable",
    }


def test_research_run_is_idempotent_and_does_not_mutate_authority_or_field_lock(admin_user):
    _work, edition = _edition()
    person = Person.objects.create(
        preferred_name="George Herbert Mead",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    lock = FieldLock.objects.create(
        edition=edition,
        field_name="publisher",
        locked_by=admin_user,
        locked_value="原始出版社",
        reason="人工锁定",
    )

    discovery = SimpleNamespace(
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
    orchestrator = ResearchOrchestrator(entity_discovery=discovery)
    draft = {
        "bibliography": {"publisher": "候选出版社"},
        "contributors": {"items": [{"display_name": "George Herbert Mead"}]},
    }

    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        first, first_created = orchestrator.prepare(
            edition,
            active_step="contributors",
            draft_data=draft,
            changed_fields=["contributors.items.0.display_name"],
            actor=admin_user,
            dispatch=False,
        )
        repeated, repeated_created = orchestrator.prepare(
            edition,
            active_step="contributors",
            draft_data=draft,
            changed_fields=["contributors.items.0.display_name"],
            actor=admin_user,
            dispatch=False,
        )

        assert first.id == repeated.id
        assert first_created is True
        assert repeated_created is False
        assert ResearchRun.objects.count() == 1

        orchestrator._run_enrichment = lambda **kwargs: [
            {"field": "publisher", "proposed_value": "候选出版社", "human_confirmation_required": True}
        ]
        orchestrator._run_entity_discovery = lambda **kwargs: []
        orchestrator._run_editorial_evidence = lambda **kwargs: []
        completed = orchestrator.execute(str(first.id))

    edition.refresh_from_db()
    person.refresh_from_db()
    lock.refresh_from_db()
    assert completed.status == ResearchRun.Status.COMPLETED
    assert edition.publisher == "原始出版社"
    assert lock.locked_value == "原始出版社"
    assert lock.reason == "人工锁定"
    assert person.preferred_name == "George Herbert Mead"
    assert person.authority_status == Person.AuthorityStatus.VERIFIED
    assert Person.objects.count() == 1


def test_research_prepare_preassigns_owner_and_rejects_wrong_worker(
    admin_user,
    django_capture_on_commit_callbacks,
):
    _work, edition = _edition(title="preassigned-owner")
    with (
        patch(
            "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
            return_value={"suggestions": [], "errors": []},
        ),
        patch("catalog.tasks.execute_research_run.apply_async") as dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        run, created = ResearchOrchestrator().prepare(
            edition,
            active_step="contributors",
            draft_data={"contributors": {"items": [{"display_name": "Max Weber"}]}},
            actor=admin_user,
            dispatch=True,
        )

    assert created is True
    assert run.status == ResearchRun.Status.QUEUED
    assert run.task_id
    dispatch.assert_called_once_with(args=[str(run.id)], task_id=run.task_id)

    wrong = execute_research_run.apply(
        args=[str(run.id)],
        task_id="wrong-worker-owner",
        throw=False,
    )
    run.refresh_from_db()
    assert wrong.successful()
    assert wrong.result["ignored"] == "owner_mismatch"
    assert run.status == ResearchRun.Status.QUEUED
    assert run.task_id != "wrong-worker-owner"


def test_research_dispatch_failure_is_terminal_and_does_not_leave_false_queue_owner(
    admin_user,
    django_capture_on_commit_callbacks,
):
    _work, edition = _edition(title="dispatch-failure")
    with (
        patch(
            "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
            return_value={"suggestions": [], "errors": []},
        ),
        patch(
            "catalog.tasks.execute_research_run.apply_async",
            side_effect=ConnectionError("broker unavailable"),
        ),
        django_capture_on_commit_callbacks(execute=True),
    ):
        run, created = ResearchOrchestrator().prepare(
            edition,
            active_step="contributors",
            draft_data={"contributors": {"items": [{"display_name": "Pierre Bourdieu"}]}},
            actor=admin_user,
            dispatch=True,
        )

    run.refresh_from_db()
    assert created is True
    assert run.status == ResearchRun.Status.FAILED
    assert run.error_code == "research_dispatch_failed"
    assert any(
        row["code"] == "research_dispatch_failed"
        for row in run.diagnostics["errors"]
    )


def test_intake_candidate_persistence_is_idempotent_when_web_rank_changes(admin_user):
    _work, edition = _edition(title="candidate-deduplication")
    item = _item(admin_user, edition)

    def group(identifier):
        return {
            "entity_type": "person",
            "field": "contributors.contributors",
            "results": [
                {
                    "id": identifier,
                    "entity_type": "person",
                    "label": "Same Web Candidate",
                    "candidate_group": "external_web",
                    "provider": "searxng",
                    "source_url": "https://example.org/same-person",
                    "evidence_status": "lead_only",
                    "confidence": 0.62,
                    "available_actions": ["inspect", "keep_unresolved", "reject"],
                }
            ],
        }

    first = group("web:person:0")
    second = group("web:person:7")
    ResearchOrchestrator._persist_intake_entity_candidates(item=item, groups=[first])
    ResearchOrchestrator._persist_intake_entity_candidates(item=item, groups=[second])

    rows = EntityResolutionCandidate.objects.filter(upload_item=item)
    assert rows.count() == 1
    assert first["results"][0]["review_candidate_id"] == second["results"][0]["review_candidate_id"]
    candidate = rows.get()
    assert candidate.supporting_properties["candidate_group"] == "external_web"
    assert candidate.supporting_properties["evidence_status"] == "lead_only"


@pytest.mark.parametrize(
    ("step", "field", "entity_type", "allow_create_draft"),
    [
        ("work", "translation_of", "work", False),
        ("classification", "subdisciplines", "knowledge_node", False),
        ("contributors", "contributors", "person", True),
    ],
)
def test_background_entity_discovery_respects_exact_create_draft_contract(
    step,
    field,
    entity_type,
    allow_create_draft,
):
    _work, edition = _edition(title=f"background-contract-{step}-{field}")
    payload = _discovery_payload(
        candidate_id=f"authority:{entity_type}:contract",
        query="Contract Candidate",
        entity_type=entity_type,
        field=f"{step}.{field}",
    )
    discovery = SimpleNamespace(discover=lambda _request: payload)
    diagnostics = ResearchDiagnostics(
        context_revision="test-context",
        active_step=step,
        changed_fields=[],
    )

    groups = ResearchOrchestrator(entity_discovery=discovery)._run_entity_discovery(
        context=_context(edition, step=step),
        tasks=[{"step": step, "field": field, "query": "Contract Candidate"}],
        diagnostics=diagnostics,
    )

    actions = set(groups[0]["results"][0]["available_actions"])
    assert ("create_draft" in actions) is allow_create_draft


def test_persisted_research_candidate_cannot_bypass_field_create_draft_policy(admin_user):
    _work, edition = _edition(title="persisted-translation-contract")
    item = _item(admin_user, edition)
    payload = _discovery_payload(
        candidate_id="authority:work:translation-contract",
        query="Original Work Candidate",
        entity_type="work",
        field="work.translation_of",
    )

    ResearchOrchestrator._persist_intake_entity_candidates(
        item=item,
        groups=[payload],
    )

    candidate = EntityResolutionCandidate.objects.get(upload_item=item)
    assert "create_draft" not in available_resolution_actions(candidate)
    assert "create_draft" not in payload["results"][0]["available_actions"]
    with pytest.raises(ResolutionDecisionError, match="不支持此操作"):
        decide_entity_resolution(
            candidate,
            action="create_draft",
            target_type="work",
            actor=admin_user,
            reason="contract bypass regression",
        )


def test_research_candidate_does_not_claim_same_named_legacy_ocr_candidate(admin_user):
    _work, edition = _edition(title="candidate-source-boundary")
    item = _item(admin_user, edition)
    legacy = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="Same Named Person",
        candidate_entity_type="person_draft",
        label="Same Named Person",
        supporting_properties={
            "extraction_method": "ocr",
            "source_field": "front_matter",
        },
        preview_data={"source": "ocr", "text": "Same Named Person"},
    )
    original_properties = dict(legacy.supporting_properties)
    original_preview = dict(legacy.preview_data)
    payload = {
        "entity_type": "person",
        "field": "contributors.contributors",
        "results": [
            {
                "id": "web:same-name:research",
                "entity_type": "person",
                "label": "Same Named Person",
                "candidate_group": "external_web",
                "provider": "searxng",
                "source_url": "https://example.org/same-named-person",
                "evidence_status": "lead_only",
                "confidence": 0.61,
                "available_actions": ["inspect", "keep_unresolved", "reject"],
            }
        ],
    }

    ResearchOrchestrator._persist_intake_entity_candidates(
        item=item,
        groups=[payload],
    )

    rows = EntityResolutionCandidate.objects.filter(upload_item=item)
    assert rows.count() == 2
    legacy.refresh_from_db()
    assert legacy.status == EntityResolutionCandidate.Status.PROPOSED
    assert legacy.supporting_properties == original_properties
    assert legacy.preview_data == original_preview
    research = rows.exclude(pk=legacy.pk).get()
    assert payload["results"][0]["review_candidate_id"] == str(research.id)
    assert research.supporting_properties["research_candidate_key"]
    assert research.supporting_properties["provider"] == "searxng"
    assert research.supporting_properties["evidence_status"] == "lead_only"


def test_work_research_api_binds_post_and_latest_get_to_requested_edition(
    api_client,
    admin_user,
):
    work, first_edition = _edition(title="edition-bound-research")
    second_edition = Edition.objects.create(
        work=work,
        publication_year=2027,
        publisher="第二版本出版社",
        is_primary=False,
    )
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        second_run, _created = ResearchOrchestrator().prepare(
            second_edition,
            active_step="work",
            dispatch=False,
        )
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/library/works/{work.id}/research/"

    latest = api_client.get(url, {"edition_id": str(second_edition.id)})
    assert latest.status_code == 200
    assert latest.data["id"] == str(second_run.id)
    assert latest.data["edition_id"] == str(second_edition.id)

    observed = {}

    def prepare(_self, selected_edition, **_kwargs):
        observed["edition_id"] = selected_edition.id
        return second_run, False

    with patch(
        "catalog.research_views.ResearchOrchestrator.prepare",
        autospec=True,
        side_effect=prepare,
    ):
        started = api_client.post(
            url,
            {
                "edition_id": str(second_edition.id),
                "step": "work",
                "draft": {"work": {"title": "未保存题名"}},
            },
            format="json",
        )
    assert started.status_code == 200
    assert observed["edition_id"] == second_edition.id

    other_work, other_edition = _edition(title="wrong-work-edition")
    assert other_work.id != work.id
    mismatch = api_client.get(url, {"edition_id": str(other_edition.id)})
    assert mismatch.status_code == 404


def test_read_only_research_latest_is_scoped_to_requested_step(api_client):
    reviewer = _reviewer()
    work, edition = _edition(title="step-scoped-latest-research")
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        work_run, _created = ResearchOrchestrator().prepare(
            edition,
            active_step="work",
            dispatch=False,
        )
        knowledge_run, _created = ResearchOrchestrator().prepare(
            edition,
            active_step="knowledge",
            dispatch=False,
        )
    api_client.force_authenticate(reviewer)
    url = f"/api/catalog/admin/library/works/{work.id}/research/"

    work_response = api_client.get(url, {"step": "work"})
    knowledge_response = api_client.get(url, {"step": "knowledge"})
    invalid_response = api_client.get(url, {"step": "unknown-step"})

    assert work_response.status_code == 200
    assert work_response.data["id"] == str(work_run.id)
    assert knowledge_response.status_code == 200
    assert knowledge_response.data["id"] == str(knowledge_run.id)
    assert invalid_response.status_code == 400


@pytest.mark.parametrize(
    "payload",
    [
        {"step": "work", "field": "contributors", "entity_type": "person"},
        {"step": "bibliography", "field": "publisher", "entity_type": "person"},
        {"step": "reader", "field": "text_layer_status", "entity_type": "work"},
    ],
)
def test_direct_entity_discovery_rejects_step_field_and_entity_type_mismatch(
    api_client,
    admin_user,
    payload,
):
    work, edition = _edition(title="direct-contract-validation")
    api_client.force_authenticate(admin_user)
    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "work_id": str(work.id),
            "edition_id": str(edition.id),
            "query": "Max Weber",
            **payload,
        },
        format="json",
    )
    assert response.status_code == 400
    assert not EntityResolutionCandidate.objects.exists()


def test_direct_entity_discovery_without_work_context_keeps_universal_results_read_only(
    api_client,
    admin_user,
    monkeypatch,
):
    Person.objects.create(
        preferred_name="George Herbert Mead",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.authority_suggestions",
        lambda entity_type, query: {"results": [], "warnings": []},
    )

    class SearchAdapter:
        def search(self, query, *, limit):
            assert query == "George Herbert Mead"
            return [
                SearchResult(
                    url="https://plato.stanford.edu/entries/mead/",
                    title="George Herbert Mead",
                    snippet="Discovery lead only.",
                    provider="searxng",
                    source_class="scholarly_encyclopedia",
                )
            ], None

    monkeypatch.setattr(
        "catalog.services.research.entity_discovery.configured_web_search_adapter",
        lambda: SearchAdapter(),
    )
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/catalog/admin/research/entity-discovery/",
        {
            "step": "contributors",
            "field": "contributors",
            "entity_type": "person",
            "query": "George Herbert Mead",
        },
        format="json",
    )

    assert response.status_code == 200
    groups = {row["candidate_group"] for row in response.data["results"]}
    assert {"local", "external_web", "unresolved"} <= groups
    assert response.data["context_fingerprint"]
    assert all(
        not ({"create_draft", "keep_unresolved", "reject"} & set(row["available_actions"]))
        for row in response.data["results"]
    )
    web_row = next(
        row for row in response.data["results"]
        if row["candidate_group"] == "external_web"
    )
    assert web_row["evidence_status"] == "lead_only"
    assert not EntityResolutionCandidate.objects.exists()


def test_direct_discovery_does_not_advertise_decisions_without_persistence_support(
    api_client,
    admin_user,
):
    work, edition = _edition(
        title="journal-action-contract",
        document_type=DocumentType.JOURNAL_ARTICLE,
    )
    payload = _discovery_payload(
        candidate_id="web:journal:test",
        query="Sociological Theory",
        group="external_web",
        entity_type="journal",
        field="bibliography.journal_title",
    )
    api_client.force_authenticate(admin_user)
    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=payload,
    ):
        response = api_client.post(
            "/api/catalog/admin/research/entity-discovery/",
            {
                "work_id": str(work.id),
                "edition_id": str(edition.id),
                "step": "bibliography",
                "field": "journal_title",
                "entity_type": "journal",
                "query": "Sociological Theory",
            },
            format="json",
        )

    assert response.status_code == 200
    assert response.data["results"][0]["available_actions"] == ["inspect"]


def test_research_execution_locks_only_run_and_avoids_nullable_user_join():
    queryset = ResearchOrchestrator._execution_queryset()

    assert queryset.query.select_for_update is True
    assert queryset.query.select_for_update_of == ("self",)
    assert "accounts_user" not in str(queryset.query)


def test_research_task_records_unexpected_pre_execution_failure(admin_user):
    _work, edition = _edition()
    run, _created = ResearchOrchestrator().prepare(
        edition,
        active_step="contributors",
        draft_data={"contributors": {"items": [{"display_name": "George Herbert Mead"}]}},
        actor=admin_user,
        dispatch=False,
    )

    with patch(
        "catalog.services.research.orchestrator.ResearchOrchestrator.execute",
        side_effect=RuntimeError("forced lock failure"),
    ):
        result = execute_research_run.apply(args=[str(run.id)], throw=False)

    run.refresh_from_db()
    assert result.failed()
    assert run.status == ResearchRun.Status.FAILED
    assert run.error_code == "research_task_failed"
    assert run.error_message == "forced lock failure"


def test_research_task_converts_soft_timeout_to_degraded_terminal_state(admin_user):
    _work, edition = _edition()
    run, _created = ResearchOrchestrator().prepare(
        edition,
        active_step="contributors",
        draft_data={"contributors": {"items": [{"display_name": "George Herbert Mead"}]}},
        actor=admin_user,
        dispatch=False,
    )

    with patch(
        "catalog.services.research.orchestrator.ResearchOrchestrator.execute",
        side_effect=SoftTimeLimitExceeded(),
    ):
        result = execute_research_run.apply(args=[str(run.id)], throw=False)

    run.refresh_from_db()
    assert result.successful()
    assert run.status == ResearchRun.Status.DEGRADED
    assert run.error_code == "research_timeout"
    assert any(row["code"] == "research_timeout" for row in run.diagnostics["errors"])


def test_orchestrator_does_not_swallow_provider_soft_timeout(admin_user):
    run = _queued_research_run(admin_user, title="provider-soft-timeout")
    orchestrator = ResearchOrchestrator()
    orchestrator._run_enrichment = lambda **_kwargs: (_ for _ in ()).throw(
        SoftTimeLimitExceeded()
    )

    with patch(
        "catalog.services.research.orchestrator.ResearchOrchestrator",
        return_value=orchestrator,
    ):
        result = execute_research_run.apply(args=[str(run.id)], throw=False)

    run.refresh_from_db()
    assert result.successful()
    assert run.status == ResearchRun.Status.DEGRADED
    assert run.error_code == "research_timeout"


def test_celery_research_ownership_inventory_requires_complete_worker_replies(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = False
    worker = "celery@test"
    complete = SimpleNamespace(
        ping=lambda: {worker: {"ok": "pong"}},
        active=lambda: {worker: [{"id": "active-task"}]},
        reserved=lambda: {worker: [{"id": "reserved-task"}]},
        scheduled=lambda: {
            worker: [{"request": {"id": "scheduled-task"}}],
        },
    )
    with patch("config.celery.app.control.inspect", return_value=complete):
        snapshot = celery_research_ownership_snapshot(timeout_seconds=0.2)

    assert snapshot.available is True
    assert snapshot.workers == (worker,)
    assert snapshot.task_ids == frozenset(
        {"active-task", "reserved-task", "scheduled-task"}
    )

    partial = SimpleNamespace(
        ping=lambda: {worker: {"ok": "pong"}},
        active=lambda: {worker: []},
        reserved=lambda: {},
        scheduled=lambda: {worker: []},
    )
    with patch("config.celery.app.control.inspect", return_value=partial):
        unavailable = celery_research_ownership_snapshot(timeout_seconds=0.2)

    assert unavailable.available is False
    assert unavailable.task_ids == frozenset()
    assert "不完整" in unavailable.detail


def test_research_task_claim_refreshes_updated_at_and_single_recovery_fails_closed(
    admin_user,
):
    run = _queued_research_run(admin_user, title="claim-refresh-single-recovery")
    stale_at = timezone.now() - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=run.pk).update(updated_at=stale_at)
    observed = {}

    def inspect_between_claim_and_execution(run_id, *, task_id=""):
        claimed = ResearchRun.objects.get(pk=run_id)
        assert task_id == claimed.task_id
        observed["task_id"] = claimed.task_id
        observed["updated_at"] = claimed.updated_at
        transition = recover_orphaned_research_run(
            str(run_id),
            stale_after_seconds=300,
            now=timezone.now(),
            ownership_snapshot=CeleryOwnershipSnapshot(
                available=True,
                task_ids=frozenset(),
                workers=("celery@test",),
            ),
        )
        observed["recovery_reason"] = transition.reason
        return ResearchRun.objects.get(pk=run_id)

    with patch(
        "catalog.services.research.orchestrator.ResearchOrchestrator.execute",
        side_effect=inspect_between_claim_and_execution,
    ):
        result = execute_research_run.apply(args=[str(run.id)], throw=False)

    run.refresh_from_db()
    assert result.successful()
    assert observed["task_id"]
    assert observed["updated_at"] > stale_at
    assert observed["recovery_reason"] == "recent"
    assert run.status == ResearchRun.Status.QUEUED
    assert run.task_id == observed["task_id"]
    assert not AuditEvent.objects.filter(
        action="research_run_orphan_recovered",
        object_id=str(run.id),
    ).exists()


def test_batch_recovery_rechecks_staleness_after_a_task_claims_during_inventory(
    admin_user,
):
    target = _queued_research_run(admin_user, title="claim-during-inventory-target")
    other = _queued_research_run(admin_user, title="claim-during-inventory-other")
    now = timezone.now()
    stale_at = now - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=target.pk).update(task_id="", updated_at=stale_at)
    ResearchRun.objects.filter(pk=other.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="lost-other-task",
        started_at=stale_at,
        updated_at=stale_at,
    )

    def claim_target_while_inventory_is_collected():
        with patch(
            "catalog.services.research.orchestrator.ResearchOrchestrator.execute",
            side_effect=lambda run_id, **_kwargs: ResearchRun.objects.get(pk=run_id),
        ):
            claimed = execute_research_run.apply(
                args=[str(target.id)],
                throw=False,
            )
        assert claimed.successful()
        return CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset(),
            workers=("celery@test",),
        )

    with patch(
        "catalog.services.research.recovery.celery_research_ownership_snapshot",
        side_effect=claim_target_while_inventory_is_collected,
    ):
        details = recover_stale_research_runs(
            actor=admin_user,
            stale_after_seconds=300,
            now=now,
        )

    target.refresh_from_db()
    other.refresh_from_db()
    assert target.task_id
    assert target.updated_at > stale_at
    assert target.status == ResearchRun.Status.QUEUED
    assert other.status == ResearchRun.Status.CANCELED
    assert details["candidates"] == 1
    assert details["recovered"] == 1
    assert details["run_ids"] == [str(other.id)]
    assert not AuditEvent.objects.filter(
        action="research_run_orphan_recovered",
        object_id=str(target.id),
    ).exists()


def test_stale_research_recovery_closes_only_inventory_confirmed_orphans_and_is_idempotent(
    admin_user,
):
    initial_status = ResearchRun.Status.RUNNING
    run = _queued_research_run(admin_user, title=f"stale-{initial_status}")
    now = timezone.now()
    stale_at = now - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=run.pk).update(
        status=initial_status,
        task_id=f"lost-{initial_status}-task",
        started_at=stale_at if initial_status == ResearchRun.Status.RUNNING else None,
        diagnostics={"preserved": {"provider": "local", "count": 2}},
        updated_at=stale_at,
    )
    inventory = CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        workers=("celery@test",),
    )

    first = recover_orphaned_research_run(
        str(run.id),
        actor=admin_user,
        request_id=f"recover-{initial_status}",
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=inventory,
    )
    repeated = recover_orphaned_research_run(
        str(run.id),
        actor=admin_user,
        request_id=f"recover-{initial_status}",
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=inventory,
    )

    assert first.changed is True
    assert first.reason == f"recovered_{initial_status}"
    assert repeated.changed is False
    assert repeated.reason == "terminal"
    run.refresh_from_db()
    assert run.status == ResearchRun.Status.CANCELED
    assert run.finished_at == now
    assert run.task_id == f"lost-{initial_status}-task"
    assert run.diagnostics["preserved"] == {"provider": "local", "count": 2}
    lifecycle = run.diagnostics["lifecycle_events"][-1]
    assert lifecycle["code"] == "research_run_orphaned"
    assert lifecycle["previous_status"] == initial_status
    assert lifecycle["stale_after_seconds"] == 300
    audits = AuditEvent.objects.filter(
        action="research_run_orphan_recovered",
        object_id=str(run.id),
    )
    assert audits.count() == 1
    audit = audits.get()
    assert audit.actor_id == admin_user.id
    assert audit.request_id == f"recover-{initial_status}"
    assert audit.before["status"] == initial_status
    assert audit.after["status"] == ResearchRun.Status.CANCELED


def test_stale_preassigned_queued_research_is_classified_for_same_owner_redispatch(
    admin_user,
):
    run = _queued_research_run(admin_user, title="broker-waiting-task")
    now = timezone.now()
    ResearchRun.objects.filter(pk=run.pk).update(
        task_id="preassigned-broker-task",
        updated_at=now - timedelta(minutes=30),
    )

    transition = recover_orphaned_research_run(
        str(run.id),
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset(),
            workers=("celery@test",),
        ),
    )

    assert transition.changed is False
    assert transition.reason == "redispatchable"
    run.refresh_from_db()
    assert run.status == ResearchRun.Status.QUEUED
    assert run.task_id == "preassigned-broker-task"


def test_stale_preassigned_queued_research_is_redispatched_with_same_task_id_and_executes_once(
    admin_user,
    django_capture_on_commit_callbacks,
):
    run = _queued_research_run(admin_user, title="broker-message-not-received")
    task_id = "preassigned-broker-task"
    now = timezone.now()
    stale_at = now - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=run.pk).update(
        task_id=task_id,
        diagnostics={"preserved": {"source": "before-broker-publish"}},
        updated_at=stale_at,
    )

    with (
        patch(
            "catalog.services.research.recovery._redispatch_research_run"
        ) as redispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        details = recover_stale_research_runs(
            actor=admin_user,
            stale_after_seconds=300,
            now=now,
            ownership_snapshot=CeleryOwnershipSnapshot(
                available=True,
                task_ids=frozenset(),
                workers=("celery@test",),
            ),
        )

    run.refresh_from_db()
    assert details["candidates"] == 1
    assert details["recovered"] == 0
    assert details["redispatched"] == 1
    assert details["redispatched_ids"] == [str(run.id)]
    assert run.status == ResearchRun.Status.QUEUED
    assert run.task_id == task_id
    assert run.updated_at > stale_at
    assert run.diagnostics["preserved"] == {"source": "before-broker-publish"}
    assert run.diagnostics["redispatch_count"] == 1
    assert run.diagnostics["lifecycle_events"][-1]["code"] == "research_run_redispatched"
    redispatch.assert_called_once_with(str(run.id), task_id)

    with (
        patch(
            "catalog.services.research.orchestrator.ResearchOrchestrator._run_enrichment",
            return_value=[],
        ) as enrichment,
        patch(
            "catalog.services.research.orchestrator.ResearchOrchestrator._run_entity_discovery",
            return_value=[],
        ),
        patch(
            "catalog.services.research.orchestrator.ResearchOrchestrator._run_editorial_evidence",
            return_value=[],
        ),
        patch(
            "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
            return_value={"suggestions": [], "errors": []},
        ),
    ):
        first_delivery = execute_research_run.apply(
            args=[str(run.id)],
            task_id=task_id,
            throw=False,
        )
        duplicate_delivery = execute_research_run.apply(
            args=[str(run.id)],
            task_id=task_id,
            throw=False,
        )

    run.refresh_from_db()
    assert first_delivery.successful()
    assert duplicate_delivery.successful()
    assert run.status == ResearchRun.Status.COMPLETED
    assert run.task_id == task_id
    assert enrichment.call_count == 1


def test_stale_research_recovery_skips_recent_active_unverified_and_terminal_runs(admin_user):
    now = timezone.now()
    stale_at = now - timedelta(minutes=30)
    empty_inventory = CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        workers=("celery@test",),
    )
    recent = _queued_research_run(admin_user, title="recent-run")
    ResearchRun.objects.filter(pk=recent.pk).update(task_id="recent-task", updated_at=now)
    active = _queued_research_run(admin_user, title="active-run")
    ResearchRun.objects.filter(pk=active.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="active-task",
        started_at=stale_at,
        updated_at=stale_at,
    )
    unverified = _queued_research_run(admin_user, title="unverified-run")
    ResearchRun.objects.filter(pk=unverified.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="unverified-task",
        started_at=stale_at,
        updated_at=stale_at,
    )
    terminal = _queued_research_run(admin_user, title="terminal-run")
    ResearchRun.objects.filter(pk=terminal.pk).update(
        status=ResearchRun.Status.COMPLETED,
        task_id="finished-task",
        finished_at=stale_at,
        updated_at=stale_at,
    )

    recent_result = recover_orphaned_research_run(
        str(recent.id),
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=empty_inventory,
    )
    active_result = recover_orphaned_research_run(
        str(active.id),
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset({"active-task"}),
            workers=("celery@test",),
        ),
    )
    unverified_result = recover_orphaned_research_run(
        str(unverified.id),
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=CeleryOwnershipSnapshot(
            available=False,
            task_ids=frozenset(),
            detail="control unavailable",
        ),
    )
    terminal_result = recover_orphaned_research_run(
        str(terminal.id),
        stale_after_seconds=300,
        now=now,
        ownership_snapshot=empty_inventory,
    )

    assert recent_result.reason == "recent"
    assert active_result.reason == "celery_owned"
    assert unverified_result.reason == "ownership_unverified"
    assert terminal_result.reason == "terminal"
    assert not any(
        result.changed
        for result in (recent_result, active_result, unverified_result, terminal_result)
    )
    assert not AuditEvent.objects.filter(action="research_run_orphan_recovered").exists()


def test_research_cancel_api_requires_permission_locks_audits_and_is_idempotent(
    api_client,
    admin_user,
    reader_user,
):
    run = _queued_research_run(admin_user, title="cancel-api")
    path = f"/api/catalog/admin/research/runs/{run.id}/"

    anonymous = api_client.post(path, {"action": "cancel"}, format="json")
    api_client.force_authenticate(reader_user)
    reader = api_client.post(path, {"action": "cancel"}, format="json")
    api_client.force_authenticate(admin_user)
    canceled = api_client.post(
        path,
        {"action": "cancel"},
        format="json",
        HTTP_X_REQUEST_ID="cancel-api-request",
    )
    repeated = api_client.post(
        path,
        {"action": "cancel"},
        format="json",
        HTTP_X_REQUEST_ID="cancel-api-request",
    )

    assert anonymous.status_code in {401, 403}
    assert reader.status_code == 403
    assert canceled.status_code == 200
    assert canceled.data["status"] == ResearchRun.Status.CANCELED
    assert repeated.status_code == 200
    assert repeated.data["status"] == ResearchRun.Status.CANCELED
    run.refresh_from_db()
    assert run.finished_at is not None
    audit = AuditEvent.objects.get(
        action="research_run_canceled",
        object_id=str(run.id),
    )
    assert audit.actor_id == admin_user.id
    assert audit.request_id == "cancel-api-request"


def test_orchestrator_terminal_writes_do_not_overwrite_concurrent_cancel(admin_user):
    run = _queued_research_run(admin_user, title="orchestrator-cancel-race")
    orchestrator = ResearchOrchestrator()

    def cancel_during_execution(**_kwargs):
        cancel_research_run(str(run.id), actor=admin_user)
        return []

    orchestrator._run_enrichment = cancel_during_execution
    orchestrator._run_entity_discovery = lambda **_kwargs: []
    orchestrator._run_editorial_evidence = lambda **_kwargs: []
    with patch(
        "catalog.services.research.orchestrator.WorkflowSuggestionAggregator.aggregate",
        return_value={"suggestions": [], "errors": []},
    ):
        completed = orchestrator.execute(str(run.id))

    assert completed.status == ResearchRun.Status.CANCELED
    assert AuditEvent.objects.filter(
        action="research_run_canceled",
        object_id=str(run.id),
    ).count() == 1


def test_orchestrator_failure_write_does_not_overwrite_concurrent_cancel(admin_user):
    run = _queued_research_run(admin_user, title="orchestrator-failure-cancel-race")
    orchestrator = ResearchOrchestrator()

    def cancel_then_fail(**_kwargs):
        cancel_research_run(str(run.id), actor=admin_user)
        raise RuntimeError("provider failed after cancel")

    orchestrator._run_enrichment = cancel_then_fail
    completed = orchestrator.execute(str(run.id))

    assert completed.status == ResearchRun.Status.CANCELED
    assert completed.error_code == "research_run_canceled"


@pytest.mark.parametrize(
    ("task_error", "celery_result_failed"),
    [
        (SoftTimeLimitExceeded(), False),
        (RuntimeError("worker failure after cancel"), True),
    ],
)
def test_task_terminal_writes_do_not_overwrite_concurrent_cancel(
    admin_user,
    task_error,
    celery_result_failed,
):
    run = _queued_research_run(
        admin_user,
        title=f"task-cancel-race-{task_error.__class__.__name__}",
    )

    def cancel_then_raise(_run_id, **_kwargs):
        cancel_research_run(str(run.id), actor=admin_user)
        raise task_error

    with patch(
        "catalog.services.research.orchestrator.ResearchOrchestrator.execute",
        side_effect=cancel_then_raise,
    ):
        result = execute_research_run.apply(args=[str(run.id)], throw=False)

    run.refresh_from_db()
    assert result.failed() is celery_result_failed
    assert run.status == ResearchRun.Status.CANCELED
    assert run.error_code == "research_run_canceled"
    assert AuditEvent.objects.filter(
        action="research_run_canceled",
        object_id=str(run.id),
    ).count() == 1


def test_productive_probe_uses_latest_terminal_and_reports_nonterminal_orphans(admin_user):
    now = timezone.now()
    terminal = _queued_research_run(admin_user, title="probe-terminal")
    ResearchRun.objects.filter(pk=terminal.pk).update(
        status=ResearchRun.Status.COMPLETED,
        diagnostics={"candidate_counts": {"entities": 3}},
        finished_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    orphan = _queued_research_run(admin_user, title="probe-newer-null-finished")
    ResearchRun.objects.filter(pk=orphan.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="orphan-task",
        started_at=now - timedelta(minutes=30),
        finished_at=None,
        updated_at=now - timedelta(minutes=30),
    )
    inventory = CeleryOwnershipSnapshot(
        available=True,
        task_ids=frozenset(),
        workers=("celery@test",),
    )

    with patch(
        "catalog.services.research.recovery.celery_research_ownership_snapshot",
        return_value=inventory,
    ):
        result = _research_productive_probe()

    assert result.details["run_id"] == str(terminal.id)
    assert result.details["status"] == ResearchRun.Status.COMPLETED
    assert result.details["orphan_nonterminal_count"] == 1
    assert result.details["orphan_nonterminal_ids"] == [str(orphan.id)]
    assert result.details["orphan_queued_count"] == 0
    assert result.details["orphan_queued_ids"] == []
    assert result.details["orphan_running_count"] == 1
    assert result.details["orphan_running_ids"] == [str(orphan.id)]
    assert result.productive is False
    assert result.error_code == "research_orphaned_runs"


def test_processing_center_recovery_action_closes_stale_research_runs(
    admin_user,
    django_capture_on_commit_callbacks,
):
    run = _queued_research_run(admin_user, title="processing-center-stale-run")
    stale_at = timezone.now() - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=run.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="lost-processing-center-task",
        started_at=stale_at,
        updated_at=stale_at,
    )
    incident = HealthIncident.objects.create(
        incident_key=f"research-stale:{uuid4()}",
        capability="research",
        probe_key="research_productive",
        error_code="research_orphaned_runs",
        error_message="存在孤儿 ResearchRun",
        safe_recovery_actions=["recover_stale_research"],
    )

    with (
        patch("catalog.tasks.execute_health_recovery.apply_async"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        recovery, created = request_recovery(
            incident,
            action="recover_stale_research",
            actor=admin_user,
            request_key="recover-stale-research",
        )
    with patch(
        "catalog.services.research.recovery.celery_research_ownership_snapshot",
        return_value=CeleryOwnershipSnapshot(
            available=True,
            task_ids=frozenset(),
            workers=("celery@test",),
        ),
    ):
        completed = execute_recovery(str(recovery.id))

    assert created is True
    assert completed.status == RecoveryAction.Status.SUCCEEDED
    assert completed.details["recovered"] == 1
    run.refresh_from_db()
    assert run.status == ResearchRun.Status.CANCELED
    assert AuditEvent.objects.filter(
        action="research_run_orphan_recovered",
        object_id=str(run.id),
    ).count() == 1


def test_processing_center_stale_research_recovery_fails_closed_and_backs_off_when_inventory_is_unavailable(
    admin_user,
    django_capture_on_commit_callbacks,
):
    run = _queued_research_run(admin_user, title="processing-center-unverified-run")
    stale_at = timezone.now() - timedelta(minutes=30)
    ResearchRun.objects.filter(pk=run.pk).update(
        status=ResearchRun.Status.RUNNING,
        task_id="ownership-cannot-be-verified",
        started_at=stale_at,
        updated_at=stale_at,
    )
    incident = HealthIncident.objects.create(
        incident_key=f"research-unverified:{uuid4()}",
        capability="research",
        probe_key="research_productive",
        error_code="research_ownership_unverified",
        error_message="Celery inventory 不可用",
        safe_recovery_actions=["recover_stale_research"],
    )
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        recovery, _created = request_recovery(
            incident,
            action="recover_stale_research",
            actor=admin_user,
            request_key="recover-unverified-research",
        )

    with (
        patch(
            "catalog.services.research.recovery.celery_research_ownership_snapshot",
            return_value=CeleryOwnershipSnapshot(
                available=False,
                task_ids=frozenset(),
                detail="control unavailable",
            ),
        ),
        patch("catalog.tasks.execute_health_recovery.apply_async") as retry_dispatch,
        django_capture_on_commit_callbacks(execute=True),
    ):
        failed = execute_recovery(str(recovery.id))

    assert failed.status == RecoveryAction.Status.FAILED
    assert failed.attempt == 1
    assert failed.next_retry_at is not None
    retry_dispatch.assert_called_once()
    assert retry_dispatch.call_args.kwargs["countdown"] == 30
    run.refresh_from_db()
    assert run.status == ResearchRun.Status.RUNNING
    assert not AuditEvent.objects.filter(
        action="research_run_orphan_recovered",
        object_id=str(run.id),
    ).exists()


def test_failed_research_recovery_retries_incident_run_in_bounded_celery_task(
    admin_user,
    django_capture_on_commit_callbacks,
):
    target = _queued_research_run(admin_user, title="incident-target-failure")
    unrelated = _queued_research_run(admin_user, title="newer-unrelated-failure")
    now = timezone.now()
    ResearchRun.objects.filter(pk=target.pk).update(
        status=ResearchRun.Status.FAILED,
        error_code="target_failed",
        error_message="target failure",
        finished_at=now - timedelta(minutes=5),
    )
    ResearchRun.objects.filter(pk=unrelated.pk).update(
        status=ResearchRun.Status.FAILED,
        error_code="unrelated_failed",
        error_message="unrelated failure",
        finished_at=now,
    )
    incident = HealthIncident.objects.create(
        incident_key=f"research-retry:{uuid4()}",
        capability="research",
        probe_key="research_productive",
        error_code="target_failed",
        error_message="目标研究失败",
        safe_recovery_actions=["retry_failed_research"],
        details={"run_id": str(target.id)},
    )
    with (
        patch("catalog.tasks.execute_health_recovery.apply_async"),
        django_capture_on_commit_callbacks(execute=True),
    ):
        recovery, _created = request_recovery(
            incident,
            action="retry_failed_research",
            actor=admin_user,
            request_key="retry-exact-failed-run",
        )

    with (
        patch("catalog.tasks.execute_research_run.apply_async") as research_dispatch,
        patch("catalog.services.research.orchestrator.ResearchOrchestrator.execute") as inline_execute,
        django_capture_on_commit_callbacks(execute=True),
    ):
        completed = execute_recovery(
            str(recovery.id),
            task_id=recovery.details["dispatch_task_id"],
        )

    assert completed.status == RecoveryAction.Status.SUCCEEDED
    assert completed.details["research_run_id"] == str(target.id)
    assert completed.details["execution"] == "celery_research_task"
    retry = ResearchRun.objects.get(pk=completed.details["retry_run_id"])
    assert retry.id not in {target.id, unrelated.id}
    assert retry.trigger == ResearchRun.Trigger.HEALTH
    assert retry.status == ResearchRun.Status.QUEUED
    assert retry.diagnostics["retry_of"] == str(target.id)
    research_dispatch.assert_called_once_with(args=[str(retry.id)], task_id=retry.task_id)
    inline_execute.assert_not_called()
    assert execute_research_run.soft_time_limit == 40
    unrelated.refresh_from_db()
    assert unrelated.status == ResearchRun.Status.FAILED


def test_health_dimensions_incident_resolution_and_recovery_are_persisted_and_idempotent(admin_user):
    probe_key = "test.v292.functional-health"
    state = {
        "result": ProbeResult(
            configured=True,
            reachable=True,
            functional=True,
            productive=False,
            summary="可调用但没有产生候选。",
            details={"candidate_count": 0},
            error_code="zero_candidates",
        )
    }
    if not any(row.key == probe_key for row in HEALTH_CHECKS.all()):
        HEALTH_CHECKS.register(
            HealthProbe(
                key=probe_key,
                capability="research",
                label="2.9.2 测试探测",
                interval_seconds=300,
                runner=lambda: state["result"],
                affected_features=("Research 候选",),
                probable_causes=("测试 Provider 无候选",),
                safe_recovery_actions=("rerun_probe",),
            )
        )

    degraded = run_health_probe(probe_key, source=HealthCheckRun.Source.MANUAL, actor=admin_user)
    assert degraded.status == HealthCheckRun.Status.DEGRADED
    assert (
        degraded.configured,
        degraded.reachable,
        degraded.functional,
        degraded.productive,
    ) == (True, True, True, False)

    incident = HealthIncident.objects.get(probe_key=probe_key)
    assert incident.status == HealthIncident.Status.OPEN
    assert incident.error_code == "zero_candidates"
    snapshot = functional_health_snapshot()
    dependency = next(
        dependency
        for capability in snapshot["capabilities"]
        for dependency in capability["dependencies"]
        if dependency["probe_key"] == probe_key
    )
    assert {
        key: dependency[key]
        for key in ("configured", "reachable", "functional", "productive")
    } == {
        "configured": True,
        "reachable": True,
        "functional": True,
        "productive": False,
    }
    assert snapshot["page_load_performs_live_probes"] is False

    with patch("catalog.tasks.execute_health_recovery.apply_async"):
        recovery, created = request_recovery(
            incident,
            action="rerun_probe",
            actor=admin_user,
            request_key="same-browser-request",
        )
        repeated, repeated_created = request_recovery(
            incident,
            action="rerun_probe",
            actor=admin_user,
            request_key="same-browser-request",
        )

    incident.refresh_from_db()
    assert recovery.id == repeated.id
    assert created is True
    assert repeated_created is False
    assert RecoveryAction.objects.count() == 1
    assert incident.recovery_attempt_count == 1
    assert AuditEvent.objects.filter(action="health_recovery_requested").count() == 1

    healthy_run = HealthCheckRun.objects.create(
        probe_key=probe_key,
        capability="research",
        status=HealthCheckRun.Status.HEALTHY,
        source=HealthCheckRun.Source.RECOVERY,
        configured=True,
        reachable=True,
        functional=True,
        productive=True,
        summary="恢复复核通过。",
    )
    with patch(
        "catalog.services.system_health.run_health_probe",
        return_value=healthy_run,
    ):
        completed = execute_recovery(str(recovery.id))
        repeated_completion = execute_recovery(str(recovery.id))

    assert completed.status == RecoveryAction.Status.SUCCEEDED
    assert repeated_completion.status == RecoveryAction.Status.SUCCEEDED
    assert completed.attempt == 1
    assert AuditEvent.objects.filter(action="health_recovery_completed").count() == 1

    state["result"] = ProbeResult(
        configured=True,
        reachable=True,
        functional=True,
        productive=True,
        summary="已恢复并产生有效结果。",
        details={"candidate_count": 2},
    )
    healthy = run_health_probe(probe_key)
    incident.refresh_from_db()
    assert healthy.status == HealthCheckRun.Status.HEALTHY
    assert incident.status == HealthIncident.Status.RESOLVED
    assert incident.resolved_at is not None


@pytest.mark.parametrize(
    ("state", "expected_public_url", "public_status"),
    [
        (PublicationState.DRAFT, "", 404),
        (PublicationState.READY, "", 404),
        (PublicationState.PUBLISHED, "/works/v292-preview-published", 200),
    ],
)
def test_preview_urls_and_public_visibility_follow_publication_state(
    api_client,
    admin_user,
    state,
    expected_public_url,
    public_status,
):
    slug = f"v292-preview-{state}"
    _work, edition = _edition(
        title=f"预览测试 {state}",
        state=state,
        slug=slug,
    )

    workspace = build_admin_workspace(
        edition,
        user=admin_user,
        mode="maintenance",
    )
    assert workspace["context"]["pdf_preview_url"] == ""
    assert workspace["context"]["page_preview_url"] == f"/admin/preview/works/{edition.id}"
    assert workspace["context"]["public_url"] == expected_public_url

    public_response = api_client.get(f"/api/catalog/works/{slug}/")
    assert public_response.status_code == public_status

    anonymous_preview = api_client.get(
        f"/api/catalog/admin/page-preview/editions/{edition.id}/"
    )
    assert anonymous_preview.status_code in {401, 403}

    api_client.force_authenticate(admin_user)
    admin_preview = api_client.get(
        f"/api/catalog/admin/page-preview/editions/{edition.id}/"
    )
    assert admin_preview.status_code == 200
    assert admin_preview.data["preview_mode"] is True
    assert admin_preview.data["publication_state"] == state
    assert admin_preview.data["public_url"] == expected_public_url
    assert admin_preview.data["pdf_preview_url"] == ""


def test_research_entity_decision_create_draft_is_explicit_idempotent_and_preserves_locks(
    api_client,
    admin_user,
):
    _work, edition = _edition(title="实体决定测试作品")
    item = _item(admin_user, edition)
    existing = Person.objects.create(
        preferred_name="Existing Verified Person",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    lock = FieldLock.objects.create(
        edition=edition,
        field_name="contributors",
        locked_by=admin_user,
        locked_value=[{"person_id": str(existing.id), "role": "author"}],
        reason="人工确认的责任者关系不得被研究候选覆盖",
    )
    candidate_id = "authority:wikidata:Q-new-person"
    query = "New Research Person"
    discovery = _discovery_payload(candidate_id=candidate_id, query=query)
    request = _entity_decision_request(
        item=item,
        candidate_id=candidate_id,
        query=query,
        action="create_draft",
    )
    api_client.force_authenticate(admin_user)

    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=discovery,
    ):
        response = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            request,
            format="json",
            HTTP_X_REQUEST_ID="v292-create-draft",
        )
        repeated = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            request,
            format="json",
            HTTP_X_REQUEST_ID="v292-create-draft",
        )

    assert response.status_code == 200
    assert response.data["action"] == "create_draft"
    assert response.data["idempotent"] is False
    assert response.data["candidate"]["status"] == EntityResolutionCandidate.Status.CREATE_DRAFT
    assert repeated.status_code == 200
    assert repeated.data["idempotent"] is True

    candidate = EntityResolutionCandidate.objects.get(
        upload_item=item,
        source_name=query,
    )
    created = Person.objects.get(pk=candidate.candidate_entity_id)
    assert created.preferred_name == query
    assert created.authority_status == Person.AuthorityStatus.DRAFT
    assert Contribution.objects.filter(
        edition=edition,
        person=created,
        approved=False,
    ).exists()
    existing.refresh_from_db()
    assert existing.authority_status == Person.AuthorityStatus.VERIFIED
    assert existing.preferred_name == "Existing Verified Person"
    assert Person.objects.count() == 2

    lock.refresh_from_db()
    assert lock.locked_value == [{"person_id": str(existing.id), "role": "author"}]
    assert lock.reason == "人工确认的责任者关系不得被研究候选覆盖"
    assert DecisionLog.objects.filter(
        resolution_candidate=candidate,
        action="create_draft",
    ).count() == 1
    audit = AuditEvent.objects.get(
        action="research_entity_create_draft",
        object_id=str(candidate.id),
    )
    assert audit.actor_id == admin_user.id
    assert audit.request_id == "v292-create-draft"
    assert audit.before["status"] == EntityResolutionCandidate.Status.PROPOSED
    assert audit.after["status"] == EntityResolutionCandidate.Status.CREATE_DRAFT


@pytest.mark.parametrize(
    ("action", "group", "expected_status", "creates_contributor"),
    [
        (
            "keep_unresolved",
            "unresolved",
            EntityResolutionCandidate.Status.UNRESOLVED,
            True,
        ),
        ("reject", "external_web", EntityResolutionCandidate.Status.REJECTED, False),
    ],
)
def test_research_entity_decision_preserves_verified_authorities_and_contributor_policy(
    api_client,
    admin_user,
    action,
    group,
    expected_status,
    creates_contributor,
):
    _work, edition = _edition(title=f"{action} 测试作品")
    item = _item(admin_user, edition)
    baseline = Person.objects.create(
        preferred_name="Baseline Verified Person",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    candidate_id = f"{group}:person:{action}"
    query = f"Candidate {action}"
    api_client.force_authenticate(_editor())

    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=_discovery_payload(
            candidate_id=candidate_id,
            query=query,
            group=group,
        ),
    ):
        response = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            _entity_decision_request(
                item=item,
                candidate_id=candidate_id,
                query=query,
                action=action,
            ),
            format="json",
            HTTP_X_REQUEST_ID=f"v292-{action}",
        )

    assert response.status_code == 200
    assert response.data["idempotent"] is False
    assert response.data["candidate"]["status"] == expected_status
    candidate = EntityResolutionCandidate.objects.get(upload_item=item, source_name=query)
    assert candidate.status == expected_status
    baseline.refresh_from_db()
    assert baseline.authority_status == Person.AuthorityStatus.VERIFIED
    if creates_contributor:
        created = Person.objects.get(pk=candidate.candidate_entity_id)
        assert created.preferred_name == query
        assert created.authority_status == Person.AuthorityStatus.DRAFT
        assert not ScholarProfile.objects.filter(person=created).exists()
        assert Contribution.objects.filter(
            edition=edition,
            person=created,
            approved=False,
        ).exists()
        assert Person.objects.count() == 2
    else:
        assert candidate.candidate_entity_id == ""
        assert Person.objects.count() == 1
        assert not Contribution.objects.filter(edition=edition).exists()
    assert DecisionLog.objects.filter(
        resolution_candidate=candidate,
        action=action,
    ).count() == 1
    assert AuditEvent.objects.filter(
        action=f"research_entity_{action}",
        object_id=str(candidate.id),
        request_id=f"v292-{action}",
    ).count() == 1


def test_research_entity_decision_rejects_readers_and_normalizes_legacy_reviewer(
    api_client,
    admin_user,
    reader_user,
):
    _work, edition = _edition(title="实体决定鉴权测试")
    item = _item(admin_user, edition)
    candidate_id = "unresolved:person:permission-test"
    query = "Permission Candidate"
    request = _entity_decision_request(
        item=item,
        candidate_id=candidate_id,
        query=query,
        action="keep_unresolved",
    )
    discovery = _discovery_payload(
        candidate_id=candidate_id,
        query=query,
        group="unresolved",
    )

    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=discovery,
    ) as discover:
        anonymous = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            request,
            format="json",
        )
        api_client.force_authenticate(reader_user)
        reader = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            request,
            format="json",
        )
        api_client.force_authenticate(_reviewer())
        reviewer = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            request,
            format="json",
        )

    assert anonymous.status_code in {401, 403}
    assert reader.status_code == 403
    assert reviewer.status_code == 200
    assert discover.call_count == 1
    assert EntityResolutionCandidate.objects.filter(upload_item=item).exists()
    assert DecisionLog.objects.filter(upload_item=item).exists()
    assert AuditEvent.objects.filter(action__startswith="research_entity_").exists()


def test_research_entity_decision_rejects_invalid_or_expired_discovery_candidate(
    api_client,
    admin_user,
):
    _work, edition = _edition(title="过期候选测试")
    item = _item(admin_user, edition)
    stale = EntityResolutionCandidate.objects.create(
        upload_item=item,
        target_type="person",
        source_name="Expired Candidate",
        candidate_entity_type="person_draft",
        label="Expired Candidate",
        supporting_properties={
            "research_field": "contributors.contributors",
            "candidate_group": "authority",
        },
    )
    api_client.force_authenticate(admin_user)
    current_id = "authority:wikidata:current-candidate"
    current = _discovery_payload(
        candidate_id=current_id,
        query="Current Candidate",
    )

    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=current,
    ):
        invalid = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            _entity_decision_request(
                item=item,
                candidate_id="authority:wikidata:does-not-exist",
                query="Current Candidate",
                action="reject",
            ),
            format="json",
        )
        expired = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            _entity_decision_request(
                item=item,
                candidate_id="authority:wikidata:expired-candidate",
                query="Expired Candidate",
                action="create_draft",
            ),
            format="json",
        )

    assert invalid.status_code == 409
    assert expired.status_code == 409
    assert "候选已变化" in invalid.data["detail"]
    assert "候选已变化" in expired.data["detail"]
    stale.refresh_from_db()
    assert stale.status == EntityResolutionCandidate.Status.PROPOSED
    assert stale.candidate_entity_id == ""
    assert Person.objects.count() == 0
    assert DecisionLog.objects.filter(upload_item=item).count() == 0
    assert AuditEvent.objects.filter(action__startswith="research_entity_").count() == 0


def test_research_entity_decision_rejects_local_candidate_and_invalid_action(
    api_client,
    admin_user,
):
    _work, edition = _edition(title="决定参数测试")
    item = _item(admin_user, edition)
    candidate_id = "local:person:test"
    query = "Local Candidate"
    local = _discovery_payload(
        candidate_id=candidate_id,
        query=query,
        group="local",
    )
    api_client.force_authenticate(admin_user)

    invalid_action = api_client.post(
        "/api/catalog/admin/research/entity-decisions/",
        _entity_decision_request(
            item=item,
            candidate_id=candidate_id,
            query=query,
            action="link_existing",
        ),
        format="json",
    )
    with patch(
        "catalog.research_views.UniversalEntityDiscovery.discover",
        return_value=local,
    ):
        local_candidate = api_client.post(
            "/api/catalog/admin/research/entity-decisions/",
            _entity_decision_request(
                item=item,
                candidate_id=candidate_id,
                query=query,
                action="reject",
            ),
            format="json",
        )

    assert invalid_action.status_code == 400
    assert local_candidate.status_code == 409
    assert not EntityResolutionCandidate.objects.filter(upload_item=item).exists()
