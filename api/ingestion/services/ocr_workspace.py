"""Page review over the existing OCR worker and immutable publication pipeline."""
from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
import re
from uuid import uuid5

from django.db import transaction
from django.db.models import BooleanField, Case, F, Value, When
from django.db.models.functions import Length
from django.utils import timezone

from catalog.models import Asset, DocumentOutlineRevision, Edition, KnowledgePublicationEvent, Page, PageTextRevision, Passage, PublicationState, SemanticIndexStatus
from catalog.services.document_intelligence import stage_document_asset, synchronize_document_revision
from catalog.services.document_outline import outline_state
from catalog.services.text import normalize_search_text, sanitize_unicode
from ingestion.models import AuditEvent, ProcessingJob
from .catalog_ocr import ACTIVE, catalog_ocr_action, ocr_context, source_problem, start_catalog_ocr
from .ocr_provider import normalize_task_options


class OCRWorkspaceConflict(ValueError):
    pass


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")).encode()).hexdigest()


def fingerprint(asset, page, document_id=None):
    if document_id is None:
        document_id = str(asset.document_revisions.filter(is_active=True).values_list("pk", flat=True).first() or "")
    return digest([str(asset.pk), asset.sha256, asset.page_count, asset.is_current,
                   document_id, page.index if page else None,
                   page.text if page else "", page.is_text_manual if page else False,
                   str(page.manual_text_revision_id) if page else ""])


def revision_payload(row):
    if row is None:
        return None
    event = row.publication_event
    return {"id": str(row.pk), "revision": row.revision, "pdf_page": row.page_index,
            "text": row.text, "original_text": row.original_text, "note": row.note,
            "confirmed": row.confirmed, "source_fingerprint": row.source_fingerprint,
            "review_only": row.review_only,
            "created_at": row.created_at, "applied_at": row.applied_at,
            "applied_asset_id": str(row.applied_asset_id) if row.applied_asset_id else None,
            "publication": {"id": str(event.pk), "status": event.status,
                            "revision_status": event.catalog_revision.status if event.catalog_revision_id else ""} if event else None}


def reviewed_page_query(asset):
    document_id = asset.document_revisions.filter(is_active=True).values_list("pk", flat=True).first()
    return asset.pages.filter(reviewed_text_revision__confirmed=True, reviewed_text_revision__review_only=True,
        reviewed_text_revision__document_revision_id=document_id, reviewed_text_revision__text=F("text"))


def page_status(row, failed, options):
    if row["is_text_manual"]:
        return "manual", "人工文字已确认并保护"
    if row.get("reviewed"):
        return "reviewed", "管理员已对照当前来源核验；这是一项人工决定，不代表 OCR 已执行"
    if row["index"] in failed:
        return "failed", "本页识别中断，已保留此前文字"
    if row["text_source"] == "none" or row["char_count"] == 0:
        return "unread", "尚无可用文字；请对照原页判断扫描页、图版或空白页"
    if options["detect_garbled"] and row.get("replacement_character"):
        return "needs_review", "文字含实际替换符 U+FFFD，可能存在乱码，请对照原页"
    if options["detect_spreads"] and row.get("width", 0) > row.get("height", 0) * 1.2 > 0:
        return "needs_review", "页面宽高比呈横向，可能为双页合扫或横向图版；请人工核对，不自动拆页"
    if row["text_source"] in {"ocr", "hybrid"} and row["confidence"] < options["quality_threshold"]:
        return "needs_review", "识别引擎返回的置信度偏低，请人工核对；这不是已校准的正确率"
    return "completed", "已有文字，尚未逐字人工确认"


def quality_spans(page, text, options):
    """Code-point offsets into this exact text, never guessed character boxes."""
    spans = []
    if options["detect_garbled"]:
        spans.extend({"start": match.start(), "end": match.end(), "reason": "实际替换符 U+FFFD，可能存在乱码，请对照原页。"}
                     for match in re.finditer("\ufffd+", text))
    if page and not page.is_text_manual and page.text_source in {"ocr", "hybrid"} and page.text == text:
        blocks = list(page.blocks.order_by("order"))
        # The OCR ingestion path joins these exact blocks with two newlines.
        # If the stored text no longer has that alignment, keep only literal evidence.
        if "\n\n".join(block.text for block in blocks) == text:
            offset = 0
            for block in blocks:
                # Legacy imports also used zero for absent scores; do not turn
                # that missing evidence into a located recognition warning.
                if block.text.strip() and 0 < block.confidence < options["quality_threshold"]:
                    spans.append({"start": offset, "end": offset + len(block.text),
                        "reason": "此文字段的识别引擎置信度偏低，需人工核对；不代表已确定存在错字。"})
                offset += len(block.text) + 2
    merged = []
    for span in sorted(spans, key=lambda row: (row["start"], row["end"])):
        if merged and span["start"] <= merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], span["end"])
            if span["reason"] not in merged[-1]["reason"]:
                merged[-1]["reason"] += " " + span["reason"]
        else:
            merged.append(dict(span))
    return merged


def workspace_state(asset, actor, *, pdf_page=1, list_page=1, status="all", history_page=1,
                    quality_threshold=.75, detect_spreads=True, detect_garbled=True):
    options = normalize_task_options({"quality_threshold": quality_threshold, "detect_spreads": detect_spreads, "detect_garbled": detect_garbled})
    summary = outline_state(asset)["asset"]
    summary["publication_state"] = asset.edition.state
    summary["source_error"] = source_problem(asset)
    summary["source_current"] = not bool(summary["source_error"])
    jobs = list(ProcessingJob.objects.filter(edition=asset.edition, job_type="ocr").order_by("-created_at")[:30])
    related = [job for job in jobs if str(job.stats.get("requested_asset_id") or job.stats.get("text_source_asset_id") or job.asset_id) == str(asset.pk)]
    failed = set()
    for job in reversed(related):
        failed.difference_update(job.stats.get("completed_page_indexes") or [])
        if job.status == "failed":
            failed.update(job.stats.get("active_page_indexes") or [])
    reviewed = set(reviewed_page_query(asset).values_list("index", flat=True))
    rows = list(asset.pages.annotate(char_count=Length("text"), replacement_character=Case(
        When(text__contains="\ufffd", then=Value(True)), default=Value(False), output_field=BooleanField())).order_by("index").values(
        "index", "printed_label", "text_source", "confidence", "is_text_manual", "char_count", "width", "height", "replacement_character"))
    for row in rows:
        row["reviewed"] = row["index"] in reviewed
        row["status"], row["reason"] = page_status(row, failed, options)
        row["pdf_page"] = row.pop("index")
    counts = dict(Counter(row["status"] for row in rows))
    filtered = [row for row in rows if status == "all" or row["status"] == status or status == "issues" and row["status"] in {"failed", "unread", "needs_review"}]
    count = len(filtered)
    list_page = min(list_page, max(1, (count + 19) // 20))
    visible = filtered[(list_page-1)*20:list_page*20]
    visible_pages = {p.index: p for p in asset.pages.filter(index__in=[row["pdf_page"] for row in visible])}
    for row in visible:
        row["source_fingerprint"] = fingerprint(asset, visible_pages[row["pdf_page"]], summary["document_revision_id"])
    selected = asset.pages.select_related("manual_text_revision__publication_event__catalog_revision").filter(index=pdf_page).first()
    revisions = asset.text_corrections.select_related("publication_event__catalog_revision")
    history = revisions.filter(page_index=pdf_page)
    history_count = history.count()
    history_page = min(history_page, max(1, (history_count + 9) // 10))
    latest = history.filter(review_only=False).first()
    protected = selected.manual_text_revision if selected else None
    detail = {"pdf_page": pdf_page, "text": selected.text if selected else "", "parsed": selected is not None,
              "original_text": protected.original_text if protected else selected.text if selected else "",
              "manual": selected.is_text_manual if selected else False,
              "manual_revision_id": str(selected.manual_text_revision_id) if selected and selected.manual_text_revision_id else None,
              "manual_revision": revision_payload(protected),
              "latest": revision_payload(latest), "source_fingerprint": fingerprint(asset, selected),
              "history": [revision_payload(row) for row in history[(history_page-1)*10:history_page*10]],
              "history_count": history_count, "history_page": history_page,
              "history_next_page": history_page + 1 if history_page * 10 < history_count else None}
    detail["quality_spans"] = quality_spans(selected, detail["text"], options)
    detail["original_quality_spans"] = detail["quality_spans"] if detail["original_text"] == detail["text"] else quality_spans(None, detail["original_text"], options)
    context = ocr_context(asset.edition, actor)
    return {"asset": summary, "source_version": asset.updated_at.isoformat(),
            "expected_revision": revisions.values_list("revision", flat=True).first() or 0,
            "pages": visible, "count": count,
            "list_page": list_page, "next_page": list_page+1 if list_page*20 < count else None,
            "counts": counts, "parsed_page_count": len(rows), "missing_page_count": max(0, asset.page_count-len(rows)),
            "detail": detail, "jobs": [job for job in context["jobs"] if str(asset.pk) in {job["source_asset_id"], job["result_asset_id"]}], "active_job_id": context["active_job_id"],
            "paused": context["paused"], "can_run": context["can_run"], "denied_reason": context["denied_reason"],
            "provider_label": context["provider_label"], "checked_at": timezone.now(),
            "settings": {"languages": "中文、繁体中文、英语", "layout": "现有识别服务的版面分析",
                         "manual_text": "已确认的人工文字始终跳过，不由重新识别覆盖", "service_verified": False,
                         "quality_threshold": options["quality_threshold"]}}


def locked_asset(identifier):
    edition_id = Asset.objects.values_list("edition_id", flat=True).get(pk=identifier)
    Edition.objects.select_for_update().get(pk=edition_id)
    return Asset.objects.select_for_update(of=("self",)).select_related("edition__active_catalog_revision", "edition__work").get(pk=identifier)


def guard(asset, data):
    page = asset.pages.select_for_update().filter(index=data["pdf_page"]).first()
    if not page:
        raise ValueError("本页尚未解析，不能以人工文字补造物理页；请先恢复解析。")
    if source_problem(asset):
        raise OCRWorkspaceConflict(source_problem(asset))
    latest = asset.text_corrections.values_list("revision", flat=True).first() or 0
    if data["expected_revision"] != latest or data["source_fingerprint"] != fingerprint(asset, page):
        raise OCRWorkspaceConflict("文件、页面文字或修订已有变化，请保留输入，对照最新版本后再提交。")
    return page


def command_fingerprint(data, actor):
    return digest({**data, "actor": str(actor.pk)})


def replay(asset, data, actor, *, applying=False):
    key = "apply_request_id" if applying else "request_id"
    row = asset.text_corrections.filter(**{key: data["request_id"]}).first()
    if row:
        expected = row.apply_fingerprint if applying else row.request_fingerprint
        if expected != command_fingerprint(data, actor):
            raise OCRWorkspaceConflict("同一请求标识不能用于其他修订或账户。")
    return row


@transaction.atomic
def save_correction(identifier, data, actor):
    asset = locked_asset(identifier)
    previous = replay(asset, data, actor)
    if previous:
        return previous
    page = guard(asset, data)
    text = sanitize_unicode(data["text"])
    if not text.strip() and not data.get("note", "").strip():
        raise ValueError("空白页或图版没有文字时，请说明确认依据。")
    return PageTextRevision.objects.create(asset=asset, page_index=page.index,
        document_revision=asset.document_revisions.filter(is_active=True).first(),
        revision=data["expected_revision"]+1, source_fingerprint=fingerprint(asset, page),
        original_text=page.text, text=text, note=data.get("note", ""), confirmed=data["confirmed"],
        request_id=data["request_id"], request_fingerprint=command_fingerprint(data, actor), created_by=actor)


@transaction.atomic
def review_pages(identifier, data, actor):
    asset = locked_asset(identifier)
    identity = command_fingerprint(data, actor)
    receipt = AuditEvent.objects.filter(actor=actor, action="ocr.pages.review", object_id=str(asset.pk), request_id=str(data["request_id"])).first()
    if receipt:
        if receipt.after.get("fingerprint") != identity:
            raise OCRWorkspaceConflict("同一次核验请求不能更换页面或来源。")
        return
    if not data["confirmed"]:
        raise ValueError("请明确确认已经对照所选原页及当前文字。")
    if source_problem(asset):
        raise OCRWorkspaceConflict(source_problem(asset))
    revision = asset.text_corrections.values_list("revision", flat=True).first() or 0
    if data["expected_revision"] != revision:
        raise OCRWorkspaceConflict("页面核验已有新记录，请刷新后重新核对。")
    entries = data["pages"]
    indexes = [entry["pdf_page"] for entry in entries]
    if len(indexes) != len(set(indexes)):
        raise ValueError("核验页面不能重复。")
    pages = {page.index: page for page in asset.pages.select_for_update().filter(index__in=indexes)}
    document = asset.document_revisions.filter(is_active=True).first()
    if len(pages) != len(indexes) or sum(len(page.text) for page in pages.values()) > 1000000:
        raise ValueError("核验页面缺少解析记录或合计文字超过一百万字，请缩小范围。")
    for entry in entries:
        page = pages[entry["pdf_page"]]
        if fingerprint(asset, page, str(document.pk) if document else "") != entry["source_fingerprint"]:
            raise OCRWorkspaceConflict("所选页面的文字或来源已改变，本次核验尚未保存。")
        if not page.text.strip() and not data.get("note", "").strip():
            raise ValueError("无文字页面需要说明确为空白或图版的依据。")
    for entry in entries:
        page = pages[entry["pdf_page"]]
        revision += 1
        row = PageTextRevision.objects.create(asset=asset, document_revision=document, page_index=page.index,
            revision=revision, review_only=True, source_fingerprint=entry["source_fingerprint"],
            original_text=page.text, text=page.text, note=data.get("note", ""), confirmed=True,
            request_id=uuid5(data["request_id"], str(page.index)), request_fingerprint=identity, created_by=actor)
        page.reviewed_text_revision = row
        page.save(update_fields=["reviewed_text_revision", "updated_at"])
    AuditEvent.objects.create(actor=actor, action="ocr.pages.review", object_type="asset", object_id=str(asset.pk),
        request_id=str(data["request_id"]), after={"fingerprint": identity, "pages": indexes})


def prepare_correction(asset, row):
    page = asset.pages.filter(index=row.page_index).first()
    blockers = []
    if source_problem(asset):
        blockers.append(source_problem(asset))
    if not page or fingerprint(asset, page) != row.source_fingerprint:
        blockers.append("候选基于旧文字或文件，请重新对照保存。")
    if not row.confirmed:
        blockers.append("请明确确认已对照原页核验这份人工文字。")
    if row.applied_at:
        blockers.append("此修订已经采用，请查看对应文件和公开更新状态。")
    if ProcessingJob.objects.filter(edition=asset.edition, job_type="ocr", status__in=ACTIVE).exists():
        blockers.append("此版本仍有 OCR 任务，请先完成或安全取消，避免候选与正在识别的文字冲突。")
    active = asset.edition.active_catalog_revision
    if asset.edition.state == PublicationState.WITHDRAWN:
        blockers.append("此版本已撤回，请先到版本发布区处理。")
    if asset.edition.state == PublicationState.PUBLISHED and (not active or active.reader_asset_id != asset.pk):
        blockers.append("此文件不是当前公开阅读文件，请先完成文件切换。")
    if asset.edition.catalog_revisions.filter(revision__gt=active.revision if active else 0, status__in=["preparing", "failed"]).exists():
        blockers.append("此版本有待完成的公开更新，请先在发布区处理。")
    result = {"revision_id": str(row.pk), "pdf_page": row.page_index, "before": page.text if page else "",
              "after": row.text, "blockers": blockers, "can_apply": not blockers,
              "mode": "publish" if asset.edition.state == PublicationState.PUBLISHED else "apply_draft",
              "notice": "只采用这一页文字；原文件和旧引用保留。人工文字没有可证明的字形坐标，阅读器只定位到实际页。"}
    result["prepared_fingerprint"] = digest(result)
    return result


@transaction.atomic
def apply_correction(identifier, data, actor):
    from catalog.services.knowledge_publication import create_catalog_publication_event
    from .extract import ExtractedBlock, _passage_chunks

    asset = locked_asset(identifier)
    previous = replay(asset, data, actor, applying=True)
    if previous:
        return previous
    guard(asset, data)
    row = asset.text_corrections.select_for_update().get(pk=data["revision_id"], page_index=data["pdf_page"])
    prepared = prepare_correction(asset, row)
    if prepared["prepared_fingerprint"] != data["prepared_fingerprint"]:
        raise OCRWorkspaceConflict("采用影响已改变，请重新查看差异后确认。")
    if prepared["blockers"]:
        raise ValueError(" ".join(prepared["blockers"]))
    document = asset.document_revisions.filter(is_active=True).first()
    outline = asset.outline_revisions.filter(is_active=True, source_checksum=asset.sha256, document_revision=document).first() if document else None
    staged = stage_document_asset(asset, stage_key=f"manual-text:{row.pk}")
    page = staged.pages.select_for_update().get(index=row.page_index)
    page.text, page.normalized_text = row.text, normalize_search_text(row.text)
    page.is_text_manual, page.manual_text_revision = True, row
    page.text_source = Page.TextSource.HYBRID
    page.save(update_fields=["text", "normalized_text", "is_text_manual", "manual_text_revision", "text_source", "updated_at"])
    # The typed text is verified at page level, never assigned guessed glyph boxes.
    page.blocks.all().delete()
    page.passages.all().delete()
    Passage.objects.bulk_create([Passage(page=page, order=order, text=text, normalized_text=normalize_search_text(text),
                                        start_offset=start, end_offset=end, bbox_union=[])
                                 for order, text, start, end, _ in _passage_chunks(
                                     [ExtractedBlock(order=i, text=row.text[i:i+700], bbox=[]) for i in range(0, len(row.text), 700)], row.text)])
    result = synchronize_document_revision(staged, parser_name=document.parser_name if document else "manual-text",
        parser_version=document.parser_version if document else "manual-text-v1", extraction_method="human_review",
        extraction_version="manual-text-v1", ocr_provider=document.ocr_provider if document else "",
        ocr_model=document.ocr_model if document else "", ocr_version=document.ocr_version if document else "",
        changed_page_indexes=[row.page_index], actor=actor)
    if outline:
        staged.outline_revisions.filter(is_active=True).update(is_active=False)
        DocumentOutlineRevision.objects.create(asset=staged, document_revision_id=result["revision_id"],
            revision=(staged.outline_revisions.values_list("revision", flat=True).first() or 0)+1,
            source_checksum=staged.sha256, parser_version=outline.parser_version, nodes=deepcopy(outline.nodes),
            diagnostics=deepcopy(outline.diagnostics), origin="manual_text", is_active=True, reviewed=outline.reviewed, created_by=actor)
    if prepared["mode"] == "publish":
        row.publication_event = create_catalog_publication_event(asset.edition,
            event_type=KnowledgePublicationEvent.EventType.CATALOG_UPDATED, changed_fields=["document_revision", "fulltext_ready"],
            actor=actor, idempotency_key=f"manual-text:{row.pk}", content_asset_id=staged.pk,
            provenance={"source": "ocr_text_correction", "page_text_revision_id": str(row.pk), "source_asset_id": str(asset.pk)})
    else:
        # A draft may still have served historically, in which case staging
        # returned a distinct asset. Activate only the normalized selection.
        Asset.objects.filter(edition=asset.edition, kind="normalized", is_current=True).exclude(pk=staged.pk).update(is_current=False, updated_at=timezone.now())
        Asset.objects.filter(pk=staged.pk).update(is_current=True, updated_at=timezone.now())
        asset.edition.semantic_index_status = SemanticIndexStatus.PENDING
        asset.edition.publication_mode = Edition.PublicationMode.DOCUMENT
        asset.edition.save(update_fields=["semantic_index_status", "publication_mode", "updated_at"])
    row.applied_asset, row.applied_at = staged, timezone.now()
    row.apply_request_id, row.apply_fingerprint = data["request_id"], command_fingerprint(data, actor)
    row.save(update_fields=["applied_asset", "applied_at", "apply_request_id", "apply_fingerprint", "publication_event", "updated_at"])
    return row


@transaction.atomic
def task_command(identifier, data, actor):
    asset = locked_asset(identifier)
    action = data["action"]
    # Audit receipt is checked before current-state/CAS validation after a lost response.
    identity = command_fingerprint(data, actor)
    receipt = AuditEvent.objects.filter(actor=actor, action="ocr.workspace.command", object_id=str(asset.pk), request_id=str(data["request_id"])).first()
    if receipt:
        if receipt.after.get("fingerprint") != identity:
            raise OCRWorkspaceConflict("同一次请求不能改变识别任务或页码。")
        return
    if action == "start":
        if data["source_version"] != asset.updated_at.isoformat():
            raise OCRWorkspaceConflict("文件已有变化，请重新选择需要识别的实际页。")
        job, _ = start_catalog_ocr({**data, "edition_id": str(asset.edition_id), "asset_id": str(asset.pk)}, actor)
    else:
        job = ProcessingJob.objects.select_for_update().get(pk=data["job_id"], edition_id=asset.edition_id, job_type="ocr")
        if str(asset.pk) not in {str(job.asset_id), str(job.stats.get("requested_asset_id") or job.stats.get("text_source_asset_id") or "")}:
            raise ValueError("这个识别任务不属于当前阅读文件，请从相应文件进入。")
        if data["job_version"] != job.updated_at.isoformat():
            raise OCRWorkspaceConflict("任务已有进展，请读取最新状态后操作。")
        job = catalog_ocr_action({"edition_id": str(asset.edition_id), "job_id": str(job.pk),
                                 "action": {"pause": "pause_catalog_ocr", "resume": "resume_catalog_ocr", "cancel": "cancel_catalog_ocr"}[action]}, actor)
    AuditEvent.objects.create(actor=actor, action="ocr.workspace.command", object_type="asset", object_id=str(asset.pk),
                              request_id=str(data["request_id"]), after={"fingerprint": identity, "job_id": str(job.pk)})
