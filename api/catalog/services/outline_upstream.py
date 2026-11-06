"""Small MIT algorithms adapted from fixed upstream versions; no upstream runtime/models.
Docling c715294cd774ef0a59dd8e5c8a63ae3432cd611e and pdf-toc-ocr 577c36d248556d69f17ee2dd07ba5a24463a9889.
Copyright The Docling Contributors; Copyright (c) 2026 Hermes contributors.
Licenses: api/third_party/docling-LICENSE.txt and pdf-toc-ocr-LICENSE.txt.
"""

import re
from difflib import SequenceMatcher
from typing import Any

def _cluster_sizes(sizes: set[float], tolerance: float) -> dict[float, int]:
    """Group font sizes into clusters, largest first, and map each size to its cluster index.

    The size of a heading is the median height of its cells, which measures the glyphs that are
    actually on the line rather than the font size: a heading with descenders ("Securing and
    protecting") measures a couple of points taller than one without ("Contents") in the very same
    font. Treating every distinct height as its own level therefore invents levels and, because
    each level then holds a single heading, leaves no headings for weight or slant to separate.
    Consecutive sizes within ``tolerance`` (relative) are merged to absorb that measurement noise.
    """
    clusters: dict[float, int] = {}
    index = 0
    previous: float | None = None
    for size in sorted(sizes, reverse=True):
        if previous is not None and (previous - size) > tolerance * previous:
            index += 1
        clusters[size] = index
        previous = size
    return clusters

_LEADING_MARKER = re.compile(
    r"^\s*(?:"
    r"(?:part|title|book|division|subdivision|chapter|article|section|clause|schedule|annex|appendix|rule)"
    r"\b[\s.:]*[0-9ivxlcdm]*"
    r"|§+\s*[0-9.]+"
    r"|\(?[0-9]+(?:\.[0-9]+)*[.)\]]?"
    r"|\(?[A-Za-z]{1,2}(?:[.)\]]|(?=\s*[:\-\u2013\u2014]))"
    r")[\s.:)\-\u2013\u2014]*",
    re.IGNORECASE,
)

def _norm(text: str) -> str:
    """Lower-case, collapse whitespace and trim outer punctuation for matching."""
    s = re.sub(r"\s+", " ", (text or "").lower()).strip()
    # Trim leading/trailing punctuation (incl. unicode dash variants) and underscores.
    return re.sub(r"^[\W_]+|[\W_]+$", "", s)

def _strip_marker(text: str) -> str:
    return _LEADING_MARKER.sub("", text or "", count=1)

def _match_score(cand_text: str, bm_title: str) -> float:
    """Fuzzy similarity in 0..1 between a detected heading and a bookmark title.

    Both strings are compared with and without their leading numbering marker (bookmarks often
    omit or carry a different marker), and containment of one normalized title in the other
    boosts the score (bookmarks are frequently truncated).
    """
    variants_a = {_norm(cand_text), _norm(_strip_marker(cand_text))} - {""}
    variants_b = {_norm(bm_title), _norm(_strip_marker(bm_title))} - {""}
    best = 0.0
    for a in variants_a:
        for b in variants_b:
            best = max(best, SequenceMatcher(None, a, b).ratio())
            if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
                best = max(best, 0.92)
    return best

def _cluster_columns(fragments: list[dict[str, Any]], gap_threshold: float = 60.0) -> list[list[dict[str, Any]]]:
    """按 X 坐标将碎片聚类为列，处理双列/多列目录排版。"""
    if not fragments:
        return []
    sorted_frags = sorted(fragments, key=lambda v: v["x"])
    columns: list[list[dict[str, Any]]] = [[sorted_frags[0]]]
    for frag in sorted_frags[1:]:
        last_col = columns[-1]
        last_x_max = max(f.get("x2", f["x"] + 10) for f in last_col)
        gap = frag["x"] - last_x_max
        if gap > gap_threshold:
            columns.append([frag])
        else:
            last_col.append(frag)
    # 按列左边界排序（从左到右）
    columns.sort(key=lambda col: min(f["x"] for f in col))
    return columns

def _group_column_rows(column: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将单个列的 fragments 按行合并。"""
    rows: list[dict[str, Any]] = []
    for fragment in sorted(column, key=lambda v: ((v["y"] + v["y2"]) / 2, v["x"])):
        center = (fragment["y"] + fragment["y2"]) / 2
        height = max(fragment["y2"] - fragment["y"], 1)
        best = None
        best_distance = float("inf")
        for row in rows:
            distance = abs(center - row["center"])
            tolerance = max(5.0, min(height, row["height"]) * 0.65)
            if distance <= tolerance and distance < best_distance:
                best, best_distance = row, distance
        if best is None:
            rows.append({"parts": [fragment], "center": center, "height": height})
        else:
            best["parts"].append(fragment)
            count = len(best["parts"])
            best["center"] = (best["center"] * (count - 1) + center) / count
            best["height"] = max(best["height"], height)
    return rows

def group_ocr_rows(fragments: list[dict[str, Any]], column_mode: str = "auto") -> list[dict[str, Any]]:
    """把 OCR 拆开的"标题 / 点线 / 页码"文本框重新组合成目录行。

    column_mode: "single"=不分列, "two"=强制双列, "auto"=自动检测。
    """
    if column_mode == "single":
        columns = [fragments]
    elif column_mode == "two":
        tagged_columns = sorted({int(f["column"]) for f in fragments if "column" in f})
        if tagged_columns:
            columns = [[f for f in fragments if f.get("column") == column] for column in tagged_columns]
        # Backward-compatible fallback for callers that pass untagged boxes.
        elif not fragments:
            columns = []
        else:
            mid_x = sorted(f["x"] for f in fragments)[len(fragments) // 2]
            columns = [
                [f for f in fragments if f["x"] < mid_x],
                [f for f in fragments if f["x"] >= mid_x],
            ]
            columns = [c for c in columns if c]
    else:
        columns = _cluster_columns(fragments)
    if not columns:
        return []

    # 对于双列目录，按列分开处理后再拼接（左列在前，右列在后），
    # 避免两列行按 Y 交错。多列（>=3）时仍按原有方式按 Y 混合。
    if len(columns) == 2:
        all_rows = _group_column_rows(columns[0]) + _group_column_rows(columns[1])
    else:
        all_rows: list[dict[str, Any]] = []
        for column in columns:
            all_rows.extend(_group_column_rows(column))
        all_rows.sort(key=lambda v: v["center"])

    output: list[dict[str, Any]] = []
    for row in all_rows:
        parts = sorted(row["parts"], key=lambda v: v["x"])
        text = " ".join(part["text"].strip() for part in parts if part["text"].strip())
        # 某些 OCR 会把"点线 + 4"识别为"4 + 点线"。
        text = re.sub(r"\b(\d{1,4})\s*([.．…·•]{2,})", r"\2 \1", text)
        output.append({"text": text, "x": parts[0]["x"], "y": min(part["y"] for part in parts),
                       "score": min(part["score"] for part in parts),
                       "column": parts[0].get("column")})
    return output
