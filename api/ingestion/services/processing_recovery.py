"""Current activity and explicit recovery through the original task queues."""
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import SemanticIndexJob
from catalog.services.editorial_issues import EditConflict
from ingestion.models import AuditEvent


def recovery_state(job, *, now=None):
    now = now or timezone.now()
    stats = job.stats or {}
    result = {"state": "inactive", "last_activity_at": None, "activity_kind": "none", "eligible_at": None,
              "can_recover": False, "notice": "当前任务不在排队或执行中。"}
    if job.status not in {"pending", "queued", "running"}:
        return result
    if isinstance(job, SemanticIndexJob):
        result.update(state="unsupported", last_activity_at=job.updated_at, activity_kind="checkpoint",
                      notice="此历史索引任务沿原维护入口恢复，请先核对索引与任务状态。")
        return result
    discovery = job.job_type == "discovery_index"
    if discovery:
        from catalog.services.discovery_indexing import discovery_recovery_window
        last, seconds = discovery_recovery_window(job)
        if seconds is None:
            result.update(state="waiting_sources", last_activity_at=job.updated_at, activity_kind="checkpoint",
                          notice="全库索引正在等待各来源任务汇总。协调任务此时不持续发送心跳，请在索引维护中查看各来源进度。")
            return result
        activity = "checkpoint" if job.status == "running" else "queue"
    else:
        seconds = settings.INGESTION_STAGE_STALLED_SECONDS if job.status == "running" else settings.INGESTION_QUEUE_STALLED_SECONDS
        last = (job.heartbeat_at or job.started_at) if job.status == "running" else job.updated_at
        activity = ("heartbeat" if job.heartbeat_at else "started") if job.status == "running" else "queue"
    eligible = last + timedelta(seconds=seconds) if last else None
    stale = bool(eligible and now >= eligible)
    supported = (discovery and stats.get("action") in {"build", "source"}
                 or job.job_type == "ocr" or job.job_type == "text_extraction" and stats.get("operation") in {"outline_rebuild", "outline_export", "page_mapping_export"})
    exhausted = job.attempt >= job.max_attempts or discovery and job.status == "running" and job.attempt + 1 >= job.max_attempts
    allowed = supported and stale and not exhausted and not stats.get("retry_replacement_id")
    state = "recoverable" if allowed else "delayed" if stale else "waiting" if job.status == "pending" else "active"
    notice = "已超过本任务的恢复保护期。可继续等待，也可核对原材料后重新派发；已保存结果保留。" if stale else "尚在原任务保护期内，请继续等待；心跳或检查点未更新并不能单独证明处理服务已经退出。"
    if exhausted:
        notice = "此任务已达到恢复次数边界，请等待原恢复机制标记结果，再从失败任务核对并明确重试。"
    elif not supported:
        notice = "此任务类型沿原处理入口和自动恢复机制处理，当前面板不直接重新派发。"
    elif stats.get("retry_replacement_id"):
        notice = "已有接续任务，请查看接续任务；原记录与结果保留。"
    elif not last:
        notice = "此历史任务尚无可核对的活动时间，不能据此重新派发。请从原处理入口核对服务和任务记录。"
    elif job.pause_requested_at:
        notice += " 本任务已请求暂停，核对恢复时优先保存为暂停状态。"
    result.update(state=state, last_activity_at=last, activity_kind=activity if last else "none", eligible_at=eligible,
                  can_recover=allowed, notice=notice)
    return result


def recover_processing_task(job, actor):
    """Caller owns the account, original parent and task locks and request receipt."""
    state = recovery_state(job)
    if not state["can_recover"]:
        raise EditConflict("任务状态或活动记录已变化，当前不能重新派发。请重新读取后核对。")
    before = {"status": job.status, "task_id": job.task_id, "heartbeat_at": str(job.heartbeat_at or ""),
              "updated_at": str(job.updated_at), "attempt": job.attempt, "error_code": job.error_code,
              "error_message": job.error_message, "pause_requested": bool(job.pause_requested_at)}
    if job.job_type == "discovery_index":
        from catalog.services.discovery_indexing import recover_interrupted_job
        from catalog.services.discovery_projection import DiscoveryIndexError
        try:
            job = recover_interrupted_job(job.pk)
        except DiscoveryIndexError as exc:
            raise EditConflict(str(exc)) from exc
    else:
        try:
            if job.job_type == "ocr":
                from .catalog_ocr import check_resume_source
                check_resume_source(job)
            elif job.job_type == "text_extraction" and job.stats.get("operation") in {"outline_rebuild", "outline_export", "page_mapping_export"}:
                from catalog.services.document_outline import _source_current
                _source_current(job.asset)
                if job.stats.get("operation") in {"outline_export", "page_mapping_export"}:
                    from catalog.services.outline_exports import current_export_revision
                    current_export_revision(job.asset, job.stats)
                document = job.asset.document_revisions.filter(is_active=True).first()
                if (job.asset.sha256 != job.stats.get("source_sha256")
                        or str(document.pk if document else "") != str(job.stats.get("document_revision_id") or "")):
                    raise EditConflict("原目录任务的文件或正文修订已变化，请从当前材料新建任务。")
            else:
                raise ValidationError("请从该任务的原处理入口恢复。")
        except ValueError as exc:
            raise EditConflict(str(exc)) from exc
        from .processing import recover_stalled_processing_jobs
        result = recover_stalled_processing_jobs(limit=1, job_id=job.pk)
        if not result["candidates"]:
            raise EditConflict("任务已恢复活动或不再符合恢复条件，请重新读取。")
        job.refresh_from_db()
    AuditEvent.objects.create(actor=actor, action="processing.recover_from_checkpoint", object_type="processing_job",
        object_id=str(job.pk), before=before, after={"status": job.status, "task_id": job.task_id, "attempt": job.attempt})
    return {"job_id": str(job.pk), "status": job.status, "recovery_requested": True}
