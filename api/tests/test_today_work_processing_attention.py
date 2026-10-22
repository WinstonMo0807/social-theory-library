from unittest.mock import patch

import pytest

from catalog.models import Asset, Edition, OcrStatus, SemanticIndexStatus, Work
from ingestion.models import UploadBatch, UploadItem
from ingestion.views import _dashboard_processing_attention


pytestmark = pytest.mark.django_db


def test_today_work_surfaces_ocr_and_index_attention_with_processing_link(admin_user, api_client):
    work = Work.objects.create(title="今日工作提醒")
    edition = Edition.objects.create(
        work=work,
        ocr_status=OcrStatus.PENDING,
        semantic_index_status=SemanticIndexStatus.NOT_INDEXED,
    )
    original = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.ORIGINAL,
        file="synthetic/today-work-original.pdf",
        sha256="a" * 64,
        byte_size=20,
        status=Asset.Status.READY,
        is_current=True,
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="synthetic/today-work.pdf",
        sha256="a" * 64,
        byte_size=20,
        status=Asset.Status.READY,
        is_current=True,
        source_asset=original,
    )
    batch = UploadBatch.objects.create(created_by=admin_user, expected_count=1)
    UploadItem.objects.create(
        batch=batch,
        edition=edition,
        asset=original,
        source_filename="today-work.pdf",
        sha256="a" * 64,
        status=UploadItem.Status.READY,
        preflight_summary={
            "detected_ocr_pages": 8,
            "scheduled_ocr_pages": 8,
            "ocr_decision": "required",
        },
    )
    availability = {
        edition.pk: {
            "capabilities": [
                {"key": "text", "status": "pending", "detail": "正文等待 OCR。"},
                {"key": "viewpoint", "status": "pending", "detail": "观点索引尚未建立。"},
            ]
        }
    }

    with patch("catalog.services.catalog_availability.batch_catalog_availability", return_value=availability):
        result = _dashboard_processing_attention()

    assert result["total"] == 1
    assert result["ocr_count"] == 1
    assert result["index_count"] == 1
    row = result["items"][0]
    assert row["title"] == "今日工作提醒"
    assert row["ocr"]["status"] == OcrStatus.PENDING
    assert row["ocr"]["scheduled_pages"] == 8
    assert row["source_filename"] == "today-work.pdf"
    assert row["index"]["status"] == SemanticIndexStatus.NOT_INDEXED
    assert row["processing_url"].startswith("/admin/processing?surface=documents&q=")
    assert f"edition_id={edition.pk}" in row["processing_url"]
    assert "%E4%BB%8A%E6%97%A5%E5%B7%A5%E4%BD%9C%E6%8F%90%E9%86%92" in row["processing_url"]

    api_client.force_authenticate(admin_user)
    with patch("catalog.services.catalog_availability.batch_catalog_availability", return_value=availability):
        response = api_client.get("/api/ingestion/dashboard/")
    assert response.status_code == 200, response.data
    assert response.data["processing_attention"]["items"][0]["id"] == str(edition.pk)


def test_today_work_includes_published_viewpoint_projection_after_semantic_ready():
    work = Work.objects.create(title="公开观点投影提醒")
    edition = Edition.objects.create(
        work=work,
        state="published",
        ocr_status=OcrStatus.SUCCEEDED,
        semantic_index_status=SemanticIndexStatus.READY,
    )
    Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file="synthetic/published-viewpoint.pdf",
        sha256="b" * 64,
        byte_size=20,
        status=Asset.Status.READY,
        is_current=True,
    )
    availability = {
        edition.pk: {
            "capabilities": [
                {"key": "text", "status": "ready", "detail": "正文已就绪。"},
                {"key": "viewpoint", "status": "pending", "detail": "公开观点投影尚未完成。"},
            ]
        }
    }

    with patch("catalog.services.catalog_availability.batch_catalog_availability", return_value=availability):
        result = _dashboard_processing_attention()

    assert result["total"] == 1
    assert result["ocr_count"] == 0
    assert result["index_count"] == 1
    assert result["items"][0]["index"]["label"] == "观点索引未完成"
