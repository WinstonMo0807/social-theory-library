"""Deferred acceptance: concept retries must never schedule another OCR pass."""
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.services.editorial_issues import EditConflict
from ingestion.models import ProcessingJob
from ingestion.services.concept_retry import run_concept_job
from ingestion.services.processing_commands import task_version
from .test_resilient_publication_v260 import create_item_with_files

pytestmark = pytest.mark.django_db
URL = "/api/ingestion/processing-workspace/"


def original(settings, tmp_path, actor):
    _, edition, _, asset = create_item_with_files(settings, tmp_path)
    return ProcessingJob.objects.create(job_type="ocr", status="succeeded", edition=edition, asset=asset,
        created_by=actor, task_id=str(uuid4()), progress=100,
        stats={"source_sha256": asset.sha256, "completed_page_indexes": [1], "concept_alignment": {"state": "failed"},
               "theory_suggestion_warning": "original failure"})


def body(job, action="retry_followup"):
    return {"action": action, "source": "processing_job", "job_id": str(job.pk), "request_id": str(uuid4()), "expected_version": task_version(job)}


def submit(api_client, actor, payload):
    return api_client.post(URL, payload, format="json", HTTP_X_EDITOR_OWNER=str(actor.pk))


def legacy_child(parent):
    return ProcessingJob.objects.create(job_type="text_extraction", asset=parent.asset, edition=parent.edition,
        created_by=parent.created_by, task_id=str(uuid4()), stats={"operation":"concept_alignment", "ocr_job_id":str(parent.pk)})


def test_old_retry_is_retired_and_keeps_original_text(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.processing.dispatch_ocr_job") as ocr, patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
        assert submit(api_client, admin_user, body(parent)).status_code == 409
    ocr.assert_not_called(); generate.assert_not_called()
    parent.refresh_from_db()
    assert parent.status == "succeeded" and parent.progress == 100 and parent.stats["completed_page_indexes"] == [1]
    assert not ProcessingJob.objects.filter(stats__operation="concept_alignment").exists()


def test_old_delivery_cancels_only_its_legacy_task_and_preserves_source(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    child = legacy_child(parent)
    old_task = child.task_id
    with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
        assert run_concept_job(child.pk, task_id=str(uuid4())).status == "pending"
        assert run_concept_job(child.pk, task_id=old_task).status == "canceled"
        assert run_concept_job(child.pk, task_id=old_task).status == "canceled"
    generate.assert_not_called()
    api_client.force_authenticate(admin_user)
    child.refresh_from_db()
    assert child.error_code == "knowledge_producer_retired"
    assert submit(api_client, admin_user, body(child, "retry")).status_code == 409
    parent.refresh_from_db()
    assert parent.status == "succeeded" and parent.stats["completed_page_indexes"] == [1]


def test_original_recovery_dispatch_cannot_revive_retired_producer(api_client, admin_user, settings, tmp_path):
    from ingestion.services.processing import _dispatch_processing_job
    from ingestion.services.processing_recovery import recovery_state
    from catalog.services.knowledge_retirement import cancel_legacy_processing_batch
    parent = original(settings, tmp_path, admin_user)
    child = legacy_child(parent)
    child.status = "running"
    child.heartbeat_at = child.started_at = timezone.now() - timedelta(seconds=settings.INGESTION_STAGE_STALLED_SECONDS + 60)
    child.save()
    assert not recovery_state(child)["can_recover"]
    api_client.force_authenticate(admin_user)
    assert submit(api_client, admin_user, body(child, "recover")).status_code == 409
    assert not _dispatch_processing_job(str(child.pk), child.job_type, child.task_id)
    another = legacy_child(parent)
    projection = ProcessingJob.objects.create(job_type="discovery_index", edition=parent.edition, status="pending")
    assert cancel_legacy_processing_batch() == 1
    another.refresh_from_db(); projection.refresh_from_db(); parent.refresh_from_db()
    assert another.status == "canceled" and projection.status == "pending"
    assert parent.stats["completed_page_indexes"] == [1] and parent.status == "succeeded"


def test_stopped_intent_cannot_create_stage(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    request = body(parent)
    stopped = api_client.post(f"{URL}commands/{request['request_id']}/", {"action": "cancel_pending"}, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert stopped.status_code == 200
    assert submit(api_client, admin_user, request).data["state"] == "cancelled"
    assert not ProcessingJob.objects.filter(stats__operation="concept_alignment").exists()
