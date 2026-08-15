from dataclasses import dataclass
from pathlib import Path
import re

import fitz
from django.db import transaction

from catalog.models import Asset, Page, Passage, TextBlock
from catalog.services.text import clean_page_label, normalize_search_text
from .ocr_provider import (
    OCRConfigurationError,
    OCRServiceUnavailable,
    parse_pdf_pages_with_ocr,
    parse_pdf_with_ocr,
)


class OCRRequired(RuntimeError):
    pass


@dataclass
class ExtractedBlock:
    order: int
    text: str
    bbox: list[float]
    block_type: str = "paragraph"
    confidence: float = 1


@dataclass
class ExtractedPage:
    index: int
    printed_label: str
    chapter_title: str
    width: float
    height: float
    text: str
    source: str
    confidence: float
    blocks: list[ExtractedBlock]
    label_source: str = Page.LabelSource.UNKNOWN
    label_confidence: float = 0
    raster_coverage: float = 0
    ocr_reasons: tuple[str, ...] = ()


def _explicit_page_labels(document) -> bool:
    try:
        return bool(document.get_page_labels())
    except (AttributeError, RuntimeError, ValueError):
        return False


def _page_label(page, *, explicit_labels: bool) -> tuple[str, str, float]:
    if not explicit_labels:
        return "", Page.LabelSource.FILE_INDEX, 0.25
    label = clean_page_label(page.get_label())
    if not label:
        return "", Page.LabelSource.UNKNOWN, 0
    return label, Page.LabelSource.PDF_PAGE_LABELS, 0.95


def _page_raster_coverage(page) -> float:
    page_area = max(float(page.rect.width) * float(page.rect.height), 1)
    coverage = 0.0
    try:
        for image in page.get_image_info():
            rectangle = fitz.Rect(image.get("bbox", (0, 0, 0, 0))) & page.rect
            if rectangle.is_empty:
                continue
            coverage = max(coverage, (rectangle.width * rectangle.height) / page_area)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return 0
    return round(max(0, min(1, coverage)), 4)


def _has_unmapped_composite_font(document, page) -> bool:
    unreliable_encodings = {
        "GB-EUC-H",
        "GB-EUC-V",
        "GBK-EUC-H",
        "GBK-EUC-V",
        "Identity-H",
        "Identity-V",
    }
    try:
        fonts = page.get_fonts(full=True)
    except (AttributeError, RuntimeError, ValueError):
        return False
    for font in fonts:
        if len(font) < 6 or str(font[2]).casefold() != "type0":
            continue
        encoding = str(font[5] or "")
        if encoding not in unreliable_encodings:
            continue
        try:
            value_type, value = document.xref_get_key(int(font[0]), "ToUnicode")
        except (RuntimeError, TypeError, ValueError):
            continue
        if value_type == "null" or not str(value or "").strip() or str(value).strip() == "null":
            return True
    return False


def _native_pages(path: str | Path) -> list[ExtractedPage]:
    document = fitz.open(str(path))
    try:
        explicit_labels = _explicit_page_labels(document)
        chapter_by_page = {}
        for _level, title, page_number, *_rest in document.get_toc(simple=True):
            if page_number > 0 and title:
                chapter_by_page.setdefault(page_number, title.strip())
        pages: list[ExtractedPage] = []
        for page_index, page in enumerate(document, start=1):
            printed_label, label_source, label_confidence = _page_label(
                page,
                explicit_labels=explicit_labels,
            )
            raw = page.get_text("dict", sort=True)
            blocks: list[ExtractedBlock] = []
            for raw_block in raw.get("blocks", []):
                if raw_block.get("type") != 0:
                    continue
                line_texts = []
                for line in raw_block.get("lines", []):
                    span_text = "".join(span.get("text", "") for span in line.get("spans", []))
                    if span_text.strip():
                        line_texts.append(span_text.strip())
                text = "\n".join(line_texts).strip()
                if text:
                    blocks.append(
                        ExtractedBlock(
                            order=len(blocks),
                            text=text,
                            bbox=[round(float(value), 2) for value in raw_block.get("bbox", (0, 0, 0, 0))],
                        )
                    )
            text = "\n\n".join(block.text for block in blocks)
            compact_length = len(re.sub(r"\s+", "", text))
            raster_coverage = _page_raster_coverage(page)
            reasons = []
            if raster_coverage >= 0.35 and compact_length < 40:
                reasons.append("scanned_page")
            if _has_unmapped_composite_font(document, page):
                reasons.append("missing_tounicode")
            pages.append(
                ExtractedPage(
                    index=page_index,
                    printed_label=printed_label,
                    chapter_title=chapter_by_page.get(page_index, ""),
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    text=text,
                    source=Page.TextSource.EMBEDDED if blocks else Page.TextSource.NONE,
                    confidence=1,
                    blocks=blocks,
                    label_source=label_source,
                    label_confidence=label_confidence,
                    raster_coverage=raster_coverage,
                    ocr_reasons=tuple(reasons),
                )
            )
        return pages
    finally:
        document.close()


def _document_text_is_insufficient(pages: list[ExtractedPage]) -> bool:
    if not pages:
        return True
    non_space = sum(len(re.sub(r"\s+", "", page.text)) for page in pages)
    populated = sum(1 for page in pages if len(re.sub(r"\s+", "", page.text)) >= 40)
    return non_space / len(pages) < 80 or populated / len(pages) < 0.35


def ocr_required_page_indexes(pages: list[ExtractedPage]) -> list[int]:
    explicit = [page.index for page in pages if page.ocr_reasons]
    if explicit:
        return explicit
    if not _document_text_is_insufficient(pages):
        return []
    # Compatibility fallback for image-only PDFs whose image metadata cannot
    # be inspected. Blank pages in an otherwise healthy born-digital PDF do
    # not reach this branch.
    return [page.index for page in pages if len(re.sub(r"\s+", "", page.text)) < 40]


def _needs_ocr(pages: list[ExtractedPage]) -> bool:
    return bool(ocr_required_page_indexes(pages))


def extract_native_pages(path: str | Path) -> tuple[list[ExtractedPage], bool]:
    pages = _mark_repeated_marginalia(_native_pages(path))
    return pages, _needs_ocr(pages)


def _ocr_pages(
    path: str | Path,
    *,
    page_numbers: list[int] | None = None,
) -> tuple[list[ExtractedPage], str]:
    try:
        if page_numbers is None:
            payload, provider = parse_pdf_with_ocr(path)
        else:
            payload, provider = parse_pdf_pages_with_ocr(path, page_numbers)
    except OCRServiceUnavailable:
        raise
    except OCRConfigurationError as exc:
        raise OCRRequired(f"文档需要 OCR，但解析服务当前不可用。{exc}") from exc
    source_document = fitz.open(str(path))
    explicit_labels = _explicit_page_labels(source_document)
    chapter_by_page = {}
    for _level, title, page_number, *_rest in source_document.get_toc(simple=True):
        if page_number > 0 and title:
            chapter_by_page.setdefault(page_number, title.strip())
    pages = []
    for raw_page in payload.get("pages", []):
        page_index = int(raw_page["index"])
        source_page = source_document[page_index - 1]
        printed_label, label_source, label_confidence = _page_label(
            source_page,
            explicit_labels=explicit_labels,
        )
        blocks = [
            ExtractedBlock(
                order=index,
                text=block.get("text", ""),
                bbox=block.get("bbox", []),
                block_type=block.get("type", "paragraph"),
                confidence=float(block.get("confidence", 0)),
            )
            for index, block in enumerate(raw_page.get("blocks", []))
            if block.get("text", "").strip()
        ]
        pages.append(
            ExtractedPage(
                index=page_index,
                printed_label=printed_label,
                chapter_title=chapter_by_page.get(page_index, ""),
                width=float(raw_page.get("width", 0)),
                height=float(raw_page.get("height", 0)),
                text="\n\n".join(block.text for block in blocks),
                source=Page.TextSource.OCR,
                confidence=float(raw_page.get("confidence", 0)),
                blocks=blocks,
                label_source=label_source,
                label_confidence=label_confidence,
            )
        )
    source_document.close()
    if not pages:
        raise OCRServiceUnavailable("OCR 服务没有返回可索引页面。")
    return pages, provider


def extract_ocr_pages(path: str | Path) -> tuple[list[ExtractedPage], str]:
    pages, provider = _ocr_pages(path)
    return _mark_repeated_marginalia(pages), provider


def extract_ocr_page_batch(
    path: str | Path,
    page_numbers: list[int],
) -> tuple[list[ExtractedPage], str]:
    pages, provider = _ocr_pages(path, page_numbers=page_numbers)
    return _mark_repeated_marginalia(pages), provider


def extract_pages(path: str | Path) -> tuple[list[ExtractedPage], str]:
    pages, needs_ocr = extract_native_pages(path)
    if needs_ocr:
        return extract_ocr_pages(path)
    return pages, "embedded"


def _mark_repeated_marginalia(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    if len(pages) < 3:
        return pages
    occurrences: dict[str, set[int]] = {}
    for page in pages:
        for block in page.blocks:
            if len(block.bbox) != 4 or len(block.text) > 220:
                continue
            top, bottom = block.bbox[1], block.bbox[3]
            if top > page.height * 0.14 and bottom < page.height * 0.86:
                continue
            key = normalize_search_text(block.text)
            if key:
                occurrences.setdefault(key, set()).add(page.index)
    minimum = max(3, round(len(pages) * 0.3))
    repeated = {key for key, page_indexes in occurrences.items() if len(page_indexes) >= minimum}
    if not repeated:
        return pages
    for page in pages:
        retained = []
        for block in page.blocks:
            if normalize_search_text(block.text) in repeated and len(block.bbox) == 4:
                block.block_type = "header" if block.bbox[1] <= page.height * 0.14 else "footer"
            else:
                retained.append(block.text)
        page.text = "\n\n".join(retained)
    return pages


def _passage_chunks(blocks: list[ExtractedBlock], target_size: int = 700):
    chunk_texts = []
    chunk_boxes = []
    chunk_start = 0
    page_offset = 0
    order = 0
    for block in blocks:
        if block.block_type in {"header", "footer"}:
            continue
        text = block.text.strip()
        if not text:
            continue
        if chunk_texts and sum(len(item) for item in chunk_texts) + len(text) > target_size:
            joined = "\n".join(chunk_texts)
            yield order, joined, chunk_start, chunk_start + len(joined), _bbox_union(chunk_boxes)
            order += 1
            chunk_texts = []
            chunk_boxes = []
            chunk_start = page_offset
        chunk_texts.append(text)
        chunk_boxes.append(block.bbox)
        page_offset += len(text) + 1
    if chunk_texts:
        joined = "\n".join(chunk_texts)
        yield order, joined, chunk_start, chunk_start + len(joined), _bbox_union(chunk_boxes)


def _bbox_union(boxes: list[list[float]]) -> list[float]:
    valid = [box for box in boxes if len(box) == 4]
    if not valid:
        return []
    return [
        min(box[0] for box in valid),
        min(box[1] for box in valid),
        max(box[2] for box in valid),
        max(box[3] for box in valid),
    ]


@transaction.atomic
def persist_pages(
    asset: Asset,
    pages: list[ExtractedPage],
    *,
    replace_missing: bool = True,
    preserve_existing_labels: bool = False,
) -> None:
    """Replace derived text while preserving stable Page primary keys.

    OCR may finish after publication and after readers have created notes.
    Recreating Page rows would cascade those user records, so only derived
    blocks and passages are replaced.
    """

    page_indexes = {page.index for page in pages}
    persisted = {}
    for extracted in pages:
        existing = Page.objects.filter(asset=asset, index=extracted.index).first()
        preserve_label = bool(
            existing
            and (
                preserve_existing_labels
                or existing.is_label_manual
                or existing.label_source == Page.LabelSource.MANUAL
            )
        )
        page, _ = Page.objects.update_or_create(
            asset=asset,
            index=extracted.index,
            defaults={
                "printed_label": (
                    existing.printed_label if preserve_label else extracted.printed_label
                ),
                "chapter_title": extracted.chapter_title,
                "text": extracted.text,
                "normalized_text": normalize_search_text(extracted.text),
                "text_source": extracted.source,
                "confidence": extracted.confidence,
                "label_source": (
                    existing.label_source if preserve_label else extracted.label_source
                ),
                "label_confidence": (
                    existing.label_confidence
                    if preserve_label
                    else extracted.label_confidence
                ),
                "width": extracted.width,
                "height": extracted.height,
            },
        )
        persisted[extracted.index] = page
    if replace_missing:
        asset.pages.exclude(index__in=page_indexes).delete()
        TextBlock.objects.filter(page__asset=asset).delete()
        Passage.objects.filter(page__asset=asset).delete()
    else:
        TextBlock.objects.filter(page__asset=asset, page__index__in=page_indexes).delete()
        Passage.objects.filter(page__asset=asset, page__index__in=page_indexes).delete()
    block_rows = []
    passage_rows = []
    for extracted in pages:
        page = persisted[extracted.index]
        for block in extracted.blocks:
            block_rows.append(
                TextBlock(
                    page=page,
                    order=block.order,
                    block_type=block.block_type,
                    text=block.text,
                    normalized_text=(
                        ""
                        if block.block_type in {"header", "footer"}
                        else normalize_search_text(block.text)
                    ),
                    bbox=block.bbox,
                    confidence=block.confidence,
                )
            )
        for order, text, start, end, bbox in _passage_chunks(extracted.blocks):
            passage_rows.append(
                Passage(
                    page=page,
                    order=order,
                    text=text,
                    normalized_text=normalize_search_text(text),
                    start_offset=start,
                    end_offset=end,
                    bbox_union=bbox,
                )
            )
    TextBlock.objects.bulk_create(block_rows, batch_size=1000)
    Passage.objects.bulk_create(passage_rows, batch_size=1000)


def persist_page_batch(asset: Asset, pages: list[ExtractedPage]) -> None:
    persist_pages(
        asset,
        pages,
        replace_missing=False,
        preserve_existing_labels=True,
    )
