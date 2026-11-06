"""A separate downloadable PDF from the active automatic or corrected outline."""
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

from django.core.files import File
from django.db import transaction
from django.utils import timezone
from kombu.exceptions import OperationalError

from catalog.models import Asset
from catalog.services.document_outline import OutlineConflict, OutlineJobInterrupted, _source_current, _tree_order
from ingestion.models import AuditEvent, ProcessingJob

OPERATION = "outline_export"
PROCESSOR = "adopted-outline-export"


def current_download_copy(asset):
    """Resolve only the active navigation copy; authorization remains on its reader anchor."""
    active = asset.outline_revisions.filter(is_active=True, source_checksum=asset.sha256).first()
    if not active:
        return None
    try:
        export_revision(asset, active.pk)
    except OutlineConflict:
        return None
    job = ProcessingJob.objects.filter(asset=asset, status="succeeded", stats__operation=OPERATION,
        stats__outline_revision_id=str(active.pk), stats__source_sha256=asset.sha256).order_by("-finished_at").first()
    if not job:
        return None
    return Asset.objects.filter(pk=job.stats.get("result_asset_id"), source_asset=asset, edition=asset.edition,
        kind=Asset.Kind.WEB_DERIVATIVE, processor=PROCESSOR, status="ready", validation_status="valid",
        page_count=asset.page_count, mime_type="application/pdf",
        validation_details__source_sha256=asset.sha256, validation_details__title_page_position_roundtrip=True).exclude(file="").first()


def queue_download_cloud_copy(anchor):
    """Use the anchor's existing publication destination, never a new provider."""
    from distribution.models import CloudObject
    from distribution.services import cloud_budget_allows_new_publication
    from distribution.tasks import sync_cloud_object
    artifact = current_download_copy(anchor)
    if artifact is None:
        return
    for source in anchor.cloud_objects.filter(status="ready", provider__enabled=True).select_related("provider"):
        record, created = CloudObject.objects.get_or_create(provider=source.provider,
            object_key=f"published/{anchor.edition_id}/outline/{artifact.sha256}.pdf",
            defaults={"asset": artifact, "sha256": artifact.sha256, "byte_size": artifact.byte_size})
        if not created:
            continue
        if not cloud_budget_allows_new_publication(source.provider):
            record.status, record.error_message = "failed", "云端预算保护已暂停书签副本同步；本地副本保留。"
            record.save(update_fields=["status", "error_message", "updated_at"])
            continue
        try:
            sync_cloud_object.apply_async(args=[str(record.pk)], kwargs={"resume_publication": False}, ignore_result=True)
        except (OperationalError, OSError, ConnectionError, TimeoutError):
            record.status, record.error_message = "failed", "书签副本尚未进入同步队列，可从文件管理重试。"
            record.save(update_fields=["status", "error_message", "updated_at"])


def export_revision(asset, revision_id):
    _source_current(asset)
    revision = asset.outline_revisions.filter(pk=revision_id, is_active=True,
        source_checksum=asset.sha256, origin__in=["automatic", "corrected", "adopted", "restored", "page_mapping"]).first()
    document = asset.document_revisions.filter(is_active=True).first()
    if not revision or str(revision.document_revision_id or "") != str(document.pk if document else ""):
        raise OutlineConflict("已采用目录或原文已变化，请重新读取当前目录；原文件保留。")
    automatic = revision.origin in {"automatic", "corrected", "restored"} and revision.parser_version == "outline-v9-docling-geometry"
    allowed = {"confirmed", "native", "matched", "generated"} if automatic else {"confirmed", "native"}
    if (not revision.nodes or not (automatic or revision.reviewed)
            or any(node.get("calibration_status") not in allowed or not node.get("pdf_page") for node in revision.nodes)):
        raise OutlineConflict("目录尚无有效落点，请重新生成或修正目录。")
    return revision


@transaction.atomic
def queue_export(asset_id, *, revision_id, request_id, actor):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    identity = f"outline-export:{actor.pk if actor else 'automatic'}:{UUID(str(request_id))}"
    prior = ProcessingJob.objects.filter(idempotency_key=identity).first()
    if prior:
        if prior.asset_id != asset.pk or prior.stats.get("outline_revision_id") != str(revision_id):
            raise OutlineConflict("原请求已绑定另一份目录，请先核对原任务。")
        return prior
    revision = export_revision(asset, revision_id)
    job = ProcessingJob.objects.create(job_type="text_extraction", asset=asset, edition=asset.edition,
        created_by=actor, task_id=str(uuid4()), idempotency_key=identity,
        stats={"operation": OPERATION, "source_sha256": asset.sha256, "outline_revision_id": str(revision.pk),
               "document_revision_id": str(revision.document_revision_id or "")})
    transaction.on_commit(lambda: dispatch_export(str(job.pk), job.task_id))
    return job


def dispatch_export(job_id, task_id):
    from ingestion.tasks import process_outline_export
    try:
        process_outline_export.apply_async(args=[job_id], task_id=task_id, ignore_result=True)
        return True
    except (OperationalError, OSError, ConnectionError, TimeoutError):
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").update(
            status="failed", error_code="queue_unavailable", error_message="PDF副本尚未进入队列，可重试；原文件保留。",
            finished_at=timezone.now(), updated_at=timezone.now())
        return False


def write_bookmarked_copy(source, destination, nodes, *, page_count, heartbeat):
    """Write to a new path and verify every title, hierarchy and destination."""
    import fitz
    nodes = _tree_order([dict(row) for row in nodes])
    expected = []
    with fitz.open(str(source)) as pdf:
        if len(pdf) != page_count or pdf.is_encrypted:
            raise OutlineConflict("原文件页数或加密状态不符合已校验记录。")
        if pdf.get_sigflags() > 0:
            raise OutlineConflict("此PDF包含数字签名，不能生成会使签名失效的书签副本；请下载原件。")
        toc = []
        for index, row in enumerate(nodes):
            if index % 100 == 0:
                heartbeat("bookmarks", index, len(nodes))
            number = row.get("pdf_page")
            if type(number) is not int or not 1 <= number <= len(pdf):
                raise OutlineConflict("目录仍有无效页码，未生成截断副本。")
            page = pdf[number - 1]
            point = fitz.Point(0, 0)
            relative = row.get("normalized_position", [])
            if len(relative) == 2 and all(type(v) in {float, int} and 0 <= v <= 1 for v in relative):
                point = fitz.Point(relative[0] * page.rect.width, relative[1] * page.rect.height)
            elif row.get("coordinate_space") == "pymupdf_toc" and len(row.get("pdf_position", [])) == 2:
                point = fitz.Point(row["pdf_position"])
            toc.append([row["level"], row["title"], number])
            expected.append((row["level"], row["title"], number, point))
        pdf.set_toc(toc)
        # PyMuPDF 1.26 set_toc offsets cropped/rotated destinations. Write each
        # destination in PDF coordinates, then retain the displayed-point check.
        for xref, (_, _, number, point) in zip(pdf.get_outline_xrefs(), expected):
            page = pdf[number - 1]
            unrotated = point * page.derotation_matrix
            target = fitz.Point(unrotated.x + page.cropbox.x0,
                                page.mediabox.y1 - page.cropbox.y0 - unrotated.y)
            pdf.xref_set_key(xref, "A/D", f"[{page.xref} 0 R /XYZ {target.x:.6f} {target.y:.6f} 0]")
        heartbeat("writing", 0, 1)
        pdf.save(str(destination), garbage=0, deflate=False)
    heartbeat("validating", 0, 1)
    with fitz.open(str(destination)) as saved:
        actual = saved.get_toc(simple=False)
        if len(saved) != page_count or len(actual) != len(expected):
            raise OutlineConflict("书签副本的页数或节点数不一致，未提供下载。")
        for index, (row, target) in enumerate(zip(actual, expected)):
            if index % 100 == 0:
                heartbeat("validating", index, len(expected))
            point = row[3].get("to")
            if tuple(row[:3]) != target[:3] or point is None or abs(point.x - target[3].x) > 1 or abs(point.y - target[3].y) > 1:
                raise OutlineConflict("书签副本的标题、层级或精确落点未能回读一致，未提供下载。")


def current_export_revision(asset, stats):
    if stats.get("operation") == "page_mapping_export":
        from catalog.services.page_mapping_exports import export_revision as mapping_revision
        return mapping_revision(asset, stats.get("mapping_revision_id"))
    return export_revision(asset, stats.get("outline_revision_id"))


def run_export(job_id, *, task_id):
    from ingestion.services.files import materialize_field_file, sha256_file
    from ingestion.services.processing import _claim_processing_job
    job, claimed = _claim_processing_job(job_id, task_id=task_id, progress_floor=5)
    if not claimed:
        return job
    cleanup, created_file, committed = None, None, False
    def heartbeat(stage, done, total):
        start, span = {"source": (5, 5), "bookmarks": (10, 35), "writing": (45, 5), "validating": (50, 35)}[stage]
        if not ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
            heartbeat_at=timezone.now(), progress=start + round(span * done / max(1, total)),
            stats={**job.stats, "stage": stage}, updated_at=timezone.now()):
            raise OutlineJobInterrupted()
    try:
        asset = job.asset
        revision = current_export_revision(asset, job.stats)
        mapping = job.stats.get("operation") == "page_mapping_export"
        processor = "page-mapping-blank-copy" if mapping else PROCESSOR
        if asset.sha256 != job.stats["source_sha256"]:
            raise OutlineConflict("任务绑定的文件已变化，请按当前来源新建任务。")
        from distribution.services import validated_ocr_rendition
        base = (validated_ocr_rendition(asset) if not mapping else None) or asset
        source, cleanup = materialize_field_file(base.file)
        heartbeat("source", 0, 1)
        if sha256_file(source)[0] != base.sha256:
            raise OutlineConflict("原文件内容与登记指纹不一致，请先校验文件。")
        with TemporaryDirectory(prefix="stl-outline-export-") as temporary:
            output = Path(temporary) / "bookmarked.pdf"
            if mapping:
                from catalog.services.page_mapping_exports import write_mapping_copy
                output_pages = write_mapping_copy(source, output, revision.data, page_count=asset.page_count, heartbeat=heartbeat)
                details = {"mapping_revision_id": str(revision.pk), "source_sha256": asset.sha256,
                    "inserted_blank_count": output_pages - asset.page_count, "original_page_identity_roundtrip": True}
            else:
                write_bookmarked_copy(source, output, revision.nodes, page_count=asset.page_count, heartbeat=heartbeat)
                output_pages = asset.page_count
                details = {"outline_revision_id": str(revision.pk), "source_sha256": asset.sha256,
                    "document_revision_id": str(revision.document_revision_id or ""), "bookmark_count": len(revision.nodes),
                    "export_base_id": str(base.pk), "export_base_sha256": base.sha256,
                    "title_page_position_roundtrip": True}
            digest, size = sha256_file(output)
            if sha256_file(source)[0] != base.sha256:
                raise OutlineConflict("生成期间原文件内容发生变化，本次副本未保存。")
            with transaction.atomic():
                asset = Asset.objects.select_for_update().get(pk=asset.pk)
                current = ProcessingJob.objects.select_for_update().get(pk=job.pk)
                if current.task_id != task_id or current.status != "running":
                    return current
                revision = current_export_revision(asset, job.stats)
                if asset.sha256 != job.stats["source_sha256"]:
                    raise OutlineConflict("原文件已变化，本次副本未采用。")
                artifact = Asset.objects.filter(sha256=digest, kind=Asset.Kind.WEB_DERIVATIVE).first()
                if artifact and (artifact.source_asset_id != asset.pk or artifact.processor != processor):
                    raise OutlineConflict("存在不属于当前目录的相同派生文件，请核对文件来源。")
                if not artifact:
                    artifact = Asset(edition=asset.edition, kind=Asset.Kind.WEB_DERIVATIVE, source_asset=asset,
                        sha256=digest, byte_size=size, page_count=output_pages, mime_type="application/pdf",
                        original_filename=f"{Path(asset.original_filename or 'document.pdf').stem}-{'补页副本' if mapping else '校准书签'}.pdf",
                        status="ready", validation_status="valid", access_status="private", is_current=False,
                        processor=processor, processor_version="1", validation_details=details)
                    with output.open("rb") as stream:
                        artifact.file.save(f"outline-{artifact.pk}.pdf", File(stream), save=False)
                    created_file = (artifact.file.storage, artifact.file.name)
                    artifact.save()
                current.status, current.progress, current.finished_at = "succeeded", 100, timezone.now()
                current.stats = {**job.stats, "stage": "complete", "result_asset_id": str(artifact.pk)}
                current.save(update_fields=["status", "progress", "finished_at", "stats", "updated_at"])
                AuditEvent.objects.create(actor=job.created_by, action="page_mapping.exported" if mapping else "outline.exported", object_type="Asset", object_id=str(asset.pk),
                    after={**details, "result_asset_id": str(artifact.pk), "job_id": str(job.pk)})
            committed = True
            if not mapping:
                queue_download_cloud_copy(asset)
            return current
    except OutlineJobInterrupted:
        return ProcessingJob.objects.get(pk=job.pk)
    except Exception as exc:
        ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(status="failed",
            error_code=type(exc).__name__, error_message=str(exc)[:2000], finished_at=timezone.now(), updated_at=timezone.now())
        raise
    finally:
        if cleanup:
            cleanup()
        if created_file and not committed:
            created_file[0].delete(created_file[1])
