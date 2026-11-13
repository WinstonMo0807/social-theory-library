"""Bounded local fixtures and fault injection; not a NAS throughput benchmark."""
from datetime import timedelta
from uuid import uuid4

import httpx
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog import models as m
from tests.test_knowledge_core import source


def test_online_inference_failure_is_shared_but_not_persisted(monkeypatch, settings):
    from catalog.services import discovery_inference as inference
    settings.DISCOVERY_INFERENCE_URL = "http://localhost:8091"
    calls = []
    def unavailable(request):
        calls.append(request.url.path)
        return httpx.Response(503, json={"detail":{"code":"service_unavailable"}})
    transport = httpx.MockTransport(unavailable)
    context = {}
    for _ in range(2):  # channels/expansions of the same query
        with inference.interactive_inference(context):
            for path in ("/normalize", "/embed", "/rerank"):
                with pytest.raises(inference.DiscoveryInferenceError):
                    inference._call(path, {}, transport=transport)
    assert calls == ["/normalize"]
    with inference.interactive_inference({}):
        with pytest.raises(inference.DiscoveryInferenceError):
            inference._call("/normalize", {}, transport=transport)
    assert len(calls) == 2  # the next query can recover immediately
    with pytest.raises(inference.DiscoveryInferenceError):
        inference._call("/embed", {}, transport=transport)
    assert len(calls) == 3  # background calls retain their existing policy


def test_optional_model_budget_is_shared_and_model_missing_is_path_specific(monkeypatch, settings):
    from catalog.services import discovery_inference as inference
    settings.DISCOVERY_QUERY_INFERENCE_BUDGET_SECONDS = 8
    clock, calls = [0.0], []
    monkeypatch.setattr(inference.time, "monotonic", lambda:clock[0])
    def response(path, payload, **kwargs):
        calls.append((path, kwargs["timeout_seconds"]))
        clock[0] += 4
        if path == "/embed":
            raise inference.DiscoveryInferenceError("model_missing")
        return {}
    monkeypatch.setattr(inference, "_request", response)
    with inference.interactive_inference({}) as state:
        with pytest.raises(inference.DiscoveryInferenceError):
            inference._call("/embed", {})
        with pytest.raises(inference.DiscoveryInferenceError):
            inference._call("/embed", {})
        assert inference._call("/normalize", {}) == {}
        with pytest.raises(inference.DiscoveryInferenceError):
            inference._call("/rerank", {})
    assert calls == [("/embed",8), ("/normalize",4)]
    assert state["calls"] == 2 and state["elapsed_seconds"] == 8


def test_interactive_request_signals_cold_service_without_waiting_for_startup(monkeypatch, settings):
    from catalog.services import discovery_inference as inference
    from common import on_demand
    settings.DISCOVERY_INFERENCE_URL = "http://localhost:8091"
    demands, timeouts = [], []
    client = httpx.Client
    def local_client(**kwargs):
        timeouts.append(kwargs["timeout"].read)
        return client(**kwargs, transport=httpx.MockTransport(lambda request:httpx.Response(200, json={})))
    monkeypatch.setattr(httpx, "Client", local_client)
    monkeypatch.setattr(on_demand, "ensure_service", lambda *args, **kwargs:demands.append(kwargs))
    with inference.interactive_inference({}):
        inference._call("/normalize", {})
    inference._call("/normalize", {})
    assert demands[0]["wait_seconds"] == 0 and "wait_seconds" not in demands[1]
    assert timeouts[0] <= 8 and timeouts[1] == settings.DISCOVERY_INFERENCE_TIMEOUT_SECONDS


@pytest.mark.django_db
def test_actual_session_persists_only_safe_measured_diagnostics(monkeypatch, settings):
    from tests.test_discovery_sessions_v308 import make_session
    from catalog.services import discovery_sessions as sessions
    settings.STL_DEEP_RETRIEVAL_ENABLED = False
    session = make_session(status="queued")
    monkeypatch.setattr(sessions, "retrieve_discovery_channel", lambda *a, **kw:{
        "canceled":False, "rows":[], "warnings":[], "version":"", "retrieval":{
            "timings":{"total_ms":123, "ranking_ms":-1, "recall_ms":"unmeasured", "url":"private"},
            "inference":{"calls":1, "elapsed_ms":12, "credential":"private"}}})
    sessions.execute_session(session.pk, session.generation, session.task_id)
    session.refresh_from_db()
    assert session.status == "completed"
    assert session.channels["passages"]["timings"] == {"total_ms":123}
    assert session.channels["passages"]["inference"] == {"calls":1, "elapsed_ms":12}
    public = sessions.serialize_session(session, ["public"])
    assert public["channels"]["passages"]["timings"] == {"total_ms":123}


@pytest.mark.django_db
def test_optional_graph_database_failure_keeps_verified_original_results(monkeypatch):
    from django.db import OperationalError
    from tests.test_discovery_sessions_v308 import fixture_source
    from catalog.services import discovery_projection as projection, discovery_sessions as sessions
    from catalog.services.retrieval import knowledge_graph
    from catalog.services.retrieval.search import retrieve_channel
    edition, _, _, documents = fixture_source(1)
    rows = projection.validate_discovery_results("passages", [{"id":str(documents[0].pk)}], ["public"])
    monkeypatch.setattr(projection, "discovery_candidates", lambda *a, **kw:{"sparse":rows, "warnings":[]})
    monkeypatch.setattr(sessions, "_rerank", lambda query, rows, *a:(rows, []))
    def failed(*args, **kwargs):
        m.Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
        raise OperationalError("synthetic graph-only transaction failure")
    monkeypatch.setattr(knowledge_graph, "recall", failed)
    result = retrieve_channel("未预置的研究问题", "passages", {}, ["public"])
    assert [r["id"] for r in result["rows"]] == [str(documents[0].pk)]
    assert result["retrieval"]["knowledge_graph"]["status"] == "unavailable"
    assert any(w["code"] == "knowledge_graph_unavailable" for w in result["warnings"])
    edition.refresh_from_db()
    assert edition.state == "published"


@pytest.mark.django_db
def test_batched_graph_visibility_preserves_withdrawal_and_redirects(source):
    from django.db.models import Prefetch
    from catalog.services.knowledge_public import assertion_public
    from catalog.services.retrieval.knowledge_graph import _statements, _visible_statements
    from tests.test_knowledge_automation import publish_fixture
    edition = publish_fixture(source)
    for index in range(24):
        entity = m.Entity.objects.create(kind="person", label=f"fixture {index}", status="published")
        statement = m.Assertion.objects.create(text="fixture", status="published")
        m.AssertionParticipant.objects.create(assertion=statement, entity=entity, role="subject")
        m.AssertionSource.objects.create(assertion=statement, edition=edition, work=edition.work, document_revision=source)
    qs = m.Assertion.objects.all()
    # Compare the existing per-identity predicates with their batched form.
    with CaptureQueriesContext(connection) as old:
        rows = list(_statements(qs).prefetch_related(None).prefetch_related(
            Prefetch("sources", queryset=m.AssertionSource.objects.select_related("document_revision__asset", "attribution"), to_attr="retrieval_sources"),
            Prefetch("participants", queryset=m.AssertionParticipant.objects.select_related("entity"), to_attr="retrieval_participants")))
        shared = {}
        expected = {s.pk for s in rows if assertion_public(s, visibility=shared)}
    with CaptureQueriesContext(connection) as new:
        actual = {s.pk for s in _visible_statements(qs, {})}
    assert actual == expected and len(actual) == 24
    assert len(new) <= 9 and len(new) < len(old) / 3
    print(f"visibility queries: per-identity={len(old)}, batch={len(new)}")
    entity.status = "withdrawn"; entity.save()
    assert len(_visible_statements(qs, {})) == 23
    survivor = m.Entity.objects.create(kind="person", label="survivor", status="published")
    entity.merged_into = survivor; entity.save()
    assert len(_visible_statements(qs, {})) == 24
    survivor.status = "withdrawn"; survivor.save()
    assert len(_visible_statements(qs, {})) == 23
    edition.state = "withdrawn"; edition.save()
    assert _visible_statements(qs, {}) == []


@pytest.mark.django_db
def test_partial_book_resume_uses_range_plan_and_keeps_exact_inputs(source, admin_user, monkeypatch):
    from catalog.services import intelligence as runner, knowledge_compilation as compilation
    from tests.test_continuous_wiki import setup, next_packet, submit
    policy = setup(source, admin_user, monkeypatch)
    first = next_packet(policy, admin_user)
    assert first.stage == 2
    plan = policy.latest_run.artifacts.get(stage=1, unit="windows")
    assert len(plan.output["windows"]) > 1
    assert all("text" not in r for w in plan.output["windows"] for r in w["ranges"])
    submit(first, admin_user, {"summary":"fixture", "questions":[], "entities":[], "assertions":[]})
    def no_replan(*args, **kwargs):
        pytest.fail("Partial resume rebuilt OCR nodes or split the book again")
    monkeypatch.setattr(runner, "prepare", no_replan)
    monkeypatch.setattr(runner, "windows", no_replan)
    with CaptureQueriesContext(connection) as queries:
        second = next_packet(policy, admin_user)
    assert second.stage == 2 and second.unit != first.unit
    assert not any('catalog_documentnode"' in q["sql"] for q in queries)
    pages = dict(source.page_snapshots.values_list("page_number", "text"))
    assert all(pages[r["page_number"]][r["start"]:r["end"]] == r["text"] for r in second.input_manifest["ranges"])
    first.refresh_from_db()
    assert first.status == "empty" and first.usage["agent_responses"] == 1
    # Tampered plans must fail instead of becoming a successful skipped window.
    m.CurationArtifact.objects.filter(pk=plan.pk).update(output={"windows":[]})
    with pytest.raises(ValidationError, match="计划哈希"):
        next_packet(policy, admin_user)


@pytest.mark.django_db
def test_resource_recovery_never_restarts_live_remote_failed_or_paused_runs(source, admin_user, monkeypatch):
    from catalog.services import intelligence as runner, knowledge_compilation as compilation, knowledge_automation as automation
    monkeypatch.setattr(runner, "schedule", lambda run:None)
    subscription = compilation.configure(source, admin_user, execution_mode="agent")
    run = subscription.latest_run
    old = timezone.now()-timedelta(minutes=2)
    for status in ("failed", "waiting_remote", "waiting_agent", "canceled", "succeeded", "running"):
        m.CurationRun.objects.filter(pk=run.pk).update(status=status, updated_at=old)
        automation.resume_resource_waiters()
        subscription.refresh_from_db()
        assert not subscription.pending_refresh
    demand = m.CapabilityDemand.objects.create(owner_type="curation_run", owner_key=str(run.pk),
        capability="llm_large", idempotency_key=str(uuid4()), state="claimed", lease_expires_at=timezone.now()+timedelta(minutes=5))
    m.CurationRun.objects.filter(pk=run.pk).update(status="waiting_resource", updated_at=old, demand=demand)
    automation.resume_resource_waiters(); subscription.refresh_from_db()
    assert not subscription.pending_refresh
    demand.state = "waiting_executor"; demand.save()
    automation.resume_resource_waiters(); subscription.refresh_from_db()
    assert subscription.pending_refresh
    compilation.reconcile_pending(); subscription.refresh_from_db()
    assert subscription.latest_run_id == run.pk and subscription.latest_run.version == run.version+1
    assert not subscription.pending_refresh
    subscription.enabled = False; subscription.save()
    m.CurationRun.objects.filter(pk=run.pk).update(status="waiting_resource", updated_at=old)
    automation.resume_resource_waiters(); subscription.refresh_from_db()
    assert not subscription.pending_refresh


@pytest.mark.django_db
def test_refresh_failure_backoff_and_existing_publication_notification(source, admin_user, monkeypatch, django_capture_on_commit_callbacks):
    from catalog.services import intelligence as runner, knowledge_compilation as compilation, discovery_indexing
    from catalog.services.retrieval.source_schedule import publication_changed
    from catalog.intelligence_tasks import refresh_compilations
    monkeypatch.setattr(runner, "schedule", lambda run:None)
    monkeypatch.setattr(discovery_indexing, "enabled", lambda:False)
    monkeypatch.setattr(refresh_compilations, "apply_async", lambda **kw:None)
    subscription = compilation.configure(source, admin_user, execution_mode="agent")
    with django_capture_on_commit_callbacks(execute=True):
        publication_changed(source.asset.edition_id)
    subscription.refresh_from_db()
    assert subscription.pending_refresh  # existing sources also receive the event
    calls = []
    original = compilation.reconcile
    def unavailable(*args, **kwargs):
        calls.append(1)
        raise ValidationError("fixture missing source")
    monkeypatch.setattr(compilation, "reconcile", unavailable)
    compilation.reconcile_pending(); subscription.refresh_from_db()
    assert subscription.refresh_failures == 1 and subscription.next_refresh_at > timezone.now()
    compilation.reconcile_pending()
    assert len(calls) == 1  # not retried by every queue notification
    m.KnowledgeCompilation.objects.filter(pk=subscription.pk).update(next_refresh_at=timezone.now()-timedelta(seconds=1))
    monkeypatch.setattr(compilation, "reconcile", original)
    compilation.reconcile_pending(); subscription.refresh_from_db()
    assert not subscription.pending_refresh and subscription.refresh_failures == 0 and subscription.next_refresh_at is None
