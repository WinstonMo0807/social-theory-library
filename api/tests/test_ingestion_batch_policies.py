from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import fitz
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import (
    Asset,
    Edition,
    OcrStatus,
    Page,
    PublicationState,
    SemanticIndexStatus,
    Work,
)
from ingestion.models import UploadBatch, UploadItem
from ingestion.services.ai_metadata import metadata_candidates_from_ai
from ingestion.services.candidate_store import persist_metadata_candidates
from ingestion.services.extract import ExtractedPage
from ingestion.services.metadata import Candidate
from ingestion.services.pipeline import run_pipeline


def _pdf_bytes(path: Path, marker: str) -> bytes:
    document = fitz.open()
    for page_index in range(2):
        page = document.new_page(width=595, height=842)
        page.insert_textbox(
            fitz.Rect(50, 50, 545, 792),
            (
                f"Policy test {marker}\nTest Author\n"
                + "Sociology institutions and social theory. " * 35
                + f"\nPage {page_index + 1}"
            ),
            fontsize=10,
        )
    document.set_metadata({"title": f"Policy test {marker}", "author": "Test Author"})
    document.save(path)
    document.close()
    return path.read_bytes()


@pytest.mark.django_db
def test_batch_create_validates_and_persists_processing_policy(api_client, admin_user):
    api_client.force_authenticate(admin_user)

    response = api_client.post(
        "/api/ingestion/batches/create/",
        {
            "expected_count": 3,
            "label": "中文专著待审",
            "access_policy": "registered",
            "ocr_strategy": "skip",
            "duplicate_policy": "block_exact",
            "external_enrichment_enabled": False,
            "ai_suggestions_enabled": True,
        },
        format="json",
    )

    assert response.status_code == 201
    batch = UploadBatch.objects.get(pk=response.data["id"])
    assert batch.label == "中文专著待审"
    assert batch.access_policy == UploadBatch.AccessPolicy.REGISTERED
    assert batch.ocr_strategy == UploadBatch.OcrStrategy.SKIP
    assert batch.duplicate_policy == UploadBatch.DuplicatePolicy.BLOCK_EXACT
    assert batch.external_enrichment_enabled is False
    assert batch.ai_suggestions_enabled is True

    invalid = api_client.post(
        "/api/ingestion/batches/create/",
        {"expected_count": 1, "ocr_strategy": "invented"},
        format="json",
    )
    assert invalid.status_code == 400
    assert "ocr_strategy" in invalid.data["error"]["detail"]


@pytest.mark.django_db(transaction=True)
def test_pipeline_consumes_batch_ocr_provider_ai_and_access_policy(
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.REQUIRE_EXTERNAL_SEARCH = False
    source = tmp_path / "policy.pdf"
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        access_policy=UploadBatch.AccessPolicy.REGISTERED,
        ocr_strategy=UploadBatch.OcrStrategy.FORCE,
        external_enrichment_enabled=False,
        ai_suggestions_enabled=True,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="policy.pdf",
        file=SimpleUploadedFile(
            "policy.pdf",
            _pdf_bytes(source, "force-ocr"),
            content_type="application/pdf",
        ),
    )
    ai_candidate = Candidate(
        "publisher",
        "AI 仅供复核出版社",
        "ai_metadata_candidate",
        0.5,
        {"page": 1, "text_quote": "AI 仅供复核出版社"},
    )

    with patch(
        "ingestion.services.pipeline.enrich_candidates_with_gateway"
    ) as gateway, patch(
        "ingestion.services.pipeline.metadata_candidates_from_ai",
        return_value=([ai_candidate], {"status": "succeeded"}),
    ) as ai_service, patch(
        "ingestion.services.pipeline.queue_ocr_job"
    ) as queue_ocr:
        result = run_pipeline(str(item.id))

    assert result.status == UploadItem.Status.READY
    gateway.assert_not_called()
    ai_service.assert_called()
    queue_ocr.assert_called_once()
    normalized = result.edition.assets.get(kind=Asset.Kind.NORMALIZED)
    assert normalized.access_status == Asset.AccessStatus.REGISTERED
    assert normalized.validation_details["ocr_strategy"] == UploadBatch.OcrStrategy.FORCE
    assert normalized.validation_details["ocr_required_page_indexes"] == [1, 2]
    item.refresh_from_db()
    assert item.preflight_summary["page_count"] == 2
    assert item.preflight_summary["text_profile"] == "born_digital"
    assert item.preflight_summary["scheduled_ocr_pages"] == 2
    candidate = item.metadata_candidates.get(
        field_name="publisher",
        source="ai_metadata_candidate",
    )
    assert candidate.lifecycle == "proposed"
    assert candidate.selected is False
    result.edition.refresh_from_db()
    assert result.edition.publisher != "AI 仅供复核出版社"


@pytest.mark.django_db(transaction=True)
def test_skip_ocr_disables_all_ocr_paths_for_scanned_pages(
    admin_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_ORIGINAL_ROOT = settings.MEDIA_ROOT / "originals"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.REQUIRE_EXTERNAL_SEARCH = False
    source = tmp_path / "skip-ocr.pdf"
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        ocr_strategy=UploadBatch.OcrStrategy.SKIP,
        external_enrichment_enabled=False,
    )
    item = UploadItem.objects.create(
        batch=batch,
        source_filename="skip-ocr.pdf",
        file=SimpleUploadedFile(
            "skip-ocr.pdf",
            _pdf_bytes(source, "skip-ocr"),
            content_type="application/pdf",
        ),
    )
    scanned_pages = [
        ExtractedPage(
            index=page_index,
            printed_label="",
            chapter_title="",
            width=595,
            height=842,
            text="",
            source=Page.TextSource.NONE,
            confidence=1,
            blocks=[],
            ocr_reasons=("scanned_page",),
        )
        for page_index in (1, 2)
    ]

    with patch(
        "ingestion.services.pipeline.extract_native_pages",
        return_value=(scanned_pages, True),
    ), patch(
        "ingestion.services.pipeline.detect_publication_places",
        return_value=[],
    ) as detect_places, patch(
        "ingestion.services.pipeline.queue_ocr_job"
    ) as queue_ocr, patch(
        "ingestion.services.pipeline.queue_semantic_job"
    ) as queue_semantic, patch(
        "ingestion.services.pipeline.queue_page_label_job"
    ) as queue_page_labels:
        result = run_pipeline(str(item.id))

    normalized = result.edition.assets.get(kind=Asset.Kind.NORMALIZED)
    result.edition.refresh_from_db()
    assert result.status == UploadItem.Status.READY
    assert normalized.extraction_method == "ocr_disabled"
    assert normalized.validation_details["ocr_detected_page_indexes"] == [1, 2]
    assert normalized.validation_details["ocr_required_page_indexes"] == []
    assert result.edition.ocr_status == OcrStatus.DISABLED
    assert result.edition.semantic_index_status == SemanticIndexStatus.NOT_INDEXED
    queue_ocr.assert_not_called()
    queue_semantic.assert_not_called()
    queue_page_labels.assert_called_once()
    assert detect_places.call_args.kwargs["allow_targeted_ocr"] is False


@pytest.mark.django_db
def test_registered_asset_requires_login_but_remains_available_to_reader(
    api_client,
    reader_user,
    tmp_path,
    settings,
):
    settings.MEDIA_ROOT = tmp_path / "media"
    settings.NAS_PUBLIC_ROOT = settings.MEDIA_ROOT / "public"
    settings.REQUIRE_CLOUD_FOR_PUBLICATION = False
    settings.ALLOW_LOCAL_PUBLIC_ASSET_ACCESS = True
    work = Work.objects.create(title="登录读者文献", normalized_title="登录读者文献")
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        canonical_filename="registered.pdf",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("registered.pdf", b"%PDF-registered"),
        sha256="f" * 64,
        byte_size=15,
        page_count=1,
        status=Asset.Status.READY,
        validation_status=Asset.ValidationStatus.VALID,
        access_status=Asset.AccessStatus.REGISTERED,
    )

    anonymous = api_client.get(f"/api/distribution/assets/{asset.id}/access/")
    assert anonymous.status_code == 401

    api_client.force_authenticate(reader_user)
    authenticated = api_client.get(f"/api/distribution/assets/{asset.id}/access/")
    assert authenticated.status_code == 200
    assert authenticated.data["requested_asset_id"] == str(asset.id)


@pytest.mark.django_db
def test_ai_metadata_result_keeps_model_provenance_and_cannot_auto_accept(admin_user):
    batch = UploadBatch.objects.create(
        created_by=admin_user,
        expected_count=1,
        ai_suggestions_enabled=True,
    )
    item = UploadItem.objects.create(batch=batch, source_filename="candidate.pdf")
    fake_client = SimpleNamespace(
        config=SimpleNamespace(enabled=True, provider="ollama", metadata_model="local-model"),
        generate_json=lambda **_kwargs: SimpleNamespace(
            data={
                "proposals": [
                    {
                        "field_name": "publisher",
                        "value": "候选出版社",
                        "evidence": [
                            {"page_number": 4, "bbox": [1, 2, 3, 4], "text_quote": "候选出版社"}
                        ],
                        "reason": "版权页出版项",
                        "warnings": [],
                    }
                ]
            },
            provider="ollama",
            model="local-model",
            prompt_version="bibliographic-candidates-v1",
            latency_ms=8,
            attempts=1,
        ),
    )

    with patch("ingestion.services.ai_metadata.AIClient", return_value=fake_client):
        candidates, summary = metadata_candidates_from_ai(
            "PDF 第 4 页\n北京：候选出版社，2026",
            upload_item=item,
        )

    assert summary["status"] == "succeeded"
    assert item.source_records.filter(provider="ai:ollama", status="succeeded").exists()
    persist_metadata_candidates(item, candidates, {"publisher": "候选出版社"})
    stored = item.metadata_candidates.get(source="ai_metadata_candidate")
    assert stored.selected is False
    assert stored.lifecycle == "proposed"
    assert stored.source_record.provider == "ai:ollama"
    assert stored.evidence_records.get().page_number == 4
