"""Synthetic Reader OCR regressions; authored for the unified acceptance run."""
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from accounts.models import User
from catalog.models import Asset, Edition, KnowledgePublicationEvent, Page, SiteSetting, Work
from distribution.reader_ocr import RECEIPT_ACTION
from ingestion.models import AuditEvent, ProcessingJob
from .v304_helpers import activate_catalog_revision


pytestmark = pytest.mark.django_db


@pytest.fixture
def reader_source():
    edition = Edition.objects.create(work=Work.objects.create(title="合成 Reader OCR 来源"), state="published")
    asset = Asset.objects.create(edition=edition, kind="normalized", status="ready", validation_status="valid",
        file="synthetic/reader-ocr-source.pdf", page_count=3, sha256="a" * 64, is_current=True)
    Page.objects.create(asset=asset, index=1, text="不应从进度接口返回的合成正文", text_source="embedded")
    activate_catalog_revision(edition, reader_asset=asset, fulltext_ready=False)
    return asset


def job_for(asset, *, status="pending", **overrides):
    stats = {"requested_mode": "selected_pages", "requested_asset_id": str(asset.pk),
             "source_sha256": asset.sha256, "source_page_count": asset.page_count,
             "target_pages": 2, "processed_pages": 1, "ocr_phase": "recognizing",
             "completed_page_indexes": [1], "requested_page_indexes": [1, 3],
             **overrides.pop("stats", {})}
    return ProcessingJob.objects.create(edition=asset.edition, asset=asset, job_type="ocr", status=status,
        stats=stats, task_id=str(uuid4()), **overrides)


def url(asset):
    return f"/api/distribution/assets/{asset.pk}/ocr-status/"


def command(asset, job, action="pause"):
    return {"action": action, "request_id": str(uuid4()), "job_id": str(job.pk),
            "job_version": job.updated_at.isoformat(), "source_sha256": asset.sha256,
            "document_revision_id": None}


def owner(user):
    return {"HTTP_X_READER_OWNER": str(user.pk)}


def post(api_client, user, asset, data):
    api_client.force_authenticate(user)
    return api_client.post(url(asset), data, format="json", **owner(user))


def test_scan_without_job_is_readable_without_fabricated_progress(api_client, reader_source):
    with patch("distribution.reader_ocr.task_command", side_effect=AssertionError("read must not mutate")):
        response = api_client.get(url(reader_source))
    assert response.status_code == 200
    assert response.data["job"] is None and response.data["document_revision_id"] is None
    assert response.data["owner_id"] is None and response.data["file_page_count"] == 3
    assert not response.data["can_pause"] and not response.data["can_resume"]
    assert response.data["processed_content"]["state"] == "unavailable"
    assert response.data["processed_content"]["url"] is None
    assert response["Cache-Control"] == "private, no-store"
    assert not AuditEvent.objects.filter(action=RECEIPT_ACTION).exists()


def test_public_status_is_allowlisted_and_uses_task_target_count(api_client, reader_source):
    job = job_for(reader_source, status="running", error_message="/private/path/provider-secret",
        stats={"provider": "provider-secret", "ocr_pdf_warning": "private warning", "ocr_phase": "unknown private phase"})
    response = api_client.get(url(reader_source))
    assert response.status_code == 200
    progress = response.data["job"]
    assert progress["id"] == str(job.pk) and progress["job_version"] == job.updated_at.isoformat()
    assert progress["completed_pages"] == 1 and progress["total_pages"] == 2 and progress["percent"] == 50
    assert progress["phase"] == "" and progress["phase_label"] == "正在处理"
    assert set(progress) == {"id", "job_version", "status", "phase", "phase_label", "completed_pages",
        "total_pages", "percent", "phase_elapsed_seconds", "updated_at", "pause_requested", "stale"}
    assert response.data["processed_content"]["state"] == "awaiting_publication"
    assert response.data["management_url"] is None and response.data["processed_content"]["url"] is None
    rendered = response.content.decode()
    assert all(value not in rendered for value in ["provider-secret", "/private/path", "private warning",
        "unknown private phase", "不应从进度接口返回的合成正文"])


@pytest.mark.parametrize("counts", [
    {"target_pages": None}, {"processed_pages": None}, {"target_pages": "2"},
    {"processed_pages": True}, {"target_pages": 0},
])
def test_unknown_or_invalid_counts_are_not_zero_or_complete(api_client, reader_source, counts):
    job_for(reader_source, stats=counts)
    progress = api_client.get(url(reader_source)).data["job"]
    assert progress["completed_pages"] is None and progress["total_pages"] is None and progress["percent"] is None


def test_jobs_of_another_file_cannot_replace_the_current_source_status(api_client, reader_source):
    expected = job_for(reader_source)
    other = Asset.objects.create(edition=reader_source.edition, kind="normalized", status="ready",
        validation_status="valid", file="synthetic/other.pdf", sha256="b" * 64, page_count=3, is_current=False)
    job_for(other, status="running")
    response = api_client.get(url(reader_source))
    assert response.data["job"]["id"] == str(expected.pk)


def test_changed_source_fingerprint_does_not_fall_back_to_an_older_task(api_client, reader_source):
    job_for(reader_source)
    job_for(reader_source, stats={"source_sha256": "c" * 64})
    assert api_client.get(url(reader_source)).data["job"] is None


@pytest.mark.parametrize("pages", [3, 4, "3", True])
def test_source_page_count_uses_saved_total_not_selected_target_count(api_client, reader_source, pages):
    job = job_for(reader_source)
    job.stats.pop("source_page_count")
    job.stats["total_pages"] = pages
    job.save(update_fields=["stats"])
    response = api_client.get(url(reader_source))
    assert response.status_code == 200
    if type(pages) is int and pages == 3:
        assert response.data["job"]["total_pages"] == 2
    else:
        assert response.data["job"] is None


@pytest.mark.parametrize("mode", ["anonymous", "reader", "editor", "missing_owner", "changed_owner"])
def test_command_requires_capabilities_and_fixed_owner(api_client, admin_user, reader_user, reader_source, mode):
    job = job_for(reader_source)
    user = None if mode == "anonymous" else reader_user if mode in {"reader", "editor"} else admin_user
    if mode == "editor":
        reader_user.role = "editor"
        reader_user.save(update_fields=["role"])
    api_client.force_authenticate(user)
    headers = {} if mode in {"anonymous", "missing_owner"} else owner(user)
    if mode == "changed_owner":
        headers["HTTP_X_READER_OWNER"] = str(reader_user.pk)
    response = api_client.post(url(reader_source), command(reader_source, job), format="json", **headers)
    assert response.status_code == 403
    job.refresh_from_db()
    assert job.status == "pending" and job.pause_requested_at is None
    assert not AuditEvent.objects.filter(action=RECEIPT_ACTION).exists()


def test_optional_owner_on_get_is_always_checked(api_client, admin_user, reader_user, reader_source):
    api_client.force_authenticate(admin_user)
    assert api_client.get(url(reader_source), **owner(reader_user)).status_code == 403
    response = api_client.get(url(reader_source), **owner(admin_user))
    assert response.status_code == 200 and response.data["owner_id"] == admin_user.pk


@pytest.mark.parametrize("status", ["pending", "running"])
def test_pause_uses_real_cooperative_task_state(api_client, admin_user, reader_source, status):
    job = job_for(reader_source, status=status)
    before = deepcopy(job.stats)
    response = post(api_client, admin_user, reader_source, command(reader_source, job))
    assert response.status_code == 200, response.data
    job.refresh_from_db()
    assert job.status == ("paused" if status == "pending" else "running")
    assert job.pause_requested_at is not None and job.stats == before
    assert response.data["job"]["pause_requested"] is (status == "running")
    assert not response.data["can_pause"]
    assert response.data["receipt"]["applied"] is True
    assert response.data["processed_content"]["state"] == "admin_preview"
    if status == "running":
        assert "当前页保存" in response.data["job"]["phase_label"]


def test_resume_reuses_checkpoint_and_dispatches_only_once(api_client, admin_user, reader_source,
        django_capture_on_commit_callbacks):
    job = job_for(reader_source, status="paused", pause_requested_at=timezone.now())
    data = command(reader_source, job, "resume")
    before = deepcopy(job.stats)
    with patch("ingestion.services.processing.dispatch_ocr_job") as dispatch, django_capture_on_commit_callbacks(execute=True):
        response = post(api_client, admin_user, reader_source, data)
        replay = post(api_client, admin_user, reader_source, deepcopy(data))
    assert response.status_code == replay.status_code == 200
    assert dispatch.call_count == 1
    job.refresh_from_db()
    assert job.status == "pending" and job.pause_requested_at is None and job.stats == before
    assert ProcessingJob.objects.filter(edition=reader_source.edition).count() == 1
    assert AuditEvent.objects.filter(action=RECEIPT_ACTION).count() == 1


def test_receipt_is_actor_bound_and_replay_cannot_pause_a_newer_job(api_client, admin_user, reader_source):
    job = job_for(reader_source)
    data = command(reader_source, job)
    api_client.force_authenticate(admin_user)
    unknown = api_client.get(url(reader_source), {"request_id": data["request_id"]}, **owner(admin_user))
    assert unknown.status_code == 200 and unknown.data["receipt"] is None
    saved = post(api_client, admin_user, reader_source, data)
    assert saved.status_code == 200
    newer = job_for(reader_source, status="running")
    receipt = api_client.get(url(reader_source), {"request_id": data["request_id"]}, **owner(admin_user))
    replay = post(api_client, admin_user, reader_source, deepcopy(data))
    assert receipt.status_code == replay.status_code == 200
    assert replay.data["receipt"]["job_id"] == str(job.pk) and replay.data["job"]["id"] == str(newer.pk)
    newer.refresh_from_db()
    assert newer.status == "running" and newer.pause_requested_at is None
    other = User.objects.create_user(username="other-ocr-admin@example.org", email="other-ocr-admin@example.org",
        role="admin", password="Synthetic-OCR-Admin-Password")
    api_client.force_authenticate(other)
    assert api_client.get(url(reader_source), {"request_id": data["request_id"]}, **owner(other)).data["receipt"] is None
    assert api_client.get(url(reader_source), {"request_id": data["request_id"]}).status_code == 403


def test_reused_nonce_with_different_command_is_rejected(api_client, admin_user, reader_source):
    job = job_for(reader_source)
    data = command(reader_source, job)
    assert post(api_client, admin_user, reader_source, data).status_code == 200
    assert post(api_client, admin_user, reader_source, {**data, "action": "resume"}).status_code == 409
    job.refresh_from_db()
    assert job.status == "paused" and AuditEvent.objects.filter(action=RECEIPT_ACTION).count() == 1


@pytest.mark.parametrize("changed", ["version", "sha", "revision", "job"])
def test_stale_identity_cannot_mutate_any_task(api_client, admin_user, reader_source, changed):
    job = job_for(reader_source)
    data = command(reader_source, job)
    if changed == "version":
        data["job_version"] = "old-version"
    elif changed == "sha":
        data["source_sha256"] = "b" * 64
    elif changed == "revision":
        data["document_revision_id"] = str(uuid4())
    else:
        job_for(reader_source)
    assert post(api_client, admin_user, reader_source, data).status_code == 409
    assert not ProcessingJob.objects.filter(edition=reader_source.edition, pause_requested_at__isnull=False).exists()
    assert not AuditEvent.objects.filter(action=RECEIPT_ACTION).exists()


def test_global_pause_and_legacy_jobs_are_not_resumed_from_reader(api_client, admin_user, reader_source):
    job = job_for(reader_source, status="paused")
    SiteSetting.objects.update_or_create(key="ocr_processing_paused", defaults={"value": True})
    response = post(api_client, admin_user, reader_source, command(reader_source, job, "resume"))
    assert response.status_code == 409
    SiteSetting.objects.update_or_create(key="ocr_processing_paused", defaults={"value": False})
    job.stats.pop("requested_mode")
    job.save(update_fields=["stats", "updated_at"])
    api_client.force_authenticate(admin_user)
    response = api_client.get(url(reader_source), **owner(admin_user))
    assert response.status_code == 200 and not response.data["can_resume"]
    assert response.data["management_url"] == f"/admin/library/assets/{reader_source.pk}/ocr"


@pytest.mark.parametrize("access", ["registered", "private", "restricted"])
def test_anonymous_status_does_not_bypass_source_access(api_client, reader_source, access):
    reader_source.access_status = access
    reader_source.save(update_fields=["access_status"])
    assert api_client.get(url(reader_source)).status_code in {401, 403}


def test_withdrawal_hides_status_and_blocks_old_commands(api_client, admin_user, reader_source):
    job = job_for(reader_source)
    data = command(reader_source, job)
    reader_source.edition.state = "withdrawn"
    reader_source.edition.save(update_fields=["state"])
    assert api_client.get(url(reader_source)).status_code == 404
    assert post(api_client, admin_user, reader_source, data).status_code == 404
    job.refresh_from_db()
    assert job.pause_requested_at is None


@pytest.mark.parametrize("corruption", [None, "source_hash", "stage_hash", "stage_key"])
def test_published_normalized_result_retains_exact_source_identity(api_client, reader_source, corruption):
    job = job_for(reader_source, status="succeeded")
    result = Asset.objects.create(edition=reader_source.edition, kind="normalized", status="ready",
        validation_status="valid", file=reader_source.file.name,
        sha256=("b" * 64 if corruption == "stage_hash" else reader_source.sha256),
        page_count=3, is_current=True, source_asset=reader_source,
        validation_details={"text_source_asset_id": str(reader_source.pk),
            "text_stage_key": f"ocr-job:{uuid4() if corruption == 'stage_key' else job.pk}"})
    reader_source.is_current = False
    if corruption == "source_hash":
        reader_source.sha256 = "c" * 64
    reader_source.save(update_fields=["is_current", "sha256"])
    Page.objects.create(asset=result, index=1, text="已经确认公开的合成识别结果", text_source="ocr")
    revision = activate_catalog_revision(reader_source.edition, reader_asset=result)
    event = KnowledgePublicationEvent.objects.create(event_type="catalog_updated", object_type="edition",
        object_id=reader_source.edition_id, catalog_revision=revision, idempotency_key=f"reader-ocr-test:{uuid4()}")
    job.asset = result
    job.stats = {**job.stats, "staging_asset_id": str(result.pk), "knowledge_publication_event_id": str(event.pk)}
    job.save(update_fields=["asset", "stats"])
    response = api_client.get(url(result))
    assert response.status_code == 200
    if corruption:
        assert response.data["job"] is None and response.data["processed_content"]["state"] == "unavailable"
    else:
        assert response.data["job"]["id"] == str(job.pk)
        assert response.data["source_sha256"] == result.sha256
        assert response.data["processed_content"]["state"] == "published"
        assert response.data["document_revision_id"] == str(revision.document_revision_id)
        assert response.data["processed_content"]["url"].startswith(f"/reader/{result.pk}?page=1&revision=")
    assert api_client.get(url(reader_source)).status_code == 404


def test_invalid_event_metadata_cannot_break_status(api_client, reader_source):
    job_for(reader_source, stats={"knowledge_publication_event_id": "invalid legacy id"})
    assert api_client.get(url(reader_source)).status_code == 200


def test_command_pins_the_actual_published_document_revision(api_client, admin_user, reader_source):
    revision = activate_catalog_revision(reader_source.edition, reader_asset=reader_source)
    job = job_for(reader_source)
    data = command(reader_source, job)
    assert post(api_client, admin_user, reader_source, data).status_code == 409
    data["document_revision_id"] = str(revision.document_revision_id)
    response = post(api_client, admin_user, reader_source, data)
    assert response.status_code == 200
    assert response.data["document_revision_id"] == str(revision.document_revision_id)
