"""Deferred acceptance: configured creation must survive an ambiguous response."""
from unittest.mock import patch
from uuid import uuid4

import pytest

from ingestion.models import AuditEvent, ProcessingJob
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def test_outline_creation_replay_source_conflict_and_stopped_intent(api_client, admin_user, settings, tmp_path):
    _, _, _, asset = create_item_with_files(settings, tmp_path)
    api_client.force_authenticate(admin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(admin_user.pk)}
    body = {"action": "create", "task_type": "outline", "request_id": str(uuid4()),
            "asset_id": str(asset.pk), "source_version": asset.updated_at.isoformat(), "confirmed": True}
    with patch("catalog.services.document_outline.dispatch_outline_job"):
        first = api_client.post(URL, body, format="json", **headers)
        assert first.status_code == 200, first.data
        asset.save()  # Simulate a source revision after the response was lost.
        replay = api_client.post(URL, body, format="json", **headers)
        assert replay.status_code == 200 and replay.data["job_id"] == first.data["job_id"]
        assert ProcessingJob.objects.filter(stats__operation="outline_rebuild").count() == 1
        stale = api_client.post(URL, {**body, "request_id": str(uuid4())}, format="json", **headers)
        assert stale.status_code == 409
        stopped_id = str(uuid4())
        stop = api_client.post(f"{URL}commands/{stopped_id}/", {"action": "cancel_pending"}, format="json", **headers)
        assert stop.status_code == 200 and stop.data["state"] == "cancelled"
        late = api_client.post(URL, {**body, "request_id": stopped_id, "source_version": asset.updated_at.isoformat()}, format="json", **headers)
        assert late.status_code == 200 and late.data["state"] == "cancelled"
        assert ProcessingJob.objects.filter(stats__operation="outline_rebuild").count() == 1
        foreign = api_client.post(URL, {**body, "request_id": str(uuid4())}, format="json", HTTP_X_EDITOR_OWNER=str(uuid4()))
        assert foreign.status_code == 403


def test_discovery_retry_keeps_original_checkpoint_and_failure_record(admin_user):
    from catalog.services.discovery_indexing import retry_job
    location = {"unit_id": str(uuid4()), "pdf_page": 7, "start_offset": 32, "end_offset": 96}
    job = ProcessingJob.objects.create(job_type="discovery_index", status="failed", error_code="queue_unavailable",
        error_message="队列未响应", attempt=2, stats={"action": "build", "completed_units": 4, "active_unit": location})
    with patch("catalog.services.discovery_indexing._dispatch"):
        result = retry_job(job.pk, actor=admin_user)
    assert result.pk == job.pk and result.status == "pending"
    assert result.stats["completed_units"] == 4 and result.stats["active_unit"] == location
    audit = AuditEvent.objects.get(action="discovery.retry_from_checkpoint", object_id=str(job.pk))
    assert audit.before["error_message"] == "队列未响应" and audit.before["attempt"] == 2
