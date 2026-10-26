"""Pin a checkpoint to an existing OCR service, without changing global settings."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
import json
from uuid import uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent
from .ocr_provider import OCRConfigurationError, OCR_MODEL_ID, ocr_runtime_config

active_ocr_config = ContextVar("active_ocr_config", default=None)
TARGETS = {"nas": "NAS OCR 服务", "remote": "配置的远程 OCR 服务"}


def target_version(config, target):
    values = ([config["nas_url"], OCR_MODEL_ID] if target == "nas" else
              [config["remote_url"], config["remote_model"], settings.OCR_REMOTE_API_KEY])
    return sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def configured(config, target):
    return bool(config["nas_url"] if target == "nas" else
                config["remote_url"] and config["remote_model"] and config["remote_key_configured"])


def can_transfer(job):
    if getattr(job, "job_type", "") != "ocr" or job.pause_requested_at:
        return False
    if job.stats.get("ocr_phase", "") not in {"", "queued", "preparing", "recognizing"}:
        return False  # Finalization must finish its original publication transaction.
    if job.status in {"failed", "paused"}:
        return not job.stats.get("retry_replacement_id")
    from .processing_recovery import recovery_state
    return recovery_state(job)["can_recover"]


def transfer_state(job, actor, config):
    if getattr(job, "job_type", "") != "ocr":
        return None
    binding = job.stats.get("ocr_service_binding") or {}
    allowed = all(has_capability(actor, capability) for capability in
                  (Capability.RETRY_JOBS, Capability.VIEW_SYSTEM_STATUS, Capability.MANAGE_AI))
    current = binding.get("target", "")
    return {"current": current, "current_label": TARGETS.get(current, "沿全站 OCR 服务配置"),
            "configuration_changed": bool(current in TARGETS and binding.get("version") != target_version(config, current)),
            "can_transfer": allowed and can_transfer(job),
            "targets": [{"id": target, "label": label, "configured": configured(config, target),
                         "version": target_version(config, target), "external": target == "remote"}
                        for target, label in TARGETS.items()]}


def resolve_bound_config(binding):
    config = ocr_runtime_config()
    if not binding:
        return config
    target = binding.get("target")
    if (target not in TARGETS or not configured(config, target)
            or binding.get("version") != target_version(config, target)):
        raise OCRConfigurationError("指定的 OCR 服务配置已变化或不可用，请重新核对目标服务；已保存页面保留。")
    return {**config, "mode": "nas_only" if target == "nas" else "remote_only"}


@contextmanager
def bound_ocr_service(binding):
    token = active_ocr_config.set(resolve_bound_config(binding))
    try:
        yield
    finally:
        active_ocr_config.reset(token)


def transfer_ocr_job(job, *, actor, target, version, acknowledge_remote=False):
    """Caller holds the account, edition and job locks and fixed request receipt."""
    from .catalog_ocr import check_resume_source
    from .processing import dispatch_ocr_job, processing_workload_paused
    if not has_capability(actor, Capability.MANAGE_AI):
        from rest_framework.exceptions import PermissionDenied
        raise PermissionDenied("当前账户不能更改任务使用的 OCR 服务。")
    if not can_transfer(job) or processing_workload_paused("ocr"):
        raise EditConflict("任务已恢复活动、正在整理结果或处于暂停保护中，请刷新后核对。")
    config = ocr_runtime_config()
    if target not in TARGETS or not configured(config, target) or version != target_version(config, target):
        raise EditConflict("目标服务配置已变化或不完整，请重新读取后选择。")
    if target == "remote" and not acknowledge_remote:
        raise EditConflict("请明确确认将待识别页面发送到已配置的远程 OCR 服务。")
    check_resume_source(job, manual_retry=job.status == "failed")
    before = {"status": job.status, "task_id": job.task_id, "attempt": job.attempt,
              "error_code": job.error_code, "error_message": job.error_message,
              "binding": job.stats.get("ocr_service_binding"), "processed_pages": job.stats.get("processed_pages")}
    if job.status == "failed":
        job.attempt = 0
    job.stats = {**job.stats, "ocr_service_binding": {"target": target, "version": version},
                 "batch_session_started": False, "service_activity": "unavailable"}
    job.task_id, job.status = str(uuid4()), "pending"
    job.started_at = job.heartbeat_at = job.finished_at = None
    job.error_code = job.error_message = ""
    job.save(update_fields=["stats", "task_id", "status", "started_at", "heartbeat_at", "finished_at",
                            "error_code", "error_message", "attempt", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="processing.transfer_ocr", object_type="processing_job",
        object_id=str(job.pk), before=before, after={"binding": job.stats["ocr_service_binding"],
            "task_id": job.task_id, "acknowledged_remote": target == "remote", "requested_at": timezone.now().isoformat()})
    transaction.on_commit(lambda jid=str(job.pk), tid=job.task_id: dispatch_ocr_job(jid, tid))
    return {"job_id": str(job.pk), "status": job.status, "target": target}
