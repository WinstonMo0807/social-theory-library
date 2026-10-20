"""Public-safe OCR state for one authorized Reader source; existing workers stay authoritative."""
import json
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError

from catalog.models import Asset, Edition, KnowledgePublicationEvent, OcrStatus
from catalog.services.publication_eligibility import active_document_q, public_editions
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.services.catalog_ocr import progress_row
from ingestion.services.ocr_workspace import OCRWorkspaceConflict, digest, task_command
from ingestion.services.processing import processing_workload_paused
from .reader_ocr_serializers import ReaderOCRCommandInput
from .views import _public_asset

RECEIPT_ACTION = "reader.ocr.command"
PHASES = {"queued", "preparing", "recognizing", "finalizing", "pdf", "publishing", "complete"}


class ReaderOCRConflict(APIException):
    status_code = 409
    default_detail = "任务或阅读来源已有变化，请重新读取当前状态后确认操作。"


def reader_source(asset_id, request):
    asset = _public_asset(asset_id, request)
    # Match the public catalog's recycled-work/edition boundary as well.
    if not public_editions().filter(pk=asset.edition_id).exists():
        raise NotFound("该阅读来源当前不可用。")
    return asset


def document_revision(asset):
    value = Asset.objects.filter(active_document_q(asset_prefix=""), pk=asset.pk,
        edition__active_catalog_revision__document_revision__asset_id=asset.pk).values_list(
            "edition__active_catalog_revision__document_revision_id", flat=True).first()
    return str(value) if value else None


def can_control(user):
    return has_capability(user, Capability.ACCESS_BACK_OFFICE) and has_capability(user, Capability.RETRY_JOBS)


def require_actor(request):
    if not can_control(request.user):
        raise PermissionDenied("当前账户不能暂停或恢复文字识别。")
    if request.headers.get("X-Reader-Owner") != str(request.user.pk):
        raise PermissionDenied("登录账户已变化，请重新读取当前账户的任务状态。")


def current_job(asset):
    # Filter in SQL first; task identity must belong to this exact source or its
    # verified OCR result, never simply the most recent task of the edition.
    row = ProcessingJob.objects.filter(edition_id=asset.edition_id, job_type="ocr").filter(
        Q(stats__requested_asset_id=str(asset.pk)) | Q(stats__text_source_asset_id=str(asset.pk)) | Q(asset_id=asset.pk)
    ).select_related("asset", "asset__source_asset", "edition__active_catalog_revision").order_by("-created_at", "-id").first()
    if row is None:
        return None
    stats = row.stats or {}
    source_id = str(stats.get("requested_asset_id") or stats.get("text_source_asset_id") or row.asset_id or "")
    source_match = source_id == str(asset.pk)
    result_match = (row.asset_id == asset.pk and str(asset.source_asset_id) == source_id
                    and stats.get("staging_asset_id") == str(asset.pk))
    if not (source_match or result_match):
        return None
    source = asset if source_match else row.asset.source_asset
    result = row.asset
    if source is None or result is None or source.edition_id != asset.edition_id or result.edition_id != asset.edition_id:
        return None
    if result.pk != source.pk:
        details = result.validation_details or {}
        if (result.source_asset_id != source.pk or result.sha256 != source.sha256
                or result.page_count != source.page_count
                or stats.get("staging_asset_id") != str(result.pk)
                or details.get("text_source_asset_id") != source_id
                or details.get("text_stage_key") != f"ocr-job:{row.pk}"):
            return None
    # Normalized text stages share the source PDF bytes. Searchable OCR PDFs
    # are separate renditions and cannot become a different-hash task anchor.
    # Never fall back to an older task after this source's newest job has
    # failed identity verification.
    if stats.get("source_sha256") and stats["source_sha256"] != source.sha256:
        return None
    expected_pages = stats.get("source_page_count")
    if expected_pages is None:
        expected_pages = stats.get("total_pages")
    if expected_pages is not None and (type(expected_pages) is not int or expected_pages != source.page_count):
        return None
    return row


def receipt_for(asset, actor, request_id):
    return AuditEvent.objects.filter(actor=actor, action=RECEIPT_ACTION,
        object_type="asset", object_id=str(asset.pk), request_id=str(request_id)).first()


def receipt_output(row):
    if row is None:
        return None
    return {"request_id": row.request_id, "action": row.after["action"], "job_id": row.after["job_id"], "applied": True}


def processed_content(asset, job, actor, event, revision_id):
    empty = {"state": "unavailable", "url": None, "label": "查看已处理内容",
             "notice": "暂无已确认可读取的本次识别内容；扫描原页仍可阅读。"}
    if job is None:
        return empty
    # A percentage or succeeded flag alone does not prove activation of this
    # particular result. No pending OCR text is returned from this endpoint.
    active = asset.edition.active_catalog_revision
    published = bool(event and event.catalog_revision_id == active.pk and active.fulltext_ready
                     and active.document_revision_id and str(active.document_revision_id) == revision_id
                     and active.reader_asset_id == asset.pk and job.asset_id == asset.pk)
    if published:
        return {"state": "published", "url": f"/reader/{asset.pk}?page=1&revision={revision_id}",
                "label": "在新标签页查看已公开内容", "notice": "本次文字结果已进入当前正式阅读版本。"}
    completed = (job.stats or {}).get("processed_pages")
    if type(completed) is int and completed > 0:
        if (has_capability(actor, Capability.ACCESS_BACK_OFFICE) and job.asset
                and job.asset.edition_id == asset.edition_id and job.asset.kind == "normalized"):
            return {"state": "admin_preview", "url": f"/admin/library/assets/{job.asset_id}/ocr",
                    "label": "在新标签页核对已处理内容", "notice": "这是管理预览，识别结果仍须通过正式公开流程。"}
        return {"state": "awaiting_publication", "url": None, "label": "已处理内容等待公开",
                "notice": "已完成页数已经保存，尚未获准公开的文字暂不提供阅读。"}
    return empty


def status_payload(asset, actor, *, receipt=None):
    job = current_job(asset)
    revision_id = document_revision(asset)
    managed = has_capability(actor, Capability.ACCESS_BACK_OFFICE)
    allowed = can_control(actor)
    output = {
        "asset_id": str(asset.pk), "edition_id": str(asset.edition_id),
        "owner_id": actor.pk if actor.is_authenticated else None,
        "document_revision_id": revision_id, "source_sha256": asset.sha256,
        "file_page_count": asset.page_count,
        "ocr_status": asset.edition.ocr_status if asset.edition.ocr_status in OcrStatus.values else "unknown",
        "checked_at": timezone.now(),
        "job": None, "can_pause": False, "can_resume": False,
        "denied_reason": "" if allowed else "暂停和恢复识别需要任务管理权限。",
        "management_url": f"/admin/library/assets/{asset.pk}/ocr" if managed else None,
        "processed_content": processed_content(asset, None, actor, None, revision_id),
        "receipt": receipt_output(receipt),
    }
    if job is None:
        return output
    event_id = (job.stats or {}).get("knowledge_publication_event_id")
    # Retained legacy metadata is not allowed to turn a read into an invalid UUID query.
    event = None
    if event_id:
        from uuid import UUID
        try:
            event_id = UUID(str(event_id))
        except (ValueError, TypeError, AttributeError):
            event_id = None
        if event_id:
            event = KnowledgePublicationEvent.objects.filter(pk=event_id, catalog_revision__edition_id=asset.edition_id).select_related("catalog_revision").first()
    progress = progress_row(job, actor=actor, event=event, edition=asset.edition)
    pause_requested = job.pause_requested_at is not None and job.status in {"pending", "running"}
    count_valid = type((job.stats or {}).get("target_pages")) is int and type((job.stats or {}).get("processed_pages")) is int
    output["job"] = {
        "id": str(job.pk), "job_version": job.updated_at.isoformat(),
        "status": job.status if job.status in ProcessingJob.Status.values else "unknown",
        "phase": progress["phase"] if progress["phase"] in PHASES else "",
        "phase_label": "正在等待当前页保存后暂停" if pause_requested else progress["phase_label"],
        "completed_pages": progress["completed_pages"] if count_valid else None,
        "total_pages": progress["total_pages"] if count_valid else None,
        "percent": progress["percent"] if count_valid else None,
        "phase_elapsed_seconds": progress["phase_elapsed_seconds"],
        "updated_at": job.updated_at, "pause_requested": pause_requested, "stale": progress["stale"],
    }
    identity_ready = bool(re.fullmatch(r"[0-9a-f]{64}", asset.sha256 or ""))
    global_pause = processing_workload_paused("ocr")
    output["can_pause"] = bool(allowed and identity_ready and progress["can_pause"] and not pause_requested)
    output["can_resume"] = bool(allowed and identity_ready and progress["can_resume"] and not global_pause)
    if allowed:
        output["denied_reason"] = ("OCR 任务目前处于全局暂停状态，请在管理工作台核对。" if global_pause
            else "正在等待当前页保存，随后会安全暂停。" if pause_requested
            else "此任务当前不能从阅读页恢复，请到管理工作台核对。" if job.status in {"paused", "failed"} and not output["can_resume"]
            else "此任务由旧处理流程建立，请到管理工作台核对。" if (job.stats or {}).get("requested_mode") not in {"all_pages", "selected_pages"}
            else "当前文件缺少完整来源校验标识，请在管理工作台核对。" if not identity_ready else "")
    output["processed_content"] = processed_content(asset, job, actor, event, revision_id)
    return output


@transaction.atomic
def control(request, asset_id, raw):
    require_actor(request)
    if not isinstance(raw, dict) or len(json.dumps(raw, default=str)) > 4000:
        raise ValidationError({"detail": "任务命令内容过大或无效。"})
    serializer = ReaderOCRCommandInput(data=raw)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    initial = reader_source(asset_id, request)
    Edition.objects.select_for_update().get(pk=initial.edition_id)
    Asset.objects.select_for_update().get(pk=asset_id)
    asset = reader_source(asset_id, request)
    fingerprint = digest({**data, "actor": str(request.user.pk), "asset_id": str(asset.pk)})
    previous = receipt_for(asset, request.user, data["request_id"])
    if previous:
        if previous.after.get("fingerprint") != fingerprint:
            raise ReaderOCRConflict("该操作请求已用于不同内容，请保留原请求并核对结果。")
        return status_payload(asset, request.user, receipt=previous)
    if (data["source_sha256"] != asset.sha256
            or (str(data["document_revision_id"]) if data["document_revision_id"] else None) != document_revision(asset)):
        raise ReaderOCRConflict("阅读来源已变化，请重新读取来源后再操作。")
    selected = current_job(asset)
    if selected is None or selected.pk != data["job_id"]:
        raise ReaderOCRConflict("当前文件的识别任务已变化，旧请求不会操作新的任务。")
    job = ProcessingJob.objects.select_for_update().get(pk=selected.pk)
    if data["job_version"] != job.updated_at.isoformat():
        raise ReaderOCRConflict()
    current = status_payload(asset, request.user)
    if not current[f"can_{data['action']}"]:
        raise ReaderOCRConflict(current["denied_reason"] or "任务当前不能执行此操作，请读取最新状态。")
    try:
        task_command(asset.pk, {key: data[key] for key in ("action", "request_id", "job_id", "job_version")}, request.user)
    except (OCRWorkspaceConflict, ValueError, ProcessingJob.DoesNotExist):
        # Existing administrative errors may contain paths/provider details.
        raise ReaderOCRConflict("任务状态或来源已变化，请重新核对；已处理内容保持保存。") from None
    receipt = AuditEvent.objects.create(actor=request.user, action=RECEIPT_ACTION, object_type="asset",
        object_id=str(asset.pk), request_id=str(data["request_id"]),
        after={"fingerprint": fingerprint, "action": data["action"], "job_id": str(data["job_id"])})
    asset = reader_source(asset_id, request)
    return status_payload(asset, request.user, receipt=receipt)
