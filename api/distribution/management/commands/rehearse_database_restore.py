from pathlib import Path
import json
import tarfile

from django.core.management.base import BaseCommand, CommandError

from distribution.database_backup import DatabaseBackupError, extract_backup_database, rehearse_database_archive


class Command(BaseCommand):
    help = "Restore one BackupJob archive into an empty disposable PostgreSQL database."

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--confirm-disposable-database", required=True,
            help="Must exactly match the current target database name.")

    def handle(self, *args, **options):
        archive = options["archive"].expanduser().resolve()
        if not archive.is_file():
            raise CommandError(f"Backup archive not found: {archive}")
        try:
            report = rehearse_database_archive(archive,
                confirmation=options["confirm_disposable_database"].strip())
        except (DatabaseBackupError, KeyError, OSError, tarfile.TarError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))

    _extract_database = staticmethod(extract_backup_database)
