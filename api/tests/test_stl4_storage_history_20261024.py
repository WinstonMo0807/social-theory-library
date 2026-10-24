"""Deferred pagination and permission acceptance; never run during implementation."""
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from distribution.models import BackupJob, BackupVerification

pytestmark = pytest.mark.django_db
URL = "/api/distribution/storage/verifications/"


def test_complete_verification_history_pages_filters_and_never_dispatches(superadmin_user):
    client = APIClient(); client.force_authenticate(user=superadmin_user)
    client.credentials(HTTP_X_EDITOR_OWNER=str(superadmin_user.pk))
    first_backup = BackupJob.objects.create(requested_by=superadmin_user, destination_path="never-used")
    second_backup = BackupJob.objects.create(requested_by=superadmin_user, destination_path="never-used")
    BackupVerification.objects.bulk_create([BackupVerification(backup=first_backup, requested_by=superadmin_user,
        expected_checksum="a"*64, status="failed", error_message="合成失败说明") for _ in range(35)])
    BackupVerification.objects.create(backup=second_backup, requested_by=superadmin_user, expected_checksum="b"*64)
    with patch("distribution.storage_tasks.enqueue_verification", side_effect=AssertionError("GET must not dispatch")):
        first = client.get(URL)
        assert first.status_code == 200 and first.data["count"] == 36 and len(first.data["results"]) == 20
        added = BackupVerification.objects.create(backup=first_backup, requested_by=superadmin_user, expected_checksum="c"*64)
        second = client.get(URL, {"page": 2, "as_of": first.data["as_of"]})
        assert second.data["count"] == 36 and len(second.data["results"]) == 16
        assert not set(row["id"] for row in first.data["results"]) & set(row["id"] for row in second.data["results"])
        assert str(added.pk) not in {row["id"] for row in second.data["results"]}
        scoped = client.get(URL, {"backup_id": str(first_backup.pk), "status": "failed"})
        assert scoped.data["count"] == 35
        assert {str(row["backup_id"]) for row in scoped.data["results"]} == {str(first_backup.pk)}
        assert first["Cache-Control"] == "private, no-store"


def test_history_rejects_duplicate_future_unknown_and_inaccessible_queries(superadmin_user):
    client = APIClient(); client.force_authenticate(user=superadmin_user)
    assert client.get(URL+"?page=1&page=2").status_code == 400
    assert client.get(URL, {"page": 2}).status_code == 400
    assert client.get(URL, {"as_of": (timezone.now()+timedelta(days=1)).isoformat()}).status_code == 400
    assert client.get(URL, {"unexpected": "value"}).status_code == 400
    assert client.get(URL, HTTP_X_EDITOR_OWNER="different-owner").status_code == 403
    assert APIClient().get(URL).status_code in (401,403)


def test_backup_page_keeps_creation_boundary_without_reading_storage(superadmin_user):
    from distribution.storage_workspace import storage_snapshot
    BackupJob.objects.bulk_create([BackupJob(requested_by=superadmin_user,destination_path="unused") for _ in range(25)])
    with patch("distribution.storage_workspace._location", return_value={}), patch("distribution.storage_workspace.restore_reports", return_value=([], False)):
        first = storage_snapshot(superadmin_user)
        added = BackupJob.objects.create(requested_by=superadmin_user,destination_path="unused")
        second = storage_snapshot(superadmin_user, page=2, as_of=first["backups"]["as_of"])
    assert first["backups"]["count"] == second["backups"]["count"] == 25
    assert len(second["backups"]["results"]) == 5
    assert str(added.pk) not in {row["id"] for row in second["backups"]["results"]}
