"""Opt-in local-engine integration. Fixture text is not a corpus quality benchmark."""
import os
from time import perf_counter
from urllib.parse import urlsplit

import pytest
from django.db import connection

from catalog import models as m
from catalog.services import discovery_indexing as indexing
from catalog.services.document_intelligence import document_text_checksum
from catalog.services.discovery_sources import get_source
from catalog.services.retrieval.search import retrieve_channel
from tests.test_logical_retrieval import indexing_source

pytestmark = [pytest.mark.django_db, pytest.mark.meilisearch_integration]


def test_real_keyword_engine_without_models_and_withdrawal(settings):
    url = os.environ.get("STL_TEST_MEILI_URL", "")
    if not url:
        pytest.skip("set STL_TEST_MEILI_URL for a disposable local Meilisearch")
    assert urlsplit(url).hostname in {"127.0.0.1", "localhost", "::1"}
    assert connection.vendor == "postgresql", "use an isolated PostgreSQL test database"
    settings.MEILISEARCH_URL = url
    settings.MEILISEARCH_MASTER_KEY = os.environ.get("STL_TEST_MEILI_KEY", "")
    settings.DISCOVERY_ENABLED = True
    settings.NAS_ON_DEMAND_ENABLED = False
    settings.DISCOVERY_INFERENCE_URL = "http://127.0.0.1:1"
    settings.DISCOVERY_INFERENCE_ALLOWED_HOSTS = "127.0.0.1"
    edition, asset, revision, generation, job, old = indexing_source()
    texts = ["制度治理的原文证据。甲😀乙。", "Empirical social theory examines institutional governance."]
    for page, text in zip(asset.pages.order_by("index"), texts):
        page.text = text
        page.save(update_fields=["text"])
    revision.text_checksum = document_text_checksum(asset)
    revision.save(update_fields=["text_checksum"])
    header = get_source("edition", edition.pk)[1]
    job.stats = {**job.stats, "source_revision":header["source_revision"],
        "semantic_waiting":{"code":"keyword_only"}}
    job.save()
    m.DiscoveryDocument.objects.filter(pk__in=[row.pk for row in old]).update(keyword_ready=False, vector_ready=False)
    assert generation.uid.startswith("discovery-test-")
    try:
        started = perf_counter()
        indexing.ensure_index(generation)
        for _ in range(8):
            if indexing.process_source(job, generation):
                break
        else:
            pytest.fail("Keyword receipts did not complete in bounded retries")
        indexed_seconds = perf_counter()-started
        documents = m.DiscoveryDocument.objects.filter(generation=generation, keyword_ready=True)
        assert documents.count() == 2 and not documents.filter(vector_ready=True).exists()
        measured = []
        for query in ("制度治理", "institutional governance", "甲😀乙"):
            started = perf_counter()
            result = retrieve_channel(query, "passages", {}, ["public"])
            measured.append(round(perf_counter()-started, 3))
            assert result["rows"]
            assert result["retrieval"]["inference"]["calls"] == 1
            assert any(w["code"] == "normalization_unavailable" for w in result["warnings"])
            for row in result["rows"]:
                assert row["text"] in texts and row["locator"]["exact"] == row["text"]
                assert row["document_revision_id"] == str(revision.pk)
                assert "revision="+str(revision.pk) in row["reader_url"]
        # A failed index is distinguishable from a genuine no-match response.
        empty = retrieve_channel("zzunmatchedfixturetoken", "passages", {"_keyword_only":True}, ["public"])
        assert not empty["rows"] and not empty["warnings"]
        settings.MEILISEARCH_URL = "http://127.0.0.1:1"
        failed = retrieve_channel("制度治理", "passages", {"_keyword_only":True}, ["public"])
        assert not failed["rows"] and failed["warnings"]
        settings.MEILISEARCH_URL = url
        asset.access_status = "private"
        asset.save(update_fields=["access_status"])
        assert not retrieve_channel("制度治理", "passages", {}, ["public"])["rows"]
        print(f"Local engine: index={indexed_seconds:.3f}s; 3 full retrieval calls={measured}s; vector-ready=0")
    finally:
        settings.MEILISEARCH_URL = url
        indexing.wait_index_task(indexing.meili("DELETE", f"/indexes/{generation.uid}"))
