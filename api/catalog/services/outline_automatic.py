"""Automatic navigation from existing OCR geometry, without another OCR/model service."""
from collections import defaultdict
from copy import deepcopy
import re

from .outline_upstream import _match_score, _cluster_sizes, group_ocr_rows
from .outline_labels import OutlineLabels
from .page_geometry import locator_geometry


def _key(text):
    return re.sub(r"[\W_]+", "", text).casefold()


def _clean(text):
    return re.sub(r"[.．·…_*\s]+$", "", text.strip(" '\"‘’"))


def _caps(text):
    letters = [c for c in text if c.isalpha()]
    return len(letters) >= 5 and sum(c.isupper() for c in letters) / len(letters) > .85


def automatic_nodes(asset, nodes):
    from .document_outline import CONTENTS, ENTRY, TRAILING_PAGE, HEADING, _node, _parents, _tree_order
    pages = list(asset.pages.order_by("index").prefetch_related("blocks"))
    by_page, repeated = {}, defaultdict(set)
    labels = OutlineLabels([{"index": p.index, "printed_label": p.printed_label,
        "label_segment": p.label_segment} for p in pages], (asset.validation_details or {}).get("page_mapping"))
    for page in pages:
        width, height = page.width or 1, page.height or 1
        rows = []
        for item in page.blocks.all():
            if len(item.bbox or []) != 4 or not item.text.strip():
                continue
            x, y, x2, y2 = item.bbox
            text = _clean(item.text)
            row = {"text": text, "page": page.index, "x": x / width * 1000,
                   "x2": x2 / width * 1000, "y": y / height * 1000,
                   "y2": y2 / height * 1000, "score": 1.0,
                   "locator": locator_geometry(item.bbox, page.geometry)}
            rows.append(row)
            if row["y"] < 100 or row["y2"] > 920:
                repeated[_key(text)].add(page.index)
        by_page[page.index] = rows
    contents_pages = {node.get("contents_page") for node in nodes if node.get("contents_page")}
    contents = []
    for number, rows in by_page.items():
        if number not in contents_pages and not any(CONTENTS.fullmatch(row["text"]) for row in rows[:8]):
            continue
        contents_pages.add(number)
        # Numeric ends on both halves identify two independent TOC columns.
        numbers = [r for r in rows if r["text"].isdigit()]
        two_columns = sum(r["x2"] < 520 for r in numbers) >= 3 and sum(r["x"] > 520 for r in numbers) >= 3
        for row in rows:
            if two_columns:
                row["column"] = int(row["x"] >= 520)
        for row in group_ocr_rows(rows, "two" if two_columns else "single"):
            match = ENTRY.match(row["text"]) or TRAILING_PAGE.match(row["text"])
            if match:
                title = _clean(match["title"])
                if len(title) >= 2 and not title.isdecimal():
                    contents.append({"title": title, "label": match["label"], "contents_page": number,
                                     "x": row["x"] - (520 if row.get("column") == 1 else 0)})
    # Existing native bookmarks remain useful only when their own observations passed.
    native = [deepcopy(n) for n in nodes if n.get("calibration_status") == "native"]
    suppressed = {key for key, occurrences in repeated.items() if len(occurrences) >= max(3, len(pages) * .08)}
    candidates = []
    for number, rows in by_page.items():
        if number in contents_pages:
            continue
        for row in rows:
            text = row["text"]
            if row["y"] < 90 or row["y2"] > 940 or _key(text) in suppressed:
                continue
            inline = re.match(r"^(.{3,100}?)\s*[.。]?\s*[—–]", text)
            if inline:
                candidates.append({**row, "text": _clean(inline[1]), "inline_heading": True})
            if not 3 <= len(text) <= 180:
                continue
            candidates.append(row)
            # Recover adjacent title fragments in the same column, even if OCR interleaves another column.
            following = [r for r in rows if r is not row and -.3 * (row["y2"] - row["y"]) <= r["y"] - row["y2"] < 16 and r["y"] > row["y"]
                         and abs((r["x"] + r["x2"]) - (row["x"] + row["x2"])) < 130
                         and (_caps(r["text"]) and _caps(text))]
            if following:
                nxt = min(following, key=lambda r:r["y"])
                candidates.append({**row, "text": text + " " + nxt["text"], "y2": nxt["y2"], "joined": True})
    selected, unresolved, occupied = [], [], set()
    if contents:
        anchors = []
        for index, entry in enumerate(contents):
            if entry["label"].isdigit():
                hits = {r["page"] for r in candidates if _key(r["text"]) == _key(entry["title"])}
                if len(hits) == 1:
                    anchors.append((index, int(entry["label"]), next(iter(hits))))
        indents = []
        for x in sorted({r["x"] for r in contents}):
            if not indents or x - indents[-1] > 20:
                indents.append(x)
        for index, entry in enumerate(contents):
            title = entry["title"]
            ranked = []
            observations = labels.observations(entry["label"])
            expected = observations[0]["pdf_page"] if len(observations) == 1 else None
            # Nearby exact title observations guide ambiguous matches; they never
            # create a destination by applying one offset to the whole volume.
            nearby = sorted(anchors, key=lambda anchor: abs(anchor[0] - index))[:2]
            if expected is None and entry["label"].isdigit() and len(nearby) == 2:
                offsets = {page - label for _, label, page in nearby}
                if len(offsets) == 1:
                    expected = int(entry["label"]) + offsets.pop()
            for row in candidates:
                if labels.has_missing_label(entry["label"]):
                    break
                if len(row["text"]) > max(30, len(title) * 1.8):
                    continue
                score = _match_score(row["text"], title)
                if score < .73:
                    continue
                distance = abs(row["page"] - expected) if expected is not None else 0
                if expected is not None and distance > 3 and score < .98:
                    continue
                # Offset guides ties only. A printed TOC error must not overrule an observed body heading.
                ranked.append((score + (.06 if _caps(row["text"]) or row.get("inline_heading") else 0) - distance * .03, score, row))
            ranked.sort(key=lambda item:(-item[0], item[2]["page"], item[2]["y"]))
            best = ranked[0] if ranked else None
            different = next((r for r in ranked[1:] if r[2]["page"] != best[2]["page"]), None) if best else None
            if not best or best[1] < .78 or (different and best[0] - different[0] < .025):
                unresolved.append({"title": title, "printed_label": entry["label"], "contents_page": entry["contents_page"]})
                continue
            row = best[2]
            identity = (_key(title), row["page"])
            if identity in occupied:
                continue
            occupied.add(identity)
            level = min(6, min(range(len(indents)), key=lambda i:abs(indents[i] - entry["x"])) + 1)
            node = _node(asset, index, title, row["page"], source="printed_contents", level=level,
                         label=entry["label"], contents_page=entry["contents_page"],
                         locator={**row["locator"], "algorithm":"docling-title-match", "observed_title":row["text"]})
            node["calibration_status"] = "matched"
            selected.append(node)
    else:
        # Title geometry and casing supplement native fonts on image-only/OCR PDFs.
        possible = [r for r in candidates if HEADING.match(r["text"]) or (_caps(r["text"]) and len(r["text"]) >= 18 and len(r["text"].split()) >= 2)]
        joined = [r for r in possible if r.get("joined")]
        possible = [r for r in possible if not any(r is not j and r["page"] == j["page"] and r["text"] in j["text"] for j in joined)]
        sizes = _cluster_sizes({round(r["y2"] - r["y"], 1) for r in possible}, .2)
        for index, row in enumerate(sorted(possible, key=lambda r:(r["page"],r["y"],r["x"]))):
            if row["text"].startswith(("EDITORIAL", "COPYRIGHT", "ALL RIGHTS")):
                continue
            identity = (_key(row["text"]), row["page"])
            if identity in occupied:
                continue
            occupied.add(identity)
            level = 1 if row.get("joined") else min(4, sizes[round(row["y2"] - row["y"], 1)] + 1)
            node = _node(asset, index, row["text"], row["page"], source="generated_heading", level=level, locator=row["locator"])
            node["calibration_status"] = "generated"
            selected.append(node)
        if not selected:
            selected = [deepcopy(n) for n in nodes if n.get("pdf_page") and n.get("source") == "generated_heading"
                        and n.get("calibration_status") == "generated"]
    selected = _parents(selected)
    targets = {(_key(n["title"]), n["pdf_page"]): n["id"] for n in selected}
    replacements = {n["id"]: targets[(_key(n["title"]), n["pdf_page"])] for n in native
                    if (_key(n["title"]), n["pdf_page"]) in targets}
    for node in native:
        if node["id"] not in replacements:
            node["parent_id"] = replacements.get(node.get("parent_id"), node.get("parent_id"))
            selected.append(node)
    ids = {node["id"] for node in selected}
    for node in selected:
        if node.get("parent_id") not in ids:
            node["parent_id"] = None
    diagnostics = [{"code":"automatic_outline" if selected else "no_outline_detected",
                    "message":"目录已自动生成，可在后台修正。" if selected else "尚未识别到可定位的章节，可完成文字识别后重新生成，或在后台补充。",
                    "algorithm":"outline-v9-docling-geometry"}]
    if unresolved:
        diagnostics.append({"code":"unresolved_contents", "message":"这些条目尚无可靠落点，其余目录已生成。", "entries":unresolved})
    return _tree_order(selected), diagnostics
