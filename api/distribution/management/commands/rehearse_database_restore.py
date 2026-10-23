from pathlib import Path, PurePosixPath
import json
import re
import shutil
import tarfile
import tempfile

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from distribution.database_backup import (
    DatabaseBackupError,
    file_sha256,
    restore_database_dump,
)


DISPOSABLE_DATABASE_MARKERS = ("disposable", "evaluation", "rehearsal", "restore", "test")


class Command(BaseCommand):
    help = "Restore one BackupJob archive into an empty disposable PostgreSQL database."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--write-report", action="store_true", help="Write a signed result in the configured backup root after the isolated restore succeeds.")
        parser.add_argument("--expected-sha256", help="Expected archive identity; required when saving a signed rehearsal report.")
        parser.add_argument(
            "--confirm-disposable-database",
            required=True,
            help="Must exactly match the current target database name.",
        )

    def handle(self, *args, **options):
        archive = options["archive"].expanduser().resolve()
        confirmation = options["confirm_disposable_database"].strip()
        if connection.vendor != "postgresql":
            raise CommandError("Restore rehearsal requires PostgreSQL.")
        if not archive.is_file():
            raise CommandError(f"Backup archive not found: {archive}")
        expected = options.get("expected_sha256")
        if options.get("write_report") and not expected:
            raise CommandError("Saving a rehearsal report requires --expected-sha256 from the backup record.")
        if expected and not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise CommandError("Archive checksum must be a lowercase SHA-256 value.")

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database_name = str(cursor.fetchone()[0])
            cursor.execute(
                "SELECT COUNT(*) FROM pg_catalog.pg_tables "
                "WHERE schemaname NOT IN ('pg_catalog', 'information_schema')"
            )
            table_count = int(cursor.fetchone()[0])
        if confirmation != database_name:
            raise CommandError("Disposable database confirmation does not match target.")
        if not any(marker in database_name.casefold() for marker in DISPOSABLE_DATABASE_MARKERS):
            raise CommandError("Target database name does not identify a disposable restore database.")
        if table_count:
            raise CommandError(
                f"Disposable restore database must be empty; found {table_count} tables."
            )

        try:
            archive_checksum = file_sha256(archive)
            if expected and archive_checksum != expected:
                raise ValueError("Backup archive checksum does not match the expected backup.")
            with tempfile.TemporaryDirectory(prefix="library-restore-") as temporary:
                temporary_root = Path(temporary)
                manifest, dump_path = self._extract_database(archive, temporary_root)
                if file_sha256(archive) != archive_checksum:
                    raise ValueError("Backup archive changed during extraction; restore not started.")
                metadata = manifest.get("database_metadata") or {}
                if not isinstance(metadata, dict):
                    raise ValueError("Backup database metadata is invalid.")
                runtime = restore_database_dump(
                    dump_path,
                    dump_client_major=metadata.get("pg_dump_major"),
                )
                report = {
                    "status": "restored",
                    "archive_filename": archive.name,
                    "archive_sha256": archive_checksum,
                    "database": database_name,
                    "database_dump_sha256": file_sha256(dump_path),
                    "source_server_version": metadata.get("server_version"),
                    "source_pg_dump_version": metadata.get("pg_dump_version"),
                    "target_server_version": runtime["server_version"],
                    "pg_restore_version": runtime["pg_restore_version"],
                    "migration_heads": manifest.get("migration_heads") or [],
                }
        except (DatabaseBackupError, KeyError, OSError, tarfile.TarError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if options.get("write_report"):
            from distribution.storage_workspace import write_restore_report
            try:
                report["report_filename"] = write_restore_report(report)
            except (OSError, ValueError) as exc:
                self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
                raise CommandError("隔离数据库已导入，但恢复记录未写入；请保留命令输出并核对备份记录目录。") from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _extract_database(archive: Path, destination: Path) -> tuple[dict, Path]:
        with tarfile.open(archive, "r:gz") as bundle:
            try:
                manifest_member = bundle.getmember("manifest.json")
            except KeyError as exc:
                raise ValueError("Backup archive has no manifest.json.") from exc
            if not manifest_member.isfile():
                raise ValueError("Backup archive manifest is not a regular file.")
            if manifest_member.size > 16 * 1024**2:
                raise ValueError("Backup archive manifest exceeds the supported size.")
            manifest_handle = bundle.extractfile(manifest_member)
            if manifest_handle is None:
                raise ValueError("Backup archive manifest is unreadable.")
            manifest = json.loads(manifest_handle.read(manifest_member.size + 1).decode("utf-8"))
            if not isinstance(manifest, dict):
                raise ValueError("Backup archive manifest is not an object.")
            database_name = str(manifest.get("database") or "")
            database_path = PurePosixPath(database_name)
            if (
                not database_name
                or database_path.is_absolute()
                or ".." in database_path.parts
                or len(database_path.parts) != 1
                or "\\" in database_name
                or ":" in database_name
                or database_path.name != database_name
            ):
                raise ValueError("Backup archive database path is unsafe.")
            try:
                database_member = bundle.getmember(database_name)
            except KeyError as exc:
                raise ValueError("Backup archive database artifact is missing.") from exc
            if not database_member.isfile():
                raise ValueError("Backup archive database artifact is not a regular file.")
            if database_member.size <= 0 or database_member.size > shutil.disk_usage(destination).free * .8:
                raise ValueError("Insufficient temporary space for isolated restore extraction.")
            database_handle = bundle.extractfile(database_member)
            if database_handle is None:
                raise ValueError("Backup archive database artifact is unreadable.")
            target = destination / database_path.name
            with target.open("wb") as output:
                shutil.copyfileobj(database_handle, output)
        expected_checksum = str(manifest.get("database_sha256") or "")
        actual_checksum = file_sha256(target)
        if not expected_checksum:
            raise ValueError("Backup archive has no database checksum.")
        if actual_checksum != expected_checksum:
            raise ValueError("Backup archive database checksum mismatch.")
        return manifest, target
