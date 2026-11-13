import pytest
from uuid import uuid4
from types import SimpleNamespace

from tests.test_discovery_sessions_v308 import fixture_source
from tests.test_shared_citation_20261019 import raw_page

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("indexed", [True, False])
def test_logged_in_reader_can_cite_registered_source_without_search_index(api_client, reader_user, indexed):
    from catalog.services.discovery_sources import source_queryset
    edition, asset, spans, _ = fixture_source(count=1)
    asset.access_status = "registered"
    asset.save(update_fields=["access_status"])
    edition.active_catalog_revision.fulltext_ready = indexed
    edition.active_catalog_revision.save(update_fields=["fulltext_ready"])
    assert source_queryset("edition", ["registered"]).filter(pk=edition.pk).exists() == indexed
    api_client.force_authenticate(reader_user)
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw_page(asset, spans[0]), "selected_text": "来自同一正式修订"}, format="json")
    assert response.status_code == 200, response.data
    assert response.data["reference"]["quote"] == "来自同一正式修订"


@pytest.mark.parametrize("access", ["registered", "private", "restricted"])
def test_anonymous_cannot_quote_login_or_private_sources(api_client, access):
    _, asset, spans, _ = fixture_source(count=1)
    asset.access_status = access
    asset.save(update_fields=["access_status"])
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw_page(asset, spans[0])}, format="json")
    assert response.status_code == 400
    assert "真实夹具文本" not in str(response.data)


@pytest.mark.parametrize("change", ["checksum", "revision", "withdrawn", "hash"])
def test_index_independence_does_not_accept_stale_or_withdrawn_text(api_client, reader_user, change):
    edition, asset, spans, _ = fixture_source(count=1)
    revision = edition.active_catalog_revision
    revision.fulltext_ready = False
    revision.save(update_fields=["fulltext_ready"])
    raw = raw_page(asset, spans[0])
    if change == "checksum":
        asset.sha256 = "f" * 64
        asset.save(update_fields=["sha256"])
    elif change == "revision":
        raw["document_revision_id"] = str(uuid4())
    elif change == "hash":
        raw["content_hash"] = "a" * 64
    else:
        edition.state = "withdrawn"
        edition.save(update_fields=["state"])
    api_client.force_authenticate(reader_user)
    response = api_client.post("/api/reading/citation-preview/", {"reference": raw}, format="json")
    assert response.status_code == 400


@pytest.mark.parametrize("printed", ["", "xv", "137"])
def test_reader_sidebar_does_not_treat_pdf_ordinal_as_printed_page(api_client, printed):
    edition, _, spans, _ = fixture_source(count=1)
    page = spans[0].page
    page.printed_label = printed
    page.save(update_fields=["printed_label"])
    response = api_client.get(f"/api/catalog/editions/{edition.id}/citations/?pdf_page=1")
    assert response.status_code == 200
    assert response.data["page"]["citation_label"] == printed
    assert ("PDF 第 1 页" in response.data["gbt7714-2025"]) == (not printed)


def test_registered_excerpt_can_be_saved_and_retry_does_not_duplicate(reader_user):
    from reading import booklists, citation_booklists
    from reading.models import Annotation, ReadingList
    edition, asset, spans, _ = fixture_source(count=1)
    asset.access_status = "registered"
    asset.save(update_fields=["access_status"])
    revision = edition.active_catalog_revision
    revision.fulltext_ready = False
    revision.save(update_fields=["fulltext_ready"])
    target = ReadingList.objects.create(user=reader_user, title="合成检查书单")
    data = {"request_id": uuid4(), "expected_version": booklists.version(target),
            "edition_id": edition.id, "reference": raw_page(asset, spans[0]), "save_excerpt": True, "note": ""}
    request = SimpleNamespace(user=reader_user)
    result = citation_booklists.save(request, target.id, data)
    repeated = citation_booklists.save(request, target.id, data)
    assert len(result["note_ids"]) == 1
    assert repeated["note_ids"] == result["note_ids"]
    assert Annotation.objects.filter(user=reader_user).count() == 1
