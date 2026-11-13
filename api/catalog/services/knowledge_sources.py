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

STRUCTURE_VERSION = "stl-raw-structure-v2"
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


def _running_headers(nodes):
    """Only repeated generated titles at validated top-margin positions.

    Human corrections and printed TOC entries are never discarded by this rule.
    Raw page text remains untouched, including the ignored header occurrences.
    """
    from collections import defaultdict
    repeated = defaultdict(list)
    for row in nodes:
        location = row.get("source_locator") or {}
        box = location.get("normalized_bbox") or []
        if (row.get("source") == "generated_heading" and location.get("geometry_status") == "validated"
                and len(box) == 4 and all(isinstance(v, (int,float)) for v in box) and 0 <= box[1] < box[3] <= .16):
            key = re.sub(r"[\s|｜—-]", "", row.get("title", ""))
            key = re.sub(r"(?<=部分)一(?=第)", "", key)
            repeated[key].append(row)
    return {row["id"] for group in repeated.values() if len({r.get("pdf_page") for r in group}) >= 3 for row in group}


def _outline_heading(page_text, raw):
    title = raw.get("title", "")
    label = str(raw.get("printed_label") or "")
    # TOC leader dots/page labels are not part of the body title.
    clean = re.sub(r"[.·…]+\s*" + re.escape(label) + r"\s*$", "", title).strip() if label else title
    observed = (raw.get("source_locator") or {}).get("observed_title", "") if raw.get("calibration_status") == "matched" else ""
    # Prefer the longest exact verified spelling, e.g. a full section heading
    # over a truncated last line from the printed TOC. No fuzzy raw offsets.
    for candidate in sorted({clean, observed} - {""}, key=len, reverse=True):
        offset = _locate_title(page_text, candidate)
        if offset is not None:
            return candidate, offset
    return title, None


def current_structure(revision, *, prepare=False):
    outline = DocumentOutlineRevision.objects.filter(document_revision=revision, is_active=True).first()
    result = revision.structures.filter(outline_revision=outline).order_by("-created_at").first()
    return result or (build_structure(revision) if prepare else None)


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
    outline_nodes = outline.nodes if outline else []
    running_headers = _running_headers(outline_nodes)
    for raw in outline_nodes:
        if raw.get("id") in running_headers:
            continue
        if raw.get("source") == "generated_heading" and len(raw.get("title", "")) > 35:
            gaps.append({"outline_id": raw.get("id"), "title": raw.get("title"),
                         "page": raw.get("pdf_page"), "reason": "generated_heading_requires_review"})
            continue
        page = by_page.get(raw.get("pdf_page"))
        title, offset = _outline_heading(page.text, raw) if page else (raw.get("title", ""), None)
        if offset is None:
            gaps.append({"outline_id": raw.get("id"), "title": raw.get("title"),
                         "page": raw.get("pdf_page"), "reason": "heading_text_not_unique"})
            continue
        headings.append({**raw, "title":title, "start": starts[page.page_number] + offset, "level": int(raw.get("level") or 1)})
    headings.sort(key=lambda h: (h["start"], h["level"]))
    coverage = {"page_count": len(pages), "characters": sum(len(p.text) for p in pages),
                "missing_text_pages": [p.page_number for p in pages if not p.text.strip()],
                "unmapped_headings": gaps, "mapped_headings": len(headings),
                "ignored_running_headers": sorted(running_headers),
                "structure_status": "mapped" if headings and not gaps else "needs_structure_review",
                "paragraph_method": "raw_blank_lines_page_bounded",
                "cross_page_paragraphs_inferred": False}
    if not headings:
        coverage["limitations"] = ["缺少已映射章节；按实际页范围读取，不代表已识别整书章节。"]
    structure = DocumentStructure.objects.create(document_revision=revision, outline_revision=outline,
        parser="existing_text_and_outline", parser_version=STRUCTURE_VERSION, input_hash=fingerprint, coverage=coverage)
    ordinal = 0
    pending_nodes, pending_segments = [], []

    def node(kind, start, end, *, title="", parent=None, source=None):
        nonlocal ordinal
        row = DocumentNode(structure=structure, document_revision=revision,
            parent=parent, kind=kind, order=ordinal, title=title, content_hash=digest(full[start:end]), source=source or {})
        ordinal += 1
        pending_nodes.append(row)
        segments = []
        for page in pages:
            base = starts[page.page_number]
            left, right = max(0, start - base), min(len(page.text), end - base)
            if left < right:
                segments.append(DocumentNodeSegment(node=row, page=page, order=len(segments),
                    start=left, end=right, content_hash=digest(page.text[left:right])))
        pending_segments.extend(segments)
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
    # UUIDs exist before insertion, so parent/segment references remain exact.
    # Long OCR books must not issue two database writes for every printed line.
    DocumentNode.objects.bulk_create(pending_nodes, batch_size=1000)
    DocumentNodeSegment.objects.bulk_create(pending_segments, batch_size=1000)
    previous = revision.structures.filter(parser__in=["docling", "docling_outline_remap", "human_correction", "human_outline_remap"]).exclude(outline_revision=outline).order_by("-created_at").first()
    if previous:
        return _retain_parsed_leaves(previous, structure, starts)
    return structure


def _retain_parsed_leaves(previous, baseline, starts):
    """Create a new hierarchy, retaining verified immutable ranges and notes."""
    from catalog.models import DocumentNodeReference
    leaves = list(previous.nodes.exclude(kind__in=["document", "chapter", "section", "part", "preface", "appendix"])
        .filter(children__isnull=True).prefetch_related("segments__page"))
    if not leaves:
        return baseline
    key=digest(["outline-remap-v1",baseline.input_hash,previous.input_hash])
    existing=DocumentStructure.objects.filter(document_revision=baseline.document_revision,input_hash=key).first()
    if existing: return existing
    preserved = {k:v for k,v in previous.coverage.items() if k in {"parse_batches","parser_scope","docling_items",
        "alignment_gaps","ignored_ranges","unmatched_ranges","verified_cross_page_items","paragraph_method"}}
    coverage={**baseline.coverage,**preserved,"outline_remapped_from":str(previous.pk)}
    if preserved.get("alignment_gaps") or preserved.get("unmatched_ranges"):
        coverage["structure_status"]="needs_structure_review"
    structure=DocumentStructure.objects.create(document_revision=baseline.document_revision,
        outline_revision=baseline.outline_revision,parser="human_outline_remap" if any(n.source.get("human_corrected") for n in leaves) else "docling_outline_remap",parser_version=previous.parser_version,
        input_hash=key,coverage=coverage)
    headings=list(baseline.nodes.exclude(kind="paragraph").prefetch_related("segments__page"))
    def bounds(n):
        segments=list(n.segments.all())
        return (min((starts[s.page.page_number]+s.start for s in segments),default=0),
                max((starts[s.page.page_number]+s.end for s in segments),default=0))
    positions={n.pk:bounds(n) for n in [*headings,*leaves]}
    ordered=sorted([*headings,*leaves],key=lambda n:(positions[n.pk][0],
        0 if n.kind=="document" else 1 if n in headings else 2,n.order))
    order={n.pk:i for i,n in enumerate(ordered)}
    mapping={}
    for old in headings:
        mapping[old.pk]=DocumentNode.objects.create(structure=structure,document_revision=baseline.document_revision,
            parent=mapping.get(old.parent_id),kind=old.kind,order=order[old.pk],title=old.title,
            content_hash=old.content_hash,source=old.source)
    root=next(mapping[n.pk] for n in headings if n.kind=="document")
    for old in leaves:
        start,end=positions[old.pk]
        containers=[n for n in headings if n.kind!="document" and positions[n.pk][0]<=start and end<=positions[n.pk][1]]
        parent=mapping[min(containers,key=lambda n:positions[n.pk][1]-positions[n.pk][0]).pk] if containers else root
        mapping[old.pk]=DocumentNode.objects.create(structure=structure,document_revision=baseline.document_revision,
            parent=parent,kind=old.kind,order=order[old.pk],title=old.title,content_hash=old.content_hash,
            source={**old.source,"retained_from_node":str(old.pk)})
    for old in [*headings,*leaves]:
        DocumentNodeSegment.objects.bulk_create([DocumentNodeSegment(node=mapping[old.pk],page=seg.page,
            order=seg.order,start=seg.start,end=seg.end,content_hash=seg.content_hash) for seg in old.segments.all()])
    for ref in DocumentNodeReference.objects.filter(source_id__in=mapping,target_id__in=mapping):
        DocumentNodeReference.objects.create(source=mapping[ref.source_id],target=mapping[ref.target_id],
            kind=ref.kind,label=ref.label,provenance=ref.provenance)
    return structure


def node_text(node):
    return "\n".join(s.page.text[s.start:s.end] for s in node.segments.select_related("page").all())


@transaction.atomic
def create_anchor(revision, segments):
    if not isinstance(segments, list) or not 1 <= len(segments) <= 100:
        raise ValidationError("证据须含1至100个有序原文片段。")
    DocumentRevision.objects.select_for_update().get(pk=revision.pk)
    page_numbers = [raw.get("page_number") for raw in segments if isinstance(raw, dict)]
    if len(page_numbers) != len(segments) or any(type(n) is not int or n < 1 for n in page_numbers):
        raise ValidationError("证据页码须为1基物理PDF页码。")
    # An index may create thousands of small anchors. Fetch only cited pages;
    # avoid reading the entire book's text/geometry for every chunk.
    pages = {p.page_number: p for p in revision.page_snapshots.filter(page_number__in=page_numbers)}
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
        else:
            # Choose an actual containing node; never infer continuity at a page break.
            structure = revision.structures.order_by("-created_at").first()
            if structure:
                from django.db.models import F
                containing = DocumentNodeSegment.objects.filter(node__structure=structure, page=page,
                    start__lte=start, end__gte=end).annotate(length=F("end")-F("start")).order_by("length", "node__order").select_related("node").first()
                node = containing.node if containing else None
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
    segments = getattr(anchor, "locator_segments", None)
    if segments is None:
        segments = anchor.segments.select_related("page", "node").all()
    for segment in segments:
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


def context(node, actor, *, budget=12000, editorial=False, offset=0, scope="node", focus_range=None, include_references=False):
    require_revision_access(node.document_revision, actor, editorial=editorial)
    if not 1 <= budget <= 60000:
        raise ValidationError("上下文预算须为1至60000字符。")
    if scope not in {"node", "section", "chapter"} or type(offset) is not int or offset < 0:
        raise ValidationError("上下文范围或起点无效。")
    requested = node
    if scope != "node":
        parent = node
        while parent:
            if parent.kind == scope:
                node = parent
                break
            parent = parent.parent
    source_segments = list(node.segments.select_related("page").all())
    text_budget = budget - min(2000, budget // 6) if include_references else budget
    if focus_range:
        position, found = 0, False
        for segment in source_segments:
            if (segment.page.page_number == focus_range["page"] and segment.start <= focus_range["start"] < segment.end):
                offset = max(0, position + focus_range["start"] - segment.start - text_budget // 3)
                found = True
                break
            position += segment.end - segment.start
        if not found:
            raise ValidationError("命中范围不属于所选正文上下文。")
    texts, read, total = [], 0, 0
    for segment in source_segments:
        length = segment.end - segment.start
        begin = max(0, offset - total)
        total += length
        if begin >= length or read >= text_budget:
            continue
        start = segment.start + begin
        end = min(segment.end, start + text_budget - read)
        text = segment.page.text[start:end]
        if digest(segment.page.text) != segment.page.content_hash:
            raise ValidationError("正文快照完整性校验失败。")
        texts.append({"page_number": segment.page.page_number, "printed_label": segment.page.printed_label,
            "node_id": str(node.pk), "start": start, "end": end, "exact": text, "content_hash": digest(text),
            "partial_segment": begin > 0 or end < segment.end})
        read += len(text)
    path, parent = [], node
    while parent:
        if parent.title:
            path.insert(0, parent.title)
        parent = parent.parent
    # Include explicit footnote links from the returned chapter/section ranges.
    # This does not concatenate all footnotes on a physical page into the body.
    from django.db.models import Q
    from catalog.models import DocumentNodeReference
    included = Q(pk__in=[])
    for part in texts:
        included |= Q(source__segments__page__page_number=part["page_number"],source__segments__start__lt=part["end"],source__segments__end__gt=part["start"])
    references = list(DocumentNodeReference.objects.filter(included,source__structure=node.structure,
        target__structure=node.structure).distinct().values("target_id","kind","label")[:100])
    reference_context, reference_read, references_truncated = [], 0, False
    if include_references:
        targets = {row["target_id"] for row in references if row["kind"] == "footnote"}
        for segment in DocumentNodeSegment.objects.filter(node_id__in=targets, node__kind="footnote").select_related("page").order_by("node__order", "order"):
            if digest(segment.page.text) != segment.page.content_hash:
                raise ValidationError("脚注快照完整性校验失败。")
            available = max(0, budget - read - reference_read)
            end = min(segment.end, segment.start + available)
            references_truncated |= end < segment.end
            if end <= segment.start:
                continue
            exact = segment.page.text[segment.start:end]
            reference_context.append({"node_id":str(segment.node_id), "page_number":segment.page.page_number,
                "printed_label":segment.page.printed_label, "start":segment.start,"end":end,
                "exact":exact,"content_hash":digest(exact),"partial_segment":end < segment.end})
            reference_read += len(exact)
    return {"node_id": str(node.pk), "document_revision_id": str(node.document_revision_id), "segments": texts,
            "requested_node_id": str(requested.pk), "chapter_path": path, "scope": node.kind,
            "asset_id": str(node.document_revision.asset_id), "offset_unit": "unicode_code_point",
            "returned_characters": read, "total_characters": total, "complete": offset == 0 and read == total,
            "offset": offset, "next_offset": offset + read if offset + read < total else None,
            "budget": budget, "references": references, "reference_context":reference_context,
            "returned_reference_characters":reference_read, "references_truncated":references_truncated}


@transaction.atomic
def migrate_span(span):
    mapping = KnowledgeLegacyMapping.objects.filter(source_type="evidence_span", source_id=span.pk, target_type="anchor").first()
    if mapping and mapping.target_id:
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
    values = {"target_id": target.pk if target else None, "quality": quality,
        "provenance": {"document_revision_id": str(span.document_revision_id), "content_hash": span.content_hash,
                       "original_status_preserved": True}}
    if mapping:
        for key, value in values.items():
            setattr(mapping, key, value)
        mapping.save()
        return mapping
    return KnowledgeLegacyMapping.objects.create(source_type="evidence_span", source_id=span.pk,
        target_type="anchor", **values)
