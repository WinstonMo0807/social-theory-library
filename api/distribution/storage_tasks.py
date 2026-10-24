from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
import tarfile

from common.capabilities import Capability, has_capability
from .backup_integrity import BackupIntegrityError, verify_archive
from .models import BackupJob, BackupVerification, BackupSchedule
from accounts.models import User
from ingestion.models import AuditEvent


def enqueue_storage_cleanup(identifier):
    from .models import StorageCleanupPlan
    try:
        run_storage_cleanup.apply_async(args=[str(identifier)], ignore_result=True)
    except Exception:
        StorageCleanupPlan.objects.filter(pk=identifier, status="queued").update(status="failed",
            error_message="清理队列暂不可用，尚未开始。请重新扫描后核对，不自动重复提交。", completed_at=timezone.now(), updated_at=timezone.now())


@shared_task(ignore_result=True, soft_time_limit=3500, time_limit=3600)
def run_storage_cleanup(identifier):
    from .storage_cleanup import process_plan
    from .models import StorageCleanupPlan
    try:
        process_plan(identifier)
    except Exception:
        StorageCleanupPlan.objects.filter(pk=identifier, status__in=["queued", "running"]).update(status="failed",
            error_message="清理中断。已有逐项结果保留；未登记结果不能认定未删除，请重新扫描核对。任务不会自动重跑。",
            completed_at=timezone.now(), updated_at=timezone.now())
        raise


def enqueue_authorized_backup(identifier):
    try:
        run_authorized_backup.apply_async(args=[str(identifier)], ignore_result=True)
    except Exception:
        BackupJob.objects.filter(pk=identifier, status="queued").update(status="failed",
            error_message="备份队列暂不可用，请核对任务服务后重新发起备份。", completed_at=timezone.now(), updated_at=timezone.now())


@shared_task(ignore_result=True)
def run_authorized_backup(identifier):
    """Recheck the actor on delivery, then reuse the original archive builder."""
    from .tasks import create_backup_archive
    with transaction.atomic():
        job = BackupJob.objects.select_for_update(of=("self",)).select_related("requested_by").get(pk=identifier)
        if job.status != "queued":
            return
        if not job.requested_by.is_active or not has_capability(job.requested_by, Capability.RUN_BACKUP):
            job.status = "failed"
            job.error_message = "发起账户的备份维护权限已变化，备份未执行。"
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
            return
    return create_backup_archive.run(identifier)


def enqueue_verification(identifier):
    try:
        verify_backup_archive.apply_async(args=[str(identifier)], ignore_result=True)
    except Exception:
        BackupVerification.objects.filter(pk=identifier, status="queued").update(status="failed",
            error_message="校验队列暂不可用，备份归档保留，请重新发起校验。", completed_at=timezone.now(), updated_at=timezone.now())


@shared_task(bind=True, ignore_result=True, soft_time_limit=3500, time_limit=3600)
def verify_backup_archive(self, identifier):
    with transaction.atomic():
        record = BackupVerification.objects.select_for_update(of=("self",)).select_related("backup", "requested_by").get(pk=identifier)
        if record.status != "queued":
            return
        actor = record.requested_by
        if not actor.is_active or not has_capability(actor, Capability.RUN_BACKUP):
            record.status = "failed"
            record.error_message = "发起账户的备份维护权限已变化，校验未执行。"
            record.completed_at = timezone.now()
            record.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
            return
        record.status = "running"
        record.started_at = timezone.now()
        record.save(update_fields=["status", "started_at", "updated_at"])
    try:
        report = verify_archive(record.backup, record.expected_checksum)
    except (BackupIntegrityError, OSError, tarfile.TarError, ValueError, SoftTimeLimitExceeded) as exc:
        message = str(exc) if isinstance(exc, BackupIntegrityError) else "归档校验未完成，请核对文件可读性及工作任务时限。"
        BackupVerification.objects.filter(pk=identifier, status="running").update(status="failed", error_message=message[:500], completed_at=timezone.now(), updated_at=timezone.now())
    except Exception:
        BackupVerification.objects.filter(pk=identifier, status="running").update(status="failed",
            error_message="校验任务异常结束，原归档保留，请核对任务服务后重试。", completed_at=timezone.now(), updated_at=timezone.now())
        raise
    else:
        BackupVerification.objects.filter(pk=identifier, status="running").update(status="completed", report=report, completed_at=timezone.now(), updated_at=timezone.now())


@shared_task(ignore_result=True)
def dispatch_due_backups():
    """Beat dispatches opted-in plans; one outstanding job per plan, no catch-up burst."""
    due = list(BackupSchedule.objects.filter(enabled=True, next_run_at__lte=timezone.now()).order_by("next_run_at").values("pk", "configured_by_id")[:20])
    for item in due:
        with transaction.atomic():
            # Same lock order as interactive configuration: account, then plan.
            actor = User.objects.select_for_update().filter(pk=item["configured_by_id"]).first()
            plan = BackupSchedule.objects.select_for_update().filter(pk=item["pk"], configured_by_id=item["configured_by_id"], enabled=True, next_run_at__lte=timezone.now()).first()
            if plan is None:
                continue
            if not actor or not actor.is_active or not has_capability(actor, Capability.RUN_BACKUP):
                plan.enabled = False
                plan.last_error = "配置账户的备份维护权限已变化，计划已暂停，未创建新任务。"
                plan.save(update_fields=["enabled", "last_error", "updated_at"])
                continue
            if plan.last_job_id and BackupJob.objects.filter(pk=plan.last_job_id, status__in=["queued", "running"]).exists():
                continue
            root = settings.NAS_BACKUP_ROOT.resolve()
            if not root.is_dir():
                plan.last_error = "备份目录暂不可用，本次未创建备份；一小时后重新核对。"
                plan.next_run_at = timezone.now() + timedelta(hours=1)
                plan.save(update_fields=["last_error", "next_run_at", "updated_at"])
                continue
            job = BackupJob.objects.create(requested_by=actor, destination_path=str(root), include_originals=plan.scope == "originals")
            plan.last_job = job
            plan.next_run_at = timezone.now() + timedelta(hours=plan.interval_hours)
            plan.last_error = ""
            plan.save(update_fields=["last_job", "next_run_at", "last_error", "updated_at"])
            AuditEvent.objects.create(actor=actor, action="storage_scheduled_backup_requested", object_type="BackupJob", object_id=str(job.pk), after={"scope": plan.scope, "schedule_id": str(plan.pk)})
            transaction.on_commit(lambda identifier=job.pk: enqueue_authorized_backup(identifier))
