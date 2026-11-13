"""Automatic navigation from existing OCR geometry, without another OCR/model service."""
from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
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


_CHAPTER = re.compile(r"^(?:第\s*[一二三四五六七八九十百零〇\dⅠⅡⅢIVXIlO\s]+章|chapter\s+[\w]+)[\s:：.、-]*", re.I)
_PART = re.compile(r"^(?:第\s*[一二三四五六七八九十百零〇\d\s]+(?:部分|部|编|篇)|part\s+[\w]+)[\s:：.、-]*", re.I)
_FRONT_BACK = re.compile(r"^(?:自\s*序|前言|序言|(?:译者|出版)?后记|参考(?:文献|书目)|附录|preface\b|foreword\b|bibliography\b|references\b|appendix\b)", re.I)


def _body_key(text):
    return _key(_CHAPTER.sub("", text)) or _key(text)


def _contents_entries(rows, number, two_columns):
    from .document_outline import CONTENTS, ENTRY, TRAILING_PAGE
    pending, entries = None, []
    for row in group_ocr_rows(rows, "two" if two_columns else "single"):
        text = _clean(row["text"])
        if CONTENTS.fullmatch(text) or re.fullmatch(r"目\s*[录錄]\s*\d*", text) or row["y"] > 920:
            pending = None
            continue
        match = ENTRY.match(text) or TRAILING_PAGE.match(text)
        if not match:
            # OCR may retain only one leader dot next to the observed label.
            match = re.match(r"^(?P<title>.+?)\s+[.．·…_]\s*(?P<label>\d{1,5})$", text)
        if not match:
            # Preserve an observed OCR label such as 0g2; never silently repair
            # it to a guessed page. A unique body heading can still locate it.
            match = re.match(r"^(?P<title>.+?)\s+(?P<label>\d[\dA-Za-z]{1,4})$", text)
        if match:
            title = _clean(match["title"])
            duplicate = ENTRY.match(title) or TRAILING_PAGE.match(title)
            if (duplicate and duplicate["label"] == match["label"]
                    and re.search(r"[.．…·_]$", duplicate["title"].rstrip())):
                title = _clean(duplicate["title"])
            # Continuation lines are visibly indented beneath an unnumbered
            # first line. Do not attach a missing-label entry to its next peer.
            if (pending and pending.get("column") == row.get("column")
                    and 0 < row["y"] - pending["y"] < 40
                    and row["x"] - pending["x"] > 15
                    and not _CHAPTER.match(title)):
                title = pending["text"] + " " + title
                row = {**row, "x": pending["x"]}
            elif (pending and pending.get("column") == row.get("column")
                    and 0 < row["y"] - pending["y"] < 40 and abs(row["x"] - pending["x"]) < 12):
                entries.append({"title":pending["text"], "label":"", "contents_page":number,
                                "x":pending["x"] - (520 if row.get("column") == 1 else 0)})
            if len(title) >= 2 and not title.isdecimal():
                entries.append({"title":title, "label":match["label"], "contents_page":number,
                                "x":row["x"] - (520 if row.get("column") == 1 else 0)})
            pending = None
        elif _PART.match(text):
            entries.append({"title":text, "label":"", "contents_page":number,
                            "x":row["x"] - (520 if row.get("column") == 1 else 0)})
            pending = None
        else:
            pending = {**row, "text":text} if 3 <= len(text) <= 180 else None
    # Odd/even page margins are layout, not an extra hierarchy level.
    chapter_x = [r["x"] for r in entries if _CHAPTER.match(r["title"])]
    if chapter_x:
        for entry in entries:
            entry["x"] -= min(chapter_x)
    return entries


def automatic_nodes(asset, nodes):
    from .document_outline import CONTENTS, ENTRY, TRAILING_PAGE, HEADING, PARSER_VERSION, _node, _parents, _tree_order
    pages = list(asset.pages.order_by("index").prefetch_related("blocks"))
    page_texts = {p.index:getattr(p,"text","") for p in pages}
    by_page, repeated = {}, defaultdict(set)
    labels = OutlineLabels([{"index": p.index, "printed_label": p.printed_label,
        "label_segment": p.label_segment} for p in pages], (asset.validation_details or {}).get("page_mapping"))
    for page in pages:
        width, height = page.width or 1, page.height or 1
        rows, cursor, aligned = [], 0, True
        raw_text = getattr(page, "text", "")
        page_hash = sha256(raw_text.encode()).hexdigest()
        for item in page.blocks.all():
            if not item.text.strip():
                continue
            start = raw_text.find(item.text, cursor) if aligned and item.text else -1
            aligned = start >= 0 and not raw_text[cursor:start].strip()
            raw_range = {}
            if aligned:
                cursor = start + len(item.text)
                raw_range = {"start":start,"end":cursor,"exact":item.text,
                             "page_text_hash":page_hash,"unit":"unicode_codepoint"}
            if len(item.bbox or []) != 4 or not item.text.strip():
                continue
            x, y, x2, y2 = item.bbox
            text = _clean(item.text)
            row = {"text": text, "page": page.index, "x": x / width * 1000,
                   "x2": x2 / width * 1000, "y": y / height * 1000,
                   "y2": y2 / height * 1000, "score": 1.0,
                   "locator": {**locator_geometry(item.bbox, page.geometry),
                               **({"raw_text_range":raw_range} if raw_range else {})}}
            rows.append(row)
            if row["y"] < 100 or row["y2"] > 920:
                repeated[_key(text)].add(page.index)
        by_page[page.index] = rows
    contents_pages = {node.get("contents_page") for node in nodes if node.get("contents_page")}
    contents, layout_contents = [], []
    for number, rows in by_page.items():
        known_contents = number in contents_pages or any(CONTENTS.fullmatch(row["text"]) for row in rows[:8])
        # Numeric ends on both halves identify two independent TOC columns.
        numbers = [r for r in rows if r["text"].isdigit()]
        two_columns = sum(r["x2"] < 520 for r in numbers) >= 3 and sum(r["x"] > 520 for r in numbers) >= 3
        for row in rows:
            if two_columns:
                row["column"] = int(row["x"] >= 520)
        entries = _contents_entries(rows, number, two_columns)
        if not known_contents:
            # A damaged/missing "Contents" heading is not a reason to use every
            # chapter listed on that page as a body heading. Require repeated
            # title/label rows and independently observed right-aligned labels.
            numbered = [e for e in entries if e["label"].isdigit() and len(e["title"]) <= 100]
            if (len(numbered) < 4 or sum(bool(_CHAPTER.match(e["title"])) for e in numbered) < 2
                    or sum(r["x"] > 650 for r in numbers) < 4):
                continue
            layout_contents.append(number)
        contents_pages.add(number)
        contents.extend(entries)
    # Existing native bookmarks remain useful only when their own observations passed.
    native = [deepcopy(n) for n in nodes if n.get("calibration_status") == "native"]
    suppressed = {key for key, occurrences in repeated.items() if len(occurrences) >= max(3, len(pages) * .08)}
    contents_keys = {_body_key(r["title"]) for r in contents}
    full_contents_keys = {_key(r["title"]) for r in contents}
    candidates = []
    for number, rows in by_page.items():
        if number in contents_pages:
            continue
        # OCR can store a title before its chapter number, or split a two-word
        # title horizontally. Match the visual row, retain each raw fragment.
        for row in rows:
            if (row["y"] < 90 or row["y2"] > 940
                    or not (_PART.match(row["text"]) or _CHAPTER.match(row["text"]))):
                continue
            parts = sorted([r for r in rows if abs((r["y"]+r["y2"]-row["y"]-row["y2"])/2)
                            <= min(r["y2"]-r["y"],row["y2"]-row["y"])*.65], key=lambda r:r["x"])
            joined = " ".join(r["text"] for r in parts)
            if len(parts) < 2 or _key(joined) not in full_contents_keys:
                continue
            boxes = [p["locator"].get("normalized_bbox") for p in parts]
            ranges = [p["locator"].get("raw_text_range") for p in parts]
            if not all(ranges) or not all(box and len(box)==4 for box in boxes):
                continue
            locator = {**row["locator"], "raw_text_fragments":ranges,
                       "normalized_bbox":[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]}
            locator.pop("raw_text_range",None);locator.pop("bbox",None)
            candidates.append({**row,"text":joined,"locator":locator,"joined":True})
        for row in rows:
            text = row["text"]
            if row["y"] < 90 or row["y2"] > 940 or _key(text) in suppressed:
                continue
            inline = re.match(r"^(.{3,100}?)\s*[.。]?\s*[—–]", text)
            if inline:
                candidates.append({**row, "text": _clean(inline[1]), "inline_heading": True})
            if not 2 <= len(text) <= 180 or len(text) == 2 and _body_key(text) not in contents_keys:
                continue
            candidates.append(row)
            # A wrapped body heading must match the complete observed TOC title.
            # Its union box is made only from contiguous, overlapping text boxes.
            parts = [row]
            for _ in range(2):
                last = parts[-1]
                following = [r for r in rows if r not in parts and 0 <= r["y"] - last["y2"] < 20
                             and min(r["x2"], last["x2"]) > max(r["x"], last["x"])]
                if not following:
                    break
                nxt = min(following, key=lambda r:r["y"])
                parts.append(nxt)
                joined = " ".join(r["text"] for r in parts)
                if len(joined) > 180:
                    break
                if _body_key(joined) in contents_keys:
                    boxes = [p["locator"].get("normalized_bbox") for p in parts]
                    locator = {}
                    if all(box and len(box) == 4 for box in boxes):
                        locator = {**row["locator"], "normalized_bbox":[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]}
                        # The old single-line source bbox no longer describes the union.
                        locator.pop("bbox", None)
                    locator.pop("raw_text_range", None)
                    ranges = [p["locator"].get("raw_text_range") for p in parts]
                    if all(ranges):
                        first, last_range = ranges[0], ranges[-1]
                        original = page_texts[number][first["start"]:last_range["end"]]
                        if "".join(original.split()) == "".join("".join(r["exact"] for r in ranges).split()):
                            locator["raw_text_range"] = {**first,"end":last_range["end"],"exact":original}
                    candidates.append({**row, "text":joined, "y2":nxt["y2"], "locator":locator, "joined":True})
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
        for x in sorted({r["x"] for r in contents if not _FRONT_BACK.match(r["title"])}):
            if not indents or x - indents[-1] > 20:
                indents.append(x)
        if not indents:
            indents = [0]
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
                body_key, title_key = _body_key(row["text"]), _body_key(title)
                if min(len(body_key),len(title_key)) < max(len(body_key),len(title_key)) * .8:
                    continue
                score = _match_score(body_key, title_key)
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
            if _PART.match(title) or _FRONT_BACK.match(title):
                level = 1
            elif _CHAPTER.match(title):
                level = 1
            elif any(_CHAPTER.match(r["title"]) for r in contents):
                level = max(2, level)
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
    # Only a part with a verified body destination can own later chapters.
    # Unresolved translated TOC groups must not indent the entire book.
    in_part = False
    for node in sorted(selected,key=lambda n:(n["pdf_page"],n["position"])) if contents else []:
        if _PART.match(node["title"]):
            in_part = True
        elif _FRONT_BACK.match(node["title"]):
            in_part = False
        elif in_part:
            node["level"] = 2 if _CHAPTER.match(node["title"]) else min(6,node["level"]+1)
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
                    "algorithm":PARSER_VERSION}]
    if layout_contents:
        diagnostics.append({"code":"contents_layout_observed", "pages":layout_contents,
                            "message":"目录标题文字不完整，已依据重复的标题与右侧页码版面识别。"})
    if unresolved:
        diagnostics.append({"code":"unresolved_contents", "message":"这些条目尚无可靠落点，其余目录已生成。", "entries":unresolved})
    return _tree_order(selected), diagnostics
