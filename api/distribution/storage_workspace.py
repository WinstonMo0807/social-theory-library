"""Storage and backup presentation over the original catalog and backup queue."""
from datetime import timedelta
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
from .index_backup import index_backup_configured


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
    return {"scope": scope, "label": {"database":"数据库与文件清单", "originals":"数据库、清单与原件", "incremental":"数据库与增量原件", "indexes":"检索索引"}[scope],
        "include_indexes": scope == 'indexes' or bool(row and row.include_indexes),
        "base_backup_id": str(row.incremental_base_id) if row and row.incremental_base_id else None,
        "base_checksum": row.incremental_base.checksum if row and row.incremental_base_id else "",
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
        "index_verified": report.get('index_verified') is True,
        "originals_verified": int(report.get("originals_verified") or 0), "detail": str(report.get("detail") or ""),
        "restore_verified": False}


def backup_payload(row, *, latest=None):
    manifest = row.manifest if isinstance(row.manifest, dict) else {}
    database_metadata = manifest.get('database_metadata')
    catalog_snapshot = isinstance(database_metadata, dict) and database_metadata.get('catalog_inventory_snapshot') is True
    base = manifest.get('incremental_base')
    export = manifest.get('search_index_export')
    index_task = export.get('task_uid') if isinstance(export, dict) else None
    scope = "完整数据库与增量原件（依赖全量基准）" if row.incremental_base_id else "数据库、文件清单与原件" if row.include_originals else "数据库与文件清单"
    scope = '检索索引（独立导出）' if row.index_only else scope + ('及检索索引' if row.include_indexes else '')
    size = manifest.get("archive_bytes")
    duration = (row.completed_at - row.started_at).total_seconds() if row.completed_at and row.started_at else None
    error = "备份未完成，现有归档及原件保留。请核对备份目录、数据库备份工具与后台任务。" if row.status == "failed" else ""
    stalled = backup_stalled(row)
    return {"id": str(row.pk), "status": row.status, "status_label": "执行状态待核对" if stalled else row.get_status_display(),
        "stalled": stalled, "version": row.updated_at.isoformat(),
        "include_originals": row.include_originals, "scope": scope,
        "include_indexes": row.include_indexes, "index_only": row.index_only,
        "index_task_uid": index_task if type(index_task) is int else None,
        "index_export_unknown": bool(export) and type(index_task) is not int,
        "index_detail": ('包含同一检索实例的全部索引、文档与设置。索引导出与数据库不共享事务快照，恢复需隔离核对公开/私人边界及索引代次；不包含本地模型文件。' if row.include_indexes else ''),
        "incremental_base_id": str(row.incremental_base_id) if row.incremental_base_id else None,
        "incremental_base_checksum": base.get('archive_sha256','') if isinstance(base,dict) else '',
        "can_seed_incremental": bool(row.status=='completed' and row.include_originals and not row.incremental_base_id and latest and latest.status=='completed' and latest.expected_checksum==row.checksum),
        "consistency_detail": ('此为独立索引归档，不含数据库及原件。' if row.index_only else "此归档记录数据库、馆藏文件清单与迁移记录来自同一快照；原件按该清单的哈希复制，恢复仍须隔离核对。" if catalog_snapshot else
                               "此记录尚未提供数据库与馆藏清单共享快照的证据。旧备份不会自动升级此标记，须在隔离恢复时核对。"),
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
    """A recent window for existing summaries; full history has its own cursor."""
    from .restore_history import report_window
    page = report_window(checksum=checksum, limit=50)
    limited = bool(page['next_after'] or page['directory_errors'] or page['unverified_count'] or page['source_status'] == 'unavailable')
    return page['results'], limited


def storage_snapshot(actor, *, page=1, status="", as_of=None):
    from .storage_cleanup import retention_policy
    from .models import StorageCleanupPlan
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
    schedules = {row.scope: row for row in BackupSchedule.objects.select_related("last_job", "incremental_base").all()}
    rehearsals, reports_limited = restore_reports() if can_backup else ([], False)
    can_cleanup = can_backup and has_capability(actor, Capability.DESTRUCTIVE_MAINTENANCE)
    cleanup_rows = StorageCleanupPlan.objects.filter(requested_by=actor).order_by("-created_at", "-id")
    latest_cleanup = (cleanup_rows.filter(status__in=["queued", "running"]).values_list("pk", flat=True).first()
        or cleanup_rows.values_list("pk", flat=True).first()) if can_cleanup else None
    return {"checked_at": timezone.now(), "permissions": {"can_backup": can_backup, "can_verify": can_backup, "can_prepare_restore": can_backup, "can_cleanup": can_cleanup},
        "locations": [_location("library", "馆藏主目录", settings.MEDIA_ROOT),
            _location("originals", "原件目录", settings.NAS_ORIGINAL_ROOT), _location("public", "公开派生文件", settings.NAS_PUBLIC_ROOT),
            _location("backups", "本地备份目录", settings.NAS_BACKUP_ROOT)],
        "file_types": files, "catalog_file_bytes": sum(row["bytes"] for row in files),
        "categories": [{"label": "原件与扫描文件", "bytes": sum(max(0, row["bytes"] or 0) for row in stats if row["kind"] == "original")},
            {"label": "登记的阅读派生文件", "bytes": sum(max(0, row["bytes"] or 0) for row in stats if row["kind"] != "original")},
            {"label": "数据库与索引", "bytes": None}, {"label": "系统与其他", "bytes": None}],
        "file_statistics_notice": "分类数值来自登记的馆藏文件；不包含未登记缓存、模型、数据库或索引，不能代替所在卷实际占用。",
        "schedule": {"configured": any(row.enabled for row in schedules.values()),
            "detail": "原任务服务执行数据库、全量或增量原件、独立索引计划。索引备份需同一实例导出目录的只读挂载；配置存在不代表运行可用。索引与数据库快照的时点分别核对。",
            "plans": [schedule_payload(scope, schedules.get(scope)) for scope in ("originals", "incremental", "database", "indexes")]},
        "index_backup_configured": index_backup_configured(),
        "backups": {"count": count, "page": page, "page_size": 20, "as_of": as_of, "results": [backup_payload(row, latest=latest.get(row.pk)) for row in page_rows]},
        "verifications": [verification_payload(row) for row in BackupVerification.objects.order_by("-created_at", "-id")[:30]],
        "rehearsals": rehearsals, "rehearsals_limited": reports_limited,
        "retention_policy": retention_policy(),
        "retention": [{"label": "原件与历史文件", "duration_label": "不自动到期", "policy": "保留原件及已有历史版本", "detail": "不按缓存清理规则删除。"},
            {"label": "账户与私人资料", "duration_label": "本人设置与账户规则", "policy": "账户身份保留；私人内容按本人设置", "detail": "维护页面不会变更读者的保存偏好或删除私人记录。"},
            {"label": "模型与活动索引", "duration_label": "未设自动到期", "policy": "保护当前在用版本", "detail": "重建不等于已获准删除旧版本，须单独核对依赖。"},
            {"label": "衍生文件与缓存", "duration_label": "按清单核对", "policy": "先核对具体影响", "detail": "现有登记不足以证明文件可删时，保持保护。"}],
        "cleanup": {"status": "not_scanned", "can_execute": can_cleanup, "candidate_count": None, "candidate_bytes": None,
            "latest_id": str(latest_cleanup) if latest_cleanup else None,
            "protected_count": sum(row["count"] for row in files),
            "detail": "原件、阅读派生文件、媒体与历史版本受保护。只扫描已完成上传的专用导入临时目录，不将 OCR 成果、缩略图或未登记文件当作垃圾。"}}


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
    if operation in {"save_retention", "scan_cleanup", "queue_cleanup", "cancel_cleanup"}:
        from .storage_cleanup import command
        return {"request_id": str(identifier), "operation": operation, **command(actor, values)}
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
        row.include_indexes = scope == 'indexes' or values.get('include_indexes', False)
        if values['enabled'] and row.include_indexes and not index_backup_configured():
            raise ValidationError('同一索引实例的导出共享目录尚未配置，无法启用索引备份计划。')
        if scope == 'incremental' and values.get('base_backup_id') and (values['enabled'] or values['base_backup_id'] != row.incremental_base_id):
            from .incremental_backup import require_base
            from .backup_integrity import BackupIntegrityError
            try:
                row.incremental_base = require_base(values['base_backup_id'], values.get('expected_base_checksum'))
            except BackupIntegrityError as error:
                raise ValidationError(str(error)) from error
        elif scope != 'incremental':
            row.incremental_base = None
        row.enabled = values["enabled"]
        row.interval_hours = values["interval_hours"]
        row.next_run_at = values.get("first_run_at") if row.enabled else None
        row.configured_by = actor
        row.last_error = ""
        if row.enabled and row.last_job_id and BackupJob.objects.filter(pk=row.last_job_id, status='failed', include_indexes=True).exists():
            # Explicit schedule save acknowledges the old failure. Its job and
            # remote receipt remain in history; beat itself never retries it.
            row.last_job = None
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
            if existing.requested_by_id != actor.pk or existing.include_originals != values["include_originals"] or existing.incremental_base_id != values.get('base_backup_id') or existing.include_indexes != values.get('include_indexes', False) or existing.index_only != values.get('index_only', False):
                raise StorageConflict("请求编号已用于不同的备份。")
            return {"request_id": str(identifier), "operation": operation, "backup": backup_payload(existing)}
        destination = settings.NAS_BACKUP_ROOT.resolve()
        if not destination.is_dir():
            raise ValidationError("配置的备份目录尚不可用，请先核对存储挂载。")
        source_id = values.get("retry_from_id")
        source = None
        if values.get('include_indexes') and not index_backup_configured():
            raise ValidationError('索引备份导出共享目录尚未配置。现有数据库与原件备份仍可使用。')
        if source_id:
            source = BackupJob.objects.filter(pk=source_id, status="failed").first()
            if source is None or source.include_originals != values["include_originals"] or source.incremental_base_id != values.get('base_backup_id') or source.include_indexes != values.get('include_indexes', False) or source.index_only != values.get('index_only', False):
                raise StorageConflict("原备份状态或范围已变化，请重新读取失败记录。")
        base = None
        manifest = {}
        if values.get('base_backup_id'):
            from .incremental_backup import require_base, base_identity
            from .backup_integrity import BackupIntegrityError
            try:
                base = require_base(values['base_backup_id'], values['expected_base_checksum'])
            except BackupIntegrityError as error:
                raise ValidationError(str(error)) from error
            manifest = {'incremental_base':base_identity(base)}
        if source and source.include_indexes and isinstance(source.manifest, dict) and source.manifest.get('search_index_export'):
            export = source.manifest['search_index_export']
            if not isinstance(export, dict) or type(export.get('task_uid')) is not int:
                raise StorageConflict('原索引导出响应未知。请核对远端任务；不能自动重发。明确需要另一次导出时，从发起备份新建任务。')
            manifest['search_index_export'] = export
        job = BackupJob.objects.create(pk=identifier, requested_by=actor, destination_path=str(destination), include_originals=values["include_originals"], incremental_base=base, manifest=manifest,
            include_indexes=values.get('include_indexes', False), index_only=values.get('index_only', False))
        AuditEvent.objects.create(actor=actor, action="storage_backup_requested", object_type="BackupJob", object_id=str(job.pk), request_id=str(identifier),
            after={"include_originals": job.include_originals, "include_indexes": job.include_indexes, "index_only": job.index_only, "retry_from_id": str(source_id) if source_id else None, **manifest})
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
    verified = backup.verifications.filter(expected_checksum=backup.checksum).order_by('-created_at', '-pk').first()
    if verified and verified.status != 'completed':
        verified = None
    if verified and backup.incremental_base_id:
        from .incremental_backup import require_base
        from .backup_integrity import BackupIntegrityError
        identity = backup.manifest.get('incremental_base', {}) if isinstance(backup.manifest, dict) else {}
        try:
            if not isinstance(identity, dict) or not identity.get('archive_sha256'):
                raise BackupIntegrityError('完整基准身份缺失。')
            require_base(backup.incremental_base_id, identity['archive_sha256'])
        except BackupIntegrityError:
            verified = None
    return {"request_id": str(identifier), "operation": "restore_plan", "restore_plan": {
        "backup_id": str(backup.pk), "archive_name": Path(backup.archive_path).name, "archive_sha256": backup.checksum,
        "integrity_verified_at": verified.completed_at if verified else None, "restore_executed": False,
        "ready_for_rehearsal": bool(verified), "target": "全新隔离 Meilisearch 实例" if backup.index_only else "空白隔离 PostgreSQL 数据库",
        "command": "meilisearch --import-dump <隔离目录/search-index.dump>" if backup.index_only else "rehearse_database_restore", "report_option": "" if backup.index_only else "--write-report",
        "requirements": ([f"这是增量原件归档，必须同时保留完整基准 {backup.incremental_base_id}；恢复仅提取本次清单列明的原件，不把基准已删旧文件全部重新公开。"] if backup.incremental_base_id else []) +
            (["先校验归档与索引导出文件；仅在全新隔离实例导入，不指向活动索引目录。",
              "保留源Meilisearch版本；不得向更旧版本导入。模型、运行凭据与网络配置不由此归档恢复。",
              "索引包含实例全部文档与设置。导入可能恢复旧任务，隔离环境须阻断对生产API、Provider和私有数据服务的访问。",
              "核对索引代次、应用映射、公开撤回状态与私人数据授权后才能考虑接入；不直接切换当前实例。",
              "索引校验不产生数据库恢复签名报告；索引导入与查询验收仍须独立登记。"] if backup.include_indexes else []) +
            ([] if backup.index_only else ["先完成归档、数据库文件和所包含原件的校验。",
              "目标必须为空白隔离数据库，名称明确含rehearsal/restore/test等标记，并逐字确认数据库名。",
              "rehearse_database_restore的--expected-sha256填写本清单archive_sha256；使用--write-report保存签名演练记录。",
              "沿既有命令检查PostgreSQL客户端与服务器版本；索引与数据库不共享事务时点，导入成功不代表整站恢复。", "导入后核对账号、文件、索引映射与业务。"])+
            ["生产恢复或不可逆清理须另行提交具体影响与回退方案，并取得最终确认。"]}}
