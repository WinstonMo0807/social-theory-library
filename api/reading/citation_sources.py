"""Owner-only source files within citation tasks; no catalog or search-index writes."""
from copy import deepcopy
from bisect import bisect_right
import hashlib
import json

from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from .models import CitationAudit
from .research import identifier, unpack

MAX_SELECTED_SOURCES = 4
MAX_SOURCE_FILES = 24
MAX_SOURCE_BYTES = 128 * 1024 * 1024
MAX_TEXT_UNITS = 10000
UNIT_CHARS = 4000


def source_ids(data):
    values = data.getlist("private_source_ids") if hasattr(data, "getlist") else data.get("private_source_ids", [])
    if not isinstance(values, list) or len(values) > MAX_SELECTED_SOURCES:
        raise ValidationError({"private_source_ids": "每项体检最多明确选择 4 份私人来源。"})
    return sorted({identifier(value, "private_source_ids") for value in values})


def ready_sources(user, identifiers, *, strict=False):
    rows = {}
    for record in CitationAudit.objects.filter(user=user, purpose="private_source", pk__in=identifiers).defer("original_ciphertext"):
        payload = unpack(record)
        if record.status in {"completed", "partial"} and payload.get("parsed") and any(unit.get("matchable", True) and unit["text"].strip() for unit in payload.get("text_units", [])):
            rows[str(record.id)] = (record, payload)
    if strict and set(rows) != set(identifiers):
        raise ValidationError({"private_source_ids": "部分私人来源不存在、未完成或没有可核对文字；请选择本人已解析的来源。"})
    return rows


def source_quota(user, size):
    rows = CitationAudit.objects.filter(user=user, purpose="private_source")
    if rows.count() >= MAX_SOURCE_FILES or (rows.aggregate(total=Sum("file_size_bytes"))["total"] or 0) + size > MAX_SOURCE_BYTES:
        raise ValidationError({"file": "私人来源最多保留 24 份，原件合计不超过 128 MiB；请先管理已有来源。"})


def current_sources(user, sources):
    generations = {str(pk): generation for pk, generation in CitationAudit.objects.filter(user=user, purpose="private_source",
        pk__in=sources, status__in=["completed", "partial"]).values_list("id", "generation")}
    return {key: value for key, value in sources.items() if generations.get(key) == value[0].generation}


def private_identity_current(entry, sources):
    found = sources.get(entry.get("selected_private_source_id"))
    return bool(found and entry.get("selected_private_source_generation") == found[0].generation
        and entry.get("selected_private_source_hash") == found[0].content_hash)


def text_units(paragraphs):
    units = []
    for paragraph in paragraphs:
        value = paragraph["text"]
        # DOCX image OCR is appended as a separate unit, not interleaved at its
        # native character position. Do not imply exact continuity through it.
        matchable = not (paragraph.get("embedded_images") or (paragraph.get("needs_ocr")
            and paragraph["location"].get("text_source") != "ocr"))
        # Empty/failed OCR paragraphs remain observable, rather than implying coverage.
        for start in range(0, max(1, len(value)), UNIT_CHARS):
            location = {key: val for key, val in paragraph["location"].items()
                if key in {"part", "paragraph", "note_id", "pdf_page", "text_source", "ocr_unit_id"}}
            location.update(start=start, end=min(len(value), start + UNIT_CHARS))
            content = value[start:start + UNIT_CHARS]
            unit_id = hashlib.sha256(json.dumps([len(units), location, content, matchable], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            units.append({"id": unit_id, "index": len(units), "text": content, "location": location, "matchable": matchable,
                "coverage_status": "parsed_text" if matchable else "unread_content"})
            if len(units) > MAX_TEXT_UNITS:
                raise ValidationError({"file": "来源的文字段落超过 10000 个处理单元，请拆分文件。"})
    return units


def paginated_units(record, query):
    payload = unpack(record)
    units = payload.get("text_units")
    if units is None:
        units = text_units(payload.get("source_paragraphs", []))
    try:
        page, size = int(query.get("page", 1)), int(query.get("page_size", 20))
    except (ValueError, TypeError):
        raise ValidationError({"page": "页码与每页数量须为整数。"})
    if page < 1 or not 1 <= size <= 50:
        raise ValidationError({"page": "页码至少为 1，每页 1—50 个文字单元。"})
    target = query.get("unit_id")
    target_location = None
    if query.get("occurrence_id") and query.get("entry_id"):
        raise ValidationError({"occurrence_id": "请选择一个引文或书目定位。"})
    for key, collection in (("occurrence_id", "occurrences"), ("entry_id", "bibliography")):
        if query.get(key):
            item = next((row for row in payload.get(collection, []) if row["id"] == identifier(query[key], key)), None)
            if item is None:
                raise NotFound("稿件中没有此定位。")
            target_location = item["location"]
    if target or target_location:
        position = next((index for index, unit in enumerate(units) if unit["id"] == target or (target_location is not None
            and all(unit["location"].get(key) == target_location.get(key) for key in ("part", "paragraph", "note_id", "pdf_page"))
            and unit["location"]["start"] <= target_location.get("start", 0) < max(unit["location"]["start"] + 1, unit["location"]["end"]))), None)
        if position is None:
            raise NotFound("该文字单元尚未取得，或定位已变化。")
        page = position // size + 1
    start = (page - 1) * size
    result = {"revision": record.revision, "generation": payload.get("text_generation", record.generation), "status": record.status,
        "count": len(units), "page": page, "next_page": page + 1 if start + size < len(units) else None,
        "units": units[start:start + size], "notice": "仅本人的解析文字；DOCX 为真实部件、段落和字符位置，不代表 Word 排版页码。OCR 文字仍需对照原件；未识别页及嵌图段落不作为连续精确匹配依据。"}
    if record.purpose == "private_source":
        result["source_id"] = str(record.id)
    else:
        result.update(audit_id=str(record.id), manuscript_revision=payload.get("manuscript_revision", 1))
    return result


def source_candidate(source_id, sources):
    found = sources.get(source_id)
    if not found:
        return {"source_id": source_id, "kind": "private_source", "source_status": "source_unavailable",
            "title": "私人来源当前不可访问", "filename": "", "citation": ""}
    record, payload = found
    return {"source_id": source_id, "kind": "private_source", "source_status": "available",
        "title": payload.get("title") or payload["filename"], "filename": payload["filename"],
        "citation": payload.get("citation", ""), "source_generation": record.generation}


def resolve_private_reference(raw, user, allowed_ids, *, sources=None):
    source_id = raw.get("source_id")
    denied = {"source_id": source_id, "source_generation": raw.get("source_generation"),
        "unit_id": raw.get("unit_id"), "source_status": "source_unavailable", "quote": "",
        "title": "私人来源已移除、变化或不可访问", "filename": "", "citation": "", "original_url": None}
    if source_id not in allowed_ids:
        return denied
    sources = ready_sources(user, [source_id]) if sources is None else sources
    found = sources.get(source_id)
    if not found:
        return denied
    record, payload = found
    if record.generation != raw.get("source_generation") or record.content_hash != raw.get("source_hash"):
        return denied
    ids = raw.get("unit_ids", [raw.get("unit_id")])
    if not isinstance(ids, list) or not 1 <= len(ids) <= 5:
        return denied
    units = {unit["id"]: unit for unit in payload.get("text_units", [])}
    if any(key not in units for key in ids):
        return denied
    chosen = [units[key] for key in ids]
    if (any(not unit.get("matchable", True) for unit in chosen)
            or any(any(unit["location"].get(key) != chosen[0]["location"].get(key) for key in ("part", "note_id")) for unit in chosen)
            or any(right["index"] != left["index"] + 1 for left, right in zip(chosen, chosen[1:]))):
        return denied
    joined = "\n".join(unit["text"] for unit in chosen)
    start, end = raw.get("start_offset"), raw.get("end_offset")
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= len(joined)
            or hashlib.sha256(joined[start:end].encode()).hexdigest() != raw.get("content_hash")):
        return denied
    return {**raw, **source_candidate(source_id, sources), "quote": joined[start:end][:4000],
        "quote_truncated": end - start > 4000, "location": deepcopy(chosen[0]["location"]),
        "original_url": f"/api/reading/citation-sources/{source_id}/original/"}


def private_matches(quote, sources):
    from .citation_audit import _normalized
    needle = _normalized(quote)
    if not needle:
        return []
    matches = []
    for source_id, (record, payload) in sources.items():
        units = payload.get("text_units", [])
        # This cache lives only in the worker's decrypted, selected source payload.
        # One bounded string scan per quote avoids repeatedly normalizing every unit.
        if "_normalized_text" not in payload:
            parts, ends, total = [], [], 0
            for unit in units:
                value = _normalized(unit["text"])
                parts.append(value)
                total += len(value)
                ends.append(total)
            payload["_normalized_text"], payload["_normalized_ends"] = "".join(parts), ends
        normalized, ends = payload["_normalized_text"], payload["_normalized_ends"]
        at = normalized.find(needle)
        while at >= 0:
            first, last = bisect_right(ends, at), bisect_right(ends, at + len(needle) - 1)
            chosen = units[first:last + 1]
            if len(chosen) <= 5 and all(unit.get("matchable", True) for unit in chosen) and all(all(unit["location"].get(key) == chosen[0]["location"].get(key)
                    for key in ("part", "note_id")) for unit in chosen):
                joined = "\n".join(item["text"] for item in chosen)
                positions = [index for index, char in enumerate(joined) for _ in _normalized(char)]
                local_at = at - (ends[first - 1] if first else 0)
                start, end = positions[local_at], positions[local_at + len(needle) - 1] + 1
                matches.append({"source_id": source_id, "source_generation": record.generation, "source_hash": record.content_hash,
                    "unit_id": chosen[0]["id"], "unit_ids": [item["id"] for item in chosen],
                    "start_offset": start, "end_offset": end,
                    "content_hash": hashlib.sha256(joined[start:end].encode()).hexdigest()})
            if len(matches) >= 10:
                return matches
            at = normalized.find(needle, at + len(needle))
    return matches


def check_private_occurrence(occurrence, entries, sources):
    linked = [entry for entry in entries if entry["id"] in occurrence["entry_ids"] and entry.get("selected_private_source_id")]
    selected = {entry["selected_private_source_id"] for entry in linked}
    candidates = {key: value for key, value in sources.items() if not selected or key in selected}
    matches = private_matches(occurrence.get("quote", ""), candidates)
    if not matches and not selected:
        return []
    return [{"kind": "private_quote", "status": "text_match" if matches else "unverified",
        "private_references": matches, "identity_status": "owner_confirmed" if linked and all(private_identity_current(entry, sources) for entry in linked) else "needs_review",
        "match_limits": {"max_adjacent_units": 5, "max_matches": 10},
        "page_status": "needs_review", "message": ("已命中本人选定来源的文字，仍须核对书目身份、版本与印刷页码。"
            if matches else "选定的私人来源未命中；识别或版本差异均可能影响结果，不能据此判为引文错误。")}]


def refresh_private_sources(payload, user):
    allowed = payload.get("private_source_ids", []) if payload.get("scope") == "private_materials" else []
    sources = ready_sources(user, allowed)
    payload["private_sources"] = [source_candidate(key, sources) for key in allowed]
    reports = [payload, *payload.get("parse_history", [])]
    for report in reports:
        for entry in report.get("bibliography", []):
            entry["private_candidates"] = [source_candidate(key, sources) for key in allowed]
            selected = entry.get("selected_private_source_id")
            if selected:
                entry["selected_private_source_status"] = "available" if private_identity_current(entry, sources) else "source_unavailable"
        for occurrence in report.get("occurrences", []):
            for version in [occurrence, *occurrence.get("history", [])]:
                for finding in version.get("findings", []):
                    if "private_references" not in finding:
                        continue
                    finding["private_references"] = [resolve_private_reference(ref, user, allowed, sources=sources) for ref in finding["private_references"]]
                    linked = [entry for entry in report.get("bibliography", []) if entry["id"] in occurrence.get("entry_ids", []) and entry.get("selected_private_source_id")]
                    if linked and not all(private_identity_current(entry, sources) for entry in linked):
                        finding["identity_status"] = "needs_review"
                    if finding["private_references"] and not any(ref["source_status"] == "available" for ref in finding["private_references"]):
                        finding.update(status="unverified", source_status="source_unavailable", page_status="needs_review",
                            message="私人来源已删除、移除或重新解析；旧记录保留，原文与旧结论不再作为当前依据。")
