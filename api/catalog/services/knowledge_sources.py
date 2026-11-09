"""Versioned source snapshots, logical structure and shared locator v1.

Offsets always address raw RevisionPage.text in Unicode code points. Search
normalization never supplies offsets. Missing layout geometry stays missing.
"""
from hashlib import sha256
import json
import re
from urllib.parse import urlencode

from django.db import transaction
from django.http import Http404
from rest_framework.exceptions import PermissionDenied, ValidationError

from catalog.models import (
    Asset, CatalogPublicationRevision, DocumentRevision, DocumentOutlineRevision,
    DocumentStructure, DocumentNode, DocumentNodeSegment, EvidenceAnchor,
    EvidenceSegment, KnowledgeLegacyMapping, Page, RevisionPage,
)
from catalog.services.page_geometry import validated_geometry, locator_geometry
from catalog.services.publication_eligibility import public_editions
from common.capabilities import Capability, has_capability

STRUCTURE_VERSION = "stl-raw-structure-v1"
LOCATOR_VERSION = "stl-locator-v1"


def requested_revision(request, asset_id):
    """Resolve an explicit historical source without relaxing active filters elsewhere."""
    from django.shortcuts import get_object_or_404
    from rest_framework import serializers
    key = serializers.UUIDField().run_validation(request.query_params.get("revision"))
    revision = get_object_or_404(DocumentRevision.objects.select_related("asset__edition__work"), pk=key, asset_id=asset_id)
    require_revision_access(revision, request.user, editorial=request.query_params.get("preview") == "1")
    if revision.source_checksum != revision.asset.sha256:
        raise ValidationError("此修订的文件摘要与保留来源不一致，暂不能打开PDF。")
    return revision


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(value.encode("utf-8")).hexdigest()


def require_revision_access(revision, actor, *, editorial=False):
    if not actor or not actor.is_authenticated or not actor.is_active:
        raise PermissionDenied("请登录后查看原文。")
    if editorial and has_capability(actor, Capability.VIEW_EVIDENCE):
        return revision
    asset = revision.asset
    if not public_editions(require_fulltext=True).filter(pk=asset.edition_id).exists():
        raise Http404("来源尚未公开或已撤回。")
    # A retained draft is not a historical publication. Check that this exact
    # asset AND interpretation were actually activated before permitting it.
    if not CatalogPublicationRevision.objects.filter(
        edition_id=asset.edition_id, reader_asset=asset, document_revision=revision,
        status__in=["active", "superseded"], fulltext_ready=True,
    ).exists():
        raise Http404("该正文修订未曾公开。")
    if asset.status != Asset.Status.READY:
        raise Http404("来源文件当前不可用。")
    if asset.access_status in {"private", "restricted"} and not has_capability(actor, Capability.VIEW_EVIDENCE):
        raise PermissionDenied("当前账户不能查看此来源。")
    return revision


@transaction.atomic
def snapshot_revision(revision):
    revision = DocumentRevision.objects.select_for_update().select_related("asset").get(pk=revision.pk)
    existing = list(revision.page_snapshots.all())
    if existing:
        return existing
    from catalog.services.document_intelligence import document_text_checksum
    if not revision.is_active or document_text_checksum(revision.asset) != revision.text_checksum:
        raise ValidationError("此历史修订没有可验证的完整正文快照，不能用当前页面重建历史。")
    pages = list(Page.objects.filter(asset=revision.asset).order_by("index").prefetch_related("blocks"))
    if not pages:
        raise ValidationError("文献尚无可读取的页面。")
    rows = [RevisionPage(
        document_revision=revision, page_number=p.index, printed_label=p.printed_label,
        text=p.text, content_hash=digest(p.text), text_source=p.text_source,
        geometry=validated_geometry(p.geometry), blocks=[{
            "id": str(b.pk), "kind": b.block_type, "text": b.text,
            "bbox": b.bbox, "order": b.order,
        } for b in p.blocks.all()],
    ) for p in pages]
    RevisionPage.objects.bulk_create(rows)
    return rows


def _locate_title(text, title):
    # Compare whitespace-insensitively, but map each match back to RAW indices.
    positions = [i for i, c in enumerate(text) if not c.isspace()]
    compact = "".join(text[i] for i in positions)
    needle = "".join(title.split())
    start = compact.find(needle) if needle else -1
    if start < 0 or compact.find(needle, start + 1) >= 0:
        return None
    return positions[start]


def _heading_kind(title, level):
    if re.match(r"^(前言|序言|序|引言|preface|foreword|introduction)", title, re.I):
        return "preface"
    if re.match(r"^(附录|appendix)", title, re.I):
        return "appendix"
    if re.match(r"^(参考文献|bibliography|references)", title, re.I):
        return "references"
    if re.match(r"^(第.+[部编篇]|part\s)", title, re.I):
        return "part"
    return "chapter" if level == 1 else "section"


@transaction.atomic
def build_structure(revision):
    revision = DocumentRevision.objects.select_for_update().get(pk=revision.pk)
    pages = snapshot_revision(revision)
    outline = DocumentOutlineRevision.objects.filter(document_revision=revision, is_active=True).first()
    fingerprint = digest([STRUCTURE_VERSION, [(p.page_number, p.content_hash) for p in pages],
                          str(outline.pk) if outline else None, outline.nodes if outline else []])
    existing = DocumentStructure.objects.filter(document_revision=revision, input_hash=fingerprint).first()
    if existing:
        return existing
    starts, full_parts, cursor = {}, [], 0
    for page in pages:
        starts[page.page_number] = cursor
        full_parts.append(page.text)
        cursor += len(page.text) + 1
    full = "\n".join(full_parts)
    by_page = {p.page_number: p for p in pages}
    headings, gaps = [], []
    for raw in (outline.nodes if outline else []):
        page = by_page.get(raw.get("pdf_page"))
        offset = _locate_title(page.text, raw.get("title", "")) if page else None
        if offset is None:
            gaps.append({"outline_id": raw.get("id"), "title": raw.get("title"),
                         "page": raw.get("pdf_page"), "reason": "heading_text_not_unique"})
            continue
        headings.append({**raw, "start": starts[page.page_number] + offset, "level": int(raw.get("level") or 1)})
    headings.sort(key=lambda h: (h["start"], h["level"]))
    coverage = {"page_count": len(pages), "characters": sum(len(p.text) for p in pages),
                "missing_text_pages": [p.page_number for p in pages if not p.text.strip()],
                "unmapped_headings": gaps, "mapped_headings": len(headings),
                "structure_status": "mapped" if headings and not gaps else "needs_structure_review",
                "paragraph_method": "raw_blank_lines_page_bounded",
                "cross_page_paragraphs_inferred": False}
    structure = DocumentStructure.objects.create(document_revision=revision, outline_revision=outline,
        parser="existing_text_and_outline", parser_version=STRUCTURE_VERSION, input_hash=fingerprint, coverage=coverage)
    ordinal = 0

    def node(kind, start, end, *, title="", parent=None, source=None):
        nonlocal ordinal
        row = DocumentNode.objects.create(structure=structure, document_revision=revision,
            parent=parent, kind=kind, order=ordinal, title=title, content_hash=digest(full[start:end]), source=source or {})
        ordinal += 1
        segments = []
        for page in pages:
            base = starts[page.page_number]
            left, right = max(0, start - base), min(len(page.text), end - base)
            if left < right:
                segments.append(DocumentNodeSegment(node=row, page=page, order=len(segments),
                    start=left, end=right, content_hash=digest(page.text[left:right])))
        DocumentNodeSegment.objects.bulk_create(segments)
        return row

    root = node("document", 0, len(full), title=revision.asset.edition.work.title)
    chapter_ranges, stack = [], []
    for i, heading in enumerate(headings):
        end = next((h["start"] for h in headings[i+1:] if h["level"] <= heading["level"]), len(full))
        while stack and stack[-1][0] >= heading["level"]:
            stack.pop()
        parent = stack[-1][1] if stack else root
        row = node(_heading_kind(heading["title"], heading["level"]), heading["start"], end,
                   title=heading["title"], parent=parent, source={"outline_id": heading["id"], "precision": "verified_text"})
        stack.append((heading["level"], row))
        chapter_ranges.append((heading["start"], end, row))
    for page in pages:
        base = starts[page.page_number]
        # Page-bounded paragraphs explicitly do not assert continuity across a
        # page break. Docling provenance can supply that continuity separately.
        for match in re.finditer(r"\S[\s\S]*?(?=\n\s*\n|\Z)", page.text):
            start, end = base + match.start(), base + match.end()
            parent = next((r for a, b, r in reversed(chapter_ranges) if a <= start and end <= b), root)
            node("paragraph", start, end, parent=parent, source={"method": "raw_blank_lines", "continuity": "page_bounded"})
    return structure


def node_text(node):
    return "\n".join(s.page.text[s.start:s.end] for s in node.segments.select_related("page").all())


@transaction.atomic
def create_anchor(revision, segments):
    if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
        raise ValidationError("证据须含1至100个有序原文片段。")
    DocumentRevision.objects.select_for_update().get(pk=revision.pk)
    pages = {p.page_number: p for p in revision.page_snapshots.all()}
    checked, previous = [], None
    for raw in segments:
        page = pages.get(raw.get("page_number"))
        start, end = raw.get("start"), raw.get("end")
        if not page or type(start) is not int or type(end) is not int or not 0 <= start < end <= len(page.text):
            raise ValidationError("证据范围不属于指定修订的原始页面文本。")
        if previous and (page.page_number, start) < previous:
            raise ValidationError("证据片段必须按原文顺序排列且不能重叠。")
        previous = (page.page_number, end)
        exact = page.text[start:end]
        if "exact" in raw and raw["exact"] != exact:
            raise ValidationError("候选引文与指定修订原文不一致。")
        node = None
        if raw.get("node_id"):
            node = DocumentNode.objects.filter(pk=raw["node_id"], document_revision=revision,
                segments__page=page, segments__start__lte=start, segments__end__gte=end).first()
            if not node:
                raise ValidationError("片段不在所声明的正文节点内。")
        geometry = {}
        # Never trust geometry supplied by a model/client. Use only exact stored
        # block matches with validated extraction coordinates.
        blocks = [b for b in page.blocks if b.get("text") == exact]
        if len(blocks) == 1 and page.text.count(exact) == 1:
            located = locator_geometry(blocks[0].get("bbox"), page.geometry)
            if located.get("normalized_bbox"):
                geometry = {**page.geometry, **located, "bbox": blocks[0]["bbox"], "basis": "exact_text_block"}
        checked.append((page, start, end, node, geometry))
    fingerprint = digest([str(revision.pk), [(str(p.pk), a, b, str(n.pk) if n else None) for p, a, b, n, _ in checked]])
    anchor = EvidenceAnchor.objects.filter(fingerprint=fingerprint).first()
    if anchor:
        return anchor
    anchor = EvidenceAnchor.objects.create(document_revision=revision, fingerprint=fingerprint,
        content_hash=digest([p.text[a:b] for p, a, b, _, _ in checked]))
    EvidenceSegment.objects.bulk_create([EvidenceSegment(anchor=anchor, page=p, node=n, order=i,
        start=a, end=b, content_hash=digest(p.text[a:b]), geometry=g,
        precision="geometry" if g else "text_range") for i, (p, a, b, n, g) in enumerate(checked)])
    return anchor


def locator(anchor, actor, *, editorial=False):
    require_revision_access(anchor.document_revision, actor, editorial=editorial)
    return locator_payload(anchor, editorial=editorial)


def locator_payload(anchor, *, editorial=False):
    """Internal serializer. Caller must establish source access before calling."""
    revision = anchor.document_revision
    asset = revision.asset
    result = []
    path = []
    for segment in anchor.segments.select_related("page", "node").all():
        page = segment.page
        exact = page.text[segment.start:segment.end]
        if page.document_revision_id != revision.pk or digest(exact) != segment.content_hash or digest(page.text) != page.content_hash:
            raise ValidationError("历史证据完整性校验失败。")
        if segment.node and not path:
            parent = segment.node
            while parent:
                if parent.title:
                    path.insert(0, parent.title)
                parent = parent.parent
        result.append({"order": segment.order, "edition_id": str(asset.edition_id), "asset_id": str(asset.pk),
            "document_revision_id": str(revision.pk), "node_id": str(segment.node_id) if segment.node_id else None,
            "page_number": page.page_number, "printed_label": page.printed_label,
            "start": segment.start, "end": segment.end, "offset_unit": "unicode_code_point",
            "exact": exact, "prefix": page.text[max(0, segment.start-64):segment.start],
            "suffix": page.text[segment.end:segment.end+64], "content_hash": segment.content_hash,
            "geometry": segment.geometry, "precision": segment.precision, "validation": "verified_text"})
    if not result:
        raise ValidationError("证据没有可读取片段。")
    return {"schema_version": LOCATOR_VERSION, "source_type": "original_text", "anchor_id": str(anchor.pk),
        "work_id": str(asset.edition.work_id), "edition_id": str(asset.edition_id), "asset_id": str(asset.pk),
        "document_revision_id": str(revision.pk), "content_hash": anchor.content_hash,
        "node_id": result[0]["node_id"], "chapter_path": path, "segments": result,
        "exact": "\n".join(s["exact"] for s in result), "offset_unit": "unicode_code_point",
        "precision": "geometry" if all(s["geometry"] for s in result) else "text_range",
        "reader_url": f"/reader/{asset.pk}?" + urlencode({"page": result[0]["page_number"], "anchor": anchor.pk,
            "revision": revision.pk, **({"preview": "1"} if editorial else {})})}


def context(node, actor, *, budget=12000, editorial=False):
    require_revision_access(node.document_revision, actor, editorial=editorial)
    if not 1 <= budget <= 60000:
        raise ValidationError("上下文预算须为1至60000字符。")
    texts, read, total = [], 0, 0
    for segment in node.segments.select_related("page").all():
        text = segment.page.text[segment.start:segment.end]
        total += len(text)
        if read + len(text) <= budget:
            texts.append({"page_number": segment.page.page_number, "start": segment.start, "end": segment.end,
                          "exact": text, "content_hash": segment.content_hash})
            read += len(text)
        else:
            # A complete segment is omitted visibly, never silently clipped.
            break
    total = sum(s.end-s.start for s in node.segments.all())
    return {"node_id": str(node.pk), "document_revision_id": str(node.document_revision_id), "segments": texts,
            "returned_characters": read, "total_characters": total, "complete": read == total,
            "budget": budget, "references": list(node.outgoing_references.values("target_id", "kind", "label"))}


@transaction.atomic
def migrate_span(span):
    mapping = KnowledgeLegacyMapping.objects.filter(source_type="evidence_span", source_id=span.pk, target_type="anchor").first()
    if mapping:
        return mapping
    page = RevisionPage.objects.filter(document_revision=span.document_revision, page_number=span.page_number).first()
    target, quality = None, "historical_text_unrecoverable"
    if page:
        start, end = span.start_offset, span.end_offset
        if page.text[start:end] == span.original_text and start < end:
            target = create_anchor(span.document_revision, [{"page_number": page.page_number,
                "start": start, "end": end, "exact": span.original_text}])
            quality = "verified_text"
        else:
            quality = "legacy_offsets_not_raw_text"
    return KnowledgeLegacyMapping.objects.create(source_type="evidence_span", source_id=span.pk,
        target_type="anchor", target_id=target.pk if target else None, quality=quality,
        provenance={"document_revision_id": str(span.document_revision_id), "content_hash": span.content_hash,
                    "original_status_preserved": True})
