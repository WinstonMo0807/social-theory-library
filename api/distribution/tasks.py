from celery import shared_task
from pathlib import Path
import json
import shutil
import tarfile
import tempfile

from django.conf import settings
from django.utils import timezone

from catalog.models import Asset

from .models import BackupJob, CloudObject
from .database_backup import (
    applied_migration_heads,
    create_database_dump,
    file_sha256,
    redact_backup_error,
)
from .services import sync_asset_to_cloud


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def sync_cloud_object(self, cloud_object_id):
    cloud_object = CloudObject.objects.select_related("asset", "provider").get(pk=cloud_object_id)
    sync_asset_to_cloud(cloud_object)
    from ingestion.services.pipeline import resume_publication_for_asset

    resume_publication_for_asset(str(cloud_object.asset_id))
    return str(cloud_object.id)


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=5,
)
def delete_cloud_object(self, cloud_object_id):
    from .services import s3_client

    cloud_object = CloudObject.objects.select_related("provider").get(pk=cloud_object_id)
    cloud_object.status = CloudObject.Status.DELETING
    cloud_object.save(update_fields=["status", "updated_at"])
    s3_client(cloud_object.provider).delete_object(
        Bucket=cloud_object.provider.bucket,
        Key=cloud_object.object_key,
    )
    cloud_object.status = CloudObject.Status.DELETED
    cloud_object.save(update_fields=["status", "updated_at"])
    return str(cloud_object.id)


def _sha256(path: Path) -> str:
    return file_sha256(path)


@shared_task(bind=True, ignore_result=True)
def create_backup_archive(self, job_id):
    job = BackupJob.objects.select_related("requested_by").get(pk=job_id)
    root = settings.NAS_BACKUP_ROOT.resolve()
    destination = Path(job.destination_path).resolve()
    if destination != root and root not in destination.parents:
        raise RuntimeError("备份目标超出配置的 NAS 备份根目录。")
    destination.mkdir(parents=True, exist_ok=True)
    job.status = BackupJob.Status.RUNNING
    job.started_at = timezone.now()
    job.error_message = ""
    job.save(update_fields=["status", "started_at", "error_message", "updated_at"])
    archive = None
    try:
        backup_created_at = timezone.now()
        stamp = backup_created_at.strftime("%Y%m%d-%H%M%S")
        archive = destination / f"library-backup-{stamp}-{str(job.id)[:8]}.tar.gz"
        with tempfile.TemporaryDirectory(prefix="library-backup-", dir=destination) as temporary:
            staging = Path(temporary)
            database = create_database_dump(staging)
            migration_heads = applied_migration_heads()
            assets = []
            for asset in Asset.objects.select_related("edition__work").all().iterator(chunk_size=200):
                source = Path(asset.file.path)
                record = {
                    "id": str(asset.id),
                    "edition_id": str(asset.edition_id),
                    "title": asset.edition.work.title,
                    "kind": asset.kind,
                    "relative_path": asset.file.name,
                    "sha256": asset.sha256,
                    "byte_size": asset.byte_size,
                    "exists": source.exists(),
                }
                assets.append(record)
                if (
                    source.exists()
                    and job.include_originals
                    and asset.kind == Asset.Kind.ORIGINAL
                ):
                    target = staging / "originals" / asset.file.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
            manifest = {
                "schema": 1,
                "created_at": backup_created_at.isoformat(),
                "database": database.filename,
                "database_sha256": database.sha256,
                "database_bytes": database.byte_size,
                "database_metadata": database.metadata,
                "migration_heads": migration_heads,
                "include_originals": job.include_originals,
                "assets": assets,
                "restore_note": "恢复前需校验归档哈希，并在维护窗口内导入数据库。",
            }
            (staging / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            with tarfile.open(archive, "w:gz") as tar:
                for path in sorted(staging.rglob("*")):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(staging))
        job.status = BackupJob.Status.COMPLETED
        job.archive_path = str(archive)
        job.checksum = _sha256(archive)
        job.manifest = {
            "artifact_filename": archive.name,
            "created_at": backup_created_at.isoformat(),
            "asset_count": len(assets),
            "included_original_count": sum(
                1 for asset in assets if asset["kind"] == Asset.Kind.ORIGINAL and job.include_originals
            ),
            "archive_bytes": archive.stat().st_size,
            "archive_sha256": job.checksum,
            "database": database.filename,
            "database_sha256": database.sha256,
            "database_bytes": database.byte_size,
            "database_metadata": database.metadata,
            "migration_heads": migration_heads,
        }
        job.completed_at = timezone.now()
        job.save(
            update_fields=[
                "status",
                "archive_path",
                "checksum",
                "manifest",
                "completed_at",
                "updated_at",
            ]
        )
        return str(archive)
    except Exception as exc:
        if archive is not None and archive.exists():
            try:
                archive.unlink()
            except OSError:
                pass
        job.status = BackupJob.Status.FAILED
        job.error_message = redact_backup_error(
            str(exc),
            secrets=(settings.DATABASES["default"].get("PASSWORD"),),
        )
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
        raise
