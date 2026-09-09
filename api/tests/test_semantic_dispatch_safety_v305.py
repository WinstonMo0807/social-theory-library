from unittest.mock import patch
from uuid import uuid4

import pytest

from catalog.models import Edition, SemanticIndexJob, SemanticIndexVersion
from catalog.services.semantic_indexing import dispatch_semantic_job
from .test_resilient_publication_v260 import create_item_with_files


pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("version_status", ["active", "retired", "building", "ready"])
def test_queue_failure_preserves_retained_indexes_but_fails_unfinished_candidate(settings, tmp_path, version_status):
    _work, edition, _original, asset = create_item_with_files(settings, tmp_path)
    version = SemanticIndexVersion.objects.create(
        uid=f"queue-safety-{uuid4()}", status=version_status, provider="huggingFace", model_repo_id="test-model", document_count=42,
    )
    previous = SemanticIndexVersion.objects.filter(pk=version.pk).values().get()
    task_id = str(uuid4())
    job = SemanticIndexJob.objects.create(asset=asset, index_version=version, operation="build", status="queued", task_id=task_id)
    with patch("catalog.tasks.build_semantic_index.apply_async", side_effect=ConnectionError("test broker unavailable")):
        assert dispatch_semantic_job(str(job.pk), task_id) is False
    version.refresh_from_db()
    job.refresh_from_db()
    edition.refresh_from_db()
    assert job.status == "failed" and job.error_code == "queue_unavailable"
    assert "test broker unavailable" in job.error_message
    assert edition.semantic_index_status == "failed"
    assert version.status == (version_status if version_status in {"active", "retired"} else "failed")
    assert version.document_count == 42
    if version_status in {"active", "retired"}:
        assert SemanticIndexVersion.objects.filter(pk=version.pk).values().get() == previous


@pytest.mark.parametrize("successor", ["completed", "requeued"])
def test_late_dispatch_error_cannot_overwrite_a_worker_or_new_task_owner(settings, tmp_path, successor):
    _work, edition, _original, asset = create_item_with_files(settings, tmp_path)
    version = SemanticIndexVersion.objects.create(uid=f"ack-safety-{uuid4()}", status="building", provider="huggingFace")
    task_id = str(uuid4())
    job = SemanticIndexJob.objects.create(asset=asset, index_version=version, operation="build", status="queued", task_id=task_id)
    next_task_id = str(uuid4()) if successor == "requeued" else task_id

    def delivered_then_disconnected(*args, **kwargs):
        SemanticIndexJob.objects.filter(pk=job.pk).update(
            status="completed" if successor == "completed" else "queued", task_id=next_task_id,
        )
        Edition.objects.filter(pk=edition.pk).update(semantic_index_status="ready")
        SemanticIndexVersion.objects.filter(pk=version.pk).update(status="ready")
        raise ConnectionError("late broker acknowledgement failure")

    with patch("catalog.tasks.build_semantic_index.apply_async", side_effect=delivered_then_disconnected):
        assert dispatch_semantic_job(str(job.pk), task_id) is False
    job.refresh_from_db()
    edition.refresh_from_db()
    version.refresh_from_db()
    assert job.status == ("completed" if successor == "completed" else "queued")
    assert job.task_id == next_task_id and job.error_code == ""
    assert edition.semantic_index_status == "ready" and version.status == "ready"
