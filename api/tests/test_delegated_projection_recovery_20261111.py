from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import ProjectionState, Work
from catalog.services.projection_refresh import reconcile_projection_runtime
from ingestion.models import ProcessingJob
from ingestion.services.processing import recover_stalled_processing_jobs

pytestmark = pytest.mark.django_db


def delegated_job(*, status="running", error_code="", semantic_status="delegated"):
    work = Work.objects.create(title="Delegated source recovery")
    job = ProcessingJob.objects.create(job_type="projection_refresh", status=status,
        attempt=3, max_attempts=3, error_code=error_code, progress=80,
        started_at=timezone.now() - timedelta(days=1),
        heartbeat_at=timezone.now() - timedelta(days=1),
        stats={"projection_results": {"public": {"status": "current"},
            "semantic": {"status": semantic_status}},
            "projection_plan": {"discovery_sources": [{"edition_id": str(work.pk)}],
                "semantic_source_revision": 1}})
    state = ProjectionState.objects.create(object_type="work", object_id=work.pk,
        projection_type="semantic", source_revision=1, projected_revision=0,
        status="projecting", lease_token=uuid4(),
        lease_expires_at=timezone.now() - timedelta(hours=1),
        task_owner_type="ProcessingJob", task_owner_key=str(job.pk))
    job.stats["projection_plan"]["semantic_state_id"] = str(state.pk)
    job.save(update_fields=["stats"])
    return job, state


def test_waiting_coordinator_keeps_attempt_budget(django_capture_on_commit_callbacks):
    job, _ = delegated_job()
    with patch("catalog.services.projection_refresh.reconcile_delegated_projection_job") as reconcile:
        with django_capture_on_commit_callbacks(execute=True):
            result = recover_stalled_processing_jobs(job_id=job.pk)
    job.refresh_from_db()
    assert job.status == "running" and job.attempt == 3
    assert result["requeued"] == result["exhausted"] == 0
    reconcile.assert_called_once_with(str(job.pk))


def test_real_coordinator_without_delegated_result_still_exhausts():
    job, _ = delegated_job(semantic_status="projecting")
    result = recover_stalled_processing_jobs(job_id=job.pk)
    job.refresh_from_db()
    assert job.status == "failed" and job.error_code == "max_attempts_exhausted"
    assert result["exhausted"] == 1


@pytest.mark.parametrize("verified,expected", [(True, "succeeded"), (False, "failed")])
def test_old_exhausted_parent_requires_verified_specialist_result(verified, expected):
    job, state = delegated_job(status="failed", error_code="max_attempts_exhausted")
    proof = {"status": "current" if verified else "delegated", "backend": "discovery"}
    with patch("catalog.services.projection_refresh._discovery_publication_result", return_value=proof), \
         patch("catalog.services.projection_refresh.dispatch_ready_projection_demands", return_value={"dispatched": 0}):
        reconcile_projection_runtime()
    job.refresh_from_db()
    state.refresh_from_db()
    assert job.status == expected and job.attempt == 3
    assert state.projected_revision == (1 if verified else 0)


def test_genuine_exhausted_failure_is_not_reopened():
    job, _ = delegated_job(status="failed", error_code="projection_partial_failure")
    with patch("catalog.services.projection_refresh._discovery_publication_result") as proof, \
         patch("catalog.services.projection_refresh.dispatch_ready_projection_demands", return_value={"dispatched": 0}):
        reconcile_projection_runtime()
    proof.assert_not_called()
    job.refresh_from_db()
    assert job.status == "failed" and job.attempt == 3
