"""Small fixtures cross the configured threshold; no production/model calls."""
from uuid import uuid4

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from catalog import models as m
from catalog.services import discovery_projection as projection, discovery_documents
from catalog.services.retrieval import coverage
from tests.test_discovery_sessions_v308 import fixture_source, make_session

pytestmark = pytest.mark.django_db


def completed_source():
    edition, asset, spans, documents = fixture_source(2)
    state = m.DiscoverySourceState.objects.create(generation=documents[0].generation,
        source_type="edition", source_id=edition.pk, source_revision=documents[0].source_revision,
        expected_count=2, completed_count=2, indexed_at=timezone.now())
    return edition, asset, documents, state


def test_large_scope_skips_header_enumeration_and_keeps_receipts_current(monkeypatch):
    edition, asset, documents, state = completed_source()
    monkeypatch.setattr(coverage, "SCOPE_PREFILTER_LIMIT", 0)
    monkeypatch.setattr(projection, "iter_source_headers", lambda *a, **kw: pytest.fail("must not enumerate catalog"))
    monkeypatch.setattr(projection, "iter_edition_metadata_headers", lambda *a, **kw: pytest.fail("must not enumerate catalog"))
    assert projection.current_scopes("passages", ["public"], allow_deferred=True) is None
    assert coverage.backfill_receipts(apply=False)["eligible"] == 1
    state.refresh_from_db()
    assert state.catalog_revision_id is None
    assert coverage.backfill_receipts(apply=True)["updated"] == 1
    with CaptureQueriesContext(connection) as queries:
        result = projection.discovery_coverage(["public"])
    assert result["eligible_editions"] == result["indexed_editions"] == result["vector_editions"] == 1
    assert result["passage_count"] == 2 and len(queries) <= 7
    document = edition.active_catalog_revision.document_revision
    m.DocumentRevision.objects.filter(pk=document.pk).update(text_checksum="changed")
    assert projection.discovery_coverage(["public"])["indexed_editions"] == 0
    assert coverage.backfill_receipts(apply=True)["skipped"] == 1
    m.Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert projection.discovery_coverage(["public"])["eligible_editions"] == 0


def test_receipt_counts_do_not_guess_complex_facet_coverage():
    _, _, documents, _ = completed_source()
    result = coverage.sql_coverage(["public"], {"topics": ["power"]}, documents[0].generation)
    assert result["scope_status"] == "candidate_filtered" and result["partial"]
    assert "indexed_editions" not in result


def test_lexical_overfetch_validates_each_batch_and_preserves_all_facets(monkeypatch):
    edition, asset, documents, _ = completed_source()
    # First page is stale identities, second page contains a valid source.
    calls = []
    def search(method, path, payload, **kwargs):
        calls.append(payload)
        if not payload.get("offset"):
            return {"hits": [{"id": str(uuid4())} for _ in range(payload["limit"])]}
        return {"hits": [{"id": str(documents[0].pk)}]}
    monkeypatch.setattr(projection, "meili", search)
    warnings = []
    result = projection.candidate_search("example", {"q": "制度", "limit": 1}, "passages", ["public"],
        {"work_ids": [str(edition.work_id)]}, deferred=True, warnings=warnings)
    assert [row["id"] for row in result["hits"]] == [str(documents[0].pk)]
    assert len(calls) == 2 and calls[1]["offset"] == 100 and not warnings
    assert not projection.candidate_search("example", {"q": "制度", "limit": 1}, "passages", ["public"],
        {"work_ids": [str(uuid4())]}, deferred=True, warnings=[])["hits"]
    assert not projection.candidate_search("example", {"q": "制度", "limit": 1}, "passages", ["public"],
        {"languages": ["en"]}, deferred=True, warnings=[])["hits"]
    m.Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert not projection.candidate_search("example", {"q": "制度", "limit": 1}, "passages", ["public"],
        {}, deferred=True, warnings=[])["hits"]


def test_budget_exhaustion_is_visible_and_dense_does_not_assume_pagination(monkeypatch):
    requests = []
    def search(method, path, payload, **kwargs):
        requests.append(payload)
        return {"hits": [{"id": str(uuid4())} for _ in range(payload["limit"])]}
    monkeypatch.setattr(projection, "meili", search)
    for vector in (False, True):
        requests.clear()
        warnings = []
        result = projection.candidate_search("example", {"q": "", "limit": 2,
            **({"vector": [1.0]} if vector else {})}, "passages", ["public"], {}, deferred=True, warnings=warnings)
        assert not result["hits"] and warnings[0]["code"] == "candidate_budget"
        assert sum(row["limit"] for row in requests) == 1000
        if vector:
            assert len(requests) == 1 and "offset" not in requests[0]


def test_deferred_source_roster_keeps_current_source_identity():
    _, _, documents, _ = completed_source()
    session = make_session(documents, status="running")
    discovery_documents.begin_document_query(session.pk, session.generation, session.task_id, None, documents[0].generation)
    session.refresh_from_db()
    row = session.results[discovery_documents.DOCUMENTS_KEY]["rows"][0]
    assert row["status"] == "running" and row["source_revision"] == documents[0].source_revision


def test_backfill_cursor_resumes_without_reindex_or_duplicate_state():
    completed_source()
    completed_source()
    first = coverage.backfill_receipts(batch_size=1, apply=True)
    second = coverage.backfill_receipts(after=first["after"], batch_size=1, apply=True)
    assert first["updated"] == second["updated"] == 1
    assert first["after"] != second["after"]
    assert coverage.backfill_receipts(after=second["after"], apply=True)["visited"] == 0
    assert m.DiscoverySourceState.objects.filter(coverage_verified_at__isnull=False).count() == 2


def test_active_source_scan_is_bounded_and_only_cleans_selected_withdrawals(monkeypatch):
    from catalog.services import discovery_indexing as indexing
    from catalog.services.retrieval import source_schedule
    fixtures = [completed_source() for _ in range(3)]
    generation = fixtures[0][2][0].generation
    for _, _, documents, state in fixtures[1:]:
        m.DiscoverySourceState.objects.filter(pk=state.pk).update(generation=generation)
        m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in documents]).update(generation=generation)
    withdrawn = fixtures[-1][0]
    m.Edition.objects.filter(pk=withdrawn.pk).update(state="withdrawn")
    monkeypatch.setattr(source_schedule,"SOURCE_TYPES",("edition",))
    monkeypatch.setattr(source_schedule,"SCAN_THRESHOLD",1)
    monkeypatch.setattr(source_schedule,"SCAN_BATCH",1)
    cleaned = []
    monkeypatch.setattr(indexing,"remove_source",lambda generation,kind,key:cleaned.append(key))
    visited = []
    for _ in range(3):
        selected, _ = source_schedule.scan_window(generation)
        assert sum(map(len,selected.values())) == 1
        visited.extend(selected["edition"])
        before = set(m.DiscoverySourceState.objects.filter(generation=generation).values_list("pk",flat=True))
        indexing.schedule_sources(generation)
        generation.refresh_from_db()
        if withdrawn.pk not in selected["edition"]:
            assert set(m.DiscoverySourceState.objects.filter(generation=generation).values_list("pk",flat=True)) == before
    assert set(visited) == {e.pk for e,_,_,_ in fixtures}
    assert cleaned == [withdrawn.pk]
    assert generation.validation_details["source_scan"]["completed_at"]
    assert "source_scan" not in generation.config_snapshot


def test_publication_notification_uses_same_producer_after_commit(monkeypatch,settings,django_capture_on_commit_callbacks):
    from catalog.services import discovery_indexing as indexing
    from catalog.services.retrieval.source_schedule import publication_changed
    edition, _, documents, _ = completed_source()
    settings.DISCOVERY_ENABLED=True
    calls=[]
    monkeypatch.setattr(indexing,"schedule_sources",lambda generation,**kw:calls.append((generation.pk,kw)))
    with django_capture_on_commit_callbacks(execute=True):
        publication_changed(edition.pk)
        assert not calls
    assert calls == [(documents[0].generation_id,{"source_keys":{"edition":[edition.pk]},"cleanup":False})]


def test_full_queue_retains_new_publication_for_priority_admission(monkeypatch):
    from catalog.services import discovery_indexing as indexing
    from catalog.services.retrieval import source_schedule
    edition, asset, documents, state = completed_source()
    previous = edition.active_catalog_revision
    m.CatalogPublicationRevision.objects.filter(pk=previous.pk).update(status="superseded")
    replacement = m.CatalogPublicationRevision.objects.create(edition=edition,revision=2,status="active",
        metadata_ready=True,fulltext_ready=True,reader_asset=asset,document_revision=previous.document_revision,
        snapshot=previous.snapshot,content_fingerprint=uuid4().hex)
    m.Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=replacement)
    generation=documents[0].generation
    assert indexing.schedule_sources(generation,max_queued=0,source_keys={"edition":[edition.pk]},cleanup=False) == 1
    state.refresh_from_db()
    assert state.indexed_at is None and state.job_id is None
    assert m.DiscoveryDocument.objects.filter(pk__in=[d.pk for d in documents],keyword_ready=True).count()==2
    monkeypatch.setattr(source_schedule,"SOURCE_TYPES",("edition",))
    monkeypatch.setattr(source_schedule,"SCAN_THRESHOLD",0)
    monkeypatch.setattr(source_schedule,"SCAN_BATCH",4)
    selected,checkpoint=source_schedule.scan_window(generation)
    assert selected["edition"]==[edition.pk] and checkpoint["visited"]==1
    indexing.schedule_sources(generation)
    state.refresh_from_db()
    assert state.job_id and state.job.status=="pending" and state.job.task_id
    assert state.job.stats["source_revision"]!=documents[0].source_revision
