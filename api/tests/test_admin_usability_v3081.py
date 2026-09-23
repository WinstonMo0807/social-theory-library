"""User-facing recovery, independent cover save and async identity boundaries."""
from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch

import pytest
from django.utils import timezone
from catalog.models import (Work, Edition, Person, ScholarProfile, Topic, RecycleEntry,
                            TheoryTimelineEvent, Contribution)
from catalog.services.recycle import recycle_object, restore_object
from catalog.services.admin_queue_query import edition_inventory
from ingestion.models import UploadBatch, UploadItem, ProcessingJob, AuditEvent
from ingestion.services.processing import recover_stalled_processing_jobs
from .test_resilient_publication_v260 import create_item_with_files
from .test_cover_workbench_v306 import cover_source, call
from .test_media_v305 import picture

pytestmark = pytest.mark.django_db


def test_bad_upload_leaves_todo_but_preserves_original_and_can_restore(settings, tmp_path, admin_user):
    work, edition, original, _ = create_item_with_files(settings, tmp_path)
    batch = UploadBatch.objects.create(created_by=admin_user)
    item = UploadItem.objects.create(batch=batch, edition=edition, source_filename="bad.pdf", status="failed",
                                     error_code="index_error", error_message="original failure")
    job = ProcessingJob.objects.create(edition=edition, upload_item=item, job_type="ocr", status="running", task_id="old-claim")
    assert edition_inventory().filter(pk=edition.pk).exists()
    entry = recycle_object(item, actor=admin_user, kind="upload", name=item.source_filename)
    assert not UploadItem.objects.filter(pk=item.pk).exists()
    assert not edition_inventory().filter(pk=edition.pk).exists()
    assert Edition.objects.filter(pk=edition.pk).exists()
    assert Work.objects.filter(pk=work.pk).exists()
    job.refresh_from_db()
    assert job.status == "canceled" and not job.task_id
    assert original.file.storage.exists(original.file.name)
    restored = restore_object(entry.pk, actor=admin_user)
    assert restored.status == "failed" and restored.error_message == "original failure"
    assert edition_inventory().filter(pk=edition.pk).exists()
    assert job.status == "canceled"
    assert AuditEvent.objects.filter(action="record.restore").count() == 1


def test_deleted_work_hides_children_without_erasing_history(settings, tmp_path, admin_user):
    work, edition, original, _ = create_item_with_files(settings, tmp_path)
    entry = recycle_object(work, actor=admin_user, kind="work", name=work.title)
    assert not Edition.objects.filter(pk=edition.pk).exists()
    assert Edition.all_objects.filter(pk=edition.pk).exists()
    assert Edition._base_manager.get(pk=edition.pk).work.pk == work.pk
    assert original.file.storage.exists(original.file.name)
    restore_object(entry.pk, actor=admin_user)
    assert Edition.objects.filter(pk=edition.pk).exists()


@pytest.mark.parametrize("kind", ["topic", "timeline-event"])
def test_public_knowledge_delete_withdraws_and_restore_never_republishes(admin_user, kind):
    obj = Topic.objects.create(name="测试主题", slug="topic-delete", editorial_status="published") if kind == "topic" else TheoryTimelineEvent.objects.create(title="已确认事件", event_type="publication", review_status="approved")
    entry = recycle_object(obj, actor=admin_user, kind=kind, name="测试")
    assert not type(obj).objects.filter(pk=obj.pk).exists()
    assert type(obj).all_objects.filter(pk=obj.pk).exists()
    restored = restore_object(entry.pk, actor=admin_user)
    assert getattr(restored, "editorial_status", None) != "published"
    assert getattr(restored, "review_status", None) != "approved"


def test_person_identity_with_contribution_is_protected_but_scholar_display_can_be_deleted(admin_user):
    from rest_framework.exceptions import ValidationError
    person = Person.objects.create(preferred_name="郑作彧")
    scholar = ScholarProfile.objects.create(person=person, slug="person-delete")
    work = Work.objects.create(title="测试")
    edition = Edition.objects.create(work=work)
    contribution = Contribution.objects.create(person=person, edition=edition, role="translator")
    with pytest.raises(ValidationError):
        recycle_object(person, actor=admin_user, kind="person", name=person.preferred_name)
    entry = recycle_object(scholar, actor=admin_user, kind="scholar", name=person.preferred_name)
    assert Contribution.objects.get(pk=contribution.pk).person_id == person.pk
    assert Person.objects.filter(pk=person.pk).exists()
    assert restore_object(entry.pk, actor=admin_user).person_id == person.pk


def test_recycle_api_rejects_reader_and_malformed_ids(api_client, reader_user, admin_user):
    api_client.force_authenticate(reader_user)
    assert api_client.get("/api/catalog/admin/recycle/").status_code == 403
    assert api_client.post("/api/catalog/admin/recycle/", {"id": str(uuid4())}).status_code == 403
    api_client.force_authenticate(admin_user)
    assert api_client.post("/api/catalog/admin/recycle/", {"id": "broken"}).status_code == 400


@pytest.mark.parametrize("role", ["author", "translator"])
def test_person_creation_replay_returns_same_person_without_linking_until_save(api_client, admin_user, role):
    work = Work.objects.create(title="作者回执")
    edition = Edition.objects.create(work=work)
    api_client.force_authenticate(admin_user)
    data = {"edition_id": str(edition.pk), "field_name": role, "label": "待确认人物", "defer_link": True, "request_id": str(uuid4())}
    first = api_client.post("/api/catalog/admin/field-assistant/create/", data, format="json")
    again = api_client.post("/api/catalog/admin/field-assistant/create/", data, format="json")
    assert first.status_code < 300, first.data
    assert again.status_code < 300, again.data
    assert first.data["entity"]["id"] == again.data["entity"]["id"]
    assert Person.objects.filter(preferred_name=data["label"]).count() == 1
    assert not Contribution.objects.filter(edition=edition).exists()
    conflict = api_client.post("/api/catalog/admin/field-assistant/create/", {**data, "label": "另一人物"}, format="json")
    assert conflict.status_code in (400, 409)
    assert not Person.objects.filter(preferred_name="另一人物").exists()


def test_cover_save_survives_unrelated_metadata_save_and_still_detects_actual_cover_change(api_client, admin_user, cover_source):
    work, edition, _ = cover_source
    api_client.force_authenticate(admin_user)
    url = f"/api/catalog/admin/editions/{edition.pk}/cover/"
    snapshot = api_client.get(url).data
    work.title = "新书名"; work.save()
    assert api_client.get(url).data["fingerprint"] == snapshot["fingerprint"]
    result = call(api_client, edition, "upload", snapshot=snapshot, image=picture())
    assert result.status_code == 200, result.data
    assert result.data["fingerprint"] != snapshot["fingerprint"]
    stale = call(api_client, edition, "default", snapshot=snapshot)
    assert stale.status_code == 409


def test_live_heartbeat_prevents_recovery_but_dead_worker_recovers(admin_user, django_capture_on_commit_callbacks):
    old = timezone.now() - timedelta(hours=3)
    live = ProcessingJob.objects.create(job_type="ocr", status="running", task_id="live", started_at=old, heartbeat_at=timezone.now(), attempt=1)
    dead = ProcessingJob.objects.create(job_type="ocr", status="running", task_id="dead", started_at=old, heartbeat_at=old, attempt=1)
    with patch("ingestion.services.processing._dispatch_processing_job") as dispatch, django_capture_on_commit_callbacks(execute=True):
        counts = recover_stalled_processing_jobs()
    live.refresh_from_db(); dead.refresh_from_db()
    assert live.status == "running" and live.task_id == "live"
    assert dead.status == "pending" and dead.task_id != "dead"
    assert counts["requeued"] == 1 and dispatch.call_count == 1


def test_long_queue_keeps_claim_identity_and_retry_budget(django_capture_on_commit_callbacks):
    job = ProcessingJob.objects.create(job_type="ocr", status="pending", task_id="same-wakeup", attempt=2)
    ProcessingJob.objects.filter(pk=job.pk).update(updated_at=timezone.now() - timedelta(hours=3))
    with patch("ingestion.services.processing._dispatch_processing_job") as dispatch, django_capture_on_commit_callbacks(execute=True):
        recover_stalled_processing_jobs()
    job.refresh_from_db()
    assert job.task_id == "same-wakeup" and job.attempt == 2 and job.status == "pending"
    assert dispatch.call_args.args[-1] == "same-wakeup"


def test_restored_recommendation_requires_new_issue_publication(admin_user):
    from catalog.services import editorial_issues as service
    from .test_v307_editorial_issues import issue_data
    issue = service.create_issue(issue_data(), admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    item = issue.items.get()
    assert len(service.issue_payload(issue, public=True)["items"]) == 1
    entry = recycle_object(item, actor=admin_user, kind="recommendation-item", name="测试推荐")
    assert service.issue_payload(issue, public=True)["items"] == []
    restore_object(entry.pk, actor=admin_user)
    assert service.issue_payload(issue, public=True)["items"] == []
    payload = service.issue_payload(issue)
    assert len(payload["items"]) == 1
    service.save_issue(issue.pk, payload, admin_user)
    service.publish_issue(issue.pk, service.issue_payload(issue)["edit_version"], admin_user)
    issue.refresh_from_db()
    assert len(service.issue_payload(issue, public=True)["items"]) == 1


def test_old_site_draft_cannot_recreate_deleted_module(admin_user):
    from catalog.models import AboutPageBlock
    from catalog.services import editorial_issues as service
    from rest_framework.exceptions import ValidationError
    block = AboutPageBlock.objects.create(key="test-block", block_type="intro", title="测试说明", visible=False)
    payload = service.site_payload()
    recycle_object(block, actor=admin_user, kind="about-block", name=block.title)
    # Refresh just the concurrency token; the old deleted block is still in this input.
    payload["edit_version"] = service.site_payload()["edit_version"]
    with pytest.raises(ValidationError, match="回收站"):
        service.save_site(payload, admin_user)
    assert AboutPageBlock.all_objects.filter(pk=block.pk).exists()
    assert not AboutPageBlock.objects.filter(pk=block.pk).exists()
