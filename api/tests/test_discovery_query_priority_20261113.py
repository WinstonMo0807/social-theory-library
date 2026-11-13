"""Interactive questions take precedence without changing recall or checkpoints."""
from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.discovery_models import DiscoverySearchSession
from catalog.services import discovery_indexing as indexing, discovery_sessions as sessions
from ingestion.models import ProcessingJob
from tests.test_discovery_sessions_v308 import fixture_source, make_session

pytestmark = pytest.mark.django_db


def test_first_evidence_is_saved_before_optional_channels(monkeypatch, settings):
    settings.STL_DEEP_RETRIEVAL_ENABLED = False
    _, _, _, docs = fixture_source(1)
    session = make_session(status="queued")
    calls, contexts = [], []

    def retrieve(query, channel, *args, **kwargs):
        assert query == session.query
        calls.append(channel)
        contexts.append(kwargs["request_context"])
        if channel != "passages":
            session.refresh_from_db()
            assert session.results["passages"][0]["id"] == str(docs[0].pk)
        return {"rows": [{"id": str(docs[0].pk), "source_revision": docs[0].source_revision}] if channel == "passages" else [],
                "warnings": [], "version": "test", "canceled": False}

    monkeypatch.setattr(sessions, "retrieve_discovery_channel", retrieve)
    sessions.execute_session(session.pk, session.generation, session.task_id)
    session.refresh_from_db()
    assert calls == ["passages", "entities", "curation"]
    assert contexts[0] is contexts[1] is contexts[2]
    assert session.status == "completed"


def test_waiting_index_job_keeps_identity_checkpoint_and_attempt(monkeypatch):
    make_session(status="queued")
    job = ProcessingJob.objects.create(job_type="discovery_index", status="pending", task_id=str(uuid4()),
        attempt=2, stats={"completed_units": 7})
    dispatched = []
    monkeypatch.setattr(indexing, "_dispatch", lambda *args, **kwargs: dispatched.append((args, kwargs)))
    monkeypatch.setattr(indexing, "_run_job", lambda *args: pytest.fail("Indexing competed with a reader question"))
    indexing.run_job(job.pk, job.task_id)
    job.refresh_from_db()
    assert job.status == "pending" and job.attempt == 2 and job.stats["completed_units"] == 7
    assert dispatched == [((job.pk, job.task_id), {"countdown": 20})]
    indexing.run_job(job.pk, "stale-delivery")
    assert len(dispatched) == 1


def test_index_yields_before_next_unit_and_keeps_completed_chunks(monkeypatch):
    _, _, _, docs = fixture_source(1)
    doc = docs[0]
    job = ProcessingJob.objects.create(job_type="discovery_index", status="running", task_id=str(uuid4()),
        stats={"source_type": "edition", "source_id": str(doc.source_id), "source_revision": doc.source_revision,
               "completed_units": 0})
    from catalog.discovery_index_models import DiscoverySourceState
    DiscoverySourceState.objects.create(generation=doc.generation, source_type="edition", source_id=doc.source_id, job=job)
    make_session(status="running")
    monkeypatch.setattr(indexing, "chunk_text", lambda *args, **kwargs: pytest.fail("Started another model call"))
    assert indexing.process_source(job, doc.generation) is False
    job.refresh_from_db()
    doc.refresh_from_db()
    assert job.stats["completed_units"] == 0 and doc.keyword_ready and doc.vector_ready


def test_coordinator_defers_cleanup_without_touching_a_live_writer(monkeypatch,settings):
    settings.DISCOVERY_ENABLED=True
    make_session(status="running")
    monkeypatch.setattr(indexing,'index_writer',lambda:pytest.fail('Coordinator competed with a reader question'))
    assert indexing.reconcile()=={'deferred':'reader_query_active'}


def test_withdrawn_index_rows_wait_for_reader_but_remain_invisible(monkeypatch):
    from catalog.discovery_index_models import DiscoverySourceState
    from catalog.models import Edition
    from catalog.services.discovery_projection import validate_discovery_results
    edition,_,_,docs=fixture_source(1)
    doc=docs[0]
    state=DiscoverySourceState.objects.create(generation=doc.generation,source_type='edition',source_id=edition.pk,
        source_revision=doc.source_revision,indexed_at=timezone.now(),expected_count=1,completed_count=1)
    Edition.objects.filter(pk=edition.pk).update(state='withdrawn')
    make_session(status='running')
    monkeypatch.setattr(indexing,'remove_source',lambda *args,**kwargs:pytest.fail('Heavy vector cleanup competed with a reader'))
    indexing.schedule_sources(doc.generation)
    assert DiscoverySourceState.objects.filter(pk=state.pk).exists()
    assert validate_discovery_results('passages',[{'id':str(doc.pk),'source_revision':doc.source_revision}],['public'])==[]


@pytest.mark.parametrize("status,age,expired", [("completed", 0, False), ("running", 16, False), ("queued", 31, False), ("running", 0, True)])
def test_terminal_stale_or_expired_queries_do_not_block_indexing(status, age, expired):
    session = make_session(status=status)
    DiscoverySearchSession.objects.filter(pk=session.pk).update(updated_at=timezone.now()-timedelta(minutes=age),
        expires_at=timezone.now()+timedelta(hours=-1 if expired else 1))
    assert indexing._reader_query_active() is False
