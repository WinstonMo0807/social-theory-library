from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import tarfile

import pytest

from distribution.database_backup import (
    DatabaseBackupError,
    DatabaseDumpResult,
    PostgresCompatibilityError,
    create_database_dump,
    inspect_postgres_backup_runtime,
    postgres_tool_version,
    restore_database_dump,
)
from distribution.models import BackupJob
from distribution.tasks import create_backup_archive


pytestmark = pytest.mark.django_db


class FakePostgresConnection:
    vendor = "postgresql"

    def __init__(self, *, password="backup-secret"):
        self.settings_dict = {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": "postgres",
            "PORT": "5432",
            "USER": "library",
            "PASSWORD": password,
            "NAME": "library",
        }
        self.closed = False

    def close(self):
        self.closed = True


def test_backup_runtime_accepts_postgresql_16_clients(monkeypatch):
    monkeypatch.setattr(
        "distribution.database_backup.postgres_server_version",
        lambda database_connection: {"version": "16.14", "major": 16},
    )
    versions = {
        "pg_dump": {"version": "16.10", "major": 16, "raw": "pg_dump 16.10"},
        "pg_restore": {"version": "17.6", "major": 17, "raw": "pg_restore 17.6"},
    }
    monkeypatch.setattr(
        "distribution.database_backup.postgres_tool_version",
        lambda executable, *, tool_name: versions[tool_name],
    )

    result = inspect_postgres_backup_runtime(FakePostgresConnection())

    assert result["server_version"] == "16.14"
    assert result["pg_dump_major"] == 16
    assert result["pg_restore_major"] == 17


@pytest.mark.parametrize("older_tool", ["pg_dump", "pg_restore"])
def test_backup_runtime_rejects_client_older_than_server(monkeypatch, older_tool):
    monkeypatch.setattr(
        "distribution.database_backup.postgres_server_version",
        lambda database_connection: {"version": "16.14", "major": 16},
    )

    def version(executable, *, tool_name):
        major = 15 if tool_name == older_tool else 16
        return {"version": f"{major}.18", "major": major, "raw": tool_name}

    monkeypatch.setattr(
        "distribution.database_backup.postgres_tool_version",
        version,
    )

    with pytest.raises(PostgresCompatibilityError, match=older_tool):
        inspect_postgres_backup_runtime(FakePostgresConnection())


def test_missing_pg_dump_executable_has_explicit_error(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr("distribution.database_backup.subprocess.run", missing)

    with pytest.raises(DatabaseBackupError, match="pg_dump executable missing"):
        postgres_tool_version("pg_dump", tool_name="pg_dump")


def test_pg_dump_failure_redacts_password_and_removes_partial_artifact(tmp_path, monkeypatch):
    password = "do-not-log-this-password"
    fake_connection = FakePostgresConnection(password=password)
    monkeypatch.setattr(
        "distribution.database_backup.inspect_postgres_backup_runtime",
        lambda database_connection: {
            "server_version": "16.14",
            "server_major": 16,
            "pg_dump_version": "16.10",
            "pg_dump_major": 16,
            "pg_restore_version": "16.10",
            "pg_restore_major": 16,
        },
    )

    def failed(command, **kwargs):
        target = Path(command[command.index("--file") + 1])
        target.write_bytes(b"partial")
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=(
                f"PGPASSWORD={password} "
                f"postgresql://library:{password}@postgres:5432/library failed"
            ),
        )

    monkeypatch.setattr("distribution.database_backup.subprocess.run", failed)

    with pytest.raises(DatabaseBackupError) as exc_info:
        create_database_dump(tmp_path, fake_connection)

    message = str(exc_info.value)
    assert password not in message
    assert "[redacted]" in message
    assert not (tmp_path / "database.dump").exists()


def test_pg_restore_failure_is_reported_and_redacted(tmp_path, monkeypatch):
    password = "restore-secret-value"
    dump = tmp_path / "database.dump"
    dump.write_bytes(b"dump")
    fake_connection = FakePostgresConnection(password=password)
    monkeypatch.setattr(
        "distribution.database_backup.inspect_postgres_restore_runtime",
        lambda database_connection, dump_client_major=None: {
            "server_version": "16.14",
            "server_major": 16,
            "pg_restore_version": "16.10",
            "pg_restore_major": 16,
        },
    )
    monkeypatch.setattr(
        "distribution.database_backup.subprocess.run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=f"PGPASSWORD={password} restore rejected",
        ),
    )

    with pytest.raises(DatabaseBackupError) as exc_info:
        restore_database_dump(dump, fake_connection, dump_client_major=16)

    assert password not in str(exc_info.value)
    assert "[redacted]" in str(exc_info.value)
    assert fake_connection.closed is True


def _create_job(django_user_model, destination: Path) -> BackupJob:
    user = django_user_model.objects.create_user(
        username="backup-test",
        email="backup-test@example.com",
        password="test-only-password",
    )
    return BackupJob.objects.create(
        requested_by=user,
        destination_path=str(destination),
        include_originals=False,
    )


def _fake_dump(destination: Path) -> DatabaseDumpResult:
    dump = destination / "database.dump"
    dump.write_bytes(b"postgres-custom-dump")
    return DatabaseDumpResult(
        filename=dump.name,
        byte_size=dump.stat().st_size,
        sha256="19b16b5d293c5a21d6df4b7762a9192a6e57188dd4b4e6b666fad07c883410a4",
        metadata={
            "engine": "postgresql",
            "server_version": "16.14",
            "server_major": 16,
            "pg_dump_version": "16.10",
            "pg_dump_major": 16,
            "pg_restore_version": "16.10",
            "pg_restore_major": 16,
        },
    )


def test_backup_job_records_runtime_manifest_and_checksum(
    tmp_path,
    settings,
    monkeypatch,
    django_user_model,
):
    settings.NAS_BACKUP_ROOT = tmp_path
    destination = tmp_path / "formal"
    job = _create_job(django_user_model, destination)
    monkeypatch.setattr("distribution.tasks.create_database_dump", _fake_dump)
    monkeypatch.setattr(
        "distribution.tasks.applied_migration_heads",
        lambda: ["catalog.0027_query_lexicon_core", "ingestion.0010_processing_pause_controls"],
    )

    archive_path = Path(create_backup_archive.run(str(job.id)))

    job.refresh_from_db()
    assert job.status == BackupJob.Status.COMPLETED
    assert archive_path.is_file()
    assert job.checksum == job.manifest["archive_sha256"]
    assert job.manifest["database_metadata"]["pg_dump_major"] == 16
    assert job.manifest["database_metadata"]["pg_restore_major"] == 16
    assert job.manifest["migration_heads"] == [
        "catalog.0027_query_lexicon_core",
        "ingestion.0010_processing_pause_controls",
    ]
    with tarfile.open(archive_path, "r:gz") as archive:
        manifest = json.load(archive.extractfile("manifest.json"))
    assert manifest["database_sha256"] == job.manifest["database_sha256"]
    assert manifest["database_metadata"]["server_version"] == "16.14"


def test_backup_job_artifact_write_failure_is_failed_and_leaves_no_archive(
    tmp_path,
    settings,
    monkeypatch,
    django_user_model,
):
    settings.NAS_BACKUP_ROOT = tmp_path
    destination = tmp_path / "write-failure"
    job = _create_job(django_user_model, destination)
    monkeypatch.setattr("distribution.tasks.create_database_dump", _fake_dump)
    monkeypatch.setattr("distribution.tasks.applied_migration_heads", lambda: [])

    def fail_archive(path, mode):
        Path(path).write_bytes(b"partial archive")
        raise OSError("artifact write failure")

    monkeypatch.setattr("distribution.tasks.tarfile.open", fail_archive)

    with pytest.raises(OSError, match="artifact write failure"):
        create_backup_archive.run(str(job.id))

    job.refresh_from_db()
    assert job.status == BackupJob.Status.FAILED
    assert "artifact write failure" in job.error_message
    assert list(destination.glob("*.tar.gz")) == []
