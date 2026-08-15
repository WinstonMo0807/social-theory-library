from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import uuid4

from django.db import transaction
from django.utils import timezone

from ingestion.models import AuditEvent, ProcessingAttempt, UploadItem


class InvalidWorkflowTransition(ValueError):
    pass


LEGACY_STATUS_WORKFLOW = {
    UploadItem.Status.RECEIVED: UploadItem.WorkflowState.UPLOADED,
    UploadItem.Status.VALIDATING: UploadItem.WorkflowState.PREFLIGHT,
    UploadItem.Status.DEDUPLICATING: UploadItem.WorkflowState.PREFLIGHT,
    UploadItem.Status.EXTRACTING: UploadItem.WorkflowState.PARSING,
    UploadItem.Status.OCR: UploadItem.WorkflowState.PARSING,
    UploadItem.Status.METADATA: UploadItem.WorkflowState.ENRICHING,
    UploadItem.Status.LINKING: UploadItem.WorkflowState.RESOLVING,
    UploadItem.Status.NEEDS_REVIEW: UploadItem.WorkflowState.NEEDS_REVIEW,
    UploadItem.Status.READY: UploadItem.WorkflowState.READY,
    UploadItem.Status.INDEXING: UploadItem.WorkflowState.INDEXING,
    UploadItem.Status.PREPARING_PUBLIC_ASSET: UploadItem.WorkflowState.INDEXING,
    UploadItem.Status.SYNCING_CLOUD: UploadItem.WorkflowState.INDEXING,
    UploadItem.Status.PUBLISHED: UploadItem.WorkflowState.PUBLISHED,
    UploadItem.Status.FAILED: UploadItem.WorkflowState.FAILED,
    UploadItem.Status.WITHDRAWN: UploadItem.WorkflowState.ARCHIVED,
    UploadItem.Status.DELETED: UploadItem.WorkflowState.ARCHIVED,
}


ALLOWED_TRANSITIONS = {
    UploadItem.WorkflowState.UPLOADED: {
        UploadItem.WorkflowState.PREFLIGHT,
        UploadItem.WorkflowState.PARSING,
        UploadItem.WorkflowState.ENRICHING,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.PREFLIGHT: {
        UploadItem.WorkflowState.PARSING,
        UploadItem.WorkflowState.ENRICHING,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.PARSING: {
        UploadItem.WorkflowState.ENRICHING,
        UploadItem.WorkflowState.INDEXING,
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.ENRICHING: {
        UploadItem.WorkflowState.PARSING,
        UploadItem.WorkflowState.RESOLVING,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.RESOLVING: {
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.NEEDS_REVIEW: {
        UploadItem.WorkflowState.ENRICHING,
        UploadItem.WorkflowState.RESOLVING,
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.INDEXING,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.READY: {
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.APPROVED,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.ARCHIVED,
        UploadItem.WorkflowState.INDEXING,
    },
    UploadItem.WorkflowState.APPROVED: {
        UploadItem.WorkflowState.INDEXING,
        UploadItem.WorkflowState.PUBLISHED,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.INDEXING: {
        UploadItem.WorkflowState.PUBLISHED,
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.FAILED,
    },
    UploadItem.WorkflowState.PUBLISHED: {
        UploadItem.WorkflowState.INDEXING,
        UploadItem.WorkflowState.ARCHIVED,
    },
    UploadItem.WorkflowState.FAILED: {
        UploadItem.WorkflowState.PREFLIGHT,
        UploadItem.WorkflowState.PARSING,
        UploadItem.WorkflowState.ENRICHING,
        UploadItem.WorkflowState.RESOLVING,
        UploadItem.WorkflowState.INDEXING,
        UploadItem.WorkflowState.NEEDS_REVIEW,
        UploadItem.WorkflowState.CANCELLED,
        UploadItem.WorkflowState.ARCHIVED,
    },
    UploadItem.WorkflowState.CANCELLED: {
        UploadItem.WorkflowState.PREFLIGHT,
        UploadItem.WorkflowState.ARCHIVED,
    },
    UploadItem.WorkflowState.ARCHIVED: {
        UploadItem.WorkflowState.READY,
        UploadItem.WorkflowState.PUBLISHED,
    },
}


@dataclass(frozen=True, slots=True)
class WorkflowTransitionResult:
    changed: bool
    previous: str
    current: str
    correlation_id: str


def legacy_workflow_state(status: str) -> str:
    try:
        return LEGACY_STATUS_WORKFLOW[status]
    except KeyError as exc:
        raise InvalidWorkflowTransition(f"未定义旧状态 {status} 对应的上架阶段。") from exc


def transition_upload_item(
    item: UploadItem,
    target_state: str,
    *,
    actor=None,
    reason: str = "",
    correlation_id: str = "",
    force: bool = False,
) -> WorkflowTransitionResult:
    allowed_values = {value for value, _label in UploadItem.WorkflowState.choices}
    if target_state not in allowed_values:
        raise InvalidWorkflowTransition(f"未知的上架阶段：{target_state}")
    correlation_id = correlation_id or uuid4().hex
    with transaction.atomic():
        locked = UploadItem.objects.select_for_update().get(pk=item.pk)
        previous = locked.workflow_state
        if previous == target_state:
            return WorkflowTransitionResult(False, previous, target_state, correlation_id)
        if not force and target_state not in ALLOWED_TRANSITIONS.get(previous, set()):
            raise InvalidWorkflowTransition(
                f"上架阶段不能从 {previous} 直接切换到 {target_state}。"
            )
        locked.workflow_state = target_state
        locked.workflow_updated_at = timezone.now()
        locked.save(update_fields=["workflow_state", "workflow_updated_at", "updated_at"])
        AuditEvent.objects.create(
            actor=actor,
            action="upload_workflow_transition",
            object_type="UploadItem",
            object_id=str(locked.id),
            before={"workflow_state": previous},
            after={
                "workflow_state": target_state,
                "reason": reason,
                "correlation_id": correlation_id,
            },
            request_id=correlation_id,
        )
    item.workflow_state = target_state
    item.workflow_updated_at = locked.workflow_updated_at
    return WorkflowTransitionResult(True, previous, target_state, correlation_id)


def idempotency_key_for_stage(item: UploadItem, stage: str, input_fingerprint: str) -> str:
    fingerprint = input_fingerprint.strip() or "no-input-fingerprint"
    dispatch = item.dispatch_task_id or f"retry-{item.retry_count}"
    digest = sha256(f"{fingerprint}:{dispatch}".encode("utf-8")).hexdigest()[:32]
    return f"upload:{item.id}:{stage}:{digest}"[:128]


def invalidate_downstream_attempts(
    item: UploadItem,
    *,
    stages: set[str],
    reason: str,
) -> int:
    now = timezone.now()
    attempts = item.attempts.filter(
        stage__in=stages,
        invalidated_at__isnull=True,
    )
    count = attempts.count()
    attempts.update(
        invalidated_at=now,
        output_summary={"invalidated": True, "reason": reason},
        updated_at=now,
    )
    return count
