from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from ingestion.models import DecisionLog, EntityResolutionCandidate, ReviewTask


class ReviewTaskActionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ReviewTaskActionResult:
    task: ReviewTask
    idempotent: bool


def _entity_resolution_pending(task: ReviewTask) -> bool:
    if task.task_type != "entity_resolution" or not task.upload_item_id:
        return False
    source_name = str((task.details or {}).get("source_name") or "").strip()
    query = EntityResolutionCandidate.objects.filter(
        upload_item_id=task.upload_item_id,
        target_type=task.target_type,
        status=EntityResolutionCandidate.Status.PROPOSED,
    )
    if source_name:
        query = query.filter(source_name=source_name)
    return query.exists()


def _query_lexicon_candidate_pending(task: ReviewTask) -> bool:
    if task.task_type != "query_lexicon_candidates":
        return False
    work_id = str((task.details or {}).get("work_id") or task.target_id or "").strip()
    if not work_id:
        return False
    from catalog.models import QueryLexiconCandidate

    return QueryLexiconCandidate.objects.filter(
        status=QueryLexiconCandidate.Status.PENDING,
        evidence_records__work_id=work_id,
        evidence_records__is_current=True,
    ).exists()


@transaction.atomic
def apply_review_task_action(
    task: ReviewTask,
    *,
    action: str,
    actor,
    reason: str = "",
    correlation_id: str = "",
) -> ReviewTaskActionResult:
    task = ReviewTask.objects.select_for_update().get(pk=task.pk)
    before = {
        "status": task.status,
        "assigned_to_id": str(task.assigned_to_id or ""),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_by_id": str(task.completed_by_id or ""),
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
    }
    now = timezone.now()
    idempotent = False
    if action in {"start", "assign_self"}:
        if task.status == ReviewTask.Status.COMPLETED:
            raise ReviewTaskActionError("已完成任务需要先恢复为待处理。")
        if task.status == ReviewTask.Status.CANCELLED:
            raise ReviewTaskActionError("已取消任务需要先恢复为待处理。")
        idempotent = task.status == ReviewTask.Status.IN_PROGRESS and task.assigned_to_id == actor.id
        task.status = ReviewTask.Status.IN_PROGRESS
        task.assigned_to = actor
        task.started_at = task.started_at or now
        task.completed_by = None
        task.completed_at = None
    elif action == "complete":
        if task.status == ReviewTask.Status.COMPLETED:
            idempotent = True
        elif _entity_resolution_pending(task):
            raise ReviewTaskActionError("该实体仍有待判断候选，请先完成实体决定。")
        elif _query_lexicon_candidate_pending(task):
            raise ReviewTaskActionError("该作品仍有待审核术语候选，请先接受或拒绝。")
        else:
            task.status = ReviewTask.Status.COMPLETED
            task.assigned_to = task.assigned_to or actor
            task.started_at = task.started_at or now
            task.completed_by = actor
            task.completed_at = now
    elif action == "reopen":
        if task.status == ReviewTask.Status.PENDING:
            idempotent = True
        else:
            task.status = ReviewTask.Status.PENDING
            task.assigned_to = None
            task.started_at = None
            task.completed_by = None
            task.completed_at = None
    elif action == "cancel":
        if task.status == ReviewTask.Status.CANCELLED:
            idempotent = True
        elif task.status == ReviewTask.Status.COMPLETED:
            raise ReviewTaskActionError("已完成任务不能直接取消，请先恢复。")
        else:
            task.status = ReviewTask.Status.CANCELLED
            task.completed_by = actor
            task.completed_at = now
    else:
        raise ReviewTaskActionError("不支持的审核任务操作。")

    task.save(
        update_fields=[
            "status",
            "assigned_to",
            "started_at",
            "completed_by",
            "completed_at",
            "updated_at",
        ]
    )
    if not idempotent:
        DecisionLog.objects.create(
            upload_item=task.upload_item,
            review_task=task,
            actor=actor,
            action=f"review_task_{action}",
            target_type=task.target_type,
            target_id=task.target_id,
            before=before,
            after={
                "status": task.status,
                "assigned_to_id": str(task.assigned_to_id or ""),
                "completed_by_id": str(task.completed_by_id or ""),
            },
            reason=reason,
            correlation_id=correlation_id,
        )
    return ReviewTaskActionResult(task=task, idempotent=idempotent)
