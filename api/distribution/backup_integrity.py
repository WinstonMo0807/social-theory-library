"""Read-only, streaming archive inspection. Never extracts or restores files."""
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

from django.conf import settings
from .database_backup import file_sha256


class BackupIntegrityError(ValueError):
    pass


def archive_path(backup):
    root = settings.NAS_BACKUP_ROOT.resolve()
    candidate = Path(backup.archive_path)
    resolved = candidate.resolve()
    if not backup.archive_path or candidate.is_symlink() or root not in resolved.parents or not resolved.is_file():
        raise BackupIntegrityError("备份归档不可读取或已离开配置的备份目录。")
    return resolved


def _name(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise BackupIntegrityError("归档包含不安全的文件名称。")
    name = PurePosixPath(value)
    if name.is_absolute() or ".." in name.parts or str(name) != value.rstrip("/"):
        raise BackupIntegrityError("归档包含不安全的相对路径。")
    return str(name)


def verify_archive(backup, expected_checksum):
    if not re.fullmatch(r"[0-9a-f]{64}", expected_checksum) or backup.checksum != expected_checksum:
        raise BackupIntegrityError("备份校验标识已变化，请重新读取备份记录。")
    archive = archive_path(backup)
    before = archive.stat()
    if file_sha256(archive) != expected_checksum:
        raise BackupIntegrityError("归档整体校验不一致，文件保留，请使用另一份备份。")
    hashes, sizes, manifest = {}, {}, None
    total = 0
    # ponytail: bounded streaming inspection; larger archives need a dedicated
    # resumable verifier instead of relaxing these worker memory/time limits.
    limit = int(getattr(settings, "BACKUP_VERIFY_MAX_BYTES", 2 * 1024**4))
    with tarfile.open(archive, "r|gz") as bundle:
        for count, member in enumerate(bundle, 1):
            if count > 100000:
                raise BackupIntegrityError("归档文件数量超出单次校验范围，请安排独立维护校验。")
            name = _name(member.name)
            if member.isdir():
                continue
            if not member.isfile() or name in hashes or member.size < 0:
                raise BackupIntegrityError("归档包含链接、重复文件或不支持的文件类型。")
            total += member.size
            if total > limit:
                raise BackupIntegrityError("归档展开大小超出本次校验上限，请安排独立维护校验。")
            stream = bundle.extractfile(member)
            if stream is None:
                raise BackupIntegrityError("归档成员不可读取。")
            with stream:
                if name == "manifest.json":
                    if member.size > 16 * 1024**2:
                        raise BackupIntegrityError("归档清单过大，不能安全校验。")
                    payload = stream.read(member.size + 1)
                    manifest = json.loads(payload)
                    digest = sha256(payload)
                else:
                    digest = sha256()
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
            hashes[name], sizes[name] = digest.hexdigest(), member.size
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise BackupIntegrityError("备份清单缺失或版本不受支持。")
    database = _name(manifest.get("database"))
    if "/" in database or database == "manifest.json" or hashes.get(database) != manifest.get("database_sha256"):
        raise BackupIntegrityError("数据库备份文件未通过独立校验。")
    if sizes.get(database) != manifest.get("database_bytes"):
        raise BackupIntegrityError("数据库备份文件大小与清单不一致。")
    assets = manifest.get("assets")
    if not isinstance(assets, list) or len(assets) > 100000 or manifest.get("include_originals") is not backup.include_originals:
        raise BackupIntegrityError("原件清单不完整或备份范围不一致。")
    expected = {database, "manifest.json"}
    original_count = 0
    if backup.include_originals:
        for asset in assets:
            if not isinstance(asset, dict):
                raise BackupIntegrityError("原件清单包含无效记录。")
            if asset.get("kind") != "original":
                continue
            name = "originals/" + _name(asset.get("relative_path"))
            if name in expected or hashes.get(name) != asset.get("sha256"):
                raise BackupIntegrityError("原件备份缺失、重复或校验不一致。")
            if asset.get("byte_size") and sizes.get(name) != asset["byte_size"]:
                raise BackupIntegrityError("原件备份大小与清单不一致。")
            expected.add(name)
            original_count += 1
    if set(hashes) != expected:
        raise BackupIntegrityError("归档包含清单以外的文件，请先核对备份来源。")
    after = archive.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise BackupIntegrityError("归档在校验期间发生变化，请重新校验。")
    return {"archive_sha256": expected_checksum, "archive_bytes": before.st_size,
        "database_verified": True, "database_bytes": sizes[database],
        "originals_included": backup.include_originals, "originals_verified": original_count,
        "restore_verified": False, "detail": "归档、数据库文件及所包含原件的校验已完成；尚未执行恢复演练。"}
