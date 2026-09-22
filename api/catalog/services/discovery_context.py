"""Restore neighbouring source text without joining unrelated quotations."""
from uuid import UUID

from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import DocumentRevision, EvidenceSpan, Passage
from catalog.services.publication_eligibility import active_document_revision_q
from catalog.services.discovery_sessions import _public_row


def _uuid(value):
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _bounded_block(text, page, role, excerpt=""):
    # A malformed OCR paragraph can contain a whole chapter. Return one
    # contiguous source window and explicitly disclose the omitted context.
    limit = 6000
    start = 0
    if len(text) > limit:
        if role == "before":
            start = len(text) - limit
        elif role == "hit":
            found = text.find(excerpt[:200]) if excerpt else -1
            start = max(0, min(len(text) - limit, found - 1200)) if found >= 0 else 0
    return {"text": text[start:start + limit], "pdf_page": page, "role": role,
            "truncated": len(text) > limit}


def session_context(session, result_id, access_statuses):
    from catalog.services.discovery_projection import validate_discovery_results
    if _uuid(result_id) is None:
        raise ValidationError({"result_id": "原文标识无效。"})
    ref = next((row for row in (session.results or {}).get("passages", [])
                if str(row.get("id")) == str(result_id)), None)
    if ref is None:
        raise NotFound("本次检索中不存在该原文。")
    rows = validate_discovery_results("passages", [ref], access_statuses)
    if not rows:
        raise NotFound("原文来源已更新、撤回或不再可访问，请重新检索。")
    row = _public_row(rows[0])
    revision_id = _uuid(row.get("document_revision_id"))
    asset_id = _uuid(row.get("asset_id"))
    revision = DocumentRevision.objects.filter(pk=revision_id, asset_id=asset_id,
        asset__access_status__in=access_statuses).filter(
        active_document_revision_q(revision_prefix="")).first()
    if revision is None:
        raise NotFound("原文修订已更新，请重新检索。")
    try:
        page_number = int(row.get("pdf_page"))
    except (ValueError, TypeError):
        raise NotFound("原文页码不可用。")
    hit_id = _uuid(row.get("evidence_span_id"))
    passage_id = _uuid(row.get("passage_id"))
    hit = EvidenceSpan.objects.filter(document_revision=revision, is_stale=False)
    if hit_id:
        hit = hit.filter(pk=hit_id)
    elif passage_id:
        hit = hit.filter(passage_id=passage_id)
    else:
        hit = hit.filter(page_number=page_number, original_text__contains=row.get("excerpt", "")[:180])
    span = hit.order_by("start_offset").first()
    blocks = []
    if span is not None:
        spans = EvidenceSpan.objects.filter(document_revision=revision, is_stale=False)
        before = list(spans.filter(Q(page_number__lt=span.page_number) |
                                  Q(page_number=span.page_number, end_offset__lte=span.start_offset))
                      .exclude(pk=span.pk).order_by("-page_number", "-start_offset")[:2])
        after = list(spans.filter(Q(page_number__gt=span.page_number) |
                                 Q(page_number=span.page_number, start_offset__gte=span.end_offset))
                     .exclude(pk=span.pk).order_by("page_number", "start_offset")[:2])
        # Only adjacent PDF pages are context; a missing page creates a visible
        # boundary instead of making distant paragraphs look continuous.
        for item in reversed(before):
            if span.page_number - item.page_number <= 1:
                blocks.append(_bounded_block(item.original_text, item.page_number, "before"))
        blocks.append(_bounded_block(span.original_text, span.page_number, "hit", row.get("excerpt", "")))
        for item in after:
            if item.page_number - span.page_number <= 1:
                blocks.append(_bounded_block(item.original_text, item.page_number, "after"))
    else:
        # Pages/Passage retain their stable Asset identity. Only use them after
        # the projected document revision has been revalidated above.
        passage = Passage.objects.filter(pk=passage_id, page__asset_id=asset_id).first() if passage_id else None
        if passage is not None:
            neighbours = list(Passage.objects.filter(page=passage.page, order__gte=max(0, passage.order - 2),
                                                     order__lte=passage.order + 2).order_by("order"))
            blocks = [_bounded_block(item.text, passage.page.index,
                       "before" if item.order < passage.order else "after" if item.order > passage.order else "hit", row.get("excerpt", ""))
                      for item in neighbours]
        else:
            blocks = [{"text": row.get("excerpt", ""), "pdf_page": page_number, "role": "hit"}]
    # Quotes are never rewritten; bounding context does not modify stored text.
    return {"result_id": str(result_id), "document_revision_id": str(revision.id),
            "asset_id": str(asset_id), "excerpt": row.get("excerpt", ""), "blocks": blocks,
            "before": "\n\n".join(item["text"] for item in blocks if item["role"] == "before"),
            "after": "\n\n".join(item["text"] for item in blocks if item["role"] == "after"),
            "reader_url": row.get("reader_url", ""),
            "locator_precision": row.get("locator_precision") or "page",
            "source_kind": row.get("source_kind", "collection_text"),
            "notice": "上下文来自同一正文修订，相邻页面分别保留页号。" +
                      ("部分长段仅显示命中位置附近的连续文字；请打开 PDF 查看完整上下文。"
                       if any(item.get("truncated") for item in blocks) else "")}
