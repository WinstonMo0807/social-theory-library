"""Deferred acceptance only; no backups are executed during implementation."""
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

import pytest
from django.utils import timezone

from distribution.database_backup import DatabaseDumpResult
from distribution.models import BackupJob
from distribution.storage_workspace import backup_stalled
from distribution.tasks import create_backup_archive
from ingestion.models import AuditEvent

pytestmark = pytest.mark.django_db


def test_stalled_backup_close_replays_and_rejects_live_or_changed_job(api_client, superadmin_user, settings):
    settings.CELERY_TASK_TIME_LIMIT = 3600
    job = BackupJob.objects.create(requested_by=superadmin_user, destination_path="unused", status="running",
                                  started_at=timezone.now() - timedelta(hours=2))
    api_client.force_authenticate(superadmin_user)
    headers = {"HTTP_X_EDITOR_OWNER": str(superadmin_user.pk)}
    body = {"operation": "close_stalled_backup", "backup_id": str(job.pk),
            "request_id": str(uuid4()), "expected_version": job.updated_at.isoformat()}
    url = "/api/distribution/storage/commands/"
    assert api_client.post(url, body, format="json", **headers).status_code == 200
    assert api_client.post(url, body, format="json", **headers).status_code == 200
    job.refresh_from_db()
    assert job.status == "failed"
    assert AuditEvent.objects.filter(action="storage_backup_closed", object_id=str(job.pk)).count() == 1
    body["request_id"] = str(uuid4())
    assert api_client.post(url, body, format="json", **headers).status_code == 409
    fresh = BackupJob.objects.create(requested_by=superadmin_user, destination_path="unused")
    body.update(backup_id=str(fresh.pk), expected_version=fresh.updated_at.isoformat(), request_id=str(uuid4()))
    assert api_client.post(url, body, format="json", **headers).status_code == 409
    settings.CELERY_TASK_TIME_LIMIT = None
    assert not backup_stalled(BackupJob(status="running", started_at=timezone.now() - timedelta(days=10)))


@pytest.mark.parametrize("late_phase", ["dump", "checksum"])
def test_late_delivery_does_not_resurrect_closed_backup_or_touch_existing_archive(
        settings, tmp_path, superadmin_user, monkeypatch, late_phase):
    settings.NAS_BACKUP_ROOT = tmp_path
    kept = tmp_path / "already-accepted.tar.gz"
    kept.write_bytes(b"unchanged prior archive")
    job = BackupJob.objects.create(requested_by=superadmin_user, destination_path=str(tmp_path))

    def close():
        BackupJob.objects.filter(pk=job.pk).update(status="failed", error_message="closed by operator",
                                                 completed_at=timezone.now(), updated_at=timezone.now())

    def dump(root):
        body = b"synthetic dump only"
        (root / "database.sql").write_bytes(body)
        if late_phase == "dump":
            close()
        return DatabaseDumpResult("database.sql", len(body), sha256(body).hexdigest(), {})

    def checksum(path):
        close()
        return sha256(path.read_bytes()).hexdigest()

    monkeypatch.setattr("distribution.tasks.create_database_dump", dump)
    monkeypatch.setattr("distribution.tasks.applied_migration_heads", lambda: [])
    if late_phase == "checksum":
        monkeypatch.setattr("distribution.tasks._sha256", checksum)
    assert create_backup_archive.run(str(job.pk)) is None
    job.refresh_from_db()
    assert job.status == "failed" and job.error_message == "closed by operator"
    assert not job.archive_path and not job.checksum
    assert kept.read_bytes() == b"unchanged prior archive"
    assert list(tmp_path.iterdir()) == [kept]
