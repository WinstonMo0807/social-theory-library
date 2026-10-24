"""Typed issue blocks reference canonical sources; they do not copy source text."""
from copy import deepcopy
from uuid import uuid4
from urllib.parse import urlsplit

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError

from catalog.models import KnowledgeNode, Person, ReadingPath, TheoryTimelineEvent
from catalog.services import shared_curation

REFERENCE_TYPES = {"evidence": "span", "work": "work", "person": "person", "concept": "node", "node": "node",
                   "timeline": "timeline", "reading_path": "reading_path"}


def _text(value, limit=6000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValidationError("内容必须为长度适当的文字。")
    return value.strip()


def normalize_text_format(row, block):
    """Bounded formatting of editorial prose, never of resolved source text.

    Offsets follow DOM UTF-16 selection. Trimming is accounted for explicitly
    so a saved mark cannot drift onto a different word or split an emoji.
    """
    if "heading_level" in row:
        level = row["heading_level"]
        if type(level) is not int or level not in {1, 2, 3} or not (block["type"] == "heading" or block["type"] == "analysis" and block.get("style") == "heading"):
            raise ValidationError({"body_blocks": "只有章节标题可以设置1至3级层次。"})
        block = {**block, "heading_level": level}
    if "text_style" not in row and "text_marks" not in row:
        return block
    style = row.get("text_style", "paragraph")
    if style not in ("paragraph", "unordered", "ordered", "quote"):
        raise ValidationError({"body_blocks": "导读段落格式无效。"})
    original = row.get("text", "")
    if not isinstance(original, str):
        raise ValidationError({"body_blocks": "导读文字格式无效。"})
    offsets, position = {0}, 0
    for character in original:
        position += 2 if ord(character) > 0xFFFF else 1
        offsets.add(position)
    trim = sum(2 if ord(character) > 0xFFFF else 1 for character in original[:len(original) - len(original.lstrip())])
    length = sum(2 if ord(character) > 0xFFFF else 1 for character in block["text"])
    values = row.get("text_marks", [])
    if not isinstance(values, list) or len(values) > 200:
        raise ValidationError({"body_blocks": "每段最多保留200处文字格式。"})
    marks, seen = [], set()
    for value in values:
        if not isinstance(value, dict) or set(value) - {"start", "end", "kind", "href"}:
            raise ValidationError({"body_blocks": "文字格式标记无效。"})
        start, end, kind = value.get("start"), value.get("end"), value.get("kind")
        if type(start) is not int or type(end) is not int or start not in offsets or end not in offsets or start >= end or kind not in ("strong", "em", "underline", "link"):
            raise ValidationError({"body_blocks": "请重新选择要设置格式的导读文字。"})
        href = value.get("href", "")
        if kind == "link":
            if not isinstance(href, str) or len(href) > 1500 or "\\" in href or any(ord(c) < 32 for c in href):
                raise ValidationError({"body_blocks": "导读链接地址无效。"})
            try:
                parsed = urlsplit(href)
            except ValueError:
                raise ValidationError({"body_blocks": "导读链接地址无效。"})
            if not ((parsed.scheme in {"http", "https"} and parsed.netloc) or (href.startswith("/") and not href.startswith("//"))):
                raise ValidationError({"body_blocks": "导读链接须为本站路径或完整http/https地址。"})
        start, end = max(0, start - trim), min(length, end - trim)
        if start >= end:
            continue
        mark = {"start": start, "end": end, "kind": kind, **({"href": href} if kind == "link" else {})}
        identity = (start, end, kind, href if kind == "link" else "")
        if identity not in seen:
            if kind == "link" and any(old["kind"] == "link" and start < old["end"] and end > old["start"] for old in marks):
                raise ValidationError({"body_blocks": "同一段文字不能重叠引用多个链接。"})
            marks.append(mark)
            seen.add(identity)
    return {**block, "text_style": style, "text_marks": marks}


def resolve_target(raw, *, public=False):
    if not isinstance(raw, dict) or set(raw) - {"type", "id", "edition_id", "document_revision_id"}:
        raise ValidationError("引用只能包含真实来源标识。")
    kind, key = raw.get("type"), shared_curation.identifier(raw.get("id"))
    if not isinstance(kind, str):
        raise ValidationError("引用类型必须是文字标识。")
    if kind in {"work", "edition", "node", "span"}:
        from catalog.services.content_placements import _source

        target, source = _source(raw, public=public)
        if public and not source["public_eligible"]:
            raise Http404
        if public:
            source.pop("edit_url", None)
        return target, source
    models = {"person": Person, "timeline": TheoryTimelineEvent, "reading_path": ReadingPath}
    if kind not in models:
        raise ValidationError("不支持的引用类型。")
    if set(raw) != {"type", "id"}:
        raise ValidationError("此对象仅接受类型与身份标识。")
    rows = models[kind].objects.all()
    if public:
        if kind == "person":
            from catalog.services.scoped_search import public_scholar_queryset
            rows = rows.filter(pk__in=public_scholar_queryset().values("person_id"))
        else:
            rows = rows.filter(**({"review_status": "approved"} if kind == "timeline" else {"status": "published"}))
    row = get_object_or_404(rows, pk=key)
    name = row.preferred_name if kind == "person" else row.title
    target = {"type": kind, "id": str(key)}
    source = {**target, "title": name}
    if kind == "person":
        from catalog.services.public_scholars import _base, _formal_profile
        from catalog.serializers import PersonCompactSerializer
        profile = get_object_or_404(_base(), person_id=key) if public else _base().filter(person_id=key).first()
        if profile:
            profile = _formal_profile(profile, profile.public_snapshot or {})
            source.update(title=profile.person.preferred_name, summary=profile.short_description,
                          href=f"/scholars/{profile.slug}", image_url=PersonCompactSerializer().get_portrait(profile.person))
    if kind == "reading_path" and public:
        from catalog.models import EditorialRevision
        revision = EditorialRevision.objects.filter(target_type="reading_path", target_id=key, status="published",
            materialized_preview__status="published").order_by("-revision").first()
        raw = revision.materialized_preview if revision else {}
        source.update(title=raw.get("title", row.title), href=f"/theories/reading-paths/{raw.get('slug', row.slug)}")
    if kind == "timeline":
        source.update(start_year=row.start_year, end_year=row.end_year, event_type=row.event_type, summary=row.description, href=f"/theories/timeline?focus={row.pk}")
    return target, source


def normalize_typed_block(row, *, retained=None):
    kind = row.get("type")
    if not isinstance(kind, str):
        raise ValidationError({"body_blocks": "文章区块类型无效。"})
    block = {"id": str(shared_curation.identifier(row["id"])) if row.get("id") else str(uuid4()),
             "type": kind, "text": _text(row.get("text", ""))}
    # Only identities already saved in this exact block may survive source
    # removal. Their text stays unavailable; publication still rechecks every
    # reference. A client cannot introduce an arbitrary missing identity.
    old_refs = block_references(retained) if retained and retained.get("id") == block["id"] and retained.get("type") == kind else []
    def resolve(reference):
        try:
            return resolve_target(reference)[0]
        except (Http404, ValidationError):
            if reference in old_refs:
                return deepcopy(reference)
            raise
    if kind in REFERENCE_TYPES:
        raw = row.get("target")
        if not isinstance(raw, dict) or raw.get("type") != REFERENCE_TYPES[kind]:
            raise ValidationError({"body_blocks": "区块类型与引用身份不一致。"})
        block["target"] = resolve(raw)
        if kind == "concept" and raw not in old_refs and not KnowledgeNode.objects.filter(pk=block["target"]["id"], node_type="concept").exists():
            raise ValidationError({"body_blocks": "概念区块须引用概念节点。"})
        return block
    if kind == "analysis":
        refs = row.get("references")
        if not isinstance(refs, list) or not 1 <= len(refs) <= 40:
            raise ValidationError({"body_blocks": "分析文字须关联1至40项真实来源。"})
        style = row.get("style", "paragraph")
        if not isinstance(style, str) or style not in {"paragraph", "heading"}:
            raise ValidationError({"body_blocks": "分析文字样式无效。"})
        return {**block, "references": [resolve(ref) for ref in refs], "style": style}
    if kind != "comparison":
        raise ValidationError({"body_blocks": "未知结构化文章区块。"})
    dimensions, incoming = row.get("dimensions"), row.get("rows")
    if not isinstance(dimensions, list) or not 1 <= len(dimensions) <= 12:
        raise ValidationError({"body_blocks": "比较须有1至12个维度。"})
    dimensions = [_text(value, 160) for value in dimensions]
    if any(not value for value in dimensions) or len(set(dimensions)) != len(dimensions):
        raise ValidationError({"body_blocks": "比较维度须非空且不重复。"})
    if not isinstance(incoming, list) or not 1 <= len(incoming) <= 12:
        raise ValidationError({"body_blocks": "比较须有1至12行。"})
    rows = []
    for row in incoming:
        if not isinstance(row, dict) or not isinstance(row.get("cells"), list) or len(row["cells"]) != len(dimensions):
            raise ValidationError({"body_blocks": "每行须明确保存每个维度的材料或缺口。"})
        person = resolve({"type": "person", "id": row.get("person_id")})
        cells = []
        for cell in row["cells"]:
            if not isinstance(cell, dict) or cell.get("dimension") not in dimensions:
                raise ValidationError({"body_blocks": "比较单元格维度无效。"})
            refs = cell.get("evidence", [])
            if not isinstance(refs, list) or len(refs) > 8 or any(not isinstance(ref, dict) or ref.get("type") != "span" for ref in refs):
                raise ValidationError({"body_blocks": "比较依据须为最多8项真实原文。"})
            cells.append({"dimension": cell["dimension"], "text": _text(cell.get("text", "")),
                          "evidence": [resolve(ref) for ref in refs], "missing": not refs})
        if {cell["dimension"] for cell in cells} != set(dimensions):
            raise ValidationError({"body_blocks": "比较单元格不能重复维度。"})
        rows.append({"person_id": person["id"], "cells": cells})
    return {**block, "dimensions": dimensions, "rows": rows}


def block_references(block):
    if block.get("type") in REFERENCE_TYPES:
        return [block["target"]]
    if block.get("type") == "analysis":
        return block["references"]
    if block.get("type") == "comparison":
        return [ref for row in block["rows"] for ref in (
            {"type": "person", "id": row["person_id"]},
            *[ref for cell in row["cells"] for ref in cell["evidence"]],
        )]
    return []


def body_payload(blocks, *, public=False, require_public=False):
    output, problems = [], []
    for position, block in enumerate(blocks):
        if block.get("type") == "image":
            from catalog.models import MediaRendition
            key = block.get("image_rendition_id")
            rendition = MediaRendition.objects.filter(pk=key).first() if key else None
            raw = {**deepcopy(block), "image_url": "", "source_status": "unavailable"}
            if rendition:
                raw.update(image_url=f"/api/catalog/editorial-media/{key}/" if public or require_public else f"/api/catalog/admin/media/renditions/{key}/file/", source_status="available")
            output.append(raw)
            continue
        refs = block_references(block)
        if not refs:
            output.append(deepcopy(block))
            continue
        sources = []
        try:
            for reference in refs:
                exact, source = resolve_target(reference, public=public or require_public)
                if exact != reference:
                    raise ValidationError("来源身份发生变化。")
                sources.append(source)
        except (Http404, ValidationError):
            problem = {"block_id": block.get("id"), "position": position, "code": "source_unavailable",
                       "detail": "文章区块的来源尚未公开、已经失效或修订不一致。"}
            problems.append(problem)
            output.append({"id": block.get("id"), "type": block["type"], "text": "", "source_status": "unavailable",
                           **({"style": block.get("style", "paragraph")} if block["type"] == "analysis" else {})}
                          if public else {**deepcopy(block), "source_status": "unavailable", "resolved_sources": []})
        else:
            output.append({**deepcopy(block), "source_status": "available", "resolved_sources": sources})
    if require_public and problems:
        raise ValidationError({"body_blocks": problems})
    return output, problems
