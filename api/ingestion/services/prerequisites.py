"""Read-only prerequisites for the initial PDF ingestion handoff."""

from __future__ import annotations

from django.db.models import Q

from ingestion.models import UploadItem


INITIAL_INGESTION_READY_STAGING_STATUSES = frozenset(
    {
        UploadItem.StagingStatus.IMPORTED,
        UploadItem.StagingStatus.CLEANUP_PENDING,
        UploadItem.StagingStatus.CLEANED,
    }
)

R2_PRE_IMPORT_BLOCK_REASONS = frozenset(
    {
        "staging_not_ready",
        "staging_import_failed",
        "staging_aborted",
        "staging_expired",
    }
)

INITIAL_INGESTION_BLOCK_MESSAGES = {
    "staging_not_ready": "PDF 尚未导入正式书库存储。",
    "staging_import_failed": "PDF 从临时区导入正式书库存储失败，需要重新导入。",
    "staging_aborted": "上传已取消，不能进入入库识别。",
    "staging_expired": "临时上传已过期，需要重新上传 PDF。",
    "staging_import_missing_file": "R2 记录显示已导入，但正式书库存储文件尚未建立。",
    "source_file_missing": "入库记录没有可读取的正式 PDF。",
}


class InitialIngestionPrerequisiteNotReady(RuntimeError):
    """A staged upload has not crossed the R2-to-intake handoff yet."""

    def __init__(self, reason: str):
        self.reason = reason
        self.error_code = reason
        super().__init__(initial_ingestion_block_message(reason))


def _has_file_name(item: UploadItem) -> bool:
    return bool(str(getattr(item.file, "name", "") or "").strip())


def initial_ingestion_block_reason(
    item: UploadItem,
    *,
    kind: str = UploadItem.DispatchKind.INITIAL,
) -> str:
    """Return the canonical reason INITIAL ingestion must not start."""

    if kind == UploadItem.DispatchKind.REVIEWED:
        return ""
    if item.staging_backend == UploadItem.StagingBackend.R2:
        if item.staging_status in INITIAL_INGESTION_READY_STAGING_STATUSES:
            return "" if _has_file_name(item) else "staging_import_missing_file"
        if item.staging_status == UploadItem.StagingStatus.IMPORT_FAILED:
            return "staging_import_failed"
        if item.staging_status == UploadItem.StagingStatus.ABORTED:
            return "staging_aborted"
        if item.staging_status == UploadItem.StagingStatus.EXPIRED:
            return "staging_expired"
        return "staging_not_ready"
    return "" if _has_file_name(item) else "source_file_missing"


def initial_ingestion_ready(
    item: UploadItem,
    *,
    kind: str = UploadItem.DispatchKind.INITIAL,
) -> bool:
    return not initial_ingestion_block_reason(item, kind=kind)


def initial_ingestion_ready_query() -> Q:
    """Database equivalent of ``initial_ingestion_ready`` for INITIAL rows."""

    return ~Q(file="") & (
        Q(staging_backend="")
        | Q(
            staging_backend=UploadItem.StagingBackend.R2,
            staging_status__in=INITIAL_INGESTION_READY_STAGING_STATUSES,
        )
    )


def initial_ingestion_block_message(reason: str) -> str:
    return INITIAL_INGESTION_BLOCK_MESSAGES.get(
        reason,
        "PDF 尚未满足首次入库处理条件。",
    )


def is_r2_pre_import_block(reason: str) -> bool:
    return reason in R2_PRE_IMPORT_BLOCK_REASONS
