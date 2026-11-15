from unittest.mock import MagicMock, patch
from datetime import timedelta

import httpx
import pytest
from django.db.models import F
from django.utils import timezone

from catalog.models import ProjectionState
from catalog.services.discovery_indexing import wait_index_task
from catalog.services.discovery_projection import DiscoveryIndexError
from catalog.services.knowledge_publication import create_catalog_publication_event, process_knowledge_event
from tests.test_metadata_publication_visibility_v305 import publication
from ingestion.models import ProcessingJob


@pytest.mark.django_db
@pytest.mark.parametrize("present,expected", [(frozenset({"waiting"}), "pending"), (None, "pending"), (frozenset(), "failed")])
def test_discovery_recovery_preserves_queued_delivery_without_masking_lost_worker(present, expected):
    from catalog.services.discovery_indexing import _reconcile
    queued = ProcessingJob.objects.create(job_type="discovery_index", status="pending", task_id="waiting",
        stats={"action": "source", "completed_units": 23})
    running = ProcessingJob.objects.create(job_type="discovery_index", status="running", task_id="interrupted",
        stats={"action": "source", "completed_units": 12})
    ProcessingJob.objects.filter(pk__in=[queued.pk, running.pk]).update(updated_at=timezone.now() - timedelta(hours=2))
    with patch("common.broker_presence.broker_delivery_ids", return_value=present), patch(
        "catalog.services.discovery_indexing.active_generation", return_value=None
    ), patch("catalog.services.discovery_indexing.finish_builds"):
        _reconcile()
    queued.refresh_from_db()
    running.refresh_from_db()
    assert queued.status == expected
    assert queued.attempt == (1 if expected == "failed" else 0)
    assert queued.task_id == "waiting" and queued.stats["completed_units"] == 23
    assert running.status == "failed" and running.attempt == 1


@pytest.mark.django_db
@pytest.mark.parametrize("quality", [0.8, 0.1])
def test_metadata_edit_keeps_qualified_text_requested_after_delivery_failure(settings, tmp_path, admin_user, quality):
    _, edition, _, _, first = publication(settings, tmp_path, admin_user, text_ready=True)
    ProjectionState.objects.filter(object_id=first.object_id).update(
        projected_revision=F("source_revision"), status="current")
    process_knowledge_event(first.pk)
    edition.refresh_from_db()
    assert edition.active_catalog_revision.fulltext_ready
    failed = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["topics"],
        idempotency_key="recovery:failed", actor=admin_user)
    ProjectionState.objects.filter(object_id=failed.object_id).update(
        projected_revision=F("source_revision"), status="current")
    ProjectionState.objects.filter(object_id=failed.object_id, projection_type="fulltext").update(
        projected_revision=0, status="failed", last_error_code="fulltext_projection_failed")
    process_knowledge_event(failed.pk)
    edition.refresh_from_db()
    captured = edition.active_catalog_revision
    assert not captured.fulltext_ready
    captured.document_revision.quality_assessments.update(fulltext_quality=quality, semantic_quality=quality)
    updated = create_catalog_publication_event(edition, event_type="catalog_updated", changed_fields=["authors"],
        idempotency_key="recovery:metadata", actor=admin_user)
    assert updated.catalog_revision.document_revision_id == captured.document_revision_id
    assert updated.payload["requested_fulltext_ready"] is (quality >= 0.55)
    assert not updated.catalog_revision.fulltext_ready


def test_discovery_waits_for_same_accepted_task_after_slow_status_read():
    clock = [0.0]
    paths = []
    def poll(method, path, **kwargs):
        paths.append((method, path))
        if clock[0] == 1:
            clock[0] += kwargs["timeout"]
            raise DiscoveryIndexError("index_unavailable") from httpx.ReadTimeout("busy")
        return {"status": "succeeded" if clock[0] >= 180 else "processing"}
    with patch("catalog.services.discovery_indexing.time.monotonic", side_effect=lambda: clock[0]), patch(
        "catalog.services.discovery_indexing.time.sleep", side_effect=lambda n: clock.__setitem__(0, clock[0] + n)
    ), patch("catalog.services.discovery_indexing.meili", side_effect=poll):
        assert wait_index_task({"taskUid": 17})["status"] == "succeeded"
    assert clock[0] == 180
    assert set(paths) == {("GET", "/tasks/17")}


def test_inference_cold_start_waits_beyond_fifteen_seconds(settings):
    from common.on_demand import ensure_service
    settings.NAS_ON_DEMAND_ENABLED = True
    clock = [0.0]
    def probe(*args, **kwargs):
        if clock[0] < 30:
            raise ConnectionRefusedError()
        return MagicMock()
    with patch("common.on_demand.time.monotonic", side_effect=lambda: clock[0]), patch(
        "common.on_demand.time.sleep", side_effect=lambda n: clock.__setitem__(0, clock[0] + n)
    ), patch("common.on_demand.socket.create_connection", side_effect=probe), patch(
        "config.celery.app.connection_for_write"
    ) as connection:
        conn = connection.return_value.__enter__.return_value
        conn.transport.driver_type = "redis"
        conn.channel.return_value.__enter__.return_value.client.pipeline.return_value.__enter__.return_value.execute.return_value = [True, False]
        ensure_service("inference", url="http://discovery-inference:8091")
    assert clock[0] == 30
