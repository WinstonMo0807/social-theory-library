import pytest
from types import SimpleNamespace
from unittest.mock import Mock

from accounts.models import User
from ingestion.models import ProcessingAttempt, UploadBatch, UploadItem
from ingestion.services.pipeline import processing_attempt, set_stage
from ingestion.tasks import _run_tracked
from ingestion.services.workflow import (
    InvalidWorkflowTransition,
    invalidate_downstream_attempts,
    transition_upload_item,
)


pytestmark = pytest.mark.django_db


def make_item():
    user = User.objects.create_user(
        username=f"workflow-{User.objects.count()}",
        email=f"workflow-{User.objects.count()}@example.test",
        password="safe-test-password",
    )
    batch = UploadBatch.objects.create(created_by=user)
    return UploadItem.objects.create(batch=batch, source_filename="example.pdf", processing_token="token")


def test_server_validates_workflow_transition_and_audits_it():
    item = make_item()

    result = transition_upload_item(item, UploadItem.WorkflowState.PREFLIGHT, reason="开始预检")

    assert result.changed is True
    item.refresh_from_db()
    assert item.workflow_state == UploadItem.WorkflowState.PREFLIGHT
    with pytest.raises(InvalidWorkflowTransition):
        transition_upload_item(item, UploadItem.WorkflowState.PUBLISHED)


def test_transition_is_idempotent_for_same_target():
    item = make_item()

    transition_upload_item(item, UploadItem.WorkflowState.PREFLIGHT)
    repeated = transition_upload_item(item, UploadItem.WorkflowState.PREFLIGHT)

    assert repeated.changed is False


def test_legacy_stage_updates_compatible_workflow_state():
    item = make_item()

    set_stage(item, UploadItem.Status.METADATA, 18)

    item.refresh_from_db()
    assert item.status == UploadItem.Status.METADATA
    assert item.workflow_state == UploadItem.WorkflowState.ENRICHING


def test_processing_attempt_reuses_completed_stage_and_skips_body_until_invalidated():
    item = make_item()
    executions = []

    with processing_attempt(item, "metadata") as attempt:
        if attempt.should_run:
            executions.append("first")
    with processing_attempt(item, "metadata") as attempt:
        if attempt.should_run:
            executions.append("second")

    assert ProcessingAttempt.objects.filter(upload_item=item, stage="metadata").count() == 1
    assert item.attempts.get(stage="metadata").status == "completed"
    assert executions == ["first"]

    invalidate_downstream_attempts(item, stages={"metadata"}, reason="候选发生变化")
    with processing_attempt(item, "metadata") as attempt:
        if attempt.should_run:
            executions.append("invalidated")
    assert executions == ["first", "invalidated"]


def test_dispatch_execution_guard_skips_completed_redelivery():
    item = make_item()
    item.dispatch_task_id = "celery-task-one"
    item.save(update_fields=["dispatch_task_id", "updated_at"])
    task = SimpleNamespace(
        request=SimpleNamespace(id="celery-task-one", hostname="test-worker"),
    )
    processor = Mock(return_value=item)

    first = _run_tracked(task, str(item.id), processor)
    repeated = _run_tracked(task, str(item.id), processor)

    assert first["status"] == item.status
    assert repeated["status"] == "already_completed"
    assert processor.call_count == 1
    execution = item.attempts.get(stage="task_execution")
    assert execution.status == "completed"
    assert execution.correlation_id == "celery-task-one"


def test_downstream_invalidation_is_explicit_and_repeat_safe():
    item = make_item()
    with processing_attempt(item, "metadata"):
        pass
    with processing_attempt(item, "indexing"):
        pass

    assert invalidate_downstream_attempts(item, stages={"indexing"}, reason="题名已变更") == 1
    assert invalidate_downstream_attempts(item, stages={"indexing"}, reason="题名已变更") == 0
