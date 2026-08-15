from __future__ import annotations

import re

from django.db import transaction

from catalog.models import Asset, Page, PageLabelSegment, PageLabelStatus


PAGE_NUMBER_RE = re.compile(
    r"^[\s\-–—·•]*(?:第\s*)?((?:\d\s*){1,5}|(?:[ivxlcdmIVXLCDM]\s*){1,12})(?:页|頁)?[\s\-–—·•]*$"
)


def _roman_to_int(value: str) -> int | None:
    values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    text = value.casefold()
    if not text or any(char not in values for char in text):
        return None
    total = 0
    previous = 0
    for char in reversed(text):
        current = values[char]
        total += -current if current < previous else current
        previous = max(previous, current)
    return total if total > 0 else None


def _int_to_roman(value: int) -> str:
    if value < 1 or value > 3999:
        return str(value)
    parts = []
    for number, token in (
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ):
        while value >= number:
            parts.append(token)
            value -= number
    return "".join(parts)


def _parse_label(value: str) -> tuple[int | None, str]:
    value = str(value or "").strip()
    if value.isdigit():
        return int(value), PageLabelSegment.Style.ARABIC
    roman = _roman_to_int(value)
    if roman is not None:
        style = (
            PageLabelSegment.Style.ROMAN_UPPER
            if value.isupper()
            else PageLabelSegment.Style.ROMAN_LOWER
        )
        return roman, style
    return None, PageLabelSegment.Style.CUSTOM


def _format_label(value: int, style: str) -> str:
    if style == PageLabelSegment.Style.ARABIC:
        return str(value)
    if style == PageLabelSegment.Style.ROMAN_UPPER:
        return _int_to_roman(value)
    if style == PageLabelSegment.Style.ROMAN_LOWER:
        return _int_to_roman(value).casefold()
    return str(value)


def _page_label_candidate(page: Page) -> tuple[str, int, str, float, str] | None:
    candidates = []
    for block in page.blocks.all():
        if len(block.bbox) != 4 or not page.height:
            continue
        _left, top, _right, bottom = [float(value) for value in block.bbox]
        if top > page.height * 0.18 and bottom < page.height * 0.82:
            continue
        match = PAGE_NUMBER_RE.fullmatch(block.text.strip())
        if not match:
            continue
        label = re.sub(r"\s+", "", match.group(1))
        number, style = _parse_label(label)
        if number is None:
            continue
        edge_distance = min(top, max(page.height - bottom, 0)) / max(page.height, 1)
        score = max(0, min(1, float(block.confidence))) * 0.8 + max(0, 0.2 - edge_distance)
        source = (
            Page.LabelSource.OCR
            if page.text_source in {Page.TextSource.OCR, Page.TextSource.HYBRID}
            else Page.LabelSource.EMBEDDED_TEXT
        )
        candidates.append((label, number, style, min(score, 1), source))
    return max(candidates, key=lambda item: item[3]) if candidates else None


@transaction.atomic
def infer_page_labels(asset: Asset) -> dict:
    pages = list(asset.pages.prefetch_related("blocks").order_by("index"))
    candidates = {
        page.index: candidate
        for page in pages
        if not page.is_label_manual and (candidate := _page_label_candidate(page)) is not None
    }
    accepted = {}
    for index, candidate in candidates.items():
        _label, number, style, _confidence, _source = candidate
        neighbors = []
        for neighbor_index, expected_delta in ((index - 1, -1), (index + 1, 1)):
            neighbor = candidates.get(neighbor_index)
            if neighbor and neighbor[2] == style:
                neighbors.append(neighbor[1] == number + expected_delta)
        # An isolated number near a margin is not sufficient evidence.  It may
        # be a chapter number, year or footnote marker.
        if any(neighbors):
            accepted[index] = candidate

    inferred = {}
    ordered_candidates = sorted(candidates.items())
    for position, (start_index, start) in enumerate(ordered_candidates):
        for end_index, end in ordered_candidates[position + 1 : position + 9]:
            file_delta = end_index - start_index
            if file_delta < 2:
                continue
            if end[2] != start[2] or end[1] - start[1] != file_delta:
                continue
            confidence = min(start[3], end[3]) * 0.8
            for page_index in range(start_index + 1, end_index):
                if page_index not in accepted:
                    inferred[page_index] = (
                        _format_label(start[1] + page_index - start_index, start[2]),
                        start[2],
                        confidence,
                    )
            break

    for page in pages:
        if page.is_label_manual or page.label_source == Page.LabelSource.PDF_PAGE_LABELS:
            continue
        candidate = accepted.get(page.index)
        if candidate:
            page.printed_label = candidate[0]
            page.label_source = candidate[4]
            page.label_confidence = candidate[3]
        elif page.index in inferred:
            page.printed_label = inferred[page.index][0]
            page.label_source = Page.LabelSource.SEQUENCE
            page.label_confidence = inferred[page.index][2]
        else:
            page.printed_label = ""
            page.label_source = Page.LabelSource.FILE_INDEX
            page.label_confidence = 0.25
        page.save(
            update_fields=[
                "printed_label",
                "label_source",
                "label_confidence",
                "updated_at",
            ]
        )
    asset.edition.page_label_status = PageLabelStatus.NEEDS_REVIEW
    asset.edition.save(update_fields=["page_label_status", "updated_at"])
    return {
        "pages": len(pages),
        "ocr_candidates": len(candidates),
        "accepted_continuous_candidates": len(accepted),
        "sequence_inferred_pages": len(inferred),
        "status": asset.edition.page_label_status,
    }


@transaction.atomic
def apply_page_label_segment(segment: PageLabelSegment) -> int:
    pages = segment.asset.pages.filter(index__gte=segment.start_file_page_index)
    if segment.end_file_page_index:
        pages = pages.filter(index__lte=segment.end_file_page_index)
    start_number, parsed_style = _parse_label(segment.start_label)
    style = segment.style or parsed_style
    updated = 0
    for page in pages.order_by("index"):
        offset = page.index - segment.start_file_page_index
        if style == PageLabelSegment.Style.NONE:
            label = ""
        elif style == PageLabelSegment.Style.CUSTOM:
            label = segment.start_label if offset == 0 else ""
        elif start_number is not None:
            label = _format_label(start_number + offset, style)
        else:
            label = ""
        page.printed_label = label
        page.label_source = Page.LabelSource.MANUAL
        page.label_confidence = 1
        page.is_label_manual = True
        page.is_label_anchor = offset == 0
        page.label_segment = str(segment.id)
        page.save(
            update_fields=[
                "printed_label",
                "label_source",
                "label_confidence",
                "is_label_manual",
                "is_label_anchor",
                "label_segment",
                "updated_at",
            ]
        )
        updated += 1
    segment.asset.edition.page_label_status = PageLabelStatus.NEEDS_REVIEW
    segment.asset.edition.save(update_fields=["page_label_status", "updated_at"])
    return updated
