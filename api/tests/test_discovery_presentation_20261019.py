"""Synthetic publication-boundary examples; written for unified acceptance only."""
import pytest
from rest_framework.exceptions import NotFound

from catalog.models import EvidenceSpan
from catalog.services.discovery_context import session_context
from catalog.services.discovery_projection import validate_discovery_results
from catalog.services.discovery_sessions import _public_row
from catalog.services.discovery_sources import edition_metadata_header
from tests.test_discovery_sessions_v308 import fixture_source, make_session

pytestmark = pytest.mark.django_db


def test_bibliography_uses_published_snapshot_and_never_draft():
    edition, asset, _, _ = fixture_source(1)
    revision = edition.active_catalog_revision
    revision.snapshot = {**revision.snapshot,
        "work": {**revision.snapshot.get("work", {}), "original_title": "Published title", "language": "en"},
        "edition": {**revision.snapshot.get("edition", {}), "publisher": "Published press", "publication_year": 2001, "public_slug": "published-slug", "version_label": "Published version"}}
    edition.publisher = "Unpublished publisher"
    edition.public_slug = "unpublished-slug"
    result = edition_metadata_header(edition)
    assert result["bibliography"]["publisher"] == "Published press"
    assert result["bibliography"]["publication_year"] == 2001
    assert result["bibliography"]["original_title"] == "Published title"
    assert result["bibliography"]["page_count"] == asset.page_count
    assert result["work"]["slug"] == "published-slug"
    assert "Unpublished" not in str(result)


def test_missing_historical_bibliography_stays_missing():
    edition, _, _, _ = fixture_source(1)
    edition.active_catalog_revision.snapshot = {"work": {}, "edition": {}}
    edition.publisher = "Private draft"
    result = edition_metadata_header(edition)
    assert result["bibliography"]["publisher"] == ""
    assert result["bibliography"]["publication_year"] is None
    assert result["work"]["slug"] == str(edition.pk)


def test_section_is_current_and_similarity_does_not_invent_attribution():
    _, _, spans, docs = fixture_source(1)
    EvidenceSpan.objects.filter(pk=spans[0].pk).update(section="Current public section")
    raw = validate_discovery_results("passages", [{"id": str(docs[0].pk)}], ["public"])[0]
    row = _public_row(raw)
    assert row["section_title"] == "Current public section"
    assert row["attribution"]["status"] == "unknown"
    assert "scope_token" not in row
    assert "bibliography" in row


def test_same_work_context_excludes_other_work_and_stale_candidates():
    _, _, spans, docs = fixture_source(4)
    _, _, _, other = fixture_source(2)
    session = make_session([*docs, *other])
    EvidenceSpan.objects.filter(pk=spans[2].pk).update(is_stale=True)
    result = session_context(session, str(docs[1].pk), ["public"])
    assert result["source"]["id"] == str(docs[1].pk)
    assert result["same_work_count"] == 3
    assert {item["id"] for item in result["same_work_results"]} == {str(docs[i].pk) for i in [0, 1, 3]}
    assert result["previous_result_id"] == str(docs[0].pk)
    assert result["next_result_id"] == str(docs[3].pk)


def test_same_work_candidate_payload_is_bounded():
    _, _, _, docs = fixture_source(23)
    result = session_context(make_session(docs), str(docs[0].pk), ["public"])
    assert result["same_work_count"] == 23
    assert len(result["same_work_results"]) == 20


def test_display_header_does_not_widen_source_permissions():
    _, asset, _, docs = fixture_source(1)
    asset.access_status = "private"
    asset.save(update_fields=["access_status"])
    assert validate_discovery_results("passages", [{"id": str(docs[0].pk)}], ["public"]) == []


def test_context_rechecks_source_after_assembling_neighbours(monkeypatch):
    from catalog.services import discovery_projection
    _, _, _, docs = fixture_source(2)
    original = discovery_projection.validate_discovery_results
    calls = 0
    def withdrawing(channel, refs, access):
        nonlocal calls
        calls += 1
        return [] if calls >= 3 else original(channel, refs, access)
    monkeypatch.setattr(discovery_projection, "validate_discovery_results", withdrawing)
    with pytest.raises(NotFound):
        session_context(make_session(docs), str(docs[0].pk), ["public"])
