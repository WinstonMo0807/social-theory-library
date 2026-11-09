"""Restore neighbouring source text without joining unrelated quotations."""
from uuid import UUID
from collections import defaultdict

from django.db.models import F, Q
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import DiscoveryDocument, DocumentRevision, EvidenceSpan, Passage
from catalog.services.publication_eligibility import active_document_revision_q, current_retrieval_source_q
from catalog.services.discovery_sessions import DEEP_RESULTS_KEY, _public_row
from catalog.services.discovery_documents import allowed_rows, effective_filters


def rerank_contexts(rows, access_statuses):
    """Experimental, bounded evidence windows. Never trust caller-supplied text.

    Public session_context retains its existing display contract. This batch
    reader is only used by the isolated comparison runner, not public ranking.
    """
    from catalog.services.discovery_projection import validate_discovery_results, DiscoveryIndexError
    from catalog.services.discovery_sources import fingerprint

    if len(rows) > 40:
        raise ValueError("上下文重排每批最多40条。")
    fresh = validate_discovery_results("passages", rows, access_statuses)
    if [row["id"] for row in fresh] != [row["id"] for row in rows]:
        raise DiscoveryIndexError("sources_changed", "候选来源已改变，请重新运行比较。")
    if not fresh:
        return []
    scope = Q(pk__in=[])
    for row in fresh:
        scope |= Q(document_revision_id=row["document_revision_id"], page__asset_id=row["asset_id"],
                   page_number__gte=max(1, row["pdf_page"] - 1), page_number__lte=row["pdf_page"] + 1)
    spans = list(EvidenceSpan.objects.filter(scope, is_stale=False).filter(
        page_number=F("page__index")
    ).values("id", "document_revision_id", "page_id", "page_number", "start_offset", "end_offset",
             "original_text", "section").order_by("document_revision_id", "page_number", "start_offset", "id")[:5001])
    if len(spans) > 5000:
        raise DiscoveryIndexError("context_limit", "邻文范围过大，拒绝生成不完整评测。")
    groups, by_id = defaultdict(list), {}
    for span in spans:
        groups[str(span["document_revision_id"])].append(span)
        by_id[str(span["id"])] = span

    def block(span, start, end, role):
        text = span["original_text"][start:end]
        return {"evidence_span_id": str(span["id"]), "document_revision_id": str(span["document_revision_id"]),
                "page_id": str(span["page_id"]), "pdf_page": span["page_number"], "role": role,
                "start_offset": span["start_offset"] + start, "end_offset": span["start_offset"] + end,
                "text": text, "text_hash": fingerprint(text)}

    output = []
    for row in fresh:
        hit = by_id.get(str(row.get("evidence_span_id")))
        blocks, before, after = [], "", ""
        if hit is not None:
            start, end = row["unit_start_offset"], row["unit_end_offset"]
            if hit["original_text"][start:end] != row["text"]:
                raise DiscoveryIndexError("sources_changed")
            if start:
                blocks.append(block(hit, max(0, start - 1000), start, "before"))
            else:
                prior = [s for s in groups[str(hit["document_revision_id"])]
                         if (s["page_number"] < hit["page_number"] or
                             s["page_number"] == hit["page_number"] and s["end_offset"] <= hit["start_offset"])
                         and s["id"] != hit["id"]]
                neighbor = prior[-1] if prior else None
                if neighbor and hit["page_number"] - neighbor["page_number"] <= 1 and not (
                        hit["section"] and neighbor["section"] and hit["section"] != neighbor["section"]):
                    blocks.append(block(neighbor, max(0, len(neighbor["original_text"]) - 1000), len(neighbor["original_text"]), "before"))
            blocks.append(block(hit, start, end, "hit"))
            if end < len(hit["original_text"]):
                blocks.append(block(hit, end, min(len(hit["original_text"]), end + 1000), "after"))
            else:
                following = [s for s in groups[str(hit["document_revision_id"])]
                             if (s["page_number"] > hit["page_number"] or
                                 s["page_number"] == hit["page_number"] and s["start_offset"] >= hit["end_offset"])
                             and s["id"] != hit["id"]]
                neighbor = following[0] if following else None
                if neighbor and neighbor["page_number"] - hit["page_number"] <= 1 and not (
                        hit["section"] and neighbor["section"] and hit["section"] != neighbor["section"]):
                    blocks.append(block(neighbor, 0, min(1000, len(neighbor["original_text"])), "after"))
            before = "\n".join(b["text"] for b in blocks if b["role"] == "before")
            after = "\n".join(b["text"] for b in blocks if b["role"] == "after")
        output.append({"before": before, "after": after, "blocks": blocks,
                       "context_available": bool(before or after), "excerpt": row["text"],
                       "fingerprint": fingerprint([row["id"], row["source_revision"], row["text"], blocks])})
    return output


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
    refs = [row for key in (DEEP_RESULTS_KEY, "passages") for row in (session.results or {}).get(key, [])
            if str(row.get("id")) == str(result_id)]
    if not refs:
        raise NotFound("本次检索中不存在该原文。")
    rows = allowed_rows(session, validate_discovery_results("passages", refs, access_statuses, filters=effective_filters(session)))
    if not rows:
        raise NotFound("原文来源已更新、撤回或不再可访问，请重新检索。")
    row = _public_row(rows[0])
    revision_id = _uuid(row.get("document_revision_id"))
    asset_id = _uuid(row.get("asset_id"))
    revision = DocumentRevision.objects.filter(pk=revision_id, asset_id=asset_id,
        asset__access_status__in=access_statuses).filter(
        active_document_revision_q(revision_prefix=""), current_retrieval_source_q(asset_prefix="asset", access_statuses=access_statuses)).first()
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
    logical = None
    if session.owner_id:
        from catalog.services.retrieval.locators import attach_locators
        from catalog.models import DocumentNode
        from catalog.services.knowledge_sources import context
        enriched = attach_locators(rows)[0]
        node = DocumentNode.objects.filter(pk=enriched.get("node_id"), document_revision=revision).first()
        if node:
            logical = context(node, session.owner, scope="section", budget=12000)
            blocks = [{"text": segment["exact"], "pdf_page": segment["page_number"],
                "start": segment["start"], "end": segment["end"], "role": "hit" if segment["page_number"] == page_number
                else "before" if segment["page_number"] < page_number else "after",
                "truncated": segment["partial_segment"]} for segment in logical["segments"]]
    # Only identities from this bounded session are candidates. Hydration again
    # checks the active publication and exact text; withdrawn neighbours vanish.
    references = {str(ref.get("id")): ref for key in (DEEP_RESULTS_KEY, "passages")
                  for ref in (session.results or {}).get(key, [])[:400] if _uuid(ref.get("id"))}
    candidate_ids = set(map(str, DiscoveryDocument.objects.filter(pk__in=references,
        channel="passages", payload__work__id=str(row.get("work", {}).get("id"))).values_list("pk", flat=True)))
    candidate_refs = [ref for key, ref in references.items() if key in candidate_ids]
    candidates = [_public_row(value) for value in allowed_rows(session, validate_discovery_results("passages", candidate_refs, access_statuses, filters=effective_filters(session)))]
    candidates.sort(key=lambda value: (str(value.get("edition_id", "")), value.get("pdf_page") or 0, value["id"]))
    current = next((index for index, value in enumerate(candidates) if value["id"] == str(result_id)), None)
    # Context assembly performs multiple reads. Recheck the requested source
    # after those reads rather than returning a quotation withdrawn meanwhile.
    fresh = allowed_rows(session, validate_discovery_results("passages", refs, access_statuses, filters=effective_filters(session)))
    if not fresh:
        raise NotFound("原文来源已更新、撤回或不再可访问，请重新检索。")
    row = _public_row(fresh[0])
    # Quotes are never rewritten; bounding context does not modify stored text.
    return {"result_id": str(result_id), "document_revision_id": str(revision.id),
            "source": row, "same_work_count": len(candidates), "same_work_results": candidates[:20],
            "previous_result_id": candidates[current - 1]["id"] if current is not None and current > 0 else None,
            "next_result_id": candidates[current + 1]["id"] if current is not None and current + 1 < len(candidates) else None,
            "asset_id": str(asset_id), "excerpt": row.get("excerpt", ""), "blocks": blocks,
            "before": "\n\n".join(item["text"] for item in blocks if item["role"] == "before"),
            "after": "\n\n".join(item["text"] for item in blocks if item["role"] == "after"),
            "reader_url": row.get("reader_url", ""),
            "locator_precision": row.get("locator_precision") or "page",
            "source_kind": row.get("source_kind", "collection_text"),
            "logical_context": logical,
            "notice": ("上下文按正文结构展开；返回范围和相关脚注见结构信息。" if logical else "上下文来自同一正文修订，相邻页面分别保留页号。") +
                      ("部分长段仅显示命中位置附近的连续文字；请打开 PDF 查看完整上下文。"
                       if any(item.get("truncated") for item in blocks) else "")}
