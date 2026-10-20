"""PDF 30–32 session controls; synthetic cases for unified acceptance, not run yet."""
from copy import deepcopy

import pytest
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIRequestFactory

from catalog.discovery_views import DiscoverySearchDetailView
from catalog.models import Asset, EvidenceSpan
from catalog.services import discovery_sessions as sessions
from tests.test_discovery_sessions_v308 import fixture_source, make_session

pytestmark = pytest.mark.django_db


def source_with_year(year, count=1):
    edition, asset, spans, documents = fixture_source(count)
    revision = edition.active_catalog_revision
    revision.snapshot = {**revision.snapshot,
                         "edition": {**revision.snapshot["edition"], "publication_year": year}}
    revision.save(update_fields=["snapshot"])
    return asset, spans, documents


@pytest.mark.parametrize("sort,order", [
    ("relevance", [0, 1, 2, 3]),
    ("year_desc", [1, 3, 0, 2]),
    ("year_asc", [0, 1, 3, 2]),
])
def test_sort_uses_full_current_materialization_before_pagination(monkeypatch, sort, order):
    _, _, older = source_with_year(1990)
    _, _, newer = source_with_year(2020, 2)
    _, _, unknown = source_with_year(None)
    documents = [older[0], newer[0], unknown[0], newer[1]]
    session = make_session(documents)
    before = deepcopy(session.results)

    def forbidden(*args, **kwargs):
        raise AssertionError("Display sorting must not launch retrieval")
    monkeypatch.setattr(sessions, "retrieve_discovery_channel", forbidden)
    first = sessions.serialize_session(session, ["public"], sort=sort, limit=2)
    second = sessions.serialize_session(session, ["public"], sort=sort, limit=2, cursor=first["next_cursor"])
    assert [row["id"] for row in [*first["passages"], *second["passages"]]] == [str(documents[i].pk) for i in order]
    assert first["sort"] == sort
    assert first["added_count"] == 0
    assert all(not row["is_new"] for row in first["passages"])
    assert second["next_cursor"] is None
    assert session.results == before


def test_year_cursor_binds_sort_session_and_generation_and_survives_withdrawal():
    _, _, spans, documents = fixture_source(5)
    session = make_session(documents)
    first = sessions.serialize_session(session, ["public"], sort="year_desc", limit=2)
    cursor = first["next_cursor"]
    for wrong_sort in ("relevance", "year_asc"):
        with pytest.raises(ValidationError):
            sessions.serialize_session(session, ["public"], sort=wrong_sort, cursor=cursor)
    with pytest.raises(ValidationError):
        sessions.serialize_session(make_session(documents), ["public"], sort="year_desc", cursor=cursor)
    EvidenceSpan.objects.filter(pk__in=[spans[0].pk, spans[2].pk]).update(is_stale=True)
    following = sessions.serialize_session(session, ["public"], sort="year_desc", cursor=cursor)
    assert [row["id"] for row in following["passages"]] == [str(documents[i].pk) for i in (3, 4)]
    assert following["count"] == 3
    assert following["source_changed"]
    session.generation += 1
    with pytest.raises(ValidationError):
        sessions.serialize_session(session, ["public"], sort="year_desc", cursor=cursor)


def test_sort_revalidates_access_and_rejects_unknown_sort():
    asset, _, documents = source_with_year(2024)
    session = make_session(documents)
    Asset.objects.filter(pk=asset.pk).update(access_status="private")
    result = sessions.serialize_session(session, ["public"], sort="year_desc")
    assert result["passages"] == []
    assert result["count"] == result["added_count"] == 0
    with pytest.raises(ValidationError, match="sort"):
        sessions.serialize_session(session, ["public"], sort="popular")


def test_canceled_retry_retains_references_and_receipt_is_idempotent(monkeypatch):
    _, _, _, documents = fixture_source(3)
    session = make_session(documents[:2], status="running")
    session.results[sessions.DEEP_RESULTS_KEY] = [sessions._reference({
        "id": str(documents[2].pk), "source_revision": documents[2].source_revision})]
    session.save(update_fields=["results"])
    original = deepcopy(session.results)
    old_generation, old_task = session.generation, session.task_id
    canceled = sessions.cancel_session(session)
    state = sessions.serialize_session(canceled, ["public"])
    assert state["can_retry"] and state["task_progress"]["retryable"]
    # A cancellation also advances the generation, but is not a retry receipt.
    with pytest.raises(ValidationError):
        sessions.retry_session(canceled, ["public"], expected_generation=old_generation)
    expected = canceled.generation
    monkeypatch.setattr(sessions, "_enqueue", lambda *args: None)
    resumed = sessions.retry_session(canceled, ["public"], expected_generation=expected)
    for channel in (*sessions.CHANNELS, sessions.DEEP_RESULTS_KEY):
        assert resumed.results[channel] == original.get(channel, [])
    assert resumed.status == "queued"
    assert resumed.expansion_count == 0
    assert resumed.access_statuses == ["public"]
    baseline = resumed.results[sessions.RESUME_KEY]["baseline"]
    assert set(baseline["passages"]) == {f"{doc.pk}:{doc.source_revision}" for doc in documents}
    assert documents[0].text not in str(resumed.results[sessions.RESUME_KEY])
    repeated = sessions.retry_session(resumed, ["public"], expected_generation=expected)
    assert repeated.generation == resumed.generation
    assert repeated.task_id == resumed.task_id

    def forbidden(*args, **kwargs):
        raise AssertionError("Canceled worker resumed retrieval")
    monkeypatch.setattr(sessions, "retrieve_discovery_channel", forbidden)
    sessions.execute_session(resumed.pk, old_generation, old_task)
    resumed.refresh_from_db()
    assert resumed.results == repeated.results
    canceled_again = sessions.cancel_session(resumed)
    with pytest.raises(ValidationError):
        sessions.retry_session(canceled_again, ["public"], expected_generation=expected)


def test_additions_are_unique_current_sources_and_reset_for_next_attempt(monkeypatch):
    _, _, spans, documents = fixture_source(4)
    session = make_session(documents[:2])
    monkeypatch.setattr(sessions, "_enqueue", lambda *args: None)
    session = sessions.expand_session(session, ["public"])
    session.results["passages"].extend([
        {"id": str(doc.pk), "source_revision": doc.source_revision} for doc in documents[2:]])
    session.results[sessions.DEEP_RESULTS_KEY] = [
        {"id": str(doc.pk), "source_revision": doc.source_revision} for doc in (documents[2], documents[1])]
    session.results[sessions.DEEP_RANKED_KEY] = True
    # A source withdrawn after the worker appended it is not a new visible result.
    EvidenceSpan.objects.filter(pk=spans[3].pk).update(is_stale=True)
    result = sessions.serialize_session(session, ["public"], limit=1)
    assert result["added_count"] == 1
    assert result["count"] == 3
    assert result["passages"][0]["id"] == str(documents[2].pk)
    assert result["passages"][0]["is_new"] is True
    assert [row["is_new"] for row in result["deep_passages"]] == [True, False]
    remaining = sessions.serialize_session(session, ["public"], cursor=result["next_cursor"])
    assert remaining["added_count"] == 1  # Total is not limited to this page.
    assert all(not row["is_new"] for row in remaining["passages"])
    assert "_resume" not in result
    session.status = "partial"
    session.save(update_fields=["results", "status"])
    next_attempt = sessions.retry_session(session, ["public"], expected_generation=session.generation)
    after = sessions.serialize_session(next_attempt, ["public"])
    assert after["added_count"] == 0
    assert all(not row["is_new"] for row in after["passages"])


def test_detail_get_accepts_sort_without_changing_task_identity():
    _, _, older = source_with_year(1990)
    _, _, newer = source_with_year(2020)
    session = make_session([*older, *newer])
    request = APIRequestFactory().get("/api/catalog/discovery-search/", {"sort": "year_desc", "limit": "1"},
                                     HTTP_X_DISCOVERY_TOKEN="test-capability")
    response = DiscoverySearchDetailView.as_view()(request, session_id=session.pk)
    assert response.status_code == 200
    assert response.data["sort"] == "year_desc"
    assert response.data["passages"][0]["id"] == str(newer[0].pk)
    assert response.data["generation"] == session.generation
