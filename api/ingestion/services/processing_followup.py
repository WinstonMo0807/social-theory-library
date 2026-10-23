"""Explicit post-OCR alignment over the existing theory review service."""
from django.db import transaction
from django.utils import timezone

from catalog.models import Asset, Edition
from catalog.services.document_outline import _source_current
from catalog.services.editorial_issues import EditConflict
from ingestion.models import AuditEvent, ProcessingJob


def followup_state(job):
    if getattr(job, "job_type", "") != "ocr":
        return None
    stats = job.stats or {}
    enabled = (stats.get("after_processing") or {}).get("align_concepts", True) is not False
    recorded = stats.get("concept_alignment") or {}
    state = recorded.get("state")
    if state not in {"running", "completed", "skipped", "disabled", "failed"}:
        if stats.get("theory_suggestion_warning"):
            state = "failed"
        elif isinstance(stats.get("theory_suggestions"), dict):
            state = "completed" if stats["theory_suggestions"].get("enabled", True) else "disabled"
        else:
            state = "waiting" if job.status in {"pending", "running", "paused", "failed"} else "unrecorded"
    counts = stats.get("theory_suggestions")
    if not isinstance(counts, dict):
        counts = {}
    return {"enabled": enabled, "state": state,
            "retry_url": f"/admin/processing?task_id={stats['concept_retry_job_id']}&task_source=processing_job" if stats.get("concept_retry_job_id") else "",
            "can_configure": state == "waiting" and job.status in {"pending", "running", "paused", "failed"},
            "counts": {key: value for key in ("created", "updated", "new_node_tasks", "protected_nodes")
                       if type(value := counts.get(key)) is int and value >= 0}}


def configure_followup(job, *, enabled, actor):
    state = followup_state(job)
    if state is None or not state["can_configure"]:
        raise EditConflict("后续对齐已经开始或此任务不支持调整，请读取最新任务状态。")
    from .catalog_ocr import ensure_source_current
    try:
        ensure_source_current(job)
    except ValueError as exc:
        raise EditConflict(str(exc)) from exc
    job.stats = {**job.stats, "after_processing": {"align_concepts": enabled}}
    job.save(update_fields=["stats", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="processing.configure_followup", object_type="processing_job",
        object_id=str(job.pk), before={"align_concepts": state["enabled"]}, after={"align_concepts": enabled})
    return {"job_id": str(job.pk), "status": job.status, "align_concepts": enabled}


def _locked_job(job):
    from .processing import OCRClaimSuperseded
    Edition.objects.select_for_update().get(pk=job.edition_id)
    current = ProcessingJob.objects.select_for_update(of=("self",)).select_related("asset__edition").filter(
        pk=job.pk, task_id=job.task_id, status="running").first()
    if current is None:
        raise OCRClaimSuperseded()
    current.asset = Asset.objects.select_for_update(of=("self",)).select_related("edition").get(pk=current.asset_id)
    _source_current(current.asset)
    if current.asset.sha256 != (current.stats.get("source_sha256") or current.asset.sha256):
        raise ValueError("原文件已变化，不能继续生成概念候选。")
    if ProcessingJob.objects.filter(edition_id=job.edition_id, job_type="ocr", created_at__gt=current.created_at).exclude(status="canceled").exists():
        raise ValueError("此版本已有新的识别任务，请核对当前材料后处理概念。")
    return current


def run_concept_followup(job):
    from .processing import generate_theory_review_tasks
    with transaction.atomic():
        current = _locked_job(job)
        state = followup_state(current)
        if state["state"] in {"completed", "skipped", "disabled"}:
            return current.stats.get("theory_suggestions") or {"enabled": False}
        next_state = "running" if state["enabled"] else "skipped"
        current.stats = {**current.stats, "concept_alignment": {"state": next_state, "at": timezone.now().isoformat()}}
        current.save(update_fields=["stats", "updated_at"])
        if not state["enabled"]:
            return {"enabled": False}
    try:
        # The original review writes share the task/source lock. A late worker
        # cannot write suggestions after cancellation or source replacement.
        with transaction.atomic():
            current = _locked_job(job)
            result = generate_theory_review_tasks(current.asset, actor=current.created_by, force=False)
            current.stats = {**current.stats, "theory_suggestions": result,
                "concept_alignment": {"state": "completed" if result.get("enabled", True) else "disabled", "at": timezone.now().isoformat()}}
            current.save(update_fields=["stats", "updated_at"])
            return result
    except Exception:
        with transaction.atomic():
            current = ProcessingJob.objects.select_for_update().filter(pk=job.pk, task_id=job.task_id, status="running").first()
            if current:
                current.stats = {**current.stats, "concept_alignment": {"state": "failed", "at": timezone.now().isoformat()}}
                current.save(update_fields=["stats", "updated_at"])
        raise
