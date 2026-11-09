"""Versioned PDF navigation using the existing Asset, Page and ProcessingJob.

Bookmarks are lossless; observed contents and headings generate navigation.
No automatic result overwrites a human-corrected directory.
"""
from collections import defaultdict
from hashlib import sha256
from itertools import islice
import json
import math
import re
from uuid import UUID, uuid4, uuid5

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from kombu.exceptions import OperationalError

from catalog.models import Asset, DocumentOutlineRevision
from catalog.services.text import sanitize_unicode
from catalog.services.page_geometry import locator_geometry, native_geometry, validated_geometry
from catalog.services.outline_labels import LABEL_ONLY, LABEL_RANGE, PRINTED_LABEL, OutlineLabels
from ingestion.models import AuditEvent, ProcessingJob


PARSER_VERSION = "outline-v9-docling-geometry"
HEADING = re.compile(r"^(?:第[一二三四五六七八九十百零\d]+[编部篇章节]|(?:chapter|part|section|appendix)\s+[\w一二三四五六七八九十]+|\d+(?:\.\d+){1,5}\s+)", re.I)
CONTENTS = re.compile(r"^(?:目\s*[录錄]|contents|table\s+of\s+contents)$", re.I)
ENTRY = re.compile(rf"^(?P<title>.+?)\s*(?:[.．·…_]{{2,}}|\s{{2,}}|\t)\s*(?P<label>{PRINTED_LABEL})\s*$")
TRAILING_PAGE = re.compile(rf"^(?P<title>.+?\D)\s+(?P<label>{PRINTED_LABEL})\s*$")
CONTENTS_TITLE_START = re.compile(r"^(?:第[一二三四五六七八九十\d]+版(?:序言|前言)|序言|前言|引言|绪论|结论|后记|附录|preface\b|introduction\b|foreword\b)", re.I)


class OutlineConflict(ValueError):
    pass


class OutlineJobInterrupted(Exception):
    pass


def _title(value):
    return " ".join(sanitize_unicode(str(value or "")).split())[:600]


def _match_key(value):
    original = re.sub(r"[①-⑳¹²³⁴⁵⁶⁷⁸⁹⁰]+$", "", _title(value))
    value = re.sub(r"^(?:第[一二三四五六七八九十百零\d]+[编部篇章节]|(?:chapter|part|section|appendix)\s+[\w]+|\d+(?:\.\d+)*)[\s:：.、-]*", "", original, flags=re.I) or original
    return re.sub(r"[\s\W_]+", "", value, flags=re.UNICODE).casefold()


def _readable(title):
    return bool(title and len(title) <= 600 and "\ufffd" not in title and not re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", title))


def _level(title):
    decimal = re.match(r"^(\d+(?:\.\d+)*)\s", title)
    if decimal:
        return min(6, decimal.group(1).count(".") + 1)
    if re.match(r"^(?:第.+[节]|section\b)", title, re.I):
        return 2
    return 1


def _node(asset, ordinal, title, page, *, level=1, source, label="", position=None, contents_page=None, locator=None):
    return {
        "id": str(uuid5(asset.pk, f"{source}:{ordinal}:{title}:{page}")),
        "parent_id": None, "position": ordinal, "level": level,
        "title": title, "pdf_page": page, "printed_label": label,
        "pdf_position": position or [], "coordinate_unit": "pdf_points" if position else "",
        "coordinate_space": "pymupdf_toc" if position else "",
        "source_locator": locator or {},
        "normalized_position": (locator or {}).get("normalized_bbox", [])[:2],
        "precision": "position" if position or (locator or {}).get("normalized_bbox") else "page",
        "source": source, "calibration_status": "unverified",
        "contents_page": contents_page,
    }


def _candidate(node):
    """An observed source, never a fabricated score or an inferred offset."""
    fields = ("id", "source", "title", "pdf_page", "printed_label", "contents_page",
              "pdf_position", "normalized_position", "coordinate_unit", "coordinate_space",
              "source_locator", "page_geometry", "calibration_status", "precision")
    return {key: node[key] for key in fields if key in node}


def _with_candidates(node):
    candidates = node.get("candidate_sources") or [_candidate(node)]
    return {**node, "candidate_sources": candidates,
            "candidate_sources_count": max(len(candidates), node.get("candidate_sources_count", 0))}


def _parents(nodes):
    """Assign parents in ONE source's original sequence, never a fused list."""
    stack = []
    for position, node in enumerate(nodes):
        while stack and stack[-1][0] >= node["level"]:
            stack.pop()
        node["parent_id"] = stack[-1][1] if stack else None
        node["position"] = position
        stack.append((node["level"], node["id"]))
    return nodes


def _tree_order(nodes):
    """Return preorder from explicit identities, preserving sibling order.

    A missing target page has no effect on ancestry. A node's level describes
    that ancestry and is never used to infer a different parent after merging.
    """
    children = defaultdict(list)
    identifiers = {node["id"] for node in nodes}
    for node in nodes:
        parent = node.get("parent_id")
        if parent and parent not in identifiers:
            raise ValueError("目录父节点缺失。")
        children[parent].append(node)
    result, visited = [], set()
    stack = [(node, 1) for node in reversed(children[None])]
    while stack:
        node, level = stack.pop()
        if node["id"] in visited:
            raise ValueError("目录节点重复或形成循环。")
        visited.add(node["id"])
        node["position"], node["level"] = len(result), level
        result.append(node)
        stack.extend((child, level + 1) for child in reversed(children[node["id"]]))
    if len(result) != len(nodes):
        raise ValueError("目录形成无法到达的循环。")
    return result


def extract_outline(asset, path, *, progress=None):
    """Fuse valid bookmarks with missing printed entries; use headings as fallback.

    Page labels are looked up independently, retaining Roman/body/appendix
    segments and ambiguous repeated labels. A whole-book offset is never guessed.
    """
    import fitz
    from catalog.services.outline_bookmarks import BookmarkObservations
    from catalog.services.outline_headings import styled_headings
    nodes, diagnostics, geometry, native_pages = [], [], {}, {}
    native_headings = []
    manual_pages = set(asset.pages.filter(is_text_manual=True).values_list("index", flat=True))
    if progress:
        progress("bookmarks", 0, asset.page_count)
    document = fitz.open(str(path))
    try:
        if len(document) != asset.page_count:
            raise OutlineConflict("实际 PDF 页数与文件校验记录不一致，请重新校验文件后生成目录。")
        label_rules = document.get_page_labels()
        file_sequence_labels = label_rules == [{"startpage": 0, "prefix": "", "firstpagenum": 1, "style": "D"}]
        bookmark_rows = document.get_toc(simple=False)
        if len(bookmark_rows) > 20000:
            raise ValueError("原生书签超过 20000 项，请分段校准；未保存截断结果。")
        bookmark_observations = BookmarkObservations(bookmark_rows)
        for number in range(1, len(document) + 1):
            if number > 1 and (number - 1) % 32 == 0:
                # Release document-owned resources as in native text extraction.
                document.close()
                document = fitz.open(str(path))
            pdf_page = document[number - 1]
            if progress and (number == 1 or number % 10 == 0 or number == len(document)):
                progress("native_headings", number, len(document))
            geometry[number] = {"pdf_width": pdf_page.rect.width, "pdf_height": pdf_page.rect.height,
                                "rotation": pdf_page.rotation, "cropbox": list(pdf_page.cropbox)}
            native_pages[number] = native_geometry(pdf_page)
            if number not in manual_pages:
                blocks = pdf_page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES).get("blocks", [])
                bookmark_observations.observe_blocks(number, blocks)
                native_headings.extend((number, row) for row in styled_headings(blocks))
                if len(native_headings) > 20000:
                    raise ValueError("字号标题候选超过 20000 项，请分段校准；未保存截断结果。")
            fitz.TOOLS.store_shrink(100)
        for ordinal, entry in enumerate(bookmark_rows):
            level, title, page = entry[:3]
            title = _title(title)
            detail = entry[3] if len(entry) > 3 and isinstance(entry[3], dict) else {}
            target = detail.get("to")
            valid = _readable(title) and 1 <= page <= asset.page_count
            position = [float(target.x), float(target.y)] if valid and hasattr(target, "x") else []
            if position and (any(not math.isfinite(value) or value < 0 for value in position)
                             or position[0] > document[page - 1].rect.width
                             or position[1] > document[page - 1].rect.height):
                position, valid = [], False
            node = _node(asset, ordinal, title, page if valid else None, level=max(1, int(level)),
                         source="pdf_bookmark", position=position)
            node["page_geometry"] = geometry.get(page, {})
            node["calibration_status"] = "native" if valid else "needs_review"
            nodes.append(node)
            if not valid:
                diagnostics.append({"code": "invalid_bookmark", "node_id": node["id"], "message": "书签标题或落点需要校准。"})
    finally:
        document.close()
    _parents(nodes)

    pages = list(asset.pages.filter(index__gte=1, index__lte=asset.page_count).order_by("index").values("index", "printed_label", "label_source", "is_label_manual", "label_segment", "text"))
    # A PDF numbering every physical page from 1 does not establish printed
    # page labels. Preserve those stored labels, but match contents to actual
    # body observations instead of treating the file index as evidence.
    label_pages = [{**page, "printed_label": ""} if file_sequence_labels and page["label_source"] == "pdf_page_labels" and not page["is_label_manual"] else page for page in pages]
    labels = OutlineLabels(label_pages, (asset.validation_details or {}).get("page_mapping"))
    titles = defaultdict(list)
    headings, contents_rows = [], []
    contents_pages = set()
    for processed, page in enumerate(pages, start=1):
        if progress and (processed == 1 or processed % 20 == 0 or processed == len(pages)):
            progress("contents_and_headings", processed, len(pages))
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        for line in lines:
            bookmark_observations.observe(page["index"], line)
        matches = [ENTRY.match(line) for line in lines]
        is_contents = (any(CONTENTS.match(_title(line)) for line in lines[:8])
            or any(CONTENTS.fullmatch(_title("".join(lines[i:i+2]))) for i in range(min(7, len(lines)-1)))
            or sum(bool(match) for match in matches) >= 3
            or page["index"]-1 in contents_pages and (any(matches) or any(line in {"目", "录", "錄"} for line in lines[:4])))
        if is_contents:
            contents_pages.add(page["index"])
            pending = ""
            for line_index, line in enumerate(lines):
                if (line_index < 4 and line in {"目", "录", "錄"}
                    or CONTENTS.fullmatch(_title(line))
                    or line_index < 7 and CONTENTS.fullmatch(_title("".join(lines[line_index:line_index+2])))
                    or 0 < line_index < 8 and CONTENTS.fullmatch(_title("".join(lines[line_index-1:line_index+1])))):
                    pending = ""
                    continue
                match = ENTRY.match(line) or TRAILING_PAGE.match(line)
                if match:
                    entry_title = _title(match.group("title"))
                    # A chapter synopsis belongs to the preceding entry, not
                    # the next explicitly numbered chapter or front matter.
                    if HEADING.match(entry_title) or CONTENTS_TITLE_START.match(entry_title):
                        pending = ""
                    title = _title(f"{pending} {entry_title}")
                    contents_rows.append((title, match.group("label"), page["index"]))
                    pending = ""
                elif LABEL_ONLY.fullmatch(line) and pending:
                    contents_rows.append((_title(pending), line, page["index"]))
                    pending = ""
                elif not CONTENTS.match(_title(line)) and len(line) < 180:
                    if HEADING.match(line) or CONTENTS_TITLE_START.match(line):
                        pending = ""
                    pending = f"{pending} {line}".strip()[:600]
            continue
        for line in lines:
            title = _title(line)
            if len(title) <= 180 and _readable(title):
                titles[_match_key(title)].append((page["index"], {}))
                if HEADING.match(title):
                    headings.append((title, page["index"]))
    # Join only adjacent observed lines that exactly reproduce a printed entry.
    # This handles split chapter titles without inventing a title or page offset.
    contents_titles = {_match_key(title): title for title, _label, _page in contents_rows}
    for page in pages:
        if page["index"] in contents_pages:
            continue
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        for start in range(min(8, len(lines))):
            for length in (2, 3):
                joined = "".join(lines[start:start+length])
                if _match_key(joined) in contents_titles:
                    titles[_match_key(joined)].append((page["index"], {}))
    # OCR returns rendered pixmap pixels. Native text blocks use MuPDF's
    # unrotated points. Keep their actual space and reference geometry; the
    # Reader adapter must not consume either as a naked PDF-point coordinate.
    repeating = defaultdict(set)
    heading_keys = set(headings)
    for number, row in native_headings:
        repeating[_match_key(row["text"])].add(number)
    suppressed = {key for key, numbers in repeating.items() if len(numbers) >= max(3, math.ceil(asset.page_count * .1))}
    for number, row in native_headings:
        title = _title(row["text"])
        if number in contents_pages or _match_key(title) in suppressed or not _readable(title):
            continue
        locator = {"bbox": row["bbox"], "coordinate_unit": "pdf_points", "coordinate_space": "pymupdf_unrotated",
                   "source_width": native_pages[number]["crop_box"][2] - native_pages[number]["crop_box"][0],
                   "source_height": native_pages[number]["crop_box"][3] - native_pages[number]["crop_box"][1],
                   "page_geometry": geometry[number], "heading_observation": {k: v for k, v in row.items() if k not in {"text", "bbox"}}}
        locator.update(locator_geometry(row["bbox"], native_pages[number]))
        titles[_match_key(title)].append((number, locator))
        if (title, number) not in heading_keys:
            headings.append((title, number))
            heading_keys.add((title, number))
    headings.sort(key=lambda item: item[1])
    if suppressed:
        diagnostics.append({"code": "repeated_heading_observations", "count": len(suppressed), "message": "重复出现的大字号文字可能是页眉，未自动补入目录；可从原文人工核对。"})
    observed_blocks = list(asset.pages.filter(index__gte=1, index__lte=asset.page_count).exclude(index__in=contents_pages).values("index", "width", "height", "geometry", "text_source", "blocks__text", "blocks__bbox").order_by("index", "blocks__order"))
    # Retain geometry for adjacent OCR title fragments, including spaced glyphs.
    by_page = defaultdict(list)
    for block in observed_blocks:
        by_page[block["index"]].append(block)
    joined_blocks = []
    for blocks in by_page.values():
        for start in range(min(8, len(blocks))):
            for length in (2, 3):
                parts = blocks[start:start+length]
                joined = "".join(_title(part["blocks__text"]) for part in parts)
                boxes = [part["blocks__bbox"] for part in parts]
                if _match_key(joined) in contents_titles and all(isinstance(box, list) and len(box) == 4 and all(type(v) in {int, float} and math.isfinite(v) for v in box) for box in boxes):
                    joined_blocks.append({**parts[0], "blocks__text": joined, "blocks__bbox": [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]})
    observed_blocks.extend(joined_blocks)
    margin_titles, margin_prefixes = defaultdict(set), defaultdict(set)
    def margin_heading(block):
        box = block["blocks__bbox"]
        return (block["index"] not in manual_pages and isinstance(box, list) and len(box) == 4
                and all(type(v) in {int, float} and math.isfinite(v) for v in box)
                and block["height"] > 0 and 0 <= box[1] / block["height"] <= .16)
    for block in observed_blocks:
        if margin_heading(block):
            title = _title(block["blocks__text"])
            margin_titles[_match_key(title)].add(block["index"])
            if prefix := HEADING.match(title):
                margin_prefixes[prefix[0]].add(block["index"])
    body_title_keys = {_match_key(block["blocks__text"]) for block in observed_blocks if not margin_heading(block)}
    running_headers = set()
    for block in observed_blocks:
        title = _title(block["blocks__text"])
        prefix = HEADING.match(title)
        if margin_heading(block) and ((len(margin_titles[_match_key(title)]) >= 3 or len(margin_titles[_match_key(title)]) >= 2 and _match_key(title) in body_title_keys) or prefix and len(margin_prefixes[prefix[0]]) >= 3):
            running_headers.add((_match_key(title), block["index"]))
    for key, number in running_headers:
        titles[key] = [hit for hit in titles[key] if hit[0] != number]
    headings = [(title, number) for title, number in headings if (_match_key(title), number) not in running_headers
                and not re.search(r"(?:译者|编者|原注)[）)]$", title)]
    if running_headers:
        diagnostics.append({"code": "repeated_running_headers", "count": len(running_headers), "message": "已排除有重复页边位置证据的页眉；原文字及坐标保持。"})
    for processed, block in enumerate(observed_blocks, start=1):
        if progress and processed % 500 == 0:
            progress("source_locations", block["index"], asset.page_count)
        title = _title(block["blocks__text"])
        if (_match_key(title), block["index"]) in running_headers:
            continue
        if block["index"] not in manual_pages:
            bookmark_observations.observe(block["index"], block["blocks__text"])
        box = block["blocks__bbox"]
        if title and len(title) <= 180 and isinstance(box, list) and len(box) == 4 and all(type(value) in {int, float} and math.isfinite(value) for value in box):
            source = block["text_source"]
            if source not in {"embedded", "ocr"}:
                continue  # Hybrid provenance cannot prove one coordinate space.
            locator = {"bbox": box, "coordinate_unit": "pixels" if source == "ocr" else "pdf_points",
                       "coordinate_space": "ocr_rendered_page" if source == "ocr" else "pymupdf_unrotated",
                       "source_width": block["width"], "source_height": block["height"],
                       "page_geometry": geometry.get(block["index"], {})}
            actual = native_pages[block["index"]]
            observed = validated_geometry(block["geometry"])
            expected_space = "rendered_pixels" if source == "ocr" else "pymupdf_unrotated"
            if (observed.get("coordinate_space") != expected_space
                    or any(observed.get(key) != actual.get(key) for key in ("page_rect", "crop_box", "rotation"))
                    or source == "ocr" and (block["width"], block["height"]) != (observed.get("render_width"), observed.get("render_height"))):
                observed = {}
            locator.update(locator_geometry(box, observed))
            titles[_match_key(title)].append((block["index"], locator))

    diagnostics.extend(bookmark_observations.review(nodes, contents_pages, lambda title: CONTENTS.fullmatch(title)))
    native_by_target = defaultdict(list)
    for node in nodes:
        native_by_target[(_match_key(node["title"]), node["pdf_page"])].append(node)
    matched_native, printed_stack = set(), []
    last_page = 0
    for ordinal, (title, label, contents_page) in enumerate(contents_rows):
        if progress and ordinal % 200 == 0:
            progress("match_contents", ordinal, len(contents_rows))
        title_matches = titles.get(_match_key(title), [])
        label_observations = labels.observations(label)
        label_pages = [row["pdf_page"] for row in label_observations]
        missing_label = labels.has_missing_label(label)
        unresolved_range = bool(LABEL_RANGE.fullmatch(label) and not label_pages)
        matches = [hit for hit in title_matches if (not label_pages or hit[0] in label_pages) and hit[0] >= last_page]
        target_pages = sorted({hit[0] for hit in matches})
        if missing_label or unresolved_range:
            page, locator, status = None, {}, "needs_review"
        elif len(target_pages) == 1:
            page = target_pages[0]
            locator = next((hit[1] for hit in matches if hit[1]), {})
            status = "matched"
        elif len(label_pages) == 1 and label_pages[0] >= last_page:
            page, locator, status = label_pages[0], {}, "needs_review"
        else:
            page, locator, status = None, {}, "needs_review"
        level = _level(title)
        while printed_stack and printed_stack[-1][0] >= level:
            printed_stack.pop()
        parent = printed_stack[-1][1] if printed_stack else None
        counterpart = next((row for row in native_by_target[(_match_key(title), page)]
                            if row["id"] not in matched_native and row["parent_id"] == parent), None) if page else None
        node = _node(asset, ordinal, title, page, source="printed_contents", label=label,
                     level=level, locator=locator, contents_page=contents_page)
        node["parent_id"] = parent
        node["calibration_status"] = status
        if missing_label or unresolved_range or len(label_pages) > 1 or any(row["spread"] for row in label_observations):
            message = ("映射记录标有缺失印刷页，未猜测物理落点，请核对原稿。" if missing_label else
                       "页码范围没有唯一且同段的实际端点，未推算落点。" if unresolved_range else
                       "此标签对应多处物理页，保留分段观察，请核对具体章节。" if len(label_pages) > 1 else
                       "标签来自双页扫描；保留整个实际物理页，不猜左右分区，请核对页内落点。")
            diagnostics.append({"code": "contents_label_review", "node_id": counterpart["id"] if counterpart else node["id"],
                                "message": f"{title}（{label}）：{message}", "observed_pages": label_pages[:20],
                                "observed_page_count": len(label_pages), "label_observations": label_observations[:20]})
        if counterpart:
            counterpart.setdefault("candidate_sources", [_candidate(counterpart)]).append(_candidate(node))
            matched_native.add(counterpart["id"])
            printed_stack.append((level, counterpart["id"]))
            last_page = page
            continue
        nodes.append(node)
        printed_stack.append((level, node["id"]))
        if page:
            last_page = page
        if status == "needs_review":
            diagnostics.append({"code": "contents_target_uncertain", "node_id": node["id"], "message": "目录页与正文落点需要人工核对。"})
    existing_targets = {(_match_key(node["title"]), node["pdf_page"]) for node in nodes}
    existing_by_target = defaultdict(list)
    for node in nodes:
        existing_by_target[(_match_key(node["title"]), node["pdf_page"])].append(node)
    generated, had_formal = [], bool(nodes)
    for ordinal, (title, page) in enumerate(headings):
        locators = [hit[1] for hit in titles[_match_key(title)] if hit[0] == page and hit[1]]
        node = _node(asset, ordinal, title, page, source="generated_heading", level=_level(title),
                     locator=locators[0] if locators else {})
        node["calibration_status"] = "needs_review" if had_formal else "generated"
        # A split first line at the same verified destination is an observation
        # of its complete printed title, not an additional chapter.
        partial = next((row for row in nodes if row["source"] == "printed_contents" and row["pdf_page"] == page
                        and _match_key(row["title"]).startswith(_match_key(title))), None)
        if partial and _match_key(partial["title"]) != _match_key(title):
            partial.setdefault("candidate_sources", [_candidate(partial)]).append(_candidate(node))
            continue
        if (_match_key(title), page) not in existing_targets:
            generated.append(node)
            existing_targets.add((_match_key(title), page))
            existing_by_target[(_match_key(title), page)].append(node)
        else:
            for existing in existing_by_target[(_match_key(title), page)]:
                existing.setdefault("candidate_sources", [_candidate(existing)]).append(_candidate(node))
    # Heading candidates form their own tree. No guessed graft onto the last
    # native chapter, including when a native parent has an unknown target.
    nodes.extend(_parents(generated))
    if generated and had_formal:
        diagnostics.append({"code": "possible_missing_headings", "message": "正文中发现可能缺少的章节；新增分支需要校准。"})
    elif not had_formal:
        diagnostics.append({"code": "generated_navigation" if nodes else "no_outline_detected",
                            "message": "这是从正文标题生成的章节导航。" if nodes else "尚未找到可用目录；请完成 OCR 或人工添加目录。"})
    if len(nodes) > 20000:
        raise ValueError("自动目录超过 20000 项，需要分段校准，未保存截断结果。")
    # Same titles on different pages remain distinct nodes. Their actual
    # observations are available side by side; no candidate is silently chosen.
    by_title = defaultdict(dict)
    for node in nodes:
        for candidate in node.get("candidate_sources") or [_candidate(node)]:
            by_title[_match_key(node["title"])][candidate["id"]] = candidate
    for node in nodes:
        candidates = by_title[_match_key(node["title"])]
        # Bound repeated-title expansion without losing the distinct tree
        # entries. Counts disclose when comparison needs a narrower selection.
        own = {row["id"]: row for row in node.get("candidate_sources") or [_candidate(node)]}
        comparison = dict(islice(own.items(), 50))
        for identifier, candidate in islice(((key, row) for key, row in candidates.items() if key not in comparison), max(0, 50 - len(comparison))):
            comparison[identifier] = candidate
        node["candidate_sources"] = list(comparison.values())
        node["candidate_sources_count"] = len(candidates)
    return _tree_order(nodes), diagnostics


def _source_current(asset):
    if asset.kind != Asset.Kind.NORMALIZED or asset.status != Asset.Status.READY or asset.validation_status != Asset.ValidationStatus.VALID:
        raise OutlineConflict("阅读文件尚未就绪。")
    if asset.is_current:
        return
    from ingestion.services.source_identity import pending_replacement_source

    if pending_replacement_source(asset):
        return
    details = asset.validation_details or {}
    if (details.get("text_publication_state") == "staging" and asset.source_asset_id
            and details.get("text_source_asset_id") == str(asset.source_asset_id)):
        parent = Asset.objects.filter(pk=asset.source_asset_id, edition=asset.edition).first()
        if parent and (parent.is_current or pending_replacement_source(parent)):
            if parent.sha256 == asset.sha256:
                return
            from catalog.services.page_mapping_exports import staging_copy_matches
            if staging_copy_matches(asset, parent):
                return
    raise OutlineConflict("文件已更换；旧目录和原文仍保留，请选择当前文件。")


def validate_nodes(asset, nodes, *, base_revision=None):
    if not isinstance(nodes, list) or len(nodes) > 20000:
        raise ValueError("目录必须为节点列表，最多 20000 项。")
    base_revision = base_revision or asset.outline_revisions.first()
    prior_nodes = {node["id"]: node for node in base_revision.nodes} if base_revision else {}
    seen, levels, result = set(), {}, []
    for position, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            raise ValueError("目录节点必须为对象。")
        identifier = str(UUID(str(raw.get("id")))) if raw.get("id") else str(uuid4())
        parent = str(UUID(str(raw["parent_id"]))) if raw.get("parent_id") else None
        if identifier in seen or (parent and parent not in seen):
            raise ValueError("目录 ID 重复，或父节点不在子节点之前。")
        title = _title(raw.get("title"))
        if not _readable(title):
            raise ValueError("目录标题为空或包含损坏文字。")
        page = raw.get("pdf_page")
        if page is not None and (type(page) is not int or not 1 <= page <= asset.page_count):
            raise ValueError("目录物理页必须在 PDF 页数范围内。")
        prior = prior_nodes.get(identifier, {})
        same_page = prior.get("pdf_page") == page
        clear_position = raw.get("clear_position", False)
        if type(clear_position) is not bool:
            raise ValueError("clear_position 必须为布尔值。")
        point = [] if clear_position else raw.get("pdf_position", prior.get("pdf_position", []) if same_page else []) or []
        if not isinstance(point, list) or len(point) not in {0, 2} or any(type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in point):
            raise ValueError("页内落点必须为非负 PDF 点坐标 [x, y]。")
        geometry = prior.get("page_geometry", {}) if same_page else {}
        relative = raw.get("normalized_position", prior.get("normalized_position", []) if same_page and not clear_position else []) or []
        if not isinstance(relative, list) or len(relative) not in {0, 2} or any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1 for value in relative):
            raise ValueError("相对落点必须为显示页面内的比例坐标 [x, y]，各值在 0—1 之间。")
        if relative:
            point = []
        if (point or relative) and page is None:
            raise ValueError("请先选择物理页，再设置页内落点。")
        if point and page:
            if not geometry:
                raise ValueError("此节点没有可验证的 PDF 坐标空间，请使用 normalized_position 比例落点。")
            if point[0] > geometry["pdf_width"] or point[1] > geometry["pdf_height"]:
                raise ValueError("页内落点超出所选 PDF 页面的范围。")
        level = levels.get(parent, 0) + 1
        if level > 32:
            raise ValueError("目录层级最多 32 层。")
        contents_page = raw.get("contents_page", prior.get("contents_page"))
        if contents_page is not None and (type(contents_page) is not int or not 1 <= contents_page <= asset.page_count):
            raise ValueError("目录原页超出 PDF 页数范围。")
        same_position = (not clear_position and same_page and point == prior.get("pdf_position", [])
                         and relative == prior.get("normalized_position", []))
        source_locator = prior.get("source_locator", {}) if same_position else {}
        coordinate_space = prior.get("coordinate_space", "") if point and point == prior.get("pdf_position") and same_page else "displayed_pdf_crop" if point else ""
        label = _title(raw.get("printed_label", prior.get("printed_label", "")))[:40]
        unchanged = bool(prior) and same_position and all((
            title == prior.get("title"), parent == prior.get("parent_id"),
            label == prior.get("printed_label", ""), contents_page == prior.get("contents_page")))
        status = raw.get("calibration_status")
        if status not in {None, "unverified", "needs_review", "confirmed", "native", "matched", "generated"}:
            raise ValueError("目录核验状态无效。")
        if status in {"native", "matched", "generated"} and (not unchanged or status != prior.get("calibration_status")):
            raise ValueError("自动来源状态只能保留，不能由人工编辑伪造；请标为待核对或明确确认。")
        if status == "confirmed" and page is None:
            raise ValueError("人工确认必须具有有效的物理页落点。")
        # A full-tree save is not a review of every row. Only an explicitly
        # requested confirmed status records a new human confirmation.
        status = status or (prior.get("calibration_status", "unverified") if unchanged else "unverified" if page else "needs_review")
        node = {"id": identifier, "parent_id": parent, "position": position, "level": level,
                       "title": title, "pdf_page": page, "printed_label": label,
                       "pdf_position": point, "coordinate_unit": "pdf_points" if point else "", "source": prior.get("source", "manual") if unchanged else "manual",
                       "coordinate_space": coordinate_space, "page_geometry": geometry,
                       "normalized_position": relative, "source_locator": source_locator,
                       "precision": "position" if point or relative or source_locator else "page",
                       "calibration_status": status, "contents_page": contents_page}
        node["candidate_sources"] = prior.get("candidate_sources") or ([_candidate(prior)] if prior else [])
        node["candidate_sources_count"] = prior.get("candidate_sources_count", len(node["candidate_sources"]))
        result.append(node)
        seen.add(identifier)
        levels[identifier] = level
    return result


def revision_payload(revision, *, nodes=True):
    if revision is None:
        return None
    data = {"id": str(revision.pk), "revision": revision.revision, "asset_id": str(revision.asset_id),
            "document_revision_id": str(revision.document_revision_id or ""), "origin": revision.origin,
            "is_active": revision.is_active, "reviewed": revision.reviewed,
            "diagnostics": revision.diagnostics, "created_at": revision.created_at,
            "node_count": len(revision.nodes), "source_checksum": revision.source_checksum,
            "parser_version": revision.parser_version,
            "restored_from_id": str(revision.restored_from_id) if revision.restored_from_id else None}
    if nodes:
        data["nodes"] = [_with_candidates(node) for node in revision.nodes]
    return data


def outline_state(asset, *, history_page=1):
    from catalog.services.publication_eligibility import active_asset_q

    revisions = asset.outline_revisions.all()
    latest = revisions.first()
    count = revisions.count()
    history_page = min(max(1, history_page), max(1, (count + 49) // 50))
    start = (history_page - 1) * 50
    try:
        _source_current(asset)
        source_current, source_error = True, ""
    except OutlineConflict as exc:
        source_current, source_error = False, str(exc)
    readable = Asset.objects.filter(pk=asset.pk, kind="normalized", status="ready", validation_status="valid",
                                    access_status__in=["inherit", "public"]).filter(active_asset_q(asset_prefix="")).exists()
    edition = asset.edition
    work = edition.work
    document = asset.document_revisions.filter(is_active=True).first()
    summary = {"id": str(asset.pk), "edition_id": str(edition.pk), "work_id": str(work.pk),
               "title": work.title, "authors": list(edition.contributions.filter(role="author").order_by("order").values_list("person__preferred_name", flat=True)),
               "edition_label": edition.version_label, "publication_year": edition.publication_year,
               "document_type": work.document_type, "page_count": asset.page_count, "sha256": asset.sha256,
               "status": asset.status, "validation_status": asset.validation_status, "is_current": asset.is_current,
               "source_current": source_current, "source_error": source_error, "original_filename": asset.original_filename,
               "document_revision_id": str(document.pk) if document else "",
               "preview_url": f"/distribution/admin/assets/{asset.pk}/preview/" if asset.is_current and asset.status == "ready" and asset.file else "",
               "reader_url": f"/reader/{asset.pk}" if readable else "",
               "cover_url": (f"/api/catalog/admin/media/renditions/{work.cover_rendition_id}/file/" if work.cover_rendition_id else
                             f"/api/catalog/works/{work.pk}/cover/?edition_id={edition.pk}" if readable and work.cover else "")}
    return {"asset_id": str(asset.pk), "asset": summary, "expected_revision": latest.revision if latest else 0,
            "active": revision_payload(revisions.filter(is_active=True).first()),
            "latest": revision_payload(latest),
            "history": [revision_payload(row, nodes=False) for row in revisions[start:start + 50]],
            "history_page": history_page, "history_count": count,
            "history_next_page": history_page + 1 if start + 50 < count else None,
            "jobs": [{"id": str(job.pk), "status": job.status, "progress": job.progress, "operation": job.stats.get("operation"),
                      "error": job.error_message, "updated_at": job.updated_at, "result_revision_id": job.stats.get("result_revision_id")}
                     | ({"download_url": f"/catalog/admin/editions/{asset.edition_id}/files/{job.stats['result_asset_id']}/content/?download=1",
                         "outline_revision_id": job.stats.get("outline_revision_id")}
                        if job.stats.get("operation") == "outline_export" and job.status == "succeeded" and job.stats.get("result_asset_id") else {})
                     for job in ProcessingJob.objects.filter(asset=asset, job_type="text_extraction", stats__operation__in=["outline_rebuild", "outline_export"]).order_by("-created_at")[:10]]}


def _assert_expected(asset, expected_revision):
    latest = asset.outline_revisions.first()
    if type(expected_revision) is not int or expected_revision != (latest.revision if latest else 0):
        raise OutlineConflict("目录已有新修订；请保留当前输入，读取最新差异后再保存。")


def _new_revision(asset, *, nodes, diagnostics=(), actor=None, origin="automatic", restored_from=None, document_revision=None):
    next_number = (asset.outline_revisions.aggregate(value=Max("revision"))["value"] or 0) + 1
    return DocumentOutlineRevision.objects.create(
        asset=asset, revision=next_number, source_checksum=asset.sha256,
        parser_version=PARSER_VERSION,
        document_revision=document_revision or asset.document_revisions.filter(is_active=True).first(),
        nodes=nodes, diagnostics=list(diagnostics), origin=origin, created_by=actor, restored_from=restored_from)


def _write_receipt(asset, *, actor, action, request_id, payload):
    identity = str(UUID(str(request_id))) if request_id else ""
    fingerprint = sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
    receipt = AuditEvent.objects.filter(actor=actor, action=action, object_type="Asset", object_id=str(asset.pk), request_id=identity).first() if identity else None
    if receipt:
        if receipt.after.get("fingerprint") != fingerprint:
            raise OutlineConflict("同一个目录请求标识不能用于不同内容。")
        return identity, fingerprint, asset.outline_revisions.get(pk=receipt.after["revision_id"])
    return identity, fingerprint, None


@transaction.atomic
def edit_outline(asset_id, *, nodes, expected_revision, actor, request_id=None, base_revision_id=None):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    payload = {"nodes": nodes, "expected_revision": expected_revision}
    if base_revision_id:
        payload["base_revision_id"] = str(base_revision_id)
    identity, fingerprint, replay = _write_receipt(asset, actor=actor, action="outline.saved", request_id=request_id,
        payload=payload)
    if replay:
        return replay
    _source_current(asset)
    _assert_expected(asset, expected_revision)
    base = asset.outline_revisions.filter(pk=base_revision_id).first() if base_revision_id else asset.outline_revisions.first()
    if base_revision_id and base is None:
        raise ValueError("编辑依据的修订不属于当前文件。")
    current_document = asset.document_revisions.filter(is_active=True).first()
    if base and (base.source_checksum != asset.sha256 or (base.document_revision_id and (not current_document or base.document_revision_id != current_document.pk))):
        raise OutlineConflict("编辑依据对应旧的正文解释，请保留输入并选择当前来源修订。")
    revision = _new_revision(asset, nodes=validate_nodes(asset, nodes, base_revision=base), actor=actor, origin="manual")
    AuditEvent.objects.create(actor=actor, action="outline.saved", object_type="Asset", object_id=str(asset.pk), request_id=identity, after={"revision_id": str(revision.pk), "fingerprint": fingerprint})
    return revision


@transaction.atomic
def adopt_outline(asset_id, *, revision_id, expected_revision, actor, restore=False, request_id=None):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    action = "outline.restored" if restore else "outline.adopted"
    identity, fingerprint, replay = _write_receipt(asset, actor=actor, action=action, request_id=request_id,
        payload={"revision_id": str(revision_id), "expected_revision": expected_revision})
    if replay:
        return replay
    _source_current(asset)
    _assert_expected(asset, expected_revision)
    revision = asset.outline_revisions.get(pk=revision_id)
    current_document = asset.document_revisions.filter(is_active=True).first()
    if revision.source_checksum != asset.sha256 or (revision.document_revision_id and (not current_document or revision.document_revision_id != current_document.pk)):
        raise OutlineConflict("这份目录对应旧的正文解释，请先重建或重新校准。")
    if not revision.nodes:
        raise ValueError("目录为空，请先添加并确认有效目录项。")
    if any(type(node.get("pdf_page")) is not int or not 1 <= node["pdf_page"] <= asset.page_count for node in revision.nodes):
        raise ValueError("仍有目录项缺少有效物理页落点，请先逐项校准。")
    allowed = {"confirmed", "native", "matched", "generated"} if restore and revision.parser_version == PARSER_VERSION else {"confirmed", "native"}
    if any(node.get("calibration_status") not in allowed for node in revision.nodes):
        raise ValueError("仍有目录项未经明确确认，请核对候选后再采用。")
    # Adoption changes the edit precondition too. Otherwise two windows can
    # both adopt different candidates with the same expected_revision value.
    revision = _new_revision(asset, nodes=revision.nodes, diagnostics=revision.diagnostics,
                             actor=actor, origin="restored" if restore else "adopted", restored_from=revision)
    previous = asset.outline_revisions.filter(is_active=True).first()
    asset.outline_revisions.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
    revision.is_active = True
    revision.reviewed = all(n.get("calibration_status") in {"confirmed", "native"} for n in revision.nodes)
    revision.save(update_fields=["is_active", "reviewed", "updated_at"])
    _schedule_source_mapping(revision)
    AuditEvent.objects.create(actor=actor, action=action, object_type="Asset", object_id=str(asset.pk), request_id=identity,
                              before={"revision_id": str(previous.pk) if previous else None}, after={"revision_id": str(revision.pk), "fingerprint": fingerprint})
    from .outline_exports import queue_export
    queue_export(asset.pk, revision_id=revision.pk, request_id=uuid5(asset.pk, str(revision.pk)), actor=actor)
    return revision


@transaction.atomic
def correct_outline(asset_id, *, nodes, expected_revision, actor, request_id, base_revision_id=None):
    """One explicit correction saves navigation and schedules its download copy."""
    from .outline_exports import queue_export
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    revision = edit_outline(asset_id, nodes=nodes, expected_revision=expected_revision, actor=actor,
                            request_id=request_id, base_revision_id=base_revision_id)
    if revision.origin == "corrected":
        return revision
    if not revision.nodes or any(type(n.get("pdf_page")) is not int or not 1 <= n["pdf_page"] <= asset.page_count for n in revision.nodes):
        raise ValueError("请为每个保留的目录项填写有效的 PDF 页码。")
    for node in revision.nodes:
        if node.get("source") == "manual" and node.get("calibration_status") in {"unverified", "needs_review"}:
            node["calibration_status"] = "confirmed"
    asset.outline_revisions.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
    revision.origin, revision.is_active = "corrected", True
    revision.reviewed = all(n.get("calibration_status") in {"confirmed", "native"} for n in revision.nodes)
    revision.save(update_fields=["origin", "is_active", "reviewed", "nodes", "updated_at"])
    _schedule_source_mapping(revision)
    queue_export(asset.pk, revision_id=revision.pk, request_id=uuid5(asset.pk, str(revision.pk)), actor=actor)
    return revision


def public_outline(asset, *, access_statuses=None):
    from catalog.services.publication_eligibility import active_asset_q, active_document_q

    if not Asset.objects.filter(pk=asset.pk, kind="normalized", status="ready", validation_status="valid",
                               access_status__in=access_statuses if access_statuses is not None else ["inherit", "public"]).filter(active_asset_q(asset_prefix="")).exists():
        return []
    fulltext_ready = Asset.objects.filter(pk=asset.pk).filter(active_document_q(asset_prefix="")).exists()
    revisions = asset.outline_revisions.filter(is_active=True, source_checksum=asset.sha256)
    if fulltext_ready:
        revisions = revisions.filter(document_revision_id=asset.edition.active_catalog_revision.document_revision_id)
    revision = revisions.first()
    if revision:
        # Automatic navigation is readable only for the current document identity.
        document = asset.document_revisions.filter(is_active=True).first()
        current_navigation = revision.document_revision_id == (document.pk if document else None)
        visible = revision.nodes if fulltext_ready or revision.reviewed or current_navigation else [node for node in revision.nodes if node["source"] == "pdf_bookmark"]
        return reader_outline_nodes(revision, visible)
    return [{"id": str(page.pk), "parent_id": None, "position": position, "level": 1,
             "index": page.index, "file_page_index": page.index, "pdf_page": page.index,
             "chapter_title": page.chapter_title, "title": page.chapter_title, "printed_label": page.printed_label,
             "source": "legacy_page_heading", "calibration_status": "unverified", "pdf_position": [], "coordinate_unit": "", "coordinate_space": "", "precision": "page"}
            for position, page in enumerate(asset.pages.exclude(chapter_title="").order_by("index"))]


def reader_outline_nodes(revision, visible=None):
    """Serialize an already-authorized, exact outline revision for the reader."""
    visible = revision.nodes if visible is None else visible
    identifiers = {node["id"] for node in visible}
    visible = [{**{key: value for key, value in node.items() if key not in {"candidate_sources", "candidate_sources_count"}},
                "parent_id": node.get("parent_id") if node.get("parent_id") in identifiers else None} for node in visible]
    return [{**node, "index": node["pdf_page"], "file_page_index": node["pdf_page"], "chapter_title": node["title"],
             "outline_revision_id": str(revision.pk)} for node in visible if node.get("pdf_page")]


@transaction.atomic
def queue_outline_rebuild(asset_id, *, actor=None, request_id=None, automatic=False):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    # Automatic work is independently durable even if the source moves between
    # document commit and execution. Its failure must not roll back saved text.
    if not automatic:
        _source_current(asset)
    document = asset.document_revisions.filter(is_active=True).first()
    request_key = str(UUID(str(request_id))) if request_id else str(uuid4())
    source_key = f"{document.pk if document else ''}:{asset.sha256}:{PARSER_VERSION}"
    identity = sha256(f"{asset.pk}:{source_key if automatic else request_key}".encode()).hexdigest()
    existing = ProcessingJob.objects.filter(idempotency_key=f"outline:{identity}").first()
    if existing:
        if not automatic and (existing.stats.get("source_sha256") != asset.sha256 or str(existing.stats.get("document_revision_id") or "") != str(document.pk if document else "")):
            raise OutlineConflict("这个请求已绑定原文件，请重新确认当前 PDF。")
        return existing
    job = ProcessingJob.objects.create(
        job_type=ProcessingJob.JobType.TEXT_EXTRACTION, asset=asset, edition=asset.edition, created_by=actor,
        task_id=str(uuid4()), idempotency_key=f"outline:{identity}",
        stats={"operation": "outline_rebuild", "source_sha256": asset.sha256,
               "document_revision_id": str(document.pk) if document else None, "automatic": automatic})
    transaction.on_commit(lambda: dispatch_outline_job(str(job.pk), job.task_id))
    return job


def dispatch_outline_job(job_id, task_id):
    from ingestion.tasks import process_outline_job

    try:
        process_outline_job.apply_async(args=[job_id], task_id=task_id, ignore_result=True)
        return True
    except (OperationalError, OSError, ConnectionError, TimeoutError):
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id, status="pending").update(status="failed", error_code="queue_unavailable", error_message="目录任务未进入队列，请重试。", finished_at=timezone.now(), updated_at=timezone.now())
        return False


@transaction.atomic
def outline_job_action(job_id, *, action, actor):
    # Match extraction's Asset → Job lock order when cancellation races commit.
    target = ProcessingJob.objects.get(pk=job_id, job_type="text_extraction", stats__operation__in=["outline_rebuild", "outline_export", "page_mapping_export"])
    asset = Asset.objects.select_for_update().get(pk=target.asset_id)
    job = ProcessingJob.objects.select_for_update().get(pk=target.pk)
    before = {"status": job.status, "error_code": job.error_code, "error_message": job.error_message, "attempt": job.attempt}
    if action == "cancel":
        if job.status not in {"pending", "running", "failed", "canceled"}:
            raise OutlineConflict("任务已完成，无需取消。")
        job.status, job.task_id, job.finished_at = "canceled", "", timezone.now()
    elif action == "retry":
        if job.status in {"pending", "running"}:
            return job
        if job.status != "failed":
            raise OutlineConflict("只有失败的任务可以重试。")
        _source_current(asset)
        if job.stats.get("operation") in {"outline_export", "page_mapping_export"}:
            from catalog.services.outline_exports import current_export_revision
            current_export_revision(asset, job.stats)
        current_document = asset.document_revisions.filter(is_active=True).first()
        if asset.sha256 != job.stats.get("source_sha256") or str(current_document.pk if current_document else "") != str(job.stats.get("document_revision_id") or ""):
            raise OutlineConflict("任务绑定的正文已变化，请基于当前文件新建任务，原失败记录保留。")
        job.status, job.task_id, job.attempt = "pending", str(uuid4()), 0
        job.error_code, job.error_message, job.finished_at = "", "", None
    else:
        raise ValueError("请选择 retry 或 cancel。")
    job.save(update_fields=["status", "task_id", "attempt", "error_code", "error_message", "finished_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=f"outline.task.{action}", object_type="ProcessingJob", object_id=str(job.pk), before=before, after={"status": job.status})
    if action == "retry":
        from catalog.services.outline_exports import dispatch_export
        dispatch = dispatch_export if job.stats.get("operation") in {"outline_export", "page_mapping_export"} else dispatch_outline_job
        transaction.on_commit(lambda: dispatch(str(job.pk), job.task_id))
    return job


def run_outline_job(job_id, *, task_id):
    from ingestion.services.processing import _claim_processing_job
    from ingestion.services.files import materialize_field_file

    job, claimed = _claim_processing_job(job_id, task_id=task_id, progress_floor=5)
    if not claimed:
        return job
    cleanup = None
    def progress(stage, completed, total):
        start, weight = {"bookmarks": (5, 0), "native_headings": (5, 25),
                         "contents_and_headings": (30, 30), "source_locations": (60, 20),
                         "match_contents": (80, 10)}.get(stage, (80, 10))
        updated = ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
            heartbeat_at=timezone.now(), progress=min(90, start + round(weight * completed / max(1, total))),
            stats={**job.stats, "stage": stage, "completed_pages": completed, "total_pages": total}, updated_at=timezone.now())
        if not updated:
            raise OutlineJobInterrupted()
    try:
        asset = job.asset
        _source_current(asset)
        path, cleanup = materialize_field_file(asset.file)
        nodes, diagnostics = extract_outline(asset, path, progress=progress)
        from .outline_automatic import automatic_nodes
        nodes, automatic_diagnostics = automatic_nodes(asset, nodes)
        diagnostics = [{**row, "stage": "before_automatic_matching"} for row in diagnostics] + automatic_diagnostics
        with transaction.atomic():
            asset = Asset.objects.select_for_update().get(pk=asset.pk)
            current = ProcessingJob.objects.select_for_update().get(pk=job.pk)
            if current.task_id != task_id or current.status != "running":
                return current
            _source_current(asset)
            document = asset.document_revisions.filter(is_active=True).first()
            if asset.sha256 != job.stats["source_sha256"] or str(document.pk if document else "") != str(job.stats.get("document_revision_id") or ""):
                raise OutlineConflict("正文解释已变化，本次目录结果未采用，请重新生成。")
            revision = _new_revision(asset, nodes=nodes, diagnostics=diagnostics, actor=job.created_by, document_revision=document)
            active = asset.outline_revisions.filter(is_active=True).first()
            # Preserve manual calibration even when a newer parser finds more nodes.
            if nodes and not (active and (active.reviewed or active.origin in {"corrected", "restored"})):
                asset.outline_revisions.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
                revision.is_active = True
                revision.save(update_fields=["is_active", "updated_at"])
                _schedule_source_mapping(revision)
                from .outline_exports import queue_export
                queue_export(asset.pk, revision_id=revision.pk, request_id=uuid5(asset.pk, str(revision.pk)), actor=job.created_by)
            current.status, current.progress, current.finished_at = "succeeded", 100, timezone.now()
            # Extraction is never a human review, even when matching produced
            # no warnings or the source contained structurally valid bookmarks.
            current.stats = {**current.stats, "result_revision_id": str(revision.pk), "node_count": len(nodes),
                             "needs_review": not nodes or any(row.get("code") == "unresolved_contents" for row in automatic_diagnostics),
                             "automatic_active": revision.is_active, "stage": "complete"}
            current.save(update_fields=["status", "progress", "finished_at", "stats", "updated_at"])
            return current
    except OutlineJobInterrupted:
        return ProcessingJob.objects.get(pk=job.pk)
    except Exception as exc:
        ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
            status="failed", error_code=type(exc).__name__, error_message=str(exc)[:2000], finished_at=timezone.now(), updated_at=timezone.now())
        raise
    finally:
        if cleanup:
            cleanup()


def _schedule_source_mapping(outline):
    if outline.document_revision_id:
        from catalog.services.knowledge_source_updates import schedule_source_update
        schedule_source_update(outline.document_revision)
