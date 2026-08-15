from unittest.mock import Mock

import httpx
import pytest
from django.test import override_settings

from catalog.models import Asset, DocumentType, Edition, Work
from ingestion.models import MetadataCandidate, SourceRecord, UploadBatch, UploadItem
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.candidate_decisions import accept_candidates_from_review, set_candidate_decision
from ingestion.services.metadata import Candidate, ProviderCandidates, resolve_openalex_doi
from ingestion.services.provider_gateway import invoke_provider, refresh_remote_candidates


def _item(admin_user, filename="provider.pdf"):
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    return UploadItem.objects.create(batch=batch, source_filename=filename)


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="crossref",
    METADATA_PROVIDER_ALLOWED_HOSTS="api.crossref.org",
    METADATA_PROVIDER_RETRIES=0,
    METADATA_PROVIDER_MIN_INTERVAL_MS=0,
)
def test_gateway_records_provenance_and_reuses_item_cache(admin_user):
    item = _item(admin_user)
    resolver = Mock(
        return_value=ProviderCandidates(
            [Candidate("title", "规训与惩罚", "crossref", 0.95, {"doi": "10.1/test"})],
            raw_response={"message": {"title": ["规训与惩罚"]}},
            external_id="10.1/test",
            provider_version="crossref-rest-v1",
        )
    )

    first, warnings = invoke_provider(
        provider="crossref",
        operation="lookup_doi",
        query={"doi": "10.1/test"},
        resolver=resolver,
        upload_item=item,
    )
    second, second_warnings = invoke_provider(
        provider="crossref",
        operation="lookup_doi",
        query={"doi": "10.1/test"},
        resolver=resolver,
        upload_item=item,
    )

    assert warnings == []
    assert second_warnings == []
    assert resolver.call_count == 1
    assert first[0].evidence["source_record_id"] == second[0].evidence["source_record_id"]
    record = SourceRecord.objects.get()
    assert record.status == SourceRecord.Status.SUCCEEDED
    assert record.raw_response["candidate_snapshot"][0]["value"] == "规训与惩罚"
    assert record.raw_response["payload"]["message"]["title"] == ["规训与惩罚"]


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="crossref",
    METADATA_PROVIDER_ALLOWED_HOSTS="api.crossref.org",
    METADATA_PROVIDER_RETRIES=0,
    METADATA_PROVIDER_MIN_INTERVAL_MS=0,
)
def test_gateway_records_failure_without_breaking_manual_ingestion(admin_user):
    item = _item(admin_user, "offline.pdf")

    def fail():
        raise httpx.ConnectError("offline")

    candidates, warnings = invoke_provider(
        provider="crossref",
        operation="lookup_doi",
        query={"doi": "10.1/offline"},
        resolver=fail,
        upload_item=item,
    )

    assert candidates == []
    assert warnings and "network_error" not in warnings[0]
    record = SourceRecord.objects.get()
    assert record.status == SourceRecord.Status.FAILED
    assert record.error_code == "network_error"
    assert "offline" in record.error_message


@pytest.mark.django_db
def test_candidate_rerun_preserves_human_decisions_and_supersedes_only_stale_proposals(admin_user):
    item = _item(admin_user, "history.pdf")
    original = [
        Candidate("title", "旧题名", "first_pages", 0.6, {"page": 1}),
        Candidate("publisher", "旧出版社", "first_pages", 0.5, {"page": 4}),
    ]
    first_stats = persist_metadata_candidates(item, original, {"title": "旧题名"})
    accepted = item.metadata_candidates.get(field_name="title")
    accepted.lifecycle = MetadataCandidate.Lifecycle.ACCEPTED
    accepted.is_locked = True
    accepted.confidence = 0.99
    accepted.save(update_fields=["lifecycle", "is_locked", "confidence", "updated_at"])

    second_stats = persist_metadata_candidates(
        item,
        [
            Candidate("title", "旧题名", "first_pages", 0.1, {"page": 2}),
            Candidate("publication_year", 2019, "first_pages", 0.8, {"page": 4}),
        ],
        {"title": "旧题名", "publication_year": 2019},
    )

    accepted.refresh_from_db()
    stale = item.metadata_candidates.get(field_name="publisher")
    year = item.metadata_candidates.get(field_name="publication_year")
    assert first_stats["added"] == 2
    assert second_stats == {"added": 1, "updated": 0, "preserved": 1, "superseded": 1}
    assert accepted.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
    assert accepted.confidence == 0.99
    assert stale.lifecycle == MetadataCandidate.Lifecycle.SUPERSEDED
    assert year.lifecycle == MetadataCandidate.Lifecycle.PROPOSED
    assert year.evidence_records.get().page_number == 4


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="crossref",
    METADATA_PROVIDER_ALLOWED_HOSTS="api.crossref.org",
    METADATA_PROVIDER_RETRIES=0,
    METADATA_PROVIDER_MIN_INTERVAL_MS=0,
)
def test_candidate_evidence_links_to_source_record(admin_user):
    item = _item(admin_user, "evidence.pdf")
    values, _ = invoke_provider(
        provider="crossref",
        operation="lookup_doi",
        query={"doi": "10.1/evidence"},
        resolver=lambda: ProviderCandidates(
            [Candidate("title", "证据题名", "crossref", 0.9, {"record_url": "https://doi.org/10.1/evidence"})],
            raw_response={"ok": True},
            external_id="10.1/evidence",
        ),
        upload_item=item,
    )

    persist_metadata_candidates(item, values, {"title": "证据题名"})
    candidate = item.metadata_candidates.get()
    evidence = candidate.evidence_records.get()
    assert candidate.source_record_id == evidence.source_record_id
    assert evidence.external_identifier == "https://doi.org/10.1/evidence"


@pytest.mark.django_db
def test_repeated_candidate_persistence_backfills_evidence_asset(admin_user):
    item = _item(admin_user, "asset-late.pdf")
    candidate = Candidate("title", "延后绑定文件", "first_pages", 0.8, {"page": 1})
    persist_metadata_candidates(item, [candidate], {"title": candidate.value})
    evidence = item.metadata_candidates.get().evidence_records.get()
    assert evidence.asset_id is None

    work = Work.objects.create(document_type=DocumentType.BOOK, title="延后绑定文件")
    edition = Edition.objects.create(work=work)
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="tests/asset-late.pdf",
        sha256="a" * 64,
        byte_size=100,
        page_count=1,
        status=Asset.Status.READY,
    )
    item.edition = edition
    item.asset = asset
    item.save(update_fields=["edition", "asset", "updated_at"])

    persist_metadata_candidates(item, [candidate], {"title": candidate.value})
    evidence.refresh_from_db()
    assert evidence.asset_id == asset.id


@pytest.mark.django_db
def test_review_acceptance_and_rejection_are_audited_without_overwriting_each_other(admin_user):
    item = _item(admin_user, "decisions.pdf")
    persist_metadata_candidates(
        item,
        [
            Candidate("title", "采用题名", "crossref", 0.9, {"record_url": "https://doi.org/x"}),
            Candidate("title", "拒绝题名", "first_pages", 0.6, {"page": 1}),
        ],
        {"title": "采用题名"},
    )
    accepted_count = accept_candidates_from_review(
        item,
        {"title": "采用题名"},
        actor=admin_user,
        locked_fields={"title"},
    )
    accepted = item.metadata_candidates.get(value="采用题名")
    rejected = item.metadata_candidates.get(value="拒绝题名")
    set_candidate_decision(rejected, action="reject", actor=admin_user)

    accepted.refresh_from_db()
    rejected.refresh_from_db()
    assert accepted_count == 1
    assert accepted.lifecycle == MetadataCandidate.Lifecycle.ACCEPTED
    assert accepted.is_locked is True
    assert rejected.lifecycle == MetadataCandidate.Lifecycle.REJECTED
    assert item.decision_logs.count() == 2

    with pytest.raises(ValueError, match="先在元数据表单中改选"):
        set_candidate_decision(accepted, action="reject", actor=admin_user)


@override_settings(
    OPENALEX_API_KEY="test-openalex-key",
    METADATA_PROVIDER_TIMEOUT_SECONDS=3,
)
def test_openalex_maps_chinese_journal_record_to_review_candidates(monkeypatch):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "results": [
            {
                "id": "https://openalex.org/W123",
                "doi": "https://doi.org/10.1000/中文测试",
                "title": "社会理论的中国经验",
                "publication_year": 2024,
                "language": "zh",
                "type": "article",
                "authorships": [
                    {"author": {"display_name": "张三"}},
                    {"author": {"display_name": "Li Ming"}},
                ],
                "primary_location": {"source": {"display_name": "社会学研究"}},
                "biblio": {"volume": "39", "issue": "2", "first_page": "15", "last_page": "31"},
            }
        ]
    }
    request = Mock(return_value=response)
    monkeypatch.setattr("ingestion.services.metadata.httpx.get", request)

    candidates = resolve_openalex_doi("10.1000/中文测试")

    values = {(candidate.field_name, str(candidate.value)) for candidate in candidates}
    assert ("title", "社会理论的中国经验") in values
    assert ("authors", "['张三', 'Li Ming']") in values
    assert ("journal_title", "社会学研究") in values
    assert ("page_range", "15-31") in values
    assert ("doi", "10.1000/中文测试") in values
    assert candidates.provider_version == "openalex-rest-v1"
    assert request.call_args.kwargs["headers"]["api_key"] == "test-openalex-key"
    assert request.call_args.kwargs["params"]["filter"].endswith("10.1000/中文测试")


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="openalex",
    METADATA_PROVIDER_ALLOWED_HOSTS="api.openalex.org",
    OPENALEX_API_KEY="",
)
def test_openalex_without_api_key_is_explicitly_not_configured(admin_user):
    item = _item(admin_user, "openalex-no-key.pdf")
    resolver = Mock()

    candidates, warnings = invoke_provider(
        provider="openalex",
        operation="search_work",
        query={"title": "中文期刊测试"},
        resolver=resolver,
        upload_item=item,
    )

    assert candidates == []
    assert warnings == ["openalex 元数据来源尚未配置 API Key"]
    resolver.assert_not_called()
    assert not SourceRecord.objects.filter(upload_item=item).exists()


@pytest.mark.django_db
@override_settings(
    METADATA_PROVIDER_ENABLED="crossref,openalex",
    METADATA_PROVIDER_ALLOWED_HOSTS="api.crossref.org,api.openalex.org",
    OPENALEX_API_KEY="configured",
)
def test_chinese_journal_title_refresh_uses_crossref_and_openalex(monkeypatch):
    work = Work.objects.create(
        document_type=DocumentType.JOURNAL_ARTICLE,
        title="社会理论的中国经验",
        language="zh-CN",
    )
    edition = Edition.objects.create(work=work)
    providers = []

    def fake_invoke(**kwargs):
        providers.append(kwargs["provider"])
        return [], []

    monkeypatch.setattr("ingestion.services.provider_gateway.invoke_provider", fake_invoke)
    candidates, warnings = refresh_remote_candidates(edition)

    assert candidates == []
    assert warnings == []
    assert providers == ["crossref", "openalex"]
