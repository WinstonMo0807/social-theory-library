"""Edition-scoped adapters for the existing immutable ingestion pipeline.

An actual file submission owns an UploadItem. It never changes the source of
an existing manual CatalogingSession or invents a file for a manual record.
"""
from hashlib import sha256
from pathlib import PurePosixPath
from uuid import UUID, NAMESPACE_URL, uuid5

from django.conf import settings
from django.db import transaction
from django.utils.dateparse import parse_datetime

from catalog.models import Asset, CatalogPublicationRevision, Edition
from ingestion.models import AuditEvent, UploadBatch, UploadItem
from ingestion.services.dispatch import schedule_upload_item


class EditionFileError(ValueError):
    def __init__(self, detail, *, code="catalog.file_conflict", status=409):
        super().__init__(detail)
        self.code, self.status = code, status


def _pdf_details(uploaded):
    if uploaded is None:
        raise EditionFileError("请选择一个 PDF。", status=400)
    name = PurePosixPath(uploaded.name.replace("\\", "/")).name
    signature = uploaded.read(5)
    uploaded.seek(0)
    if not name or not name.casefold().endswith(".pdf") or signature != b"%PDF-":
        raise EditionFileError("扩展名或文件内容不是 PDF。", code="catalog.invalid_pdf", status=400)
    digest, size = sha256(), 0
    for chunk in uploaded.chunks():
        size += len(chunk)
        if size > settings.MAX_UPLOAD_BYTES:
            raise EditionFileError("文件超过单文件上限。", code="catalog.file_too_large", status=400)
        digest.update(chunk)
    uploaded.seek(0)
    return name, digest.hexdigest(), size


@transaction.atomic
def submit_edition_file(*, edition_id, actor, uploaded, action, request_key=None,
                        expected_updated_at=None, expected_reader_asset_id=None,
                        require_context=True):
    if action not in {"supplement", "replace"}:
        raise EditionFileError("请选择补充文件或替换阅读文件。", status=400)
    name, digest, size = _pdf_details(uploaded)
    # Lock the Edition before checking its reader, the request or other work.
    # All legacy and Edition entry points use this same serialization boundary.
    edition = Edition.objects.select_for_update(of=("self",)).select_related(
        "work", "active_catalog_revision__reader_asset",
    ).filter(pk=edition_id).first()
    if edition is None:
        raise EditionFileError("出版版本不存在。", code="catalog.edition_not_found", status=404)
    try:
        operation_id = UUID(str(request_key)) if request_key else uuid5(
            NAMESPACE_URL, f"stl:edition-file:{edition.pk}:{action}:{digest}",
        )
    except (ValueError, TypeError, AttributeError) as error:
        raise EditionFileError("文件请求标识无效。", status=400) from error
    existing = UploadItem.objects.select_related("batch").filter(pk=operation_id).first()
    if existing:
        if existing.edition_id != edition.pk or existing.sha256 != digest or existing.batch.source != f"edition-{action}":
            raise EditionFileError("此请求标识不能用于当前版本或另一份文件。")
        return existing, False
    duplicate = Asset.objects.filter(kind=Asset.Kind.ORIGINAL, sha256=digest).select_related("edition__work").first()
    if duplicate:
        raise EditionFileError(
            "这份 PDF 已在馆藏中存在，请先核对重复判断；当前作品和出版版本不会自动改绑。",
            code="catalog.duplicate_edition_file",
        )
    if require_context:
        expected = parse_datetime(str(expected_updated_at or ""))
        if expected is None or expected != edition.updated_at:
            raise EditionFileError("出版版本已变化，请刷新并重新核对文件操作。", code="catalog.stale_file_context")
    active = edition.active_catalog_revision
    valid_revision = bool(active and active.edition_id == edition.pk and active.status == "active" and active.metadata_ready and edition.state == "published")
    old_asset = active.reader_asset if valid_revision else None
    if action == "replace":
        if not valid_revision or old_asset is None:
            raise EditionFileError("此版本没有正在公开使用的阅读文件，不能执行已发布文件替换。")
        if old_asset.edition_id != edition.pk or old_asset.kind != Asset.Kind.NORMALIZED or old_asset.status != Asset.Status.READY:
            raise EditionFileError("当前正式阅读文件的归属或状态不允许替换。")
        if require_context and str(expected_reader_asset_id or "") != str(old_asset.pk):
            raise EditionFileError("当前阅读文件已变化，请重新核对替换目标。", code="catalog.stale_reader_asset")
        if CatalogPublicationRevision.objects.filter(
            edition=edition, revision__gt=active.revision, status__in=["preparing", "failed"],
            reader_asset__isnull=False,
        ).exclude(reader_asset=old_asset).exists():
            raise EditionFileError("此版本已有另一阅读文件正在发布或等待恢复，请先完成原文件事项。", code="catalog.file_publication_pending")
    elif edition.assets.exists():
        raise EditionFileError("此出版版本已有文件。请核对当前阅读文件并使用替换操作，不会自动另建作品。")
    access_policy = old_asset.access_status if old_asset else UploadBatch.AccessPolicy.PUBLIC
    if access_policy == Asset.AccessStatus.INHERIT:
        # Existing distribution semantics expose INHERIT for this already
        # published anchor. Explicit restricted policies stay restricted.
        access_policy = UploadBatch.AccessPolicy.PUBLIC
    if access_policy not in UploadBatch.AccessPolicy.values:
        raise EditionFileError("此文件的特殊访问策略尚不支持自动替换，请保留原文件并由管理员核对。")
    unfinished = UploadItem.objects.filter(edition=edition).exclude(
        status__in=["published", "failed", "withdrawn", "deleted"],
    )
    if action == "replace":
        unfinished = unfinished.filter(replacement_of_asset__isnull=False)
    if unfinished.exists():
        raise EditionFileError("此版本已有文件处理事项，请在当前页面查看结果或恢复原任务。")
    batch = UploadBatch.objects.create(
        created_by=actor, source=f"edition-{action}", expected_count=1,
        status=UploadBatch.Status.PROCESSING,
        access_policy=access_policy,
        external_enrichment_enabled=False,
        notes=f"{'替换阅读文件' if action == 'replace' else '补充首份PDF'}：{edition.work.title}",
    )
    item = UploadItem.objects.create(
        id=operation_id, batch=batch, source_filename=name, file=uploaded,
        sha256=digest, byte_size=size, edition=edition, replacement_of_asset=old_asset,
        preflight_summary={"catalog_reconciliation": {
            "mode": "existing_edition", "work_id": str(edition.work_id),
            "edition_id": str(edition.pk), "requires_review": False,
            "decision_source": "explicit_edition_file_request",
        }},
    )
    # The pipeline preserves existing metadata for edition-bound files. Do not
    # overwrite FieldLock values, owners or reasons just to request a new PDF.
    AuditEvent.objects.create(
        actor=actor, action="pdf_replacement_requested" if old_asset else "edition_pdf_supplement_requested",
        object_type="Edition", object_id=str(edition.pk),
        before={"reader_asset_id": str(old_asset.pk) if old_asset else None,
                "active_revision_id": str(active.pk) if valid_revision else None},
        after={"upload_item_id": str(item.pk), "action": action, "sha256": digest,
               "source_filename": name, "work_id": str(edition.work_id)},
    )
    schedule_upload_item(str(item.pk))
    return item, True


def edition_file_result(item, *, created):
    return {
        "accepted": True, "created": created, "request_key": str(item.pk),
        "item_id": str(item.pk), "work_id": str(item.edition.work_id), "edition_id": str(item.edition_id),
        "status": item.status, "dispatch_status": item.dispatch_status,
        "workbench_url": f"/admin/library/works/{item.edition.work_id}?edition={item.edition_id}#file",
        "detail": "文件请求已保存。请查看实际处理与公开结果；旧文件、页标识和私人记录保持不变。",
    }
