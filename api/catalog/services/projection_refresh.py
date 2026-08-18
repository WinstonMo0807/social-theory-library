"""Bounded, retryable projection refreshes for the 2.7 back office.

The source models remain authoritative.  This module only coordinates the
existing QueryLexicon, semantic-index and candidate jobs for one explicitly
selected target.  It never scans the whole catalogue and never changes an
authority field or publication state.
"""

from __future__ import annotations

from hashlib import sha256
import uuid

from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError as KombuOperationalError

from catalog.models import Asset, Edition, KnowledgeNode, Person, Topic, Work
from ingestion.models import ProcessingJob


TARGET_MODELS = {
    "work": Work,
    "edition": Edition,
    "asset": Asset,
    "person": Person,
    "knowledge_node": KnowledgeNode,
    "topic": Topic,
}


def _target(target_type: str, target_id: str):
    model = TARGET_MODELS.get(str(target_type or "").strip().casefold())
    if model is None:
        raise ValueError("不支持的投影目标类型。")
    row = model.objects.filter(pk=target_id).first()
    if row is None:
        raise ValueError("投影目标不存在。")
    return row


def _idempotency_key(target_type: str, target) -> str:
    marker = f"{target_type}:{target.pk}:{target.updated_at.isoformat()}"
    digest = sha256(marker.encode("utf-8")).hexdigest()[:20]
    return f"projection-refresh:{target_type}:{target.pk}:{digest}"[:128]


def dispatch_projection_refresh_job(job_id: str, task_id: str) -> bool:
    from catalog.tasks import run_projection_refresh

    try:
        run_projection_refresh.apply_async(
            args=[job_id],
            task_id=task_id,
            ignore_result=True,
        )
    except (KombuOperationalError, OSError, ConnectionError, TimeoutError) as exc:
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(
            status=ProcessingJob.Status.FAILED,
            error_code="queue_unavailable",
            error_message=f"投影刷新任务未进入队列：{exc}"[:4000],
            finished_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return False
    return True


@transaction.atomic
def queue_projection_refresh(*, target_type: str, target_id: str, actor=None, force: bool = False) -> ProcessingJob:
    target_type = str(target_type or "").strip().casefold()
    target = _target(target_type, target_id)
    key = _idempotency_key(target_type, target)
    job = ProcessingJob.objects.filter(idempotency_key=key).first()
    if job is None:
        job = ProcessingJob.objects.create(
            job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
            status=ProcessingJob.Status.PENDING,
            engine="projection-refresh-v1",
            task_id=str(uuid.uuid4()),
            idempotency_key=key,
            correlation_id=str(uuid.uuid4()),
            created_by=actor,
            stats={"target_type": target_type, "target_id": str(target.pk)},
        )
        transaction.on_commit(
            lambda job_id=str(job.id), task_id=job.task_id: dispatch_projection_refresh_job(job_id, task_id)
        )
        return job

    if job.status in {ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING} and not force:
        return job
    if job.status == ProcessingJob.Status.SUCCEEDED and not force:
        return job

    task_id = str(uuid.uuid4())
    stats = dict(job.stats or {})
    stats["manual_retry"] = {
        "requested_at": timezone.now().isoformat(),
        "previous_status": job.status,
    }
    job.status = ProcessingJob.Status.PENDING
    job.task_id = task_id
    job.attempt = 0
    job.progress = 0
    job.error_code = ""
    job.error_message = ""
    job.error_kind = ""
    job.started_at = None
    job.finished_at = None
    job.stats = stats
    if actor is not None and job.created_by_id is None:
        job.created_by = actor
    job.save(
        update_fields=[
            "status",
            "task_id",
            "attempt",
            "progress",
            "error_code",
            "error_message",
            "error_kind",
            "started_at",
            "finished_at",
            "stats",
            "created_by",
            "updated_at",
        ]
    )
    transaction.on_commit(
        lambda job_id=str(job.id), task_id=task_id: dispatch_projection_refresh_job(job_id, task_id)
    )
    return job


def _claim(job_id: str, task_id: str) -> tuple[ProcessingJob, bool]:
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().get(pk=job_id)
        if task_id and job.task_id != task_id:
            return job, False
        if job.status not in {ProcessingJob.Status.PENDING, ProcessingJob.Status.FAILED}:
            return job, False
        if job.status == ProcessingJob.Status.FAILED and job.attempt >= job.max_attempts:
            return job, False
        job.status = ProcessingJob.Status.RUNNING
        job.attempt += 1
        job.progress = max(job.progress, 5)
        job.started_at = timezone.now()
        job.finished_at = None
        job.error_code = ""
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "attempt",
                "progress",
                "started_at",
                "finished_at",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return job, True


def _ready_assets(target_type: str, target) -> list[Asset]:
    if target_type == "asset":
        return [target]
    if target_type == "edition":
        return list(target.assets.filter(is_current=True).order_by("created_at")[:24])
    if target_type == "work":
        return list(
            Asset.objects.filter(
                edition__work_id=target.pk,
                is_current=True,
            ).order_by("created_at")[:24]
        )
    return []


def _refresh_target(target_type: str, target, actor=None) -> dict:
    from catalog.services.query_lexicon.sync import process_pending_events
    from ingestion.services.processing import queue_query_lexicon_candidate_job
    from catalog.services.semantic_indexing import queue_semantic_job

    result: dict = {
        "target_type": target_type,
        "target_id": str(target.pk),
        "query_lexicon": process_pending_events(limit=100),
        "semantic_jobs": [],
        "candidate_jobs": [],
        "bounded": True,
    }
    for asset in _ready_assets(target_type, target):
        if not asset.semantic_chunks.filter(index_status="ready").exists():
            result["semantic_jobs"].append({"asset_id": str(asset.pk), "status": "skipped_no_ready_chunks"})
            result["candidate_jobs"].append({"asset_id": str(asset.pk), "status": "skipped_no_ready_chunks"})
            continue
        semantic = queue_semantic_job(asset, force=False, actor=actor)
        result["semantic_jobs"].append(
            {"asset_id": str(asset.pk), "job_id": str(semantic.id) if semantic else None, "status": semantic.status if semantic else "not_created"}
        )
        candidate = queue_query_lexicon_candidate_job(asset, actor=actor, force=False)
        result["candidate_jobs"].append(
            {"asset_id": str(asset.pk), "job_id": str(candidate.id), "status": candidate.status}
        )
    return result


def run_projection_refresh_job(job_id: str, *, task_id: str = "") -> ProcessingJob:
    job, claimed = _claim(job_id, task_id)
    if not claimed:
        return job
    try:
        stats = dict(job.stats or {})
        target_type = str(stats.get("target_type") or "").strip().casefold()
        target_id = str(stats.get("target_id") or "")
        target = _target(target_type, target_id)
        stats.update(_refresh_target(target_type, target, actor=job.created_by))
        job.status = ProcessingJob.Status.SUCCEEDED
        job.progress = 100
        job.stats = stats
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "progress", "stats", "finished_at", "updated_at"])
        return job
    except Exception as exc:
        job.status = ProcessingJob.Status.FAILED
        job.error_code = exc.__class__.__name__
        job.error_message = str(exc)[:4000]
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error_code", "error_message", "finished_at", "updated_at"])
        raise
