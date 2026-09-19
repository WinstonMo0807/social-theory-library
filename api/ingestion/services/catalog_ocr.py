"""Edition-scoped commands and read-only progress over the existing OCR jobs."""
from hashlib import sha256
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.exceptions import ValidationError, NotFound

from common.capabilities import Capability, has_capability
from catalog.models import Asset, Edition, KnowledgePublicationEvent
from ingestion.models import AuditEvent, ProcessingJob
from .ocr_provider import ocr_runtime_config
from .processing import (
    queue_ocr_job, processing_workload_paused, request_processing_job_pause,
    resume_processing_job,
)


ACTIVE = [ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING, ProcessingJob.Status.PAUSED]


def identifier(value, label):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({label: ["请选择有效的对象。"]})


def edition_for(value, *, lock=False):
    query = Edition.objects.select_related("work", "active_catalog_revision")
    if lock:
        query = query.select_for_update(of=("self",))
    edition = query.filter(pk=identifier(value, "edition_id")).first()
    if edition is None:
        raise NotFound("未找到所选出版版本。")
    return edition


def source_problem(asset):
    if asset.kind != Asset.Kind.NORMALIZED or not asset.is_current:
        return "请选择当前出版版本的阅读文件，历史文件不能直接重跑。"
    if asset.status != Asset.Status.READY or asset.validation_status != Asset.ValidationStatus.VALID:
        return "文件尚未通过 PDF 校验，请先处理文件问题。"
    if not asset.file or asset.page_count < 1:
        return "文件缺少 PDF 或有效页数。"
    return ""


def ensure_source_current(job):
    """Called again under the edition lock before writes and publication."""
    stats = job.stats or {}
    if stats.get("requested_mode") != "all_pages":
        return
    source = Asset.objects.filter(pk=stats.get("requested_asset_id"), edition_id=job.edition_id).first()
    if not source or source_problem(source) or source.sha256 != stats.get("source_sha256") or source.page_count != stats.get("total_pages"):
        raise ValueError("识别来源已更换或不再有效；本次结果保留但不能覆盖新文件，请重新选择当前 PDF。")
    if ProcessingJob.objects.filter(edition_id=job.edition_id, job_type="ocr", created_at__gt=job.created_at).exclude(status="canceled").exists():
        raise ValueError("此版本已有较新的 OCR 任务，旧任务不能覆盖新结果。")
    if job.edition.catalog_revisions.filter(status="preparing", created_at__gt=job.created_at, reader_asset__isnull=False).exclude(reader_asset_id__in=[source.pk, job.asset_id]).exists():
        raise ValueError("此版本正在发布另一份阅读文件，请先完成文件更新。")


def progress_row(job, *, actor, event=None, edition=None):
    stats = job.stats or {}
    total = stats.get("target_pages")
    done = stats.get("processed_pages")
    total = total if isinstance(total, int) and total > 0 else None
    done = min(total, max(0, done)) if total and isinstance(done, int) else None
    phase = str(stats.get("ocr_phase") or "")
    labels = {"preparing": "正在准备 PDF", "recognizing": "正在识别文字", "finalizing": "文字识别已完成，正在整理结果", "pdf": "文字识别已完成，正在准备阅读文件", "publishing": "正在提交公开内容更新", "complete": "识别任务已完成"}
    state_labels = {"pending": "等待处理", "paused": "已暂停，已完成页数保留", "failed": "识别中断", "canceled": "本次识别已取消", "succeeded": "识别任务已完成"}
    label = labels.get(phase, "正在处理") if job.status == "running" else state_labels.get(job.status, "状态待核实")
    if job.status == "pending" and done:
        label = "已保存当前页，等待继续识别"
    public = "本次识别不会发布未公开的书目。"
    if edition:
        from catalog.services.publication_commands import catalog_publication_state

    if edition and catalog_publication_state(edition)["catalog_revision_active"]:
        public = "当前已公开版本保持可用，新文字尚未确认公开。"
    if event and event.catalog_revision_id:
        revision = event.catalog_revision
        if edition and edition.state == "published" and edition.active_catalog_revision_id == revision.pk and revision.status == "active" and revision.metadata_ready:
            public = "这次文字结果已经公开；搜索等后续更新以处理记录为准。"
        elif revision.status == "superseded":
            public = "这次文字结果已由较新的公开版本替代，历史仍保留。"
        elif event.status in {"failed", "dead_letter"} or revision.status == "failed":
            public = "文字识别已保存，但公开更新失败，稳定旧版仍保留；请到本版本发布区检查并恢复。"
        else:
            public = "文字识别已保存，公开更新仍在处理，不等于新文字已经公开。"
    allowed = has_capability(actor, Capability.RETRY_JOBS) and stats.get("requested_mode") == "all_pages"
    phase_at = parse_datetime(str(stats.get("phase_started_at") or "")) or job.started_at or job.created_at
    if timezone.is_naive(phase_at):
        phase_at = timezone.make_aware(phase_at)
    return {
        "id": str(job.pk), "status": job.status, "phase": phase, "phase_label": label,
        "completed_pages": done, "total_pages": total, "percent": round(done * 100 / total, 1) if done is not None and total else None,
        "active_pages": stats.get("active_page_indexes", []) if job.status == "running" else [],
        "updated_at": job.updated_at, "started_at": stats.get("session_started_at") or job.started_at,
        "phase_elapsed_seconds": max(0, int(((job.finished_at or timezone.now()) - phase_at).total_seconds())),
        "stale": job.status in {"pending", "running"} and (timezone.now() - job.updated_at).total_seconds() > 90,
        "error": job.error_message if job.status == "failed" else "",
        "warnings": [str(stats[key]) for key in ["ocr_pdf_warning", "page_label_warning", "front_matter_warning", "theory_suggestion_warning"] if stats.get(key)],
        "source_asset_id": str(stats.get("requested_asset_id") or stats.get("text_source_asset_id") or job.asset_id or ""),
        "result_asset_id": str(job.asset_id or ""), "public_result": public,
        "workbench_url": f"/admin/library/works/{edition.work_id}?edition={edition.pk}#publication" if edition else "",
        "can_pause": allowed and job.status in {"pending", "running"},
        "can_resume": allowed and job.status in {"paused", "failed"} and job.attempt < job.max_attempts,
        "can_cancel": allowed and job.status in {"paused", "pending", "failed"},
    }


def ocr_context(edition, actor, *, page=1):
    from .processing_identity import edition_titles
    jobs_query = ProcessingJob.objects.filter(edition=edition, job_type="ocr").order_by("-created_at", "-id")
    count = jobs_query.count()
    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        raise ValidationError({"ocr_page": ["页码必须是整数。"]})
    page = min(page, max(1, (count + 9) // 10))
    jobs = list(jobs_query[(page - 1) * 10:page * 10])
    event_ids = [row.stats.get("knowledge_publication_event_id") for row in jobs if row.stats.get("knowledge_publication_event_id")]
    events = {str(row.pk): row for row in KnowledgePublicationEvent.objects.filter(pk__in=event_ids).select_related("catalog_revision")}
    mode = ocr_runtime_config()["mode"]
    can_run = has_capability(actor, Capability.RETRY_JOBS)
    return {
        "edition_id": str(edition.pk), "work_id": str(edition.work_id), **edition_titles([edition])[str(edition.work_id)],
        "edition_label": edition.version_label or "当前出版版本", "can_run": can_run,
        "denied_reason": "" if can_run else "当前账户可查看识别结果；发起、暂停和恢复 OCR 需要管理员或系统所有者权限。",
        "paused": processing_workload_paused("ocr"),
        "provider_label": {"nas_only": "NAS OCR 服务", "nas_preferred": "NAS OCR 服务（不可用时按现有配置尝试远程服务）", "remote_only": "配置的远程 OCR 服务"}[mode],
        "files": [{"id": str(asset.pk), "filename": asset.original_filename or "阅读 PDF", "version": asset.version, "page_count": asset.page_count,
                   "source_version": asset.updated_at.isoformat(), "can_run": not bool(source_problem(asset)), "reason": source_problem(asset)}
                  for asset in edition.assets.filter(kind=Asset.Kind.NORMALIZED, is_current=True).order_by("-version", "-id")],
        "jobs": [progress_row(row, actor=actor, event=events.get(row.stats.get("knowledge_publication_event_id")), edition=edition) for row in jobs],
        "job_count": count, "page": page, "total_pages": max(1, (count + 9) // 10),
        "active_job_id": str(jobs_query.filter(status__in=ACTIVE).values_list("pk", flat=True).first() or ""),
        "checked_at": timezone.now(),
    }


@transaction.atomic
def start_catalog_ocr(data, actor):
    edition = edition_for(data.get("edition_id"), lock=True)
    asset_id = identifier(data.get("asset_id"), "asset_id")
    request_id = str(identifier(data.get("request_id"), "request_id"))
    if data.get("confirmed") is not True:
        raise ValidationError({"confirmed": ["请确认重新识别这份 PDF 及服务使用范围。"]})
    fingerprint = sha256(f"{edition.pk}:{asset_id}:{data.get('source_version', '')}".encode()).hexdigest()
    receipt = AuditEvent.objects.filter(actor=actor, action="catalog.ocr.start", request_id=request_id).first()
    if receipt:
        if receipt.after.get("fingerprint") != fingerprint:
            raise ValueError("同一次请求不能更换出版版本或 PDF，请重新确认。")
        job = ProcessingJob.objects.get(pk=receipt.after["job_id"], edition=edition)
        return job, True
    asset = edition.assets.filter(pk=asset_id).first()
    if asset is None:
        raise ValidationError({"asset_id": ["这份 PDF 不属于当前出版版本。"]})
    problem = source_problem(asset)
    if problem:
        raise ValueError(problem)
    if data.get("source_version") != asset.updated_at.isoformat():
        raise ValueError("文件已经更新，请重新读取并选择当前 PDF，再确认识别。")
    active = ProcessingJob.objects.filter(edition=edition, job_type="ocr", status__in=ACTIVE).first()
    if active:
        if active.stats.get("requested_mode") != "all_pages" or active.stats.get("requested_asset_id") != str(asset.pk):
            raise ValueError("此版本已有未结束的识别任务，请先核对并完成或取消它。")
        job = active
    else:
        job = queue_ocr_job(asset, actor=actor, force=True)
        job.idempotency_key = f"catalog-ocr:{actor.pk}:{request_id}"
        job.stats = {**job.stats, "requested_mode": "all_pages", "requested_asset_id": str(asset.pk), "source_sha256": asset.sha256,
                     "source_version": asset.updated_at.isoformat(), "total_pages": asset.page_count, "target_pages": asset.page_count,
                     "processed_pages": 0, "completed_page_indexes": [], "remaining_pages": asset.page_count, "ocr_phase": "queued"}
        job.save(update_fields=["stats", "idempotency_key", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="catalog.ocr.start", object_type="edition", object_id=str(edition.pk), request_id=request_id,
                              after={"job_id": str(job.pk), "asset_id": str(asset.pk), "fingerprint": fingerprint, "mode": "all_pages"})
    return job, bool(active)


@transaction.atomic
def catalog_ocr_action(data, actor):
    edition = edition_for(data.get("edition_id"), lock=True)
    job = ProcessingJob.objects.select_for_update(of=("self",)).select_related("edition").filter(pk=identifier(data.get("job_id"), "job_id"), edition=edition, job_type="ocr").first()
    if not job or job.stats.get("requested_mode") != "all_pages":
        raise ValueError("请选择这个版本的人工识别任务；旧暂停任务请在处理中心核对后恢复。")
    action = data.get("action")
    before = job.status
    if action == "pause_catalog_ocr":
        job = request_processing_job_pause(job)
    elif action == "resume_catalog_ocr":
        ensure_source_current(job)
        if job.status in {"pending", "running"}:
            return job
        if job.status == "failed":
            if job.attempt >= job.max_attempts:
                raise ValueError("已达到重试次数，请检查服务后取消旧任务，再明确发起新识别。")
            job.status = "paused"
            job.stats = {**job.stats, "batch_session_started": False}
            job.save(update_fields=["status", "stats", "updated_at"])
        job = resume_processing_job(job, actor=actor)
    elif action == "cancel_catalog_ocr":
        if job.status == "canceled":
            return job
        if job.status not in {"pending", "paused", "failed"}:
            raise ValueError("请先安全暂停，当前页保存完成后再取消。")
        job.status, job.task_id, job.finished_at = "canceled", "", timezone.now()
        job.save(update_fields=["status", "task_id", "finished_at", "updated_at"])
    else:
        raise ValidationError({"action": ["不支持的识别操作。"]})
    AuditEvent.objects.create(actor=actor, action=f"catalog.ocr.{action}", object_type="processing_job", object_id=str(job.pk), before={"status": before}, after={"status": job.status})
    return job
