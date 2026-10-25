"""Deferred acceptance for the published bibliography shown in R05."""
import pytest

from reading import research
from tests.test_discovery_sessions_v308 import fixture_source

pytestmark = pytest.mark.django_db


def test_research_bibliography_uses_published_snapshot_for_single_and_multi_page(reader_user):
    edition, _, spans, _ = fixture_source(count=2)
    edition.work.title = "尚未发布的修订标题"
    edition.work.document_type = "report"
    edition.work.language = "en"
    edition.work.save(update_fields=["title", "document_type", "language"])
    reference = research.resolve_reference({"evidence_span_id": str(spans[0].pk)}, reader_user, strict=True)
    assert reference["title"] == "正式检索材料"
    assert reference["document_type"] == "book" and reference["language"] == "zh"
    assert reference["publication_year"] == 2020
    combined = research.resolve_reference({"anchors": [{"evidence_span_id": str(span.pk)} for span in spans]}, reader_user, strict=True)
    assert combined["document_type"] == "book" and combined["language"] == "zh"
    assert len(combined["anchors"]) == 2


def test_withdrawn_source_does_not_retain_bibliography_or_cover(reader_user):
    _, _, spans, _ = fixture_source(count=1)
    original = research.resolve_reference({"evidence_span_id": str(spans[0].pk)}, reader_user, strict=True)
    spans[0].is_stale = True
    spans[0].save(update_fields=["is_stale"])
    withdrawn = research.resolve_reference(original, reader_user)
    assert withdrawn["source_status"] == "unavailable"
    for key in ["quote", "cover_url", "cover_media", "title", "document_type", "language", "authors"]:
        assert not withdrawn.get(key)
