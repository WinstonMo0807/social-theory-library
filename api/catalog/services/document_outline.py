"""Versioned PDF navigation using the existing Asset, Page and ProcessingJob.

Bookmarks are lossless; printed contents and heading recognition are explicit
candidates. No parser candidate overwrites a human-calibrated directory.
"""
from collections import defaultdict
from hashlib import sha256
import json
import math
import re
from uuid import UUID, uuid4, uuid5

import fitz
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from kombu.exceptions import OperationalError

from catalog.models import Asset, DocumentOutlineRevision
from catalog.services.text import sanitize_unicode
from ingestion.models import AuditEvent, ProcessingJob


PARSER_VERSION = "outline-v1"
HEADING = re.compile(r"^(?:第[一二三四五六七八九十百零\d]+[编部篇章节]|(?:chapter|part|section|appendix)\s+[\w一二三四五六七八九十]+|\d+(?:\.\d+){1,5}\s+)", re.I)
CONTENTS = re.compile(r"^(?:目\s*录|contents|table\s+of\s+contents)$", re.I)
ENTRY = re.compile(r"^(?P<title>.+?)\s*(?:[.．·…_]{2,}|\s{2,}|\t)\s*(?P<label>\d{1,5}|[ivxlcdmIVXLCDM]{1,12})\s*$")
TRAILING_PAGE = re.compile(r"^(?P<title>.+?\D)\s+(?P<label>\d{1,5}|[ivxlcdmIVXLCDM]{1,12})\s*$")


class OutlineConflict(ValueError):
    pass


class OutlineJobInterrupted(Exception):
    pass


def _title(value):
    return " ".join(sanitize_unicode(str(value or "")).split())[:600]


def _match_key(value):
    original = _title(value)
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
        "source_locator": locator or {}, "precision": "position" if position or locator else "page",
        "source": source, "calibration_status": "unverified",
        "contents_page": contents_page,
    }


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
    nodes, diagnostics, geometry = [], [], {}
    if progress:
        progress("bookmarks", 0, asset.page_count)
    with fitz.open(str(path)) as document:
        for number, pdf_page in enumerate(document, start=1):
            geometry[number] = {"pdf_width": pdf_page.rect.width, "pdf_height": pdf_page.rect.height,
                                "rotation": pdf_page.rotation, "cropbox": list(pdf_page.cropbox)}
        for ordinal, entry in enumerate(document.get_toc(simple=False)):
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
    _parents(nodes)

    pages = list(asset.pages.order_by("index").values("index", "printed_label", "text"))
    labels, titles = defaultdict(list), defaultdict(list)
    for page in pages:
        if page["printed_label"]:
            labels[str(page["printed_label"]).casefold()].append(page["index"])
    headings, contents_rows = [], []
    contents_pages = set()
    for processed, page in enumerate(pages, start=1):
        if progress and (processed == 1 or processed % 20 == 0 or processed == len(pages)):
            progress("contents_and_headings", processed, len(pages))
        lines = [line.strip() for line in page["text"].splitlines() if line.strip()]
        matches = [ENTRY.match(line) for line in lines]
        is_contents = any(CONTENTS.match(_title(line)) for line in lines[:8]) or sum(bool(match) for match in matches) >= 3
        if is_contents:
            contents_pages.add(page["index"])
            pending = ""
            for line in lines:
                match = ENTRY.match(line) or TRAILING_PAGE.match(line)
                if match:
                    title = _title(f"{pending} {match.group('title')}")
                    contents_rows.append((title, match.group("label"), page["index"]))
                    pending = ""
                elif re.fullmatch(r"\d{1,5}|[ivxlcdmIVXLCDM]{1,12}", line) and pending:
                    contents_rows.append((_title(pending), line, page["index"]))
                    pending = ""
                elif not CONTENTS.match(_title(line)) and len(line) < 180:
                    pending = f"{pending} {line}".strip()[:600]
            continue
        for line in lines:
            title = _title(line)
            if len(title) <= 180 and _readable(title):
                titles[_match_key(title)].append((page["index"], {}))
                if HEADING.match(title):
                    headings.append((title, page["index"]))
    # PaddleOCR returns rendered pixmap pixels. Native text blocks use MuPDF's
    # unrotated points. Keep their actual space and reference geometry; the
    # Reader adapter must not consume either as a naked PDF-point coordinate.
    for block in asset.pages.exclude(index__in=contents_pages).values("index", "width", "height", "text_source", "blocks__text", "blocks__bbox"):
        title = _title(block["blocks__text"])
        box = block["blocks__bbox"]
        if title and len(title) <= 180 and isinstance(box, list) and len(box) == 4 and all(type(value) in {int, float} and math.isfinite(value) for value in box):
            source = block["text_source"]
            if source not in {"embedded", "ocr"}:
                continue  # Hybrid provenance cannot prove one coordinate space.
            locator = {"bbox": box, "coordinate_unit": "pixels" if source == "ocr" else "pdf_points",
                       "coordinate_space": "ocr_rendered_page" if source == "ocr" else "pymupdf_unrotated",
                       "source_width": block["width"], "source_height": block["height"],
                       "page_geometry": geometry.get(block["index"], {})}
            titles[_match_key(title)].append((block["index"], locator))

    native_by_target = defaultdict(list)
    for node in nodes:
        native_by_target[(_match_key(node["title"]), node["pdf_page"])].append(node)
    matched_native, printed_stack = set(), []
    last_page = 0
    for ordinal, (title, label, contents_page) in enumerate(contents_rows):
        title_matches = titles.get(_match_key(title), [])
        label_pages = labels.get(label.casefold(), [])
        matches = [hit for hit in title_matches if (not label_pages or hit[0] in label_pages) and hit[0] >= last_page]
        target_pages = sorted({hit[0] for hit in matches})
        if len(target_pages) == 1:
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
        if counterpart:
            matched_native.add(counterpart["id"])
            printed_stack.append((level, counterpart["id"]))
            last_page = page
            continue
        node = _node(asset, ordinal, title, page, source="printed_contents", label=label,
                     level=level, locator=locator, contents_page=contents_page)
        node["parent_id"] = parent
        node["calibration_status"] = status
        nodes.append(node)
        printed_stack.append((level, node["id"]))
        if page:
            last_page = page
        if status == "needs_review":
            diagnostics.append({"code": "contents_target_uncertain", "node_id": node["id"], "message": "目录页与正文落点需要人工核对。"})
    existing_targets = {(_match_key(node["title"]), node["pdf_page"]) for node in nodes}
    generated, had_formal = [], bool(nodes)
    for ordinal, (title, page) in enumerate(headings):
        if (_match_key(title), page) not in existing_targets:
            locators = [hit[1] for hit in titles[_match_key(title)] if hit[0] == page and hit[1]]
            node = _node(asset, ordinal, title, page, source="generated_heading", level=_level(title),
                         locator=locators[0] if locators else {})
            node["calibration_status"] = "needs_review" if had_formal else "generated"
            generated.append(node)
            existing_targets.add((_match_key(title), page))
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
        parent = Asset.objects.filter(pk=asset.source_asset_id, edition=asset.edition, sha256=asset.sha256).first()
        if parent and (parent.is_current or pending_replacement_source(parent)):
            return
    raise OutlineConflict("文件已更换；旧目录和原文仍保留，请选择当前文件。")


def validate_nodes(asset, nodes):
    if not isinstance(nodes, list) or len(nodes) > 20000:
        raise ValueError("目录必须为节点列表，最多 20000 项。")
    active = asset.outline_revisions.filter(is_active=True).first()
    latest = asset.outline_revisions.first()
    prior_nodes = {node["id"]: node for revision in (active, latest) if revision for node in revision.nodes}
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
        point = raw.get("pdf_position") or []
        if not isinstance(point, list) or len(point) not in {0, 2} or any(type(value) not in {int, float} or not math.isfinite(value) or value < 0 for value in point):
            raise ValueError("页内落点必须为非负 PDF 点坐标 [x, y]。")
        prior = prior_nodes.get(identifier, {})
        same_page = prior.get("pdf_page") == page
        geometry = prior.get("page_geometry", {}) if same_page else {}
        relative = raw.get("normalized_position") or []
        if not isinstance(relative, list) or len(relative) not in {0, 2} or any(type(value) not in {int, float} or not math.isfinite(value) or not 0 <= value <= 1 for value in relative):
            raise ValueError("相对落点必须为显示页面内的比例坐标 [x, y]，各值在 0—1 之间。")
        if relative:
            point = []
        if point and page:
            if not geometry:
                raise ValueError("此节点没有可验证的 PDF 坐标空间，请使用 normalized_position 比例落点。")
            if point[0] > geometry["pdf_width"] or point[1] > geometry["pdf_height"]:
                raise ValueError("页内落点超出所选 PDF 页面的范围。")
        level = levels.get(parent, 0) + 1
        if level > 32:
            raise ValueError("目录层级最多 32 层。")
        contents_page = raw.get("contents_page")
        if contents_page is not None and (type(contents_page) is not int or not 1 <= contents_page <= asset.page_count):
            raise ValueError("目录原页超出 PDF 页数范围。")
        source_locator = prior.get("source_locator", {}) if same_page and not relative and not point else {}
        coordinate_space = prior.get("coordinate_space", "") if point and point == prior.get("pdf_position") and same_page else "displayed_pdf_crop" if point else ""
        result.append({"id": identifier, "parent_id": parent, "position": position, "level": level,
                       "title": title, "pdf_page": page, "printed_label": _title(raw.get("printed_label"))[:40],
                       "pdf_position": point, "coordinate_unit": "pdf_points" if point else "", "source": "manual",
                       "coordinate_space": coordinate_space, "page_geometry": geometry,
                       "normalized_position": relative, "source_locator": source_locator,
                       "precision": "position" if point or relative or source_locator else "page",
                       "calibration_status": "confirmed" if page else "needs_review", "contents_page": contents_page})
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
            "node_count": len(revision.nodes)}
    if nodes:
        data["nodes"] = revision.nodes
    return data


def outline_state(asset, *, history_page=1):
    revisions = asset.outline_revisions.all()
    latest = revisions.first()
    count = revisions.count()
    history_page = min(max(1, history_page), max(1, (count + 49) // 50))
    start = (history_page - 1) * 50
    return {"asset_id": str(asset.pk), "expected_revision": latest.revision if latest else 0,
            "active": revision_payload(revisions.filter(is_active=True).first()),
            "latest": revision_payload(latest),
            "history": [revision_payload(row, nodes=False) for row in revisions[start:start + 50]],
            "history_page": history_page, "history_count": count,
            "history_next_page": history_page + 1 if start + 50 < count else None,
            "jobs": [{"id": str(job.pk), "status": job.status, "progress": job.progress,
                      "error": job.error_message, "updated_at": job.updated_at, "result_revision_id": job.stats.get("result_revision_id")}
                     for job in ProcessingJob.objects.filter(asset=asset, job_type="text_extraction", stats__operation="outline_rebuild").order_by("-created_at")[:10]]}


def _assert_expected(asset, expected_revision):
    latest = asset.outline_revisions.first()
    if type(expected_revision) is not int or expected_revision != (latest.revision if latest else 0):
        raise OutlineConflict("目录已有新修订；请保留当前输入，读取最新差异后再保存。")


def _new_revision(asset, *, nodes, diagnostics=(), actor=None, origin="automatic", restored_from=None, document_revision=None):
    next_number = (asset.outline_revisions.aggregate(value=Max("revision"))["value"] or 0) + 1
    return DocumentOutlineRevision.objects.create(
        asset=asset, revision=next_number, source_checksum=asset.sha256,
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
def edit_outline(asset_id, *, nodes, expected_revision, actor, request_id=None):
    asset = Asset.objects.select_for_update().get(pk=asset_id)
    identity, fingerprint, replay = _write_receipt(asset, actor=actor, action="outline.saved", request_id=request_id,
        payload={"nodes": nodes, "expected_revision": expected_revision})
    if replay:
        return replay
    _source_current(asset)
    _assert_expected(asset, expected_revision)
    revision = _new_revision(asset, nodes=validate_nodes(asset, nodes), actor=actor, origin="manual")
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
    if any(not node.get("pdf_page") for node in revision.nodes):
        raise ValueError("仍有目录项缺少物理页落点，请先逐项校准。")
    # Adoption changes the edit precondition too. Otherwise two windows can
    # both adopt different candidates with the same expected_revision value.
    revision = _new_revision(asset, nodes=revision.nodes, diagnostics=revision.diagnostics,
                             actor=actor, origin="restored" if restore else "adopted", restored_from=revision)
    previous = asset.outline_revisions.filter(is_active=True).first()
    asset.outline_revisions.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
    revision.is_active, revision.reviewed = True, True
    revision.save(update_fields=["is_active", "reviewed", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=action, object_type="Asset", object_id=str(asset.pk), request_id=identity,
                              before={"revision_id": str(previous.pk) if previous else None}, after={"revision_id": str(revision.pk), "fingerprint": fingerprint})
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
        # Native bookmarks and explicitly adopted navigation are readable PDF
        # metadata. Automatically generated OCR/contents titles still require
        # the exact formal text revision or a human adoption decision.
        visible = revision.nodes if fulltext_ready or revision.reviewed else [node for node in revision.nodes if node["source"] == "pdf_bookmark"]
        identifiers = {node["id"] for node in visible}
        visible = [{**node, "parent_id": node["parent_id"] if node["parent_id"] in identifiers else None} for node in visible]
        return [{**node, "index": node["pdf_page"], "file_page_index": node["pdf_page"], "chapter_title": node["title"],
                 "outline_revision_id": str(revision.pk)} for node in visible if node.get("pdf_page")]
    return [{"id": str(page.pk), "parent_id": None, "position": position, "level": 1,
             "index": page.index, "file_page_index": page.index, "pdf_page": page.index,
             "chapter_title": page.chapter_title, "title": page.chapter_title, "printed_label": page.printed_label,
             "source": "legacy_page_heading", "calibration_status": "unverified", "pdf_position": [], "coordinate_unit": "", "coordinate_space": "", "precision": "page"}
            for position, page in enumerate(asset.pages.exclude(chapter_title="").order_by("index"))]


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
        if not automatic and existing.stats.get("source_sha256") != asset.sha256:
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
        ProcessingJob.objects.filter(pk=job_id, task_id=task_id).update(status="failed", error_code="queue_unavailable", error_message="目录任务未进入队列，请重试。", finished_at=timezone.now())
        return False


@transaction.atomic
def outline_job_action(job_id, *, action, actor):
    # Match extraction's Asset → Job lock order when cancellation races commit.
    target = ProcessingJob.objects.get(pk=job_id, job_type="text_extraction", stats__operation="outline_rebuild")
    asset = Asset.objects.select_for_update().get(pk=target.asset_id)
    job = ProcessingJob.objects.select_for_update().get(pk=target.pk)
    before = {"status": job.status, "error_code": job.error_code, "error_message": job.error_message, "attempt": job.attempt}
    if action == "cancel":
        if job.status not in {"pending", "running", "failed", "canceled"}:
            raise OutlineConflict("目录已完成，无需取消。")
        job.status, job.task_id, job.finished_at = "canceled", "", timezone.now()
    elif action == "retry":
        if job.status in {"pending", "running"}:
            return job
        if job.status != "failed":
            raise OutlineConflict("只有失败的目录任务可以重试。")
        _source_current(asset)
        current_document = asset.document_revisions.filter(is_active=True).first()
        if asset.sha256 != job.stats.get("source_sha256") or str(current_document.pk if current_document else "") != str(job.stats.get("document_revision_id") or ""):
            raise OutlineConflict("任务绑定的正文已变化，请新建目录重建任务，原失败记录保留。")
        job.status, job.task_id, job.attempt = "pending", str(uuid4()), 0
        job.error_code, job.error_message, job.finished_at = "", "", None
    else:
        raise ValueError("请选择 retry 或 cancel。")
    job.save(update_fields=["status", "task_id", "attempt", "error_code", "error_message", "finished_at", "updated_at"])
    AuditEvent.objects.create(actor=actor, action=f"outline.task.{action}", object_type="ProcessingJob", object_id=str(job.pk), before=before, after={"status": job.status})
    if action == "retry":
        transaction.on_commit(lambda: dispatch_outline_job(str(job.pk), job.task_id))
    return job


def run_outline_job(job_id, *, task_id):
    from ingestion.services.processing import _claim_processing_job
    from ingestion.services.files import materialize_field_file

    job, claimed = _claim_processing_job(job_id, task_id=task_id, progress_floor=5)
    if not claimed:
        return job
    cleanup = None
    def progress(stage, completed, total):
        updated = ProcessingJob.objects.filter(pk=job.pk, task_id=task_id, status="running").update(
            heartbeat_at=timezone.now(), progress=min(90, 5 + round(80 * completed / max(1, total))),
            stats={**job.stats, "stage": stage, "completed_pages": completed, "total_pages": total}, updated_at=timezone.now())
        if not updated:
            raise OutlineJobInterrupted()
    try:
        asset = job.asset
        _source_current(asset)
        path, cleanup = materialize_field_file(asset.file)
        nodes, diagnostics = extract_outline(asset, path, progress=progress)
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
            if nodes and not any(node["calibration_status"] == "needs_review" for node in nodes) and not (active and active.reviewed):
                asset.outline_revisions.filter(is_active=True).update(is_active=False, updated_at=timezone.now())
                revision.is_active = True
                revision.save(update_fields=["is_active", "updated_at"])
            current.status, current.progress, current.finished_at = "succeeded", 100, timezone.now()
            current.stats = {**current.stats, "result_revision_id": str(revision.pk), "node_count": len(nodes), "needs_review": bool(diagnostics), "stage": "complete"}
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
