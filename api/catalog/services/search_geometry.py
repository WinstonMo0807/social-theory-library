from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
import math
import shutil
import tempfile

import fitz
from django.core.cache import cache


MAX_HIGHLIGHTS_PER_PAGE = 200


@contextmanager
def _local_asset_path(field_file):
    try:
        yield Path(field_file.path)
        return
    except (AttributeError, NotImplementedError, ValueError):
        pass

    suffix = Path(field_file.name).suffix or ".pdf"
    temporary = tempfile.NamedTemporaryFile(
        prefix="library-search-",
        suffix=suffix,
        delete=False,
    )
    temporary_path = Path(temporary.name)
    try:
        with temporary, field_file.open("rb") as source:
            shutil.copyfileobj(source, temporary, length=1024 * 1024)
        yield temporary_path
    finally:
        temporary_path.unlink(missing_ok=True)


def _is_cjk(value: str) -> bool:
    if not value:
        return False
    cjk_count = sum("\u3400" <= character <= "\u9fff" for character in value)
    return cjk_count / len(value) >= 0.28


def _virtual_line_ranges(text: str, bbox: list[float]) -> list[tuple[int, int]]:
    explicit = text.splitlines(keepends=True)
    if len(explicit) > 1:
        ranges = []
        offset = 0
        for line in explicit:
            end = offset + len(line.rstrip("\r\n"))
            ranges.append((offset, max(offset, end)))
            offset += len(line)
        return ranges

    if len(bbox) != 4 or not text:
        return [(0, len(text))]
    width = max(float(bbox[2]) - float(bbox[0]), 1)
    height = max(float(bbox[3]) - float(bbox[1]), 1)
    character_width_ratio = 1.0 if _is_cjk(text) else 0.52
    estimated_lines = max(
        1,
        round(math.sqrt(len(text) * character_width_ratio * height / width)),
    )
    estimated_lines = min(estimated_lines, max(1, len(text)))
    characters_per_line = max(1, math.ceil(len(text) / estimated_lines))
    return [
        (start, min(start + characters_per_line, len(text)))
        for start in range(0, len(text), characters_per_line)
    ]


def estimate_block_highlights(
    text: str,
    bbox: list[float],
    query: str,
) -> list[list[float]]:
    """Estimate narrow match rectangles when a PDF has OCR data only."""
    if len(bbox) != 4 or not text or not query:
        return []
    folded_text = text.lower()
    folded_query = query.lower()
    occurrences = []
    start = 0
    while len(occurrences) < MAX_HIGHLIGHTS_PER_PAGE:
        index = folded_text.find(folded_query, start)
        if index < 0:
            break
        occurrences.append((index, index + len(query)))
        start = index + max(len(query), 1)
    if not occurrences:
        return []

    x0, y0, x1, y1 = (float(value) for value in bbox)
    line_ranges = _virtual_line_ranges(text, bbox)
    line_height = (y1 - y0) / max(len(line_ranges), 1)
    rectangles = []
    for match_start, match_end in occurrences:
        for line_index, (line_start, line_end) in enumerate(line_ranges):
            overlap_start = max(match_start, line_start)
            overlap_end = min(match_end, line_end)
            if overlap_end <= overlap_start:
                continue
            line_length = max(line_end - line_start, 1)
            left_ratio = (overlap_start - line_start) / line_length
            right_ratio = (overlap_end - line_start) / line_length
            top = y0 + line_index * line_height + line_height * 0.08
            bottom = min(y1, top + line_height * 0.84)
            rectangles.append(
                [
                    round(x0 + (x1 - x0) * left_ratio, 2),
                    round(top, 2),
                    round(x0 + (x1 - x0) * right_ratio, 2),
                    round(bottom, 2),
                ]
            )
    return rectangles[:MAX_HIGHLIGHTS_PER_PAGE]


def _pdf_text_highlights(
    asset,
    query: str,
    page_rows: list[dict],
) -> dict[int, list[dict]]:
    page_indexes = tuple(sorted({int(row["page_index"]) for row in page_rows}))
    query_digest = sha256(query.encode("utf-8")).hexdigest()[:20]
    pages_digest = sha256(",".join(map(str, page_indexes)).encode("ascii")).hexdigest()[:16]
    cache_key = f"pdf-highlight:{asset.sha256}:{query_digest}:{pages_digest}"
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return {int(key): value for key, value in cached.items()}

    stored_dimensions = {
        int(row["page_index"]): (
            max(float(row.get("width") or 0), 1),
            max(float(row.get("height") or 0), 1),
        )
        for row in page_rows
    }
    result: dict[int, list[dict]] = {}
    try:
        with _local_asset_path(asset.file) as path, fitz.open(str(path)) as document:
            for page_index in page_indexes:
                if not 1 <= page_index <= document.page_count:
                    continue
                pdf_page = document.load_page(page_index - 1)
                stored_width, stored_height = stored_dimensions[page_index]
                scale_x = stored_width / max(float(pdf_page.rect.width), 1)
                scale_y = stored_height / max(float(pdf_page.rect.height), 1)
                rectangles = []
                for rect in pdf_page.search_for(query):
                    if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                        continue
                    rectangles.append(
                        {
                            "bbox": [
                                round(float(rect.x0) * scale_x, 2),
                                round(float(rect.y0) * scale_y, 2),
                                round(float(rect.x1) * scale_x, 2),
                                round(float(rect.y1) * scale_y, 2),
                            ],
                            "text": query,
                            "source": "pdf-text",
                        }
                    )
                    if len(rectangles) >= MAX_HIGHLIGHTS_PER_PAGE:
                        break
                if rectangles:
                    result[page_index] = rectangles
    except (FileNotFoundError, OSError, RuntimeError, ValueError):
        result = {}

    cache.set(cache_key, result, timeout=15 * 60)
    return result


def search_highlights(asset, query: str, page_rows: list[dict]) -> dict[int, list[dict]]:
    """Return actual PDF match rectangles, with a narrow OCR-only fallback."""
    result = _pdf_text_highlights(asset, query, page_rows)
    for row in page_rows:
        page_index = int(row["page_index"])
        if result.get(page_index):
            continue
        estimated = []
        for block in row.get("blocks", []):
            for bbox in estimate_block_highlights(
                str(block.get("text", "")),
                block.get("bbox", []),
                query,
            ):
                estimated.append(
                    {
                        "bbox": bbox,
                        "text": query,
                        "source": "ocr-estimate",
                    }
                )
                if len(estimated) >= MAX_HIGHLIGHTS_PER_PAGE:
                    break
            if len(estimated) >= MAX_HIGHLIGHTS_PER_PAGE:
                break
        if estimated:
            result[page_index] = estimated
    return result
