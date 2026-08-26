from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from django.test import override_settings

from catalog.services.research_sources import source_adapter
from ingestion.models import CandidateEvidence, MetadataCandidate, SourceRecord, UploadBatch, UploadItem
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.metadata import (
    normalize_nlb_singapore_record,
    search_nlb_singapore_title,
)
from ingestion.services.provider_gateway import invoke_provider


SEARCH_PAYLOAD = {
    "totalRecords": 1,
    "count": 1,
    "titles": [
        {
            "brn": 200001,
            "nativeTitle": "乡土中国 / 费孝通著",
            "nativeAuthor": "费孝通",
            "format": {"code": "BK", "name": "Books"},
        }
    ],
}

DETAIL_PAYLOAD = {
    "brn": 200001,
    "nativeTitle": "乡土中国 / 费孝通著",
    "nativeAuthor": "费孝通",
    "nativeOtherAuthors": ["刘豪兴 导读"],
    "isbns": ["978-7-108-06215-6"],
    "nativeEdition": ["第1版"],
    "nativePublisher": ["北京 : 商务印书馆, 2018"],
    "publishDate": "2018",
    "nativeSeriesTitle": ["社会学经典"],
    "nativeSummary": ["本书讨论中国基层社会的结构与秩序。"],
    "format": {"code": "BK", "name": "Books"},
}


def _response(payload):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = payload
    response.content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return response


def test_nlb_normalizer_prefers_native_bibliographic_fields():
    metadata = normalize_nlb_singapore_record(DETAIL_PAYLOAD)

    assert metadata == {
        "brn": 200001,
        "title": "乡土中国",
        "authors": ["费孝通", "刘豪兴 导读"],
        "abstract": "本书讨论中国基层社会的结构与秩序。",
        "publication_date": "2018",
        "publication_year": 2018,
        "publication_place": "北京",
        "publisher": "商务印书馆",
        "isbn": "9787108062156",
        "isbn13": "9787108062156",
        "series": "社会学经典",
        "version_label": "第1版",
        "language": "zh-CN",
        "source_format": "nlb_catalogue_v2_json",
    }


@override_settings(
    METADATA_PROVIDER_TIMEOUT_SECONDS=3,
    METADATA_PROVIDER_MAX_RESPONSE_BYTES=100_000,
)
def test_nlb_adapter_search_fetch_normalize_and_evidence(monkeypatch):
    credential = json.dumps({"api_key": "private-api-key", "app_code": "private-app-code"})
    monkeypatch.setattr(
        "catalog.services.research_sources.resolve_source_credential",
        lambda _key: credential,
    )
    requester = Mock(side_effect=[_response(SEARCH_PAYLOAD), _response(DETAIL_PAYLOAD)])
    monkeypatch.setattr("ingestion.services.metadata.httpx.get", requester)

    candidates = search_nlb_singapore_title("乡土中国", limit=2)
    adapter = source_adapter("nlb_singapore")
    normalized = adapter.extract_metadata(DETAIL_PAYLOAD, content_type="application/json")
    envelope = adapter.evidence(normalized, source_url="https://openweb.nlb.gov.sg/api/swagger/index.html")

    values = {(row.field_name, str(row.value)) for row in candidates}
    assert ("title", "乡土中国") in values
    assert ("authors", "['费孝通', '刘豪兴 导读']") in values
    assert ("isbn13", "9787108062156") in values
    assert ("publisher", "商务印书馆") in values
    assert ("abstract", "本书讨论中国基层社会的结构与秩序。") in values
    assert candidates.provider_version == "nlb-catalogue-v2"
    assert requester.call_count == 2
    assert requester.call_args_list[0].kwargs["headers"]["X-Api-Key"] == "private-api-key"
    assert requester.call_args_list[1].kwargs["params"] == {"BRN": 200001}
    assert "private-api-key" not in json.dumps(candidates.raw_response, ensure_ascii=False)
    assert normalized["source_format"] == "nlb_catalogue_v2_json"
    assert envelope["quality"] == {"structured": True, "lead_only": False}
    assert envelope["provenance"]["adapter"] == "nlb_singapore"


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="nlb_singapore",
    METADATA_PROVIDER_ALLOWED_HOSTS="openweb.nlb.gov.sg",
    METADATA_PROVIDER_RETRIES=0,
    METADATA_PROVIDER_MIN_INTERVAL_MS=0,
    METADATA_PROVIDER_TIMEOUT_SECONDS=3,
    METADATA_PROVIDER_MAX_RESPONSE_BYTES=100_000,
)
def test_nlb_official_metadata_becomes_evidenced_review_candidate(admin_user, monkeypatch):
    credential = json.dumps({"api_key": "private-api-key", "app_code": "private-app-code"})
    monkeypatch.setattr(
        "catalog.services.research_sources.resolve_source_credential",
        lambda _key: credential,
    )
    monkeypatch.setattr(
        "ingestion.services.metadata.httpx.get",
        Mock(side_effect=[_response(SEARCH_PAYLOAD), _response(DETAIL_PAYLOAD)]),
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    item = UploadItem.objects.create(batch=batch, source_filename="乡土中国.pdf")

    candidates, warnings = invoke_provider(
        provider="nlb_singapore",
        operation="search_book",
        query={"title": "乡土中国", "language": "zh-CN"},
        resolver=lambda: search_nlb_singapore_title("乡土中国", limit=2),
        upload_item=item,
    )
    stats = persist_metadata_candidates(item, candidates)

    assert warnings == []
    assert stats["added"] >= 8
    title = MetadataCandidate.objects.get(
        upload_item=item,
        source="nlb_singapore",
        field_name="title",
    )
    evidence = CandidateEvidence.objects.get(metadata_candidate=title)
    source_record = SourceRecord.objects.get(pk=title.source_record_id)
    assert title.value == "乡土中国"
    assert title.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
    assert evidence.source_record_id == source_record.id
    assert evidence.external_identifier == "https://openweb.nlb.gov.sg/api/swagger/index.html"
    assert source_record.provider == "nlb_singapore"
    assert source_record.status == SourceRecord.Status.SUCCEEDED
    assert source_record.raw_response["candidate_snapshot"]
    assert "private-api-key" not in json.dumps(source_record.raw_response, ensure_ascii=False)
