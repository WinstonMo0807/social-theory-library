"""Synthetic PDF32 source-query receipts; authored for unified acceptance only."""
from copy import deepcopy

import pytest
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.discovery_index_models import DiscoverySourceState
from catalog.models import Asset, Edition
from catalog.services import discovery_documents as documents, discovery_sessions as sessions
from catalog.services.discovery_context import session_context
from catalog.services.discovery_projection import _matches, current_scopes
from tests.test_discovery_sessions_v308 import fixture_source, make_session

pytestmark = pytest.mark.django_db


def source_receipt(*, ready=True):
    edition, asset, spans, refs = fixture_source(2)
    asset.file = "synthetic/receipt.pdf"
    asset.save(update_fields=["file"])
    if ready:
        DiscoverySourceState.objects.create(generation=refs[0].generation, source_type="edition", source_id=edition.pk,
            source_revision=refs[0].source_revision, expected_count=len(refs), completed_count=len(refs), indexed_at=timezone.now())
    session = make_session(refs, status="running")
    session.filters = {"work_ids": [str(edition.work_id)]}
    session.save(update_fields=["filters"])
    documents.begin_document_query(session.pk, session.generation, session.task_id,
        current_scopes("passages", ["public"], session.filters), refs[0].generation)
    session.refresh_from_db()
    return session, edition, asset, refs


def test_index_readiness_is_not_query_completion_and_missing_material_is_not_relevance():
    session, _, _, _ = source_receipt()
    before = documents.document_payload(session, ["public"], [])
    assert before["items"][0]["status"] == "running"
    documents.finish_document_query(session, [])
    after = documents.document_payload(session, ["public"], [])
    assert after["items"][0]["status"] == "no_returned"
    assert "不据此判断相关性" in after["notice"]
    assert "title" not in session.results[documents.DOCUMENTS_KEY]["rows"][0]
    assert "text" not in str(session.results[documents.DOCUMENTS_KEY])


def test_unfinished_index_does_not_claim_that_the_source_was_queried():
    session, _, _, _ = source_receipt(ready=False)
    documents.finish_document_query(session, [])
    assert documents.document_payload(session, ["public"], [])["items"][0]["status"] == "waiting_index"


@pytest.mark.parametrize("warnings,failed,expected", [
    ([{"code": "dense_unavailable"}], False, "partial"),
    ([{"code": "keyword_unavailable"}, {"code": "dense_unavailable"}], False, "failed"),
    ([], True, "failed"),
])
def test_partial_or_failed_retrieval_never_becomes_no_material(warnings, failed, expected):
    session, _, _, _ = source_receipt()
    documents.finish_document_query(session, warnings, failed=failed)
    assert documents.document_payload(session, ["public"], [])["items"][0]["status"] == expected


def test_cancellation_blocks_late_receipts_and_preserves_existing_references():
    session, _, _, refs = source_receipt()
    generation, task = session.generation, session.task_id
    old = deepcopy(session.results["passages"])
    session = sessions.cancel_session(session)
    documents.begin_document_query(session.pk, generation, task, [], refs[0].generation)
    session.refresh_from_db()
    documents.finish_document_query(session, [])
    assert session.results["passages"] == old
    assert documents.document_payload(session, ["public"], [])["items"][0]["status"] == "canceled"


def test_readback_masks_withdrawn_metadata_and_detects_changed_access():
    session, edition, asset, _ = source_receipt()
    Asset.objects.filter(pk=asset.pk).update(access_status="private")
    assert documents.document_payload(session, ["public"], [])["items"][0]["status"] == "unreadable"
    Edition.objects.filter(pk=edition.pk).update(state="withdrawn")
    row = documents.document_payload(session, ["public"], [])["items"][0]
    assert row["title"] == "来源暂不可用" and row["bibliography"] is None
    assert row["available_versions"] == [] and row["url"] == ""


def test_removal_changes_scope_rehydration_and_context_and_is_idempotent(monkeypatch):
    session, edition, _, refs = source_receipt()
    session.status = "completed"
    session.save(update_fields=["status"])
    original = deepcopy(session.results["passages"])
    generation = session.generation
    updated = documents.remove_document(session, edition.pk, ["public"], expected_generation=generation)
    assert updated.results["passages"] == original  # Only this query's exclusion changes, not source/owner data.
    assert sessions.serialize_session(updated, ["public"])["passages"] == []
    assert current_scopes("passages", ["public"], documents.effective_filters(updated)) == []
    with pytest.raises(NotFound):
        session_context(updated, str(refs[0].pk), ["public"])
    repeated = documents.remove_document(updated, edition.pk, ["public"], expected_generation=generation)
    assert repeated.generation == updated.generation
    assert not _matches({"channel": "passages", "edition_id": str(edition.pk)}, documents.effective_filters(updated))


def test_active_removal_invalidates_old_task_and_continues_remaining_scope(monkeypatch):
    monkeypatch.setattr(sessions, "_check_admission", lambda *args: None)
    monkeypatch.setattr(sessions, "_enqueue", lambda *args: None)
    session, edition, _, _ = source_receipt()
    generation, task = session.generation, session.task_id
    with pytest.raises(ValidationError):
        documents.remove_document(session, edition.pk, ["public"], expected_generation=generation + 1)
    updated = documents.remove_document(session, edition.pk, ["public"], expected_generation=generation)
    assert updated.status == "queued" and updated.task_id != task and updated.generation > generation
    assert not sessions._task_current(session.pk, generation, task)
    assert updated.results[documents.EXCLUDED_KEY] == [str(edition.pk)]
    assert "_excluded_edition_ids" not in updated.filters
