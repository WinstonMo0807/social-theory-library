"""Bounded parallel-reading sources over the existing publication and evidence boundary."""
from hashlib import sha256
from urllib.parse import urlencode
from uuid import UUID

from django.contrib.auth.models import AnonymousUser
from django.db.models import F, Q
from django.urls import reverse
from rest_framework.exceptions import APIException, NotFound, ValidationError

from catalog.models import EvidenceSpan, Page
from catalog.services.discovery_inference import DiscoveryInferenceError
from catalog.services.discovery_projection import DiscoveryIndexError
from catalog.services.discovery_sessions import request_access, retrieve_discovery_channel
from catalog.services.publication_eligibility import public_editions
from catalog.services.text import clean_page_label, page_text_range

PAGE_SIZE = 20
MAX_TEXT = 12000
MAX_VERSIONS = 60


class ParallelSourceChanged(APIException):
    status_code = 409
    default_detail = "来源已更新，请重新选择当前版本和段落；原有私人记录保留。"


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"source": "来源标识需要有效 UUID。"})


def _access(user, public=False):
    from types import SimpleNamespace
    return request_access(SimpleNamespace(user=AnonymousUser() if public else user))


def _snapshot(edition):
    value = edition.active_catalog_revision.snapshot
    return value if isinstance(value, dict) else {}


def _parent(edition):
    value = (_snapshot(edition).get("work") or {}).get("translation_of_id")
    try:
        return str(UUID(str(value))) if value else None
    except (ValueError, TypeError, AttributeError):
        return None


def _family(source):
    """Follow only activated translation edges; bound both depth and graph size."""
    seen, frontier = {str(source.work_id)}, {str(source.work_id)}
    for _ in range(8):
        rows = list(public_editions().filter(
            Q(work_id__in=frontier) |
            Q(active_catalog_revision__snapshot__work__translation_of_id__in=sorted(frontier))
        ).order_by("work_id", "id")[:257])
        if len(rows) > 256:
            return seen, True
        found = {str(row.work_id) for row in rows}
        found.update(parent for row in rows if (parent := _parent(row)))
        frontier = found - seen
        if not frontier:
            return seen, False
        if len(seen | frontier) > 64:
            return seen, True
        seen.update(frontier)
    return seen, bool(frontier)


def serving_edition(user, asset_id, *, document_revision_id=None, public=False, require_fulltext=True):
    asset_id = _uuid(asset_id)
    rows = public_editions(require_fulltext=require_fulltext).filter(
        active_catalog_revision__reader_asset_id=asset_id,
        active_catalog_revision__reader_asset__edition_id=F("pk"),
        active_catalog_revision__reader_asset__kind="normalized",
        active_catalog_revision__reader_asset__status="ready",
        active_catalog_revision__reader_asset__validation_status="valid",
        active_catalog_revision__reader_asset__access_status__in=_access(user, public),
    )
    if require_fulltext:
        rows = rows.filter(active_catalog_revision__document_revision__asset_id=F("active_catalog_revision__reader_asset_id"))
    edition = rows.first()
    if edition is None or str((_snapshot(edition).get("document") or {}).get("asset_id")) != asset_id:
        raise NotFound("该版本当前不可阅读，或已撤回。")
    if document_revision_id is not None and str(edition.active_catalog_revision.document_revision_id) != _uuid(document_revision_id):
        raise ParallelSourceChanged()
    return edition


def validate_pair(user, left_asset_id, right_asset_id, *, left_document_revision_id=None,
                  right_document_revision_id=None, public=False, require_fulltext=True):
    """Shared by private saves and public proposals; never infer a relation from titles."""
    left = serving_edition(user, left_asset_id, document_revision_id=left_document_revision_id,
                           public=public, require_fulltext=require_fulltext)
    right = serving_edition(user, right_asset_id, document_revision_id=right_document_revision_id,
                            public=public, require_fulltext=require_fulltext)
    if left.pk == right.pk:
        raise ValidationError({"versions": "请选择两个不同的阅读版本。"})
    if left.work_id != right.work_id:
        family, truncated = _family(left)
        if str(right.work_id) not in family:
            message = "正式译作关系范围过大，请选择直接关联的版本。" if truncated else "这两个版本尚无正式确认的原作、译作或同作品关系。"
            raise ValidationError({"versions": message})
    return left, right


def resolve_parallel_reference(raw, user, *, strict=True, public=False):
    """Same resolved shape as research references, with exact revision/hash required."""
    from reading.research import resolve_reference

    if not isinstance(raw, dict):
        raise ValidationError({"reference": "原文引用需要对象。"})
    anchors = raw.get("anchors", [raw])
    if not isinstance(anchors, list) or not 1 <= len(anchors) <= 20:
        raise ValidationError({"reference": "引用需要 1 至 20 个单页锚点。"})
    for anchor in anchors:
        if not isinstance(anchor, dict) or any(not anchor.get(key) for key in ("asset_id", "document_revision_id", "content_hash")):
            raise ValidationError({"reference": "请保留原文文件、文字修订和内容校验标识。"})
    actor = AnonymousUser() if public else user
    result = resolve_reference(raw, actor, strict=strict)
    if result["source_status"] != "available":
        return result
    try:
        serving_edition(actor, result["asset_id"], document_revision_id=result["document_revision_id"])
    except (NotFound, ParallelSourceChanged):
        if strict:
            raise
        return {**result, "source_status": "unavailable", "quote": "", "reader_url": None}
    if len(result.get("quote", "")) > 20000:
        raise ValidationError({"reference": "选文过长，请缩小到 20000 字以内的原文范围。"})
    return result


def _version(edition, source, access):
    revision = edition.active_catalog_revision
    snapshot = _snapshot(edition)
    work, bibliographic = snapshot.get("work") or {}, snapshot.get("edition") or {}
    asset = revision.reader_asset
    authorized = bool(asset and asset.edition_id == edition.pk and asset.kind == "normalized" and
        asset.status == "ready" and asset.validation_status == "valid" and asset.access_status in access and
        str((snapshot.get("document") or {}).get("asset_id")) == str(asset.pk))
    available = bool(authorized and revision.fulltext_ready and revision.document_revision_id and
                     revision.document_revision.asset_id == asset.pk)
    cover = work.get("cover_media") or {}
    params = {"edition_id": str(edition.pk)}
    if cover.get("primary_rendition_id"):
        params["rendition"] = cover["primary_rendition_id"]
    return {
        "work_id": str(edition.work_id), "edition_id": str(edition.pk),
        "asset_id": str(asset.pk) if authorized else None,
        "document_revision_id": str(revision.document_revision_id) if available else None,
        "title": work.get("title", ""), "original_title": work.get("original_title", ""),
        "authors": [str((item.get("person") or {}).get("preferred_name") or item.get("name") or "")
                    for item in snapshot.get("contributions", []) if isinstance(item, dict) and item.get("role") == "author"],
        "language": work.get("language", ""), "publication_year": bibliographic.get("publication_year"),
        "version_label": bibliographic.get("version_label", ""), "publisher": bibliographic.get("publisher", ""),
        "cover_url": reverse("public-work-cover", kwargs={"work_id": edition.work_id}) + "?" + urlencode(params)
                     if work.get("cover") or cover else None,
        "total_pages": (asset.page_count or 0) if authorized else 0,
        "relation": "same_work" if edition.work_id == source.work_id else "translation",
        "current": edition.pk == source.pk, "state": "available" if available else "metadata_only",
        "notice": "" if available else "该版本已有书目，当前未提供可用于并读的文字。",
    }


def versions(user, asset_id):
    source = serving_edition(user, asset_id, require_fulltext=False)
    family, truncated = _family(source)
    rows = list(public_editions().filter(work_id__in=family).exclude(pk=source.pk)
                .order_by("work_id", "-is_primary", "id")[:MAX_VERSIONS])
    serving_edition(user, asset_id, require_fulltext=False)
    return {"source_asset_id": str(source.active_catalog_revision.reader_asset_id),
            "versions": [_version(row, source, _access(user)) for row in [source, *rows[:MAX_VERSIONS - 1]]],
            "truncated": truncated or len(rows) >= MAX_VERSIONS}


def _page_reference(edition, page):
    return {"work_id": str(edition.work_id), "edition_id": str(edition.pk), "asset_id": str(page.asset_id),
            "document_revision_id": str(edition.active_catalog_revision.document_revision_id),
            "pdf_page": page.index, "content_hash": sha256(page.text.encode()).hexdigest()}


def _segment(raw, user, *, label, order, text_length):
    truncated = text_length > MAX_TEXT
    if truncated:
        raw = {**raw, "selection_start": raw.get("selection_start", 0),
               "selection_end": raw.get("selection_start", 0) + MAX_TEXT}
    resolved = resolve_parallel_reference(raw, user)
    return {"id": resolved["reference_id"], "label": label, "order": order, "reference": resolved,
            "printed_label": clean_page_label(resolved.get("printed_label", "")), "text": resolved["quote"],
            "text_truncated": truncated}


def _focus_offset(focus, spans, source_page):
    if spans.exists():
        key = _uuid(focus.split(":", 1)[0])
        selected = spans.filter(pk=key).first()
        if selected is None:
            raise NotFound("该段落不属于当前页和文字修订。")
        before = spans.filter(Q(start_offset__lt=selected.start_offset) |
                              Q(start_offset=selected.start_offset, id__lt=selected.id)).count()
    else:
        parts = focus.split(":")
        if (len(parts) != 5 or parts[0] != str(source_page.asset_id) or parts[1] != str(source_page.index)
                or parts[2] != "range" or not parts[3].isdigit() or not parts[4].isdigit()):
            raise ValidationError({"focus": "请使用本页返回的段落定位标识。"})
        start, end = int(parts[3]), int(parts[4])
        if not 0 <= start < end <= len(source_page.text):
            raise ParallelSourceChanged()
        selected = source_page.passages.filter(start_offset__lte=start, end_offset__gt=start).order_by("order").first()
        if selected:
            if not page_text_range(source_page.text, selected.text, selected.start_offset, selected.end_offset):
                raise ParallelSourceChanged()
            before = source_page.passages.filter(order__lt=selected.order).count()
        elif source_page.passages.exists():
            raise NotFound("该选文位置不属于本页已核对的段落。")
        else:
            before = start // MAX_TEXT
    return (before // PAGE_SIZE) * PAGE_SIZE


def segments(user, asset_id, *, document_revision_id=None, page=1, offset=0, focus=""):
    edition = serving_edition(user, asset_id, document_revision_id=document_revision_id, require_fulltext=False)
    revision = edition.active_catalog_revision
    asset = revision.reader_asset
    total = asset.page_count or asset.pages.order_by("-index").values_list("index", flat=True).first() or 0
    if page > total:
        raise NotFound("该文件没有此物理页。")
    payload = {"asset_id": str(asset.pk), "edition_id": str(edition.pk),
        "document_revision_id": str(revision.document_revision_id) if revision.fulltext_ready and revision.document_revision_id else None,
        "page": page, "total_pages": total, "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < total else None, "state": "text_unavailable",
        "notice": "本页尚无获准用于并读的文字，可返回单文献阅读原页。", "segments": [],
        "offset": offset, "has_more": False, "next_offset": None}
    if not revision.fulltext_ready or not revision.document_revision_id:
        return payload
    # A fulltext-ready flag cannot substitute for the active document/file identity.
    serving_edition(user, asset_id, document_revision_id=document_revision_id)
    if document_revision_id is None:
        raise ValidationError({"document_revision_id": "请保留当前文字修订标识。"})
    source_page = Page.objects.filter(asset=asset, index=page).first()
    if source_page is None:
        return payload
    spans = source_page.evidence_spans.filter(document_revision_id=revision.document_revision_id,
        page_number=page, is_stale=False).exclude(original_text="").select_related("passage").order_by("start_offset", "id")
    if focus:
        offset = _focus_offset(focus, spans, source_page)
        payload["offset"] = offset
    rows = list(spans[offset:offset + PAGE_SIZE + 1])
    if rows:
        payload["state"] = "ready"
        for index, span in enumerate(rows[:PAGE_SIZE], start=offset + 1):
            raw = {**_page_reference(edition, source_page), "evidence_span_id": str(span.pk), "content_hash": span.content_hash}
            label = f"PDF 第 {page} 页 · 页内段落 {index}" if span.passage else f"PDF 第 {page} 页 · 原文片段 {index}"
            payload["segments"].append(_segment(raw, user, label=label, order=index, text_length=len(span.original_text)))
        payload["has_more"] = len(rows) > PAGE_SIZE
    elif spans.exists():
        payload["state"] = "ready"
    else:
        passages = list(source_page.passages.order_by("order")[offset:offset + PAGE_SIZE + 1])
        if passages:
            payload["state"] = "ready"
            for index, passage in enumerate(passages[:PAGE_SIZE], start=offset + 1):
                if not page_text_range(source_page.text, passage.text, passage.start_offset, passage.end_offset):
                    continue
                raw = {**_page_reference(edition, source_page), "selection_start": passage.start_offset,
                       "selection_end": passage.end_offset}
                payload["segments"].append(_segment(raw, user, label=f"PDF 第 {page} 页 · 页内段落 {index}",
                                                     order=index, text_length=len(passage.text)))
            payload["has_more"] = len(passages) > PAGE_SIZE
        if not payload["segments"] and not source_page.passages.exists():
            payload["state"] = "unstructured" if source_page.text.strip() else "empty"
            start = offset * MAX_TEXT
            for index in range(offset, offset + PAGE_SIZE):
                begin, end = index * MAX_TEXT, min((index + 1) * MAX_TEXT, len(source_page.text))
                if begin >= end:
                    break
                if not source_page.text[begin:end].strip():
                    continue
                raw = {**_page_reference(edition, source_page), "selection_start": begin, "selection_end": end}
                payload["segments"].append(_segment(raw, user, label=f"PDF 第 {page} 页 · 页内文字 {index + 1}",
                                                     order=index + 1, text_length=end - begin))
            payload["has_more"] = start + PAGE_SIZE * MAX_TEXT < len(source_page.text)
        elif not payload["segments"] and not payload["has_more"]:
            payload.update(state="text_unavailable", notice="本页段落位置尚不能精确核对，可返回原页阅读。")
    if payload["state"] == "ready":
        payload["notice"] = "段落过长，仅显示当前选文范围；可打开原页继续阅读。" if any(row["text_truncated"] for row in payload["segments"]) else ""
    elif payload["state"] == "unstructured":
        payload["notice"] = "本页尚无可靠段落结构，以下为原页文字，未推断段落对应关系。"
    elif payload["state"] == "empty":
        payload["notice"] = "本页没有可用文字；可能为空白页或尚未识别的扫描页，可返回原页查看。"
    if payload["has_more"]:
        payload["next_offset"] = offset + PAGE_SIZE
    serving_edition(user, asset_id, document_revision_id=document_revision_id)
    return payload


def candidates(user, left_reference, target_asset_id, target_document_revision_id):
    left = resolve_parallel_reference(left_reference, user)
    pair_kwargs = {"left_document_revision_id": left["document_revision_id"],
                   "right_document_revision_id": target_document_revision_id}
    validate_pair(user, left["asset_id"], target_asset_id, **pair_kwargs)
    output = {"state": "empty", "notice": "没有返回候选；仍可手动选择段落或明确标记无对应段。",
              "candidates": [], "warnings": [], "allows_no_correspondence": True}
    query = left["quote"][:1200]
    if not query.strip():
        raise ValidationError({"left_reference": "请选择有文字的原文范围。"})
    try:
        result = retrieve_discovery_channel(query, "passages", {"_asset_id": _uuid(target_asset_id)},
                                            _access(user), limit=24)
    except (DiscoveryIndexError, DiscoveryInferenceError) as exc:
        resolve_parallel_reference(left_reference, user)
        validate_pair(user, left["asset_id"], target_asset_id, **pair_kwargs)
        output.update(state="unavailable", notice="候选检索暂不可用，已保留手动选择与私人对齐。",
                      warnings=[{"code": exc.code, "message": "候选检索暂不可用，请稍后重试。"}])
        return output
    # Recheck both sides after potentially slow inference, including publication changes.
    resolve_parallel_reference(left_reference, user)
    validate_pair(user, left["asset_id"], target_asset_id, **pair_kwargs)
    output["warnings"] = [{"code": str(row.get("code", "partial")), "message": str(row.get("message", "候选仅部分可用。"))}
                          for row in result.get("warnings", [])[:10] if isinstance(row, dict)]
    if len(left["quote"]) > 1200:
        output["warnings"].append({"code": "query_excerpt", "message": "候选检索使用选文前 1200 字；保存仍保留原选择范围。"})
    seen = set()
    for row in result.get("rows", [])[:24]:
        if (str(row.get("asset_id")) != str(target_asset_id) or
                str(row.get("document_revision_id")) != str(target_document_revision_id)):
            continue
        if type(row.get("pdf_page")) is not int or row["pdf_page"] < 1:
            continue
        raw = {"asset_id": str(target_asset_id), "document_revision_id": str(target_document_revision_id),
               "pdf_page": row.get("pdf_page")}
        span = EvidenceSpan.objects.select_related("page").filter(pk=row["evidence_span_id"], is_stale=False).first() if row.get("evidence_span_id") else None
        if row.get("evidence_span_id") and span is None:
            continue
        page = span.page if span else Page.objects.filter(asset_id=target_asset_id, index=raw["pdf_page"]).first()
        if page is None:
            continue
        text = span.original_text if span else page.text
        raw["content_hash"] = span.content_hash if span else sha256(text.encode()).hexdigest()
        if span:
            raw["evidence_span_id"] = str(span.pk)
        start, end = row.get("unit_start_offset"), row.get("unit_end_offset")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text) or text[start:end] != row.get("text"):
            continue
        raw.update(selection_start=start, selection_end=min(end, start + MAX_TEXT))
        resolved = resolve_parallel_reference(raw, user, strict=False)
        if resolved["source_status"] != "available" or resolved["reference_id"] in seen:
            continue
        seen.add(resolved["reference_id"])
        output["candidates"].append({"reference": resolved, "label": f"PDF 第 {resolved['pdf_page']} 页",
                                     "text": resolved["quote"], "status": "pending", "text_truncated": end - start > MAX_TEXT})
        if len(output["candidates"]) == 6:
            break
    validate_pair(user, left["asset_id"], target_asset_id, **pair_kwargs)
    if output["candidates"]:
        output.update(state="partial" if output["warnings"] else "ready",
                      notice="候选仅供人工核对，选择并保存后才形成私人对齐。")
    elif output["warnings"]:
        output.update(state="partial", notice="候选检索尚不完整，可继续手动选择；未返回候选不表示无对应段。")
        codes = {warning["code"] for warning in output["warnings"]}
        if "index_pending" in codes or {"keyword_unavailable", "dense_unavailable"} <= codes:
            output.update(state="unavailable", notice="候选检索当前不可用，仍可手动选择和保存私人对齐。")
    return output
