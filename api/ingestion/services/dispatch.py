"""Durable dispatch for PDF ingestion tasks.

The database is the source of truth for task state.  Celery's result backend is
deliberately not used because losing that optional Redis connection must not
lose an uploaded PDF or hide its progress from the administration UI.
"""

from __future__ import annotations

from datetime import timedelta
import uuid

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from ingestion.models import ProcessingAttempt, UploadItem

from .prerequisites import initial_ingestion_ready, initial_ingestion_ready_query


TERMINAL_STATUSES = {
    UploadItem.Status.PUBLISHED,
    UploadItem.Status.WITHDRAWN,
    UploadItem.Status.DELETED,
}

ACTIVE_STATUSES = {
    UploadItem.Status.VALIDATING,
    UploadItem.Status.DEDUPLICATING,
    UploadItem.Status.EXTRACTING,
    UploadItem.Status.OCR,
    UploadItem.Status.METADATA,
    UploadItem.Status.LINKING,
    UploadItem.Status.INDEXING,
    UploadItem.Status.PREPARING_PUBLIC_ASSET,
    UploadItem.Status.SYNCING_CLOUD,
}


def _task_for_kind(kind: str):
    # Import lazily so task auto-discovery can import the pipeline without a
    # circular import through this module.
    from ingestion.tasks import process_reviewed_upload_item, process_upload_item

    if kind == UploadItem.DispatchKind.REVIEWED:
        return process_reviewed_upload_item
    return process_upload_item


def _record_dispatch_attempt(item: UploadItem, *, status: str, error: Exception | None = None) -> None:
    ProcessingAttempt.objects.create(
        upload_item=item,
        stage="task_dispatch",
        attempt_number=max(1, item.dispatch_attempts),
        status=status,
        finished_at=timezone.now(),
        output_summary={
            "task_id": item.dispatch_task_id,
            "kind": item.dispatch_kind,
        },
        error_code=error.__class__.__name__ if error else "",
        error_message=str(error)[:4000] if error else "",
        log_excerpt=(
            "任务已经写入后台队列。"
            if error is None
            else "PDF 已安全保存，但任务队列暂时不可用，系统会自动再次派发。"
        ),
    )


def dispatch_upload_item(item_id: str, task_id: str) -> bool:
    """Publish one already-persisted dispatch to Celery without raising to HTTP."""

    item = UploadItem.objects.filter(pk=item_id).first()
    if item is None or item.dispatch_task_id != task_id or item.status in TERMINAL_STATUSES:
        return False
    if not initial_ingestion_ready(item, kind=item.dispatch_kind):
        defer_initial_dispatch(item.id, task_id)
        return False
    task = _task_for_kind(item.dispatch_kind)
    try:
        task.apply_async(args=[str(item.id)], task_id=task_id, ignore_result=True)
    except Exception as exc:
        now = timezone.now()
        UploadItem.objects.filter(pk=item.id, dispatch_task_id=task_id).update(
            dispatch_status=UploadItem.DispatchStatus.FAILED,
            dispatch_error=str(exc)[:4000],
            error_code="queue_unavailable",
            error_message=(
                "PDF 已经保存，后台任务队列暂时不可用。"
                "系统将在 Redis 与 worker 恢复后自动重新派发。"
            ),
            updated_at=now,
        )
        item.refresh_from_db()
        _record_dispatch_attempt(item, status="failed", error=exc)
        return False

    now = timezone.now()
    # A fast worker may already have changed PENDING to RUNNING.  Never move
    # that state backwards to QUEUED.
    UploadItem.objects.filter(
        pk=item.id,
        dispatch_task_id=task_id,
        dispatch_status=UploadItem.DispatchStatus.PENDING,
    ).update(
        dispatch_status=UploadItem.DispatchStatus.QUEUED,
        dispatch_error="",
        last_dispatched_at=now,
        updated_at=now,
    )
    item.refresh_from_db()
    _record_dispatch_attempt(item, status="queued")
    return True


def schedule_upload_item(
    item_id: str,
    *,
    kind: str = UploadItem.DispatchKind.INITIAL,
    force: bool = False,
) -> str | None:
    """Persist a dispatch and publish it after the surrounding transaction commits."""

    with transaction.atomic():
        item = UploadItem.objects.select_for_update().filter(pk=item_id).first()
        if item is None or item.status in TERMINAL_STATUSES:
            return None
        if not initial_ingestion_ready(item, kind=kind):
            return None
        recent_cutoff = timezone.now() - timedelta(
            seconds=settings.INGESTION_QUEUE_STALLED_SECONDS
        )
        if (
            not force
            and item.dispatch_status
            in {UploadItem.DispatchStatus.QUEUED, UploadItem.DispatchStatus.RUNNING}
            and item.last_dispatched_at
            and item.last_dispatched_at > recent_cutoff
        ):
            return item.dispatch_task_id or None

        task_id = str(uuid.uuid4())
        item.dispatch_status = UploadItem.DispatchStatus.PENDING
        item.dispatch_kind = kind
        item.dispatch_task_id = task_id
        item.dispatch_attempts += 1
        item.last_dispatched_at = timezone.now()
        item.dispatch_error = ""
        if item.error_code == "queue_unavailable":
            item.error_code = ""
            item.error_message = ""
        item.save(
            update_fields=[
                "dispatch_status",
                "dispatch_kind",
                "dispatch_task_id",
                "dispatch_attempts",
                "last_dispatched_at",
                "dispatch_error",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        transaction.on_commit(
            lambda current_id=str(item.id), current_task_id=task_id: dispatch_upload_item(
                current_id,
                current_task_id,
            )
        )
        return task_id


def defer_initial_dispatch(item_id: str, task_id: str) -> bool:
    """Release an obsolete INITIAL task without recording a queue failure."""

    updated = UploadItem.objects.filter(
        pk=item_id,
        dispatch_kind=UploadItem.DispatchKind.INITIAL,
        dispatch_task_id=task_id,
    ).update(
        dispatch_status=UploadItem.DispatchStatus.PENDING,
        dispatch_task_id="",
        dispatch_error="",
        last_dispatched_at=None,
        updated_at=timezone.now(),
    )
    return bool(updated)


def mark_dispatch_running(item_id: str, task_id: str) -> bool:
    now = timezone.now()
    updated = UploadItem.objects.filter(
        pk=item_id,
        dispatch_task_id=task_id,
    ).exclude(status__in=TERMINAL_STATUSES).update(
        dispatch_status=UploadItem.DispatchStatus.RUNNING,
        dispatch_error="",
        error_code="",
        error_message="",
        last_dispatched_at=now,
        updated_at=now,
    )
    return bool(updated)


def mark_dispatch_finished(item_id: str, task_id: str, *, error: Exception | None = None) -> None:
    values = {
        "dispatch_status": (
            UploadItem.DispatchStatus.FAILED
            if error
            else UploadItem.DispatchStatus.COMPLETED
        ),
        "dispatch_error": str(error)[:4000] if error else "",
        "updated_at": timezone.now(),
    }
    UploadItem.objects.filter(pk=item_id, dispatch_task_id=task_id).update(**values)


def recover_ingestion_dispatches(*, limit: int = 100) -> dict[str, int]:
    """Requeue uploads left behind by an API, Redis, or worker restart."""

    now = timezone.now()
    stage_cutoff = now - timedelta(seconds=settings.INGESTION_STAGE_STALLED_SECONDS)
    initial_ready = initial_ingestion_ready_query()
    dispatch_ready = (
        Q(dispatch_kind=UploadItem.DispatchKind.REVIEWED)
        | (Q(dispatch_kind=UploadItem.DispatchKind.INITIAL) & initial_ready)
    )
    candidates = list(
        UploadItem.objects.filter(
            Q(
                status=UploadItem.Status.RECEIVED,
                dispatch_status__in=[
                    UploadItem.DispatchStatus.PENDING,
                    UploadItem.DispatchStatus.FAILED,
                ],
            )
            & dispatch_ready
            | Q(
                status__in=ACTIVE_STATUSES,
                updated_at__lte=stage_cutoff,
            )
            & dispatch_ready
            | Q(
                status=UploadItem.Status.READY,
                dispatch_kind=UploadItem.DispatchKind.REVIEWED,
                dispatch_status__in=[
                    UploadItem.DispatchStatus.PENDING,
                    UploadItem.DispatchStatus.FAILED,
                ],
            )
        )
        .exclude(status__in=TERMINAL_STATUSES)
        .order_by("updated_at")[: max(1, min(limit, 500))]
    )
    scheduled = 0
    reset = 0
    for item in candidates:
        if not initial_ingestion_ready(item, kind=item.dispatch_kind):
            continue
        if item.status in ACTIVE_STATUSES:
            UploadItem.objects.filter(pk=item.id, updated_at__lte=stage_cutoff).update(
                status=UploadItem.Status.RECEIVED,
                stage_progress=0,
                dispatch_status=UploadItem.DispatchStatus.PENDING,
                error_code="worker_interrupted",
                error_message="上一次后台处理被中断，系统正在从安全检查阶段重新执行。",
                updated_at=timezone.now(),
            )
            reset += 1
        # A successfully published QUEUED message remains owned by Redis and
        # Celery.  Replacing its task id merely because a long-running worker
        # delayed it leaves the old message in the broker and can starve the
        # newest replacement indefinitely.  Automatic recovery is therefore
        # limited to dispatches that never reached the broker, explicit broker
        # failures, and interrupted active stages.
        task_id = schedule_upload_item(
            str(item.id),
            kind=item.dispatch_kind,
            force=True,
        )
        if task_id:
            scheduled += 1
    return {"candidates": len(candidates), "scheduled": scheduled, "reset": reset}
