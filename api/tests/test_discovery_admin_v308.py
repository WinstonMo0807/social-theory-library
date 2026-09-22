"""Permission and truthful-stage checks for the existing Processing Center."""
from unittest.mock import patch

import pytest
from catalog.models import Asset, Edition, Work
from catalog.services.discovery_inference import DiscoveryInferenceError
from ingestion.models import ProcessingJob

pytestmark = pytest.mark.django_db
ENDPOINT = "/api/catalog/admin/discovery-index/"


def test_reader_cannot_inspect_private_processing_records(api_client, reader_user):
    Edition.objects.create(work=Work.objects.create(title="管理员私有待处理材料"))
    assert api_client.get(ENDPOINT).status_code in {401, 403}
    api_client.force_authenticate(reader_user)
    assert api_client.get(ENDPOINT).status_code == 403
    assert api_client.post(ENDPOINT, {"action": "rebuild"}, format="json").status_code == 403


def test_admin_sees_missing_text_without_claiming_vector_or_model_readiness(api_client, admin_user):
    edition = Edition.objects.create(work=Work.objects.create(title="阅读不等于索引"), ocr_status="pending")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        sha256="4" * 64, page_count=20, access_status="private")
    api_client.force_authenticate(admin_user)
    with patch("catalog.discovery_index_views.inference_health", side_effect=DiscoveryInferenceError("model_missing")):
        response = api_client.get(ENDPOINT)
    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["asset_id"] == str(asset.pk)
    assert row["readable"]["status"] == "private"
    assert row["text"]["status"] == "pending"
    assert row["text"]["completed_pages"] == 0
    assert row["text"]["total_pages"] == 20
    assert row["vector"]["count"] == 0
    assert response.data["model"]["ready"] is False
    assert response.data["summary"]["keyword_ready"] == 0
    assert response.data["capabilities"]["rebuild"] is False
    assert api_client.post(ENDPOINT, {"action": "rebuild"}, format="json").status_code == 403


def test_retry_reuses_failed_job_and_rejects_unrelated_ocr(api_client, admin_user):
    api_client.force_authenticate(admin_user)
    index = ProcessingJob.objects.create(job_type="discovery_index", status="failed",
        stats={"action": "build"}, attempt=3)
    ocr = ProcessingJob.objects.create(job_type="ocr", status="failed")
    with patch("catalog.services.discovery_indexing._dispatch"):
        response = api_client.post(ENDPOINT, {"action": "retry", "job_id": str(index.pk)}, format="json")
    assert response.status_code == 202
    assert response.data["job_id"] == str(index.pk)
    index.refresh_from_db()
    assert index.status == "pending" and index.task_id
    assert ProcessingJob.objects.filter(job_type="discovery_index").count() == 1
    assert api_client.post(ENDPOINT, {"action": "retry", "job_id": str(ocr.pk)}, format="json").status_code == 400
    ocr.refresh_from_db()
    assert ocr.status == "failed"
