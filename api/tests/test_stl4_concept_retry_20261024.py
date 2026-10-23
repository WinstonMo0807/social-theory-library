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


def test_retry_creates_one_stage_and_keeps_original_text(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    request = body(parent)
    with patch("ingestion.services.concept_retry.dispatch_concept_job"), patch("ingestion.services.processing.dispatch_ocr_job") as ocr:
        first = submit(api_client, admin_user, request)
        assert first.status_code == 202, first.data
        assert submit(api_client, admin_user, request).data == first.data
        child = ProcessingJob.objects.get(pk=first.data["result"]["job_id"])
        assert child.pk != parent.pk and child.stats["operation"] == "concept_alignment"
        result = {"enabled": True, "created": 1, "updated": 0, "new_node_tasks": 0, "protected_nodes": 2}
        with patch("catalog.services.theory_suggestions.generate_theory_review_tasks", return_value=result) as generate:
            assert run_concept_job(child.pk, task_id=child.task_id).status == "succeeded"
            assert run_concept_job(child.pk, task_id=child.task_id).status == "succeeded"
        generate.assert_called_once()
    ocr.assert_not_called()
    parent.refresh_from_db()
    assert parent.status == "succeeded" and parent.progress == 100 and parent.stats["completed_page_indexes"] == [1]
    assert parent.stats["concept_alignment"]["state"] == "completed" and "theory_suggestion_warning" not in parent.stats
    stages = api_client.get(URL, {"group_by": "file"}).data
    assert stages["count"] == 1 and len(stages["files"][0]["stages"]) == 2
    assert stages["counts"]["failed"] == 0


def test_cancel_and_retry_fence_old_delivery_and_changed_source(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.concept_retry.dispatch_concept_job"):
        created = submit(api_client, admin_user, body(parent))
        child = ProcessingJob.objects.get(pk=created.data["result"]["job_id"])
        old_task = child.task_id
        assert submit(api_client, admin_user, body(child, "cancel")).status_code == 202
        with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
            assert run_concept_job(child.pk, task_id=old_task).status == "canceled"
        generate.assert_not_called()
        child.refresh_from_db()
        assert submit(api_client, admin_user, {**body(child, "retry"), "page_indexes": [1]}).status_code == 400
        assert submit(api_client, admin_user, body(child, "retry")).status_code == 202
        child.refresh_from_db()
        assert child.task_id != old_task
        with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
            assert run_concept_job(child.pk, task_id=old_task).status == "pending"
        generate.assert_not_called()
        child.asset.sha256 = "f" * 64
        child.asset.save(update_fields=["sha256", "updated_at"])
        with patch("catalog.services.theory_suggestions.generate_theory_review_tasks") as generate:
            with pytest.raises(EditConflict): run_concept_job(child.pk, task_id=child.task_id)
        generate.assert_not_called()
        child.refresh_from_db()
        assert child.status == "failed"
        assert submit(api_client, admin_user, body(child, "retry")).status_code == 409


def test_concept_stage_uses_original_recovery_dispatch(api_client, admin_user, settings, tmp_path):
    from ingestion.services.processing import _dispatch_processing_job
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    with patch("ingestion.services.concept_retry.dispatch_concept_job", return_value=True) as dispatch:
        created = submit(api_client, admin_user, body(parent))
        child = ProcessingJob.objects.get(pk=created.data["result"]["job_id"])
        old_task = child.task_id
        child.status = "running"
        child.heartbeat_at = child.started_at = timezone.now() - timedelta(seconds=settings.INGESTION_STAGE_STALLED_SECONDS + 60)
        child.save()
        assert submit(api_client, admin_user, body(child, "recover")).status_code == 202
        child.refresh_from_db()
        assert child.status == "pending" and child.task_id != old_task
        assert _dispatch_processing_job(str(child.pk), child.job_type, child.task_id) is True
        dispatch.assert_called_with(str(child.pk), child.task_id)
    parent.refresh_from_db()
    assert parent.stats["completed_page_indexes"] == [1] and parent.status == "succeeded"


def test_stopped_intent_cannot_create_stage(api_client, admin_user, settings, tmp_path):
    parent = original(settings, tmp_path, admin_user)
    api_client.force_authenticate(admin_user)
    request = body(parent)
    stopped = api_client.post(f"{URL}commands/{request['request_id']}/", {"action": "cancel_pending"}, format="json", HTTP_X_EDITOR_OWNER=str(admin_user.pk))
    assert stopped.status_code == 200
    assert submit(api_client, admin_user, request).data["state"] == "cancelled"
    assert not ProcessingJob.objects.filter(stats__operation="concept_alignment").exists()
