from celery import shared_task
from pathlib import Path
import json
import shutil
import tarfile
import tempfile

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset

from .models import BackupJob, CloudObject
from .database_backup import (
    file_sha256,
    redact_backup_error,
)
from .backup_snapshot import capture_backup_snapshot
from .services import sync_asset_to_cloud


class BackupDeliveryClosed(Exception):
    """A closed delivery must not overwrite the administrator's decision."""


def _backup_delivery_open(job):
    return BackupJob.objects.filter(pk=job.pk, status=BackupJob.Status.RUNNING, started_at=job.started_at).exists()


def _require_backup_delivery(job):
    if not _backup_delivery_open(job):
        raise BackupDeliveryClosed("原备份任务已关闭。")


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def sync_cloud_object(self, cloud_object_id, *, resume_publication=True):
    cloud_object = CloudObject.objects.select_related("asset", "provider").get(pk=cloud_object_id)
    sync_asset_to_cloud(cloud_object)
    from ingestion.services.pipeline import resume_publication_for_asset

    if resume_publication:
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


def enqueue_backup_archive(job_id):
    try:
        create_backup_archive.apply_async(args=[str(job_id)], ignore_result=True)
    except Exception:
        BackupJob.objects.filter(pk=job_id, status=BackupJob.Status.QUEUED).update(
            status=BackupJob.Status.FAILED, error_message="备份队列暂不可用，请检查后台任务服务后重新创建备份。",
            completed_at=timezone.now(), updated_at=timezone.now())


@shared_task(bind=True, ignore_result=True)
def create_backup_archive(self, job_id):
    with transaction.atomic():
        job = BackupJob.objects.select_for_update().get(pk=job_id)
        if job.status != BackupJob.Status.QUEUED:
            return job.archive_path if job.status == BackupJob.Status.COMPLETED else None
        job.status = BackupJob.Status.RUNNING
        job.started_at = timezone.now()
        job.error_message = ""
        job.save(update_fields=["status", "started_at", "error_message", "updated_at"])
    archive = None
    owns_archive = False
    try:
        root = settings.NAS_BACKUP_ROOT.resolve()
        destination = Path(job.destination_path).resolve()
        if destination != root and root not in destination.parents:
            raise RuntimeError("备份目标超出配置的 NAS 备份根目录。")
        destination.mkdir(parents=True, exist_ok=True)
        backup_created_at = timezone.now()
        stamp = backup_created_at.strftime("%Y%m%d-%H%M%S")
        archive = destination / f"library-backup-{stamp}-{job.id}.tar.gz"
        with tempfile.TemporaryDirectory(prefix="library-backup-", dir=destination) as temporary:
            staging = Path(temporary)
            _require_backup_delivery(job)
            database, migration_heads, assets = capture_backup_snapshot(staging)
            _require_backup_delivery(job)
            storage = Asset._meta.get_field("file").storage
            for record in assets:
                _require_backup_delivery(job)
                source = Path(storage.path(record["relative_path"]))
                record["exists"] = source.exists()
                if job.include_originals and record["kind"] == Asset.Kind.ORIGINAL:
                    identifier = record["id"]
                    if not source.is_file():
                        raise RuntimeError(f"原始文件 {identifier} 不存在，未生成不完整备份。")
                    original_root = (staging / "originals").resolve()
                    target = (original_root / record["relative_path"]).resolve()
                    if original_root not in target.parents:
                        raise RuntimeError(f"原始文件 {identifier} 的备份相对路径无效。")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open("rb") as original, target.open("xb") as output:
                        shutil.copyfileobj(original, output, length=1024 * 1024)
                    if (not record["sha256"] or _sha256(target) != record["sha256"]
                            or (record["byte_size"] and target.stat().st_size != record["byte_size"])):
                        raise RuntimeError(f"原始文件 {identifier} 的备份副本校验失败，源文件保留。")
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
            manifest_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            if len(manifest_bytes) > 16 * 1024**2:
                raise RuntimeError("备份清单超出原归档校验器上限，未生成无法完整校验的备份。")
            (staging / "manifest.json").write_bytes(manifest_bytes)
            with archive.open("xb") as archive_output:
                owns_archive = True
                with tarfile.open(fileobj=archive_output, mode="w:gz") as tar:
                    for path in sorted(staging.rglob("*")):
                        _require_backup_delivery(job)
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
        accepted = BackupJob.objects.filter(pk=job.pk, status=BackupJob.Status.RUNNING, started_at=job.started_at).update(
            status=job.status, archive_path=job.archive_path, checksum=job.checksum, manifest=job.manifest,
            completed_at=job.completed_at, updated_at=timezone.now())
        if not accepted:
            raise BackupDeliveryClosed("原备份任务已关闭，不再登记迟到归档。")
        return str(archive)
    except Exception as exc:
        if owns_archive and archive is not None and archive.exists():
            try:
                archive.unlink()
            except OSError:
                pass
        if isinstance(exc, BackupDeliveryClosed):
            return None
        error_message = redact_backup_error(
            str(exc),
            secrets=(settings.DATABASES["default"].get("PASSWORD"),),
        )
        BackupJob.objects.filter(pk=job.pk, status=BackupJob.Status.RUNNING, started_at=job.started_at).update(
            status=BackupJob.Status.FAILED, error_message=error_message, completed_at=timezone.now(), updated_at=timezone.now())
        raise
