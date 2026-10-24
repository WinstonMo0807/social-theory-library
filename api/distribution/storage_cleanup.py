"""Only owned, inactive R2 import leftovers are eligible; all library assets stay protected."""
from datetime import datetime, timedelta
from hashlib import sha256
from itertools import islice
from pathlib import Path
import os
import re
import stat

from django.conf import settings
from django.db import transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from catalog.models import Asset, SiteSetting
from catalog.services.query_lexicon.mutations import acquire_entity_lock
from common.capabilities import Capability, has_capability
from ingestion.models import UploadItem, ProcessingJob, AuditEvent
from ingestion.services.r2_staging import verify_cleanup_original, R2CleanupBlocked, PIPELINE_READY_FOR_CLEANUP
from .models import StorageCleanupPlan
from .storage_workspace import StorageConflict

POLICY_KEY = "storage_transient_retention_v1"
PATTERN = re.compile(r"^([0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})\.[0-9a-f]{32}\.part$")
SCAN_LIMIT = 2000
PLAN_LIMIT = 100


def execution_supported():
    return os.unlink in os.supports_dir_fd and os.open in os.supports_dir_fd and hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY")


def retention_policy():
    row = SiteSetting.objects.filter(key=POLICY_KEY, public=False).first()
    value = row.value.get("temporary_days", 7) if row and isinstance(row.value, dict) else 7
    if not isinstance(value, int) or isinstance(value, bool) or not 7 <= value <= 3650:
        raise StorageConflict("临时文件保留规则无效，请先核对设置。")
    return {"temporary_days": value, "version": row.updated_at.isoformat() if row else "unconfigured",
        "detail": "仅影响已完成导入且脱离任务的遗留临时文件；到期仍须扫描、核对并明确确认，不自动删除。"}


def eligible_uploads():
    active = ProcessingJob.objects.filter(upload_item_id=OuterRef("pk"), status__in=["pending", "running", "paused"])
    return UploadItem.objects.annotate(cleanup_busy=Exists(active)).filter(cleanup_busy=False,
        staging_backend="r2", staging_status__in=["imported", "cleanup_pending", "cleaned"],
        status__in=PIPELINE_READY_FOR_CLEANUP, dispatch_status="completed", asset__kind="original")


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def scan_root():
    parent = Path(settings.NAS_INCOMING_ROOT).resolve(strict=True)
    root = parent / ".r2-imports"
    if root.is_symlink() or root.exists() and (not root.is_dir() or root.resolve().parent != parent):
        raise ValidationError("上传临时目录不能安全核对，请先检查存储挂载。")
    return root


def root_marker(root, info=None):
    info = info or root.stat()
    return sha256(f"{root.resolve()}:{info.st_dev}:{info.st_ino}".encode()).hexdigest()


def plan_payload(plan):
    rows = [{"id": row["id"], "label": "上传临时文件 · " + row["upload_id"][:8], "bytes": row["identity"][2],
        "modified_at": row["modified_at"], "outcome": plan.outcomes.get(row["id"], {}).get("status", "pending"),
        "detail": plan.outcomes.get(row["id"], {}).get("detail", "删除前将再次完整校验永久原件，并核对临时文件未变化。")}
        for row in plan.manifest]
    stale = plan.created_at < timezone.now() - timedelta(hours=1)
    stalled = plan.status in {"queued", "running"} and (plan.started_at or plan.updated_at) < timezone.now() - timedelta(seconds=3700)
    return {"id": str(plan.pk), "status": plan.status, "status_label": "执行状态待核对" if stalled else plan.get_status_display(),
        "version": plan.updated_at.isoformat(), "created_at": plan.created_at, "stale": stale, "stalled": stalled,
        "execution_supported": execution_supported(),
        "retention_days": plan.retention_days, "rows": rows, "selected": plan.selected,
        "candidate_bytes": sum(row["bytes"] for row in rows), "candidate_count": len(rows),
        "released_bytes": sum(row.get("bytes", 0) for row in plan.outcomes.values() if row.get("status") == "deleted"),
        "deleted_count": sum(row.get("status") == "deleted" for row in plan.outcomes.values()),
        "examined_count": plan.scan_summary.get("examined", 0), "protected_count": plan.scan_summary.get("protected", 0),
        "limited": plan.scan_summary.get("limited", False), "notice": plan.scan_summary.get("notice", ""),
        "error_message": plan.error_message, "scope": "已完成上传的遗留导入临时文件；不含阅读文件、OCR 成果、缩略图历史或读者资料。"}


def inspect_plan(actor, identifier):
    row = StorageCleanupPlan.objects.filter(pk=identifier, requested_by=actor).first()
    if not row:
        raise NotFound("本账户的清理清单不存在，请重新扫描。")
    return plan_payload(row)


def scan(actor, identifier):
    policy = retention_policy()
    cutoff = timezone.now() - timedelta(days=policy["temporary_days"])
    pending, examined, protected, limited = [], 0, 0, False
    summary = {"notice": "只扫描已登记上传的专用临时目录。其他缓存缺少独立可删除身份，继续保护。"}
    try:
        root = scan_root()
        if root.exists():
            marker = root_marker(root)
            with os.scandir(root) as entries:
                for entry in islice(entries, SCAN_LIMIT + 1):
                    if examined == SCAN_LIMIT:
                        limited = True; break
                    examined += 1
                    match = PATTERN.fullmatch(entry.name)
                    info = entry.stat(follow_symlinks=False)
                    if not match or not stat.S_ISREG(info.st_mode) or info.st_mtime > cutoff.timestamp():
                        protected += 1; continue
                    pending.append({"name": entry.name, "upload_id": match.group(1), "identity": identity(info)})
            uploads = {str(row.pk): row for row in eligible_uploads().select_related("asset").filter(pk__in={row["upload_id"] for row in pending})}
            manifest = []
            for row in pending:
                item = uploads.get(row["upload_id"])
                if (not item or item.updated_at > cutoff or not item.sha256 or item.sha256 != item.asset.sha256
                        or item.byte_size != item.asset.byte_size or item.byte_size != item.staging_file_size):
                    protected += 1; continue
                if len(manifest) >= PLAN_LIMIT:
                    limited = True; protected += 1; continue
                row.update(id=sha256(row["name"].encode()).hexdigest()[:24], asset_id=str(item.asset_id),
                    original_sha256=item.sha256, modified_at=datetime.fromtimestamp(row["identity"][3]/1e9, tz=timezone.get_current_timezone()).isoformat())
                manifest.append(row)
            if root_marker(root) != marker:
                raise ValidationError("扫描期间存储目录变化，请重新扫描，尚未创建清理清单。")
            summary["root_marker"] = marker
        else:
            manifest = []
            summary["notice"] = "专用上传临时目录尚不存在，本范围没有可清理项。未扫描其他目录，不代表全部存储没有缓存。"
    except OSError as error:
        raise ValidationError("临时目录暂不可读取，扫描未完成；不会按空目录处理。") from error
    summary.update(examined=examined, protected=protected, limited=limited)
    return StorageCleanupPlan.objects.create(pk=identifier, requested_by=actor, retention_days=policy["temporary_days"],
        policy_version=policy["version"], manifest=manifest, scan_summary=summary)


def command(actor, values):
    if not has_capability(actor, Capability.DESTRUCTIVE_MAINTENANCE):
        raise PermissionDenied("当前账户不能调整保留规则或处理清理清单。")
    operation = values["operation"]
    if operation == "save_retention":
        acquire_entity_lock("storage_retention", POLICY_KEY)
        if values["expected_version"] != retention_policy()["version"]:
            raise StorageConflict("保留规则已变化，请读取最新规则后再保存。")
        SiteSetting.objects.update_or_create(key=POLICY_KEY, defaults={"public": False, "updated_by": actor,
            "value": {"temporary_days": values["temporary_days"]}})
        return {"retention_saved": True}
    if operation == "scan_cleanup":
        acquire_entity_lock("storage_cleanup_scan", actor.pk)
        if StorageCleanupPlan.objects.filter(requested_by=actor, status__in=["queued", "running"]).exists():
            raise StorageConflict("已有清理任务尚未结束，请先核对进度或停止后续项目。")
        if StorageCleanupPlan.objects.filter(requested_by=actor, created_at__gt=timezone.now()-timedelta(seconds=30)).exists():
            raise ValidationError("刚刚生成过扫描清单，请先查看已有结果，30秒后可重新扫描。")
        plan = scan(actor, values["request_id"])
    else:
        plan = StorageCleanupPlan.objects.select_for_update().filter(pk=values["cleanup_id"], requested_by=actor).first()
        if not plan:
            raise NotFound("清理清单不存在。")
        if values["expected_version"] != plan.updated_at.isoformat():
            raise StorageConflict("清理状态已变化，请重新读取当前清单。")
        if operation == "cancel_cleanup":
            if plan.status in {"scanned", "queued", "running"}:
                plan.status = "cancelled"; plan.completed_at = timezone.now()
                plan.error_message = "已停止后续项目。此前已完成的删除不可撤回，逐项结果保留；未确认结果须重新扫描。"
                plan.save(update_fields=["status", "completed_at", "error_message", "updated_at"])
        else:
            acquire_entity_lock("storage_cleanup_execution", "local-transients")
            if StorageCleanupPlan.objects.filter(status__in=["queued", "running"]).exclude(pk=plan.pk).exists():
                raise StorageConflict("已有清理任务正在等待或执行，请先核对它的结果。")
            if not execution_supported():
                raise ValidationError("当前运行环境不支持保护式文件定位；可查看清单，但不能执行删除。")
            policy = retention_policy()
            if plan.status != "scanned" or plan.created_at < timezone.now()-timedelta(hours=1) or plan.policy_version != policy["version"]:
                raise StorageConflict("清单已执行、过期或保留规则变化，请重新扫描。")
            selected = values["cleanup_items"]
            if not selected or len(set(selected)) != len(selected) or not set(selected) <= {row["id"] for row in plan.manifest}:
                raise ValidationError("请选择当前清单中的文件，不能重复或扩大范围。")
            if values["confirmation"] != f"清理 {len(selected)} 个临时文件":
                raise ValidationError("请明确核对本次选择的临时文件数量。")
            plan.selected, plan.status = selected, "queued"
            plan.save(update_fields=["selected", "status", "updated_at"])
            from .storage_tasks import enqueue_storage_cleanup
            transaction.on_commit(lambda: enqueue_storage_cleanup(plan.pk))
    return {"cleanup_id": str(plan.pk)}


def delete_transient(plan, row, item):
    if (retention_policy()["version"] != plan.policy_version
            or item.updated_at > timezone.now()-timedelta(days=plan.retention_days)):
        raise R2CleanupBlocked("保留规则或上传记录近期变化，此项保留，请重新扫描。")
    root = scan_root()
    if root_marker(root) != plan.scan_summary.get("root_marker"):
        raise R2CleanupBlocked("存储位置已变化，此项保留。")
    if (not PATTERN.fullmatch(row["name"]) or row["asset_id"] != str(item.asset_id)
            or row["original_sha256"] != item.sha256 or not eligible_uploads().filter(pk=item.pk).exists()):
        raise R2CleanupBlocked("上传任务或永久原件身份已变化，此项保留。")
    asset = Asset.objects.select_for_update().get(pk=item.asset_id)
    if not execution_supported():
        raise R2CleanupBlocked("当前运行环境不支持安全定位清理文件，此项保留。")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        if root_marker(root, os.fstat(directory)) != plan.scan_summary.get("root_marker"):
            raise R2CleanupBlocked("打开时存储目录变化，此项保留。")
        try:
            descriptor = os.open(row["name"], os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=directory)
        except FileNotFoundError:
            return {"status": "missing", "bytes": 0, "detail": "临时文件已不存在；未算作本次释放空间。"}
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or identity(before) != row["identity"]:
                raise R2CleanupBlocked("临时文件变化或仍有关联，此项保留，请重新扫描。")
            verify_cleanup_original(item, asset)
            current = os.stat(row["name"], dir_fd=directory, follow_symlinks=False)
            if identity(current) != row["identity"] or identity(os.fstat(descriptor)) != row["identity"]:
                raise R2CleanupBlocked("校验期间临时文件变化，此项保留。")
            os.unlink(row["name"], dir_fd=directory)
            return {"status": "deleted", "bytes": before.st_size, "detail": "永久原件完整校验通过，只删除本条遗留临时文件。"}
        finally:
            os.close(descriptor)
    finally:
        os.close(directory)


def process_plan(identifier):
    with transaction.atomic():
        plan = StorageCleanupPlan.objects.select_for_update().get(pk=identifier)
        if plan.status != "queued":
            return
        plan.status, plan.started_at = "running", timezone.now()
        plan.save(update_fields=["status", "started_at", "updated_at"])
    for row in plan.manifest:
        if row["id"] not in plan.selected:
            continue
        with transaction.atomic():
            actor = User.objects.select_for_update(no_key=True).filter(pk=plan.requested_by_id, is_active=True).first()
            current = StorageCleanupPlan.objects.select_for_update().get(pk=identifier)
            if current.status != "running":
                return
            if not actor or not has_capability(actor, Capability.DESTRUCTIVE_MAINTENANCE):
                current.status = "failed"; current.error_message = "发起账户的维护权限已变化，剩余项目保留。"
                current.completed_at = timezone.now(); current.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
                return
            if row["id"] in current.outcomes:
                continue
            try:
                item = UploadItem.objects.select_for_update().filter(pk=row["upload_id"]).first()
                if not item:
                    raise R2CleanupBlocked("上传记录已变化，此项保留。")
                outcome = delete_transient(current, row, item)
            except (R2CleanupBlocked, ValidationError) as error:
                outcome = {"status": "protected", "bytes": 0, "detail": str(error)[:300]}
            except OSError:
                outcome = {"status": "failed", "bytes": 0, "detail": "文件无法安全核对或删除，请核对挂载与权限；未计入释放空间。"}
            current.outcomes = {**current.outcomes, row["id"]: outcome}
            current.save(update_fields=["outcomes", "updated_at"])
            AuditEvent.objects.create(actor=actor, action="storage_transient_cleanup_item", object_type="StorageCleanupPlan", object_id=str(current.pk),
                after={"item_id": row["id"], **outcome})
    with transaction.atomic():
        current = StorageCleanupPlan.objects.select_for_update().get(pk=identifier)
        if current.status == "running":
            current.status = "completed" if all(row["status"] == "deleted" for row in current.outcomes.values()) else "partial"
            current.completed_at = timezone.now()
            current.save(update_fields=["status", "completed_at", "updated_at"])
