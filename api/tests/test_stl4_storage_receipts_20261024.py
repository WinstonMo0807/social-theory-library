"""Deferred acceptance definitions; do not run during implementation."""
from uuid import uuid4
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from distribution.models import BackupJob, BackupVerification
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db
URL = "/api/distribution/storage/commands/"


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    client.credentials(HTTP_X_EDITOR_OWNER=str(user.pk))
    return client


def test_receipt_is_read_only_and_cancellation_cannot_undo_applied_backup(superadmin_user, settings, tmp_path):
    settings.NAS_BACKUP_ROOT = tmp_path
    client = client_for(superadmin_user)
    key = str(uuid4())
    body = {"operation": "create_backup", "request_id": key, "include_originals": False}
    with patch("distribution.storage_tasks.enqueue_authorized_backup"):
        first = client.post(URL, body, format="json")
        assert first.status_code == 200
        assert client.post(URL, body, format="json").data == first.data
        read = client.get(f"{URL}{key}/")
        assert read.status_code == 200 and read.data["result"]["backup"]["id"] == key
        assert read.data["result"]["operation"] == "create_backup"
        assert read["Cache-Control"] == "private, no-store"
        stopped = client.post(f"{URL}{key}/", {"action": "cancel_pending"}, format="json")
        assert stopped.data["state"] == "applied"
        assert BackupJob.objects.filter(pk=key).count() == 1
        changed = {**body, "retry_from_id": str(uuid4())}
        assert client.post(URL, changed, format="json").status_code == 409
        assert client.post(URL, {"operation": "save_schedule", "request_id": key, "scope": "database",
            "enabled": False, "interval_hours": 24, "expected_version": "unconfigured"}, format="json").status_code == 409


def test_missing_lookup_does_not_create_or_resubmit_and_cancel_blocks_late_delivery(superadmin_user):
    client = client_for(superadmin_user)
    key = str(uuid4())
    assert client.get(f"{URL}{key}/").status_code == 404
    assert not AuditEvent.objects.filter(pk=key).exists()
    with patch("distribution.storage_tasks.enqueue_authorized_backup", side_effect=AssertionError("No late dispatch")):
        response = client.post(f"{URL}{key}/", {"action": "cancel_pending"}, format="json")
        assert response.status_code == 200 and response.data["state"] == "cancelled"
        assert client.post(URL, {"operation": "create_backup", "request_id": key, "include_originals": True}, format="json").status_code == 409
        assert not BackupJob.objects.filter(pk=key).exists()
        assert client.post(f"{URL}{key}/", {"action": "cancel_pending"}, format="json").data == response.data


def test_legacy_verification_recovers_without_rechecking_changed_backup(superadmin_user):
    client = client_for(superadmin_user)
    backup = BackupJob.objects.create(requested_by=superadmin_user, destination_path="unused", status="failed", checksum="a" * 64)
    check = BackupVerification.objects.create(backup=backup, requested_by=superadmin_user, expected_checksum="b" * 64, status="failed")
    key = str(check.pk)
    with patch("distribution.storage_tasks.enqueue_verification", side_effect=AssertionError("Do not resubmit")):
        read = client.get(f"{URL}{key}/")
        assert read.status_code == 200 and read.data["legacy"]
        assert read.data["result"]["verification"]["id"] == key
        body = {"operation": "verify_archive", "request_id": key, "backup_id": str(backup.pk), "expected_checksum": "b" * 64}
        assert client.post(URL, body, format="json").status_code == 200
        assert client.post(URL, {**body, "expected_checksum": "a" * 64}, format="json").status_code == 409
        assert BackupVerification.objects.count() == 1


def test_receipt_owner_permissions_and_cancel_fields(superadmin_user, admin_user):
    key = str(uuid4())
    client = client_for(superadmin_user)
    assert client.post(f"{URL}{key}/", {"action": "cancel_pending", "backup_id": str(uuid4())}, format="json").status_code == 400
    assert client.get(f"{URL}{key}/", HTTP_X_EDITOR_OWNER="different-owner").status_code == 403
    assert client_for(admin_user).get(f"{URL}{key}/").status_code == 403
    assert APIClient().get(f"{URL}{key}/").status_code in (401, 403)
