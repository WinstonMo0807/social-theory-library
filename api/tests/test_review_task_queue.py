import pytest

from accounts.models import User
from catalog.models import DocumentType, Edition, Work
from ingestion.models import DecisionLog, ReviewTask, UploadBatch, UploadItem
from ingestion.services.reconciliation import persist_resolution_candidates


pytestmark = pytest.mark.django_db


def make_editor():
    return User.objects.create_user(
        username="review-queue-editor",
        email="review-queue-editor@example.test",
        role=User.Role.EDITOR,
        password="Review-Queue-2026",
    )


def make_item(admin_user):
    work = Work.objects.create(document_type=DocumentType.BOOK, title="审核任务示例")
    edition = Edition.objects.create(work=work)
    batch = UploadBatch.objects.create(created_by=admin_user)
    return UploadItem.objects.create(
        batch=batch,
        edition=edition,
        source_filename="review-task.pdf",
    )


def test_review_task_queue_filters_assigns_and_records_decision(api_client, admin_user):
    item = make_item(admin_user)
    task = ReviewTask.objects.create(
        upload_item=item,
        task_type="metadata_conflict",
        target_type="edition",
        target_id=str(item.edition_id),
        title="核对出版年份冲突",
        priority=3,
    )
    ReviewTask.objects.create(
        upload_item=item,
        task_type="page_labels",
        target_type="asset",
        title="核对页码",
        status=ReviewTask.Status.COMPLETED,
    )
    editor = make_editor()
    api_client.force_authenticate(editor)

    response = api_client.get("/api/ingestion/review-tasks/?status=pending")
    assert response.status_code == 200
    assert response.data["count"] == 1
    assert response.data["counts"]["pending"] == 1
    assert response.data["counts"]["completed"] == 1
    assert response.data["results"][0]["item_title"] == "审核任务示例"

    response = api_client.post(
        f"/api/ingestion/review-tasks/{task.id}/action/",
        {"action": "assign_self", "reason": "开始核对"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["task"]["status"] == ReviewTask.Status.IN_PROGRESS
    assert response.data["task"]["assigned_to"] == editor.id
    assert DecisionLog.objects.filter(review_task=task, action="review_task_assign_self").exists()

    response = api_client.post(
        f"/api/ingestion/review-tasks/{task.id}/action/",
        {"action": "complete", "reason": "已核对原书版权页"},
        format="json",
    )
    assert response.status_code == 200
    assert response.data["task"]["status"] == ReviewTask.Status.COMPLETED


def test_entity_resolution_task_cannot_be_completed_while_candidates_are_pending(
    api_client,
    admin_user,
):
    item = make_item(admin_user)
    persist_resolution_candidates(item, target_type="person", source_name="同名作者")
    task = item.review_tasks.get(task_type="entity_resolution")
    api_client.force_authenticate(make_editor())

    response = api_client.post(
        f"/api/ingestion/review-tasks/{task.id}/action/",
        {"action": "complete"},
        format="json",
    )

    assert response.status_code == 409
    assert "待判断候选" in response.data["detail"]
    task.refresh_from_db()
    assert task.status == ReviewTask.Status.PENDING


def test_reviewer_can_read_queue_but_cannot_change_task(api_client, admin_user):
    item = make_item(admin_user)
    task = ReviewTask.objects.create(
        upload_item=item,
        task_type="metadata_conflict",
        target_type="edition",
        title="只读任务",
    )
    reviewer = User.objects.create_user(
        username="review-queue-reviewer",
        email="review-queue-reviewer@example.test",
        role=User.Role.REVIEWER,
        password="Reviewer-Queue-2026",
    )
    api_client.force_authenticate(reviewer)

    assert api_client.get("/api/ingestion/review-tasks/").status_code == 200
    assert api_client.post(
        f"/api/ingestion/review-tasks/{task.id}/action/",
        {"action": "start"},
        format="json",
    ).status_code == 403
