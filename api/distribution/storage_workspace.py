"""Storage and backup presentation over the original catalog and backup queue."""
from datetime import timedelta
from itertools import islice
from pathlib import Path
from hashlib import sha256
import json
import os
import shutil

from django.conf import settings
from django.core import signing
from django.core.paginator import Paginator, InvalidPage
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Case, When, Value, CharField, Sum, Count, OuterRef, Subquery
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from catalog.models import Asset
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from .models import BackupJob, BackupVerification, BackupSchedule


class StorageConflict(APIException):
    status_code = 409
    default_detail = "记录已经变化，请刷新后重新操作。"


def backup_rows():
    return BackupJob.objects.order_by("-created_at", "-id")


def file_statistics():
    query = Asset.objects.annotate(file_type=Case(
        When(mime_type="application/pdf", then=Value("PDF")),
        When(mime_type__startswith="image/", then=Value("图像")),
        When(mime_type__in=["application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"], then=Value("Word")),
        default=Value("其他"), output_field=CharField()))
    return query.values("kind", "file_type").annotate(bytes=Sum("byte_size"), count=Count("id")).order_by("kind", "file_type")


def schedule_payload(scope, row=None):
    return {"scope": scope, "label": "数据库与文件清单" if scope == "database" else "数据库、清单与原件",
        "enabled": bool(row and row.enabled), "interval_hours": row.interval_hours if row else 24,
        "next_run_at": row.next_run_at if row else None, "version": row.updated_at.isoformat() if row else "unconfigured",
        "last_job_id": str(row.last_job_id) if row and row.last_job_id else None,
        "last_job_status": row.last_job.status if row and row.last_job_id else "",
        "last_error": row.last_error if row else ""}


def _location(key, label, root):
    root = Path(root)
    result = {"id": key, "label": label, "status": "unavailable", "total_bytes": None, "used_bytes": None,
        "free_bytes": None, "used_percent": None, "readable": False, "writable": False,
        "detail": "配置目录不可读取，请核对挂载和访问权限。"}
    try:
        if root.is_dir() and os.access(root, os.R_OK):
            usage = shutil.disk_usage(root)
            result.update(status="low_space" if usage.free < usage.total * .1 else "available",
                total_bytes=usage.total, used_bytes=usage.used, free_bytes=usage.free,
                used_percent=round(usage.used * 100 / usage.total, 1) if usage.total else None,
                readable=os.access(root, os.R_OK), writable=os.access(root, os.W_OK),
                detail="容量来自所在卷；多个配置目录可能共用同一个卷，不能相加。未执行写入探测。")
    except OSError:
        pass
    return result


def verification_payload(row):
    report = row.report if isinstance(row.report, dict) else {}
    stalled = row.status in ("queued", "running") and (row.started_at or row.created_at) < timezone.now() - timedelta(seconds=3700)
    return {"id": str(row.pk), "backup_id": str(row.backup_id), "status": row.status,
        "status_label": "执行状态待核对" if stalled else row.get_status_display(), "stalled": bool(stalled),
        "expected_checksum": row.expected_checksum, "started_at": row.started_at, "completed_at": row.completed_at,
        "created_at": row.created_at, "error_message": row.error_message,
        "database_verified": bool(report.get("database_verified")),
        "originals_verified": int(report.get("originals_verified") or 0), "detail": str(report.get("detail") or ""),
        "restore_verified": False}


def backup_payload(row, *, latest=None):
    manifest = row.manifest if isinstance(row.manifest, dict) else {}
    size = manifest.get("archive_bytes")
    duration = (row.completed_at - row.started_at).total_seconds() if row.completed_at and row.started_at else None
    error = "备份未完成，现有归档及原件保留。请核对备份目录、数据库备份工具与后台任务。" if row.status == "failed" else ""
    stalled = backup_stalled(row)
    return {"id": str(row.pk), "status": row.status, "status_label": "执行状态待核对" if stalled else row.get_status_display(),
        "stalled": stalled, "version": row.updated_at.isoformat(),
        "include_originals": row.include_originals, "scope": "数据库、文件清单与原件" if row.include_originals else "数据库与文件清单",
        "archive_name": Path(row.archive_path).name if row.archive_path else "尚未生成归档", "location": "配置的 NAS 备份目录",
        "archive_bytes": size if isinstance(size, int) and size >= 0 else None,
        "checksum": row.checksum, "duration_seconds": max(0, round(duration)) if duration is not None else None,
        "created_at": row.created_at, "started_at": row.started_at, "completed_at": row.completed_at,
        "error_message": error, "verification": verification_payload(latest) if latest else None,
        "restore_status": "not_verified"}


def backup_stalled(row):
    # Match the configured worker hard limit, with a short delivery margin.
    limit = getattr(settings, "CELERY_TASK_TIME_LIMIT", None)
    return bool(isinstance(limit, (int, float)) and limit > 0 and row.status in {"queued", "running"}
                and (row.started_at or row.created_at) < timezone.now() - timedelta(seconds=limit + 100))


def restore_reports(checksum=None):
    """Only signed reports written by the existing isolated-DB command count."""
    directory = settings.NAS_BACKUP_ROOT.resolve() / "rehearsals"
    reports, skipped = [], False
    try:
        if not directory.is_dir() or directory.is_symlink():
            return reports, skipped
        paths = list(islice(directory.iterdir(), 501))
        skipped = len(paths) > 500
        for path in paths[:500]:
            if path.is_symlink() or path.suffix != ".json" or not path.is_file() or path.stat().st_size > 65536:
                continue
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
                report = signing.loads(envelope["signed_report"], salt="stl-backup-restore-rehearsal-v1")
                if not isinstance(report, dict) or report.get("status") != "restored" or not isinstance(report.get("checked_at"), str):
                    continue
                if checksum and report.get("archive_sha256") != checksum:
                    continue
                reports.append({"checked_at": report["checked_at"], "archive_sha256": report.get("archive_sha256", ""),
                    "status": "database_restored", "detail": "已在空白隔离 PostgreSQL 中完成导入；应用功能、文件和索引恢复仍待核对。"})
            except (OSError, ValueError, TypeError, KeyError, signing.BadSignature):
                continue
    except OSError:
        return [], True
    return sorted(reports, key=lambda row: row["checked_at"], reverse=True)[:50], skipped


def storage_snapshot(actor, *, page=1, status="", as_of=None):
    as_of = as_of or timezone.now()
    if as_of > timezone.now():
        raise ValidationError("不能查询未来的备份记录。")
    rows = backup_rows().filter(created_at__lte=as_of)
    if status:
        rows = rows.filter(status=status)
    paginator = Paginator(rows, 20)
    try:
        page_rows = list(paginator.page(page).object_list)
    except InvalidPage as error:
        raise ValidationError("这一页记录已不存在，请返回第一页重新读取。") from error
    count = paginator.count
    latest = {}
    newest = BackupVerification.objects.filter(backup_id=OuterRef("backup_id")).order_by("-created_at", "-id").values("pk")[:1]
    for record in BackupVerification.objects.filter(backup_id__in=[row.pk for row in page_rows], pk=Subquery(newest)):
        latest.setdefault(record.backup_id, record)
    stats = list(file_statistics())
    files = []
    for label in ("PDF", "图像", "Word", "其他"):
        group = [row for row in stats if row["file_type"] == label]
        files.append({"label": label, "bytes": sum(max(0, row["bytes"] or 0) for row in group), "count": sum(row["count"] for row in group)})
    can_backup = has_capability(actor, Capability.RUN_BACKUP)
    schedules = {row.scope: row for row in BackupSchedule.objects.select_related("last_job").all()}
    rehearsals, reports_limited = restore_reports() if can_backup else ([], False)
    return {"checked_at": timezone.now(), "permissions": {"can_backup": can_backup, "can_verify": can_backup, "can_prepare_restore": can_backup},
        "locations": [_location("library", "馆藏主目录", settings.MEDIA_ROOT),
            _location("originals", "原件目录", settings.NAS_ORIGINAL_ROOT), _location("public", "公开派生文件", settings.NAS_PUBLIC_ROOT),
            _location("backups", "本地备份目录", settings.NAS_BACKUP_ROOT)],
        "file_types": files, "catalog_file_bytes": sum(row["bytes"] for row in files),
        "categories": [{"label": "原件与扫描文件", "bytes": sum(max(0, row["bytes"] or 0) for row in stats if row["kind"] == "original")},
            {"label": "登记的阅读派生文件", "bytes": sum(max(0, row["bytes"] or 0) for row in stats if row["kind"] != "original")},
            {"label": "数据库与索引", "bytes": None}, {"label": "系统与其他", "bytes": None}],
        "file_statistics_notice": "分类数值来自登记的馆藏文件；不包含未登记缓存、模型、数据库或索引，不能代替所在卷实际占用。",
        "schedule": {"configured": any(row.enabled for row in schedules.values()),
            "detail": "定时计划通过原任务服务发起完整数据库归档，可选择包含原件；不提供未实现的增量或独立索引备份。任务服务状态与执行结果需分别核对。",
            "plans": [schedule_payload(scope, schedules.get(scope)) for scope in ("database", "originals")]},
        "backups": {"count": count, "page": page, "page_size": 20, "as_of": as_of, "results": [backup_payload(row, latest=latest.get(row.pk)) for row in page_rows]},
        "verifications": [verification_payload(row) for row in BackupVerification.objects.order_by("-created_at", "-id")[:30]],
        "rehearsals": rehearsals, "rehearsals_limited": reports_limited,
        "retention": [{"label": "原件与历史文件", "policy": "保留原件及已有历史版本", "detail": "不按缓存清理规则删除。"},
            {"label": "账户与私人资料", "policy": "账户身份保留；私人内容按本人设置", "detail": "维护页面不会变更读者的保存偏好或删除私人记录。"},
            {"label": "模型与活动索引", "policy": "保护当前在用版本", "detail": "重建不等于已获准删除旧版本，须单独核对依赖。"},
            {"label": "衍生文件与缓存", "policy": "先核对具体影响", "detail": "现有登记不足以证明文件可删时，保持保护。"}],
        "cleanup": {"status": "not_scanned", "can_execute": False, "candidate_count": None, "candidate_bytes": None,
            "protected_count": sum(row["count"] for row in files),
            "detail": "原件、阅读派生文件、当前媒体与历史版本均受保护。尚无能证明可安全删除的缓存候选；不能把全部 OCR 或缩略图当作垃圾。"}}


def backup_detail(identifier):
    row = BackupJob.objects.filter(pk=identifier).first()
    if row is None:
        raise NotFound("备份记录不存在。")
    checks = list(row.verifications.order_by("-created_at", "-id")[:30])
    reports, limited = restore_reports(row.checksum) if row.checksum else ([], False)
    from .database_backup import redact_backup_error
    return {"backup": backup_payload(row, latest=checks[0] if checks else None),
        "verifications": [verification_payload(check) for check in checks], "rehearsals": reports, "rehearsals_limited": limited,
        "technical_error": redact_backup_error(row.error_message, secrets=(settings.DATABASES["default"].get("PASSWORD"),))}


def write_restore_report(report):
    """Called only after the existing isolated-database command succeeds."""
    import uuid
    root = settings.NAS_BACKUP_ROOT.resolve()
    directory = root / "rehearsals"
    if not root.is_dir() or directory.is_symlink() or root not in directory.resolve().parents:
        raise ValueError("恢复记录目录必须位于已配置的备份根目录内。")
    directory.mkdir(mode=0o700, exist_ok=True)
    checked_at = timezone.now()
    target = directory / f"{checked_at.strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4()}.json"
    envelope = {"signed_report": signing.dumps({**report, "checked_at": checked_at.isoformat()}, salt="stl-backup-restore-rehearsal-v1")}
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as output:
        json.dump(envelope, output, ensure_ascii=False)
    return target.name


def storage_command(request, values):
    from .storage_receipts import execute
    return execute(request, values, _apply_storage_command)


def _apply_storage_command(actor, values):
    operation, identifier = values["operation"], values["request_id"]
    if operation == "close_stalled_backup":
        fingerprint = sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
        receipt = AuditEvent.objects.filter(action="storage_backup_closed", request_id=str(identifier)).first()
        if receipt:
            if receipt.actor_id != actor.pk or receipt.after.get("fingerprint") != fingerprint:
                raise StorageConflict("原请求编号已用于其他备份操作。")
            return {"request_id": str(identifier), "operation": operation, "backup": backup_payload(
                BackupJob.objects.get(pk=receipt.object_id))}
        if BackupJob.objects.filter(pk=identifier).exists() or BackupVerification.objects.filter(pk=identifier).exists() or AuditEvent.objects.filter(request_id=str(identifier)).exists():
            raise StorageConflict("请求编号已用于其他存储操作。")
        job = BackupJob.objects.select_for_update().filter(pk=values["backup_id"]).first()
        if job is None:
            raise NotFound("备份记录不存在。")
        if job.updated_at.isoformat() != values["expected_version"] or not backup_stalled(job):
            raise StorageConflict("任务状态已变化或尚未超过任务时限，请重新读取。")
        before = {"status": job.status, "started_at": job.started_at.isoformat() if job.started_at else None}
        job.status = "failed"
        job.completed_at = timezone.now()
        job.error_message = "管理员已关闭超时备份记录。未终止工作进程；旧任务不再登记成功，已有归档和原件保留。可重新发起备份。"
        job.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="storage_backup_closed", object_type="BackupJob", object_id=str(job.pk),
            request_id=str(identifier), before=before, after={"fingerprint": fingerprint, "status": "failed"})
        return {"request_id": str(identifier), "operation": operation, "backup": backup_payload(job)}
    if operation == "save_schedule":
        scope = values["scope"]
        fingerprint = sha256(json.dumps(values, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()
        receipt = AuditEvent.objects.filter(action="storage_schedule_saved", request_id=str(identifier)).first()
        if receipt:
            if receipt.actor_id != actor.pk or receipt.after.get("fingerprint") != fingerprint:
                raise StorageConflict("原请求编号已用于不同的备份计划。")
            return {"request_id": str(identifier), "operation": operation, "schedule_saved": True}
        if BackupJob.objects.filter(pk=identifier).exists() or BackupVerification.objects.filter(pk=identifier).exists():
            raise StorageConflict("请求编号已用于其他存储任务。")
        acquire_entity_lock("storage_backup_schedule", scope)
        row = BackupSchedule.objects.select_for_update().filter(scope=scope).first()
        if values["expected_version"] != schedule_payload(scope, row)["version"]:
            raise StorageConflict("备份计划已被修改，请重新读取当前计划。")
        if values["enabled"] and (values.get("first_run_at") is None or values["first_run_at"] <= timezone.now()):
            raise ValidationError("启用计划时，请明确选择未来的首次执行时间。")
        row = row or BackupSchedule(scope=scope)
        row.enabled = values["enabled"]
        row.interval_hours = values["interval_hours"]
        row.next_run_at = values.get("first_run_at") if row.enabled else None
        row.configured_by = actor
        row.last_error = ""
        row.save()
        AuditEvent.objects.create(actor=actor, action="storage_schedule_saved", object_type="BackupSchedule", object_id=str(row.pk), request_id=str(identifier),
            after={"fingerprint": fingerprint, "scope": scope, "enabled": row.enabled, "interval_hours": row.interval_hours, "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None})
        return {"request_id": str(identifier), "operation": operation, "schedule_saved": True}
    if AuditEvent.objects.filter(action="storage_schedule_saved", request_id=str(identifier)).exists():
        raise StorageConflict("请求编号已用于备份计划。")
    if operation == "create_backup":
        if BackupVerification.objects.filter(pk=identifier).exists():
            raise StorageConflict("请求编号已用于归档校验。")
        existing = BackupJob.objects.filter(pk=identifier).first()
        if existing:
            if existing.requested_by_id != actor.pk or existing.include_originals != values["include_originals"]:
                raise StorageConflict("请求编号已用于不同的备份。")
            return {"request_id": str(identifier), "operation": operation, "backup": backup_payload(existing)}
        destination = settings.NAS_BACKUP_ROOT.resolve()
        if not destination.is_dir():
            raise ValidationError("配置的备份目录尚不可用，请先核对存储挂载。")
        source_id = values.get("retry_from_id")
        if source_id:
            source = BackupJob.objects.filter(pk=source_id, status="failed").first()
            if source is None or source.include_originals != values["include_originals"]:
                raise StorageConflict("原备份状态或范围已变化，请重新读取失败记录。")
        job = BackupJob.objects.create(pk=identifier, requested_by=actor, destination_path=str(destination), include_originals=values["include_originals"])
        AuditEvent.objects.create(actor=actor, action="storage_backup_requested", object_type="BackupJob", object_id=str(job.pk), request_id=str(identifier),
            after={"include_originals": job.include_originals, "retry_from_id": str(source_id) if source_id else None})
        from .storage_tasks import enqueue_authorized_backup
        transaction.on_commit(lambda: enqueue_authorized_backup(job.pk))
        return {"request_id": str(identifier), "operation": operation, "backup": backup_payload(job)}
    backup = BackupJob.objects.select_for_update().filter(pk=values["backup_id"]).first()
    if backup is None:
        raise NotFound("备份记录不存在。")
    if backup.status != "completed" or not backup.checksum or backup.checksum != values["expected_checksum"]:
        raise StorageConflict("备份尚未完成或校验身份已变化，请刷新记录。")
    if operation == "close_stalled_verification":
        record = backup.verifications.select_for_update().filter(pk=values["verification_id"]).first()
        if record is None:
            raise NotFound("校验记录不存在。")
        if record.status == "failed" and AuditEvent.objects.filter(action="storage_verification_closed", request_id=str(identifier), object_id=str(record.pk)).exists():
            return {"request_id": str(identifier), "operation": operation, "verification": verification_payload(record)}
        if not verification_payload(record)["stalled"]:
            raise StorageConflict("校验仍在正常任务时限内或已经结束，请刷新记录。")
        record.status = "failed"
        record.completed_at = timezone.now()
        record.error_message = "管理员已关闭超时校验记录。未更改归档；原只读任务的迟到结果不再写入，可另行发起校验。"
        record.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
        AuditEvent.objects.create(actor=actor, action="storage_verification_closed", object_type="BackupVerification", object_id=str(record.pk), request_id=str(identifier))
        return {"request_id": str(identifier), "operation": operation, "verification": verification_payload(record)}
    if operation == "verify_archive":
        if BackupJob.objects.filter(pk=identifier).exists():
            raise StorageConflict("请求编号已用于备份。")
        record = BackupVerification.objects.filter(pk=identifier).first()
        if record:
            if record.requested_by_id != actor.pk or record.backup_id != backup.pk or record.expected_checksum != backup.checksum:
                raise StorageConflict("原请求对应其他校验。")
        else:
            if backup.verifications.filter(status__in=["queued", "running"]).exists():
                raise StorageConflict("这份备份已有校验任务，请先核对其进度。")
            record = BackupVerification.objects.create(pk=identifier, backup=backup, requested_by=actor, expected_checksum=backup.checksum)
            from .storage_tasks import enqueue_verification
            transaction.on_commit(lambda: enqueue_verification(record.pk))
        return {"request_id": str(identifier), "operation": operation, "verification": verification_payload(record)}
    verified = backup.verifications.filter(status="completed", expected_checksum=backup.checksum).order_by("-completed_at").first()
    return {"request_id": str(identifier), "operation": "restore_plan", "restore_plan": {
        "backup_id": str(backup.pk), "archive_name": Path(backup.archive_path).name, "archive_sha256": backup.checksum,
        "integrity_verified_at": verified.completed_at if verified else None, "restore_executed": False,
        "ready_for_rehearsal": bool(verified), "target": "空白隔离 PostgreSQL 数据库",
        "command": "rehearse_database_restore", "report_option": "--write-report",
        "requirements": ["先完成归档、数据库文件和所包含原件的校验。", "目标必须为空白隔离数据库，名称明确含 rehearsal/restore/test 等标记，并逐字确认数据库名。",
            "命令的 --expected-sha256 必须填写本清单的 archive_sha256；使用 --write-report 保存签名演练记录。",
            "沿既有命令检查 PostgreSQL 客户端与服务器版本；不把当前生产库作为目标。", "导入完成后核对账号、文件、索引及实际业务；导入成功本身不能代表整站恢复完成。",
            "生产恢复或不可逆清理须另行提交具体影响与回退方案，并取得最终确认。"]}}
