"""Deferred: successful-page exports must not include unfinished pages or other revisions."""
import json

import pytest

from catalog.models import DocumentOutlineRevision, Page
from ingestion.models import ProcessingJob
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db


def test_ocr_exports_only_recorded_successes_and_rejects_changed_source(api_client, admin_user, settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    asset.page_count = 2; asset.save(update_fields=["page_count", "updated_at"])
    first = Page.objects.create(asset=asset, index=1, text="已成功保存的文字", text_source="ocr")
    Page.objects.create(asset=asset, index=2, text="未完成页原有文字", text_source="embedded")
    job = ProcessingJob.objects.create(job_type="ocr", status="failed", asset=asset, edition=asset.edition,
        stats={"requested_asset_id": str(asset.pk), "source_sha256": asset.sha256, "completed_page_indexes": [1], "active_page_indexes": [2]})
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    manifest = api_client.get(path, **headers)
    assert manifest.status_code == 200 and manifest.data["count"] == 1
    download = api_client.get(path, {"download": "jsonl", "expected_version": manifest.data["version"]}, **headers)
    assert download.status_code == 200 and "no-store" in download["Cache-Control"]
    records = [json.loads(line) for line in b"".join(download.streaming_content).decode().splitlines()]
    assert "owner_id" not in records[0]
    assert len(records) == 2 and records[1]["text"] == first.text
    first.text = "修订后的文字"; first.save(update_fields=["text", "updated_at"])
    assert api_client.get(path, {"download": "txt", "expected_version": manifest.data["version"]}, **headers).status_code == 409
    assert api_client.get(path, HTTP_X_EDITOR_OWNER="another-account").status_code == 403
    job.stats = {}; job.save(update_fields=["stats", "updated_at"])
    assert api_client.get(path, **headers).data["count"] == 0


def test_outline_uses_exact_job_revision_without_old_outline_fallback(api_client, admin_user, settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    revision = DocumentOutlineRevision.objects.create(asset=asset, revision=1, source_checksum=asset.sha256,
        nodes=[{"id": "chapter-one", "title": "已保存目录", "pdf_page": 1, "calibration_status": "candidate"}])
    job = ProcessingJob.objects.create(job_type="text_extraction", status="failed", asset=asset, edition=asset.edition,
        stats={"operation": "outline_rebuild", "source_sha256": asset.sha256})
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    path = f"/api/ingestion/processing-workspace/results/{job.pk}/"
    assert api_client.get(path, **headers).data["count"] == 0
    job.stats["result_revision_id"] = str(revision.pk); job.save(update_fields=["stats", "updated_at"])
    response = api_client.get(path, **headers)
    assert response.data["count"] == 1 and response.data["revision_id"] == str(revision.pk)
