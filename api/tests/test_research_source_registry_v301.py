from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import CapabilityDemand, CapabilityExecutor, SiteSetting
from catalog.services.processing_center_diagnostics import processing_center_diagnostics
from catalog.services.research_sources import (
    RESEARCH_SOURCE_ADAPTERS,
    REGISTRY_SETTING_KEY,
    STANDARD_BIBLIOGRAPHIC_FORMATS,
    extract_standard_metadata,
    research_source_enabled,
)
from ingestion.models import AuditEvent, SourceRecord


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("payload", "content_type", "expected_format", "expected_title"),
    [
        (
            '<html><head><meta name="citation_title" content="社会理论研究">'
            '<meta name="citation_author" content="张三"></head></html>',
            "text/html",
            "highwire_citation_meta",
            "社会理论研究",
        ),
        (
            '<html><script type="application/ld+json">'
            '{"@type":"ScholarlyArticle","headline":"制度与行动",'
            '"author":{"name":"李四"}}</script></html>',
            "text/html",
            "json_ld",
            "制度与行动",
        ),
        (
            "TY  - BOOK\nTI  - Mind, Self, and Society\nAU  - Mead, George Herbert\nER  -",
            "application/x-research-info-systems",
            "ris",
            "Mind, Self, and Society",
        ),
        (
            "@book{mead, title={Mind, Self, and Society}, author={Mead, George Herbert}, year={1934}}",
            "application/x-bibtex",
            "bibtex",
            "Mind, Self, and Society",
        ),
        (
            '<?xml version="1.0"?><record xmlns="http://www.loc.gov/MARC21/slim">'
            '<datafield tag="245"><subfield code="a">社会学理论</subfield></datafield>'
            '<datafield tag="100"><subfield code="a">柯林斯</subfield></datafield></record>',
            "application/marcxml+xml",
            "marc_xml",
            "社会学理论",
        ),
        (
            '<?xml version="1.0"?><rdf:RDF '
            'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<rdf:Description><dc:title>乡土中国</dc:title>'
            '<dc:creator>费孝通</dc:creator><dc:publisher>生活书店</dc:publisher>'
            '<dc:identifier>ISBN 9787108069423</dc:identifier>'
            '</rdf:Description></rdf:RDF>',
            "application/rdf+xml",
            "rdf",
            "乡土中国",
        ),
    ],
)
def test_standard_metadata_adapter_extracts_supported_formats(
    payload,
    content_type,
    expected_format,
    expected_title,
):
    result = extract_standard_metadata(payload, content_type)

    assert result["source_format"] == expected_format
    assert result["title"] == expected_title


def test_every_registered_source_implements_translator_style_contract():
    required = {
        "detect",
        "search",
        "fetch",
        "extract_metadata",
        "normalize",
        "evidence",
        "health",
        "test_fixture",
    }

    assert {"ncp_ssd", "union_catalog_z3950", "cnki", "vip", "wanfang"}.issubset(
        RESEARCH_SOURCE_ADAPTERS
    )
    assert set(STANDARD_BIBLIOGRAPHIC_FORMATS).issubset(
        RESEARCH_SOURCE_ADAPTERS["ncp_ssd"].spec.metadata_formats
    )
    for adapter in RESEARCH_SOURCE_ADAPTERS.values():
        assert all(callable(getattr(adapter, method, None)) for method in required)


def test_registry_endpoint_is_secret_safe_and_tracks_recent_provider_success(
    api_client,
    admin_user,
    settings,
):
    settings.AUTHORITY_PROVIDER_ENABLED = "viaf"
    SourceRecord.objects.create(
        provider="authority:viaf",
        operation="person",
        request_fingerprint=f"source-registry:{uuid4()}",
        status=SourceRecord.Status.SUCCEEDED,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get("/api/catalog/admin/research-sources/")

    assert response.status_code == 200
    assert response.data["secret_values_exposed"] is False
    viaf = next(row for row in response.data["adapters"] if row["key"] == "viaf")
    assert viaf["enabled"] is True
    assert viaf["last_success_at"] is not None
    assert "credential_alias" not in viaf
    assert "endpoint_alias" not in viaf
    assert response.data["permissions"] == {
        "can_edit": True,
        "can_test": True,
        "can_edit_sensitive_aliases": False,
    }


def test_administrator_can_disable_provider_but_cannot_change_sensitive_alias(
    api_client,
    admin_user,
    settings,
):
    settings.METADATA_PROVIDER_ENABLED = "crossref,openlibrary"
    api_client.force_authenticate(admin_user)

    disabled = api_client.put(
        "/api/catalog/admin/research-sources/",
        {"adapters": [{"key": "crossref", "enabled": False}]},
        format="json",
    )
    forbidden = api_client.put(
        "/api/catalog/admin/research-sources/",
        {"adapters": [{"key": "crossref", "credential_alias": "private-crossref"}]},
        format="json",
    )

    assert disabled.status_code == 200
    assert research_source_enabled("crossref", environment_default=True) is False
    assert forbidden.status_code == 403
    assert forbidden.data["code"] == "owner_required"
    assert SiteSetting.objects.get(key=REGISTRY_SETTING_KEY).public is False
    assert AuditEvent.objects.filter(action="research_source_registry_update").count() == 1


def test_owner_can_store_alias_reference_without_api_disclosure(
    api_client,
    superadmin_user,
    monkeypatch,
):
    monkeypatch.setenv("RESEARCH_SOURCE_ENDPOINT_NCPSSD_PUBLIC", "https://example.org/ncpssd")
    api_client.force_authenticate(superadmin_user)

    response = api_client.put(
        "/api/catalog/admin/research-sources/",
        {
            "adapters": [
                {
                    "key": "ncp_ssd",
                    "enabled": True,
                    "endpoint_alias": "ncpssd-public",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    source = next(row for row in response.data["adapters"] if row["key"] == "ncp_ssd")
    assert source["endpoint_alias_set"] is True
    assert source["endpoint_configured"] is True
    assert "ncpssd-public" not in str(response.data)
    assert "https://example.org/ncpssd" not in str(response.data)
    assert response.data["permissions"]["can_edit_sensitive_aliases"] is True


def test_searxng_endpoint_alias_is_consumed_without_returning_its_value(
    api_client,
    superadmin_user,
    settings,
    monkeypatch,
):
    from catalog.services.field_enrichment.web import SearXNGSearchAdapter

    monkeypatch.setenv("RESEARCH_SOURCE_ENDPOINT_LOCAL_SEARCH", "https://search.example")
    settings.FIELD_ENRICHMENT_SEARCH_ALLOWED_HOSTS = "search.example"
    api_client.force_authenticate(superadmin_user)

    response = api_client.put(
        "/api/catalog/admin/research-sources/",
        {
            "adapters": [
                {
                    "key": "searxng",
                    "enabled": True,
                    "endpoint_alias": "local-search",
                }
            ]
        },
        format="json",
    )

    assert response.status_code == 200
    assert SearXNGSearchAdapter()._base_url() == "https://search.example"
    assert "local-search" not in str(response.data)
    assert "https://search.example" not in str(response.data)


def test_owner_cannot_assign_unused_alias_to_fixed_public_source(
    api_client,
    superadmin_user,
):
    api_client.force_authenticate(superadmin_user)

    response = api_client.put(
        "/api/catalog/admin/research-sources/",
        {"adapters": [{"key": "viaf", "endpoint_alias": "unused-endpoint"}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "alias_not_supported"


def test_processing_diagnostics_exposes_worker_backlog_and_source_status(settings):
    settings.AUTHORITY_PROVIDER_ENABLED = "viaf"
    now = timezone.now()
    CapabilityExecutor.objects.create(
        executor_id="remote-gpu:4070-product",
        display_name="RTX 4070",
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        capabilities=["llm_small"],
        status=CapabilityExecutor.Status.ONLINE,
        last_heartbeat_at=now,
        heartbeat_expires_at=now + timedelta(minutes=2),
        concurrency=2,
        metadata={"task_kinds": ["claim_extraction"]},
    )
    CapabilityDemand.objects.create(
        owner_type="evidence_span",
        owner_key=str(uuid4()),
        capability="llm_small",
        state=CapabilityDemand.State.READY,
        publication_blocking=False,
        idempotency_key=f"source-runtime:{uuid4()}",
        payload={"task_kind": "claim_extraction"},
    )

    snapshot = processing_center_diagnostics()

    assert snapshot["research_sources"]["secret_values_exposed"] is False
    assert snapshot["summary"]["research_source_degradation_count"] >= 0
    assert snapshot["executors"][0]["backlog"] == {
        "compatible_ready": 1,
        "compatible_waiting": 0,
        "claimed": 0,
    }
    assert "functional_impacts" in snapshot


def test_registry_rejects_plaintext_secret_fields(api_client, superadmin_user):
    api_client.force_authenticate(superadmin_user)

    response = api_client.put(
        "/api/catalog/admin/research-sources/",
        {"adapters": [{"key": "openalex", "enabled": True, "api_key": "must-not-store"}]},
        format="json",
    )

    assert response.status_code == 400
    assert response.data["code"] == "secret_rejected"
    assert SiteSetting.objects.filter(key=REGISTRY_SETTING_KEY).exists() is False
