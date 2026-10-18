"""Local manuscript parsing and independently reviewable citation checks.

Occurrence, bibliography, match and finding are encrypted job-owned collections;
none are public catalog objects. The original package is retained byte-for-byte.
"""
from __future__ import annotations

import base64
from collections import Counter
from copy import deepcopy
import hashlib
from io import BytesIO
import json
import re
import posixpath
from pathlib import PurePath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from catalog.models import EvidenceSpan
from catalog.services.citations import format_gbt_7714_2025
from catalog.services.discovery_sources import source_queryset
from catalog.services.publication_eligibility import public_editions

from .models import CitationAudit
from .research import (ACTIVE, ResearchConflict, access_for, compact_reference, expect, identifier,
                       owned, pack, resolve_reference, save_data, source_project, text, unpack)
from .research import request_fingerprint, same_request
from .services import decrypt_private_text, encrypt_private_text

CHECKER_VERSION = "citation-local-v1"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_XML_BYTES = 40 * 1024 * 1024
MAX_TEXT_CHARS = 1_000_000
MAX_OCCURRENCES = 1000
MAX_PDF_PAGES = 1000
MAX_ACTIVE_AUDITS_PER_OWNER = 2
DEFAULT_CHECKS = ("citation_identification", "bibliography_identity", "version_page")
UPLOAD_CHECKS = (*DEFAULT_CHECKS, "scan_ocr")
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
REFERENCE_RE = re.compile(r"^\s*(?:\[(\d{1,4})\]|(\d{1,4})[.、])\s*(.+)")
CITE_RE = re.compile(r"\[(\d{1,4}(?:\s*[,，、-]\s*\d{1,4})*)\]|[（(]([^()（）\n]{1,100}?(?:18|19|20)\d{2}[a-z]?(?:[^()（）\n]{0,40}))[）)]")
QUOTE_RE = re.compile(r"[“「『\"]([^”」』\"]{8,2000})[”」』\"]")


def audit_capabilities():
    """Configuration eligibility only; an available capability is not a health probe."""
    from common.ai_runtime import AICapability
    from .local_analysis import AIServiceError, current_ai_configuration, require_local_endpoint
    from .private_ocr import UNITS_PER_ATTEMPT, _local_gateway
    ocr_available, analysis_available = False, False
    try:
        gateway, allowed = _local_gateway()
        require_local_endpoint(gateway, allowed_hosts=allowed)
        ocr_available = True
    except (AIServiceError, ValueError):
        pass
    try:
        config = current_ai_configuration(AICapability.CLAIM_STANCE)
        if config.enabled:
            require_local_endpoint(config.base_url)
            analysis_available = True
    except (AIServiceError, ValueError):
        pass
    ocr_reason = ("已配置允许的本地 OCR；运行状态与识别结果在任务中确认。" if ocr_available
                  else "未配置可用的本地 OCR 地址，扫描页会保留为待核实。")
    return {"max_upload_bytes": MAX_UPLOAD_BYTES, "max_pdf_pages": MAX_PDF_PAGES,
        "max_occurrences": MAX_OCCURRENCES, "max_active_jobs_per_owner": MAX_ACTIVE_AUDITS_PER_OWNER,
        "accepted_filetypes": ["docx", "pdf"], "default_checks": list(DEFAULT_CHECKS),
        "checks": [
            {"id": "citation_identification", "label": "引文识别", "available": True, "required": True,
                "description": "识别引文位置及参考文献，是其他检查的必要步骤。"},
            {"id": "bibliography_identity", "label": "书目身份", "available": True, "required": False,
                "description": "在已公开的馆藏版本中查找身份候选，题名相似不视为确认。"},
            {"id": "version_page", "label": "版本与页码", "available": True, "required": False,
                "requires": ["bibliography_identity"], "description": "依赖书目身份，核对可访问原文的文字及印刷页码。"},
            {"id": "scan_ocr", "label": "扫描页识别", "available": ocr_available, "required": False, "description": ocr_reason},
            {"id": "deep_analysis", "label": "深入关系分析", "available": False, "required": False,
                "description": "上传时不自动执行；报告中明确选择原文后，按本地模型配置单独发起。"}],
        "scopes": [
            {"id": "public_library", "label": "馆藏公开资料", "available": True,
                "description": "只核对当前公开且本人可访问的馆藏版本和原文。"},
            {"id": "private_materials", "label": "馆藏及本人选定材料", "available": True,
                "description": "核对公开馆藏，并补充本次明确选择的本人 PDF/DOCX 来源；私人文件不进入公共馆藏或索引。"}],
        "private_sources": {"available": True, "max_selected": 4, "max_files_per_owner": 24,
            "max_total_bytes_per_owner": 128 * 1024 * 1024, "max_upload_bytes": MAX_UPLOAD_BYTES,
            "max_text_units": 10000, "max_chars_per_file": MAX_TEXT_CHARS,
            "notice": "书目对应须本人确认；OCR 显式开启，私人来源不进入公共检索。"},
        "ocr": {"available": ocr_available, "reason": ocr_reason, "service_verified": False,
            "units_per_attempt": UNITS_PER_ATTEMPT, "max_unit_timeout_seconds": 120},
        "analysis": {"available": analysis_available, "service_verified": False,
            "reason": "已配置允许的本地模型；分析仅为待核对候选。" if analysis_available else "未配置可用的本地关系分析模型。"}}


def audit_options(data):
    raw = data.getlist("checks") if hasattr(data, "getlist") and "checks" in data else data.get("checks", list(DEFAULT_CHECKS))
    if not isinstance(raw, list) or not raw or len(raw) > len(UPLOAD_CHECKS) or any(check not in UPLOAD_CHECKS for check in raw):
        raise ValidationError({"checks": "请选择已开放的检查项。"})
    checks = [check for check in UPLOAD_CHECKS if check in raw]
    if "citation_identification" not in checks or ("version_page" in checks and "bibliography_identity" not in checks):
        raise ValidationError({"checks": "引文识别是必要步骤；版本与页码检查需要同时选择书目身份。"})
    if data.get("scope", "public_library") not in {"public_library", "private_materials"}:
        raise ValidationError({"scope": "请选择公开馆藏或馆藏及本人选定材料。"})
    return checks


def parse_docx(blob):
    from docx import Document
    from lxml import etree
    try:
        with ZipFile(BytesIO(blob)) as archive:
            infos = archive.infolist()
            if (len(infos) > 3000 or sum(item.file_size for item in infos) > MAX_XML_BYTES
                    or any(item.flag_bits & 1 for item in infos)):
                raise ValidationError({"file": "DOCX 解包大小超限或已加密。"})
            parts = [name for name in archive.namelist() if name in {
                "word/document.xml", "word/footnotes.xml", "word/endnotes.xml"}]
            if "word/document.xml" not in parts:
                raise ValidationError({"file": "缺少 DOCX 正文部件。"})
            for info in infos:
                if info.filename.endswith(".xml"):
                    xml = archive.read(info)
                    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                        raise ValidationError({"file": "DOCX XML 包含不支持的实体声明。"})
            # Validate the standard Word package through python-docx; parse locators
            # directly because its paragraph API omits note bodies and citation fields.
            Document(BytesIO(blob))
            paragraphs, text_chars = [], 0
            parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
            for name in parts:
                xml = archive.read(name)
                if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
                    raise ValidationError({"file": "DOCX XML 包含不支持的实体声明。"})
                root = etree.fromstring(xml, parser=parser)
                rel_path = posixpath.join(posixpath.dirname(name), "_rels", posixpath.basename(name) + ".rels")
                relationships = {}
                if rel_path in archive.namelist():
                    rel_xml = archive.read(rel_path)
                    if b"<!DOCTYPE" in rel_xml or b"<!ENTITY" in rel_xml:
                        raise ValidationError({"file": "DOCX 关系部件包含不支持的实体声明。"})
                    rel_root = etree.fromstring(rel_xml, parser=parser)
                    for relation in rel_root:
                        target = posixpath.normpath(posixpath.join(posixpath.dirname(name), relation.get("Target", "")))
                        if relation.get("TargetMode") != "External" and target.startswith("word/media/") and target in archive.namelist():
                            relationships[relation.get("Id")] = target
                field_stack, part_fields, paragraph_rows = [], [], {}
                for index, paragraph in enumerate(root.iter(WORD_NS + "p")):
                    value, note_refs, embedded_images = "", [], []
                    for event, element in etree.iterwalk(paragraph, events=("start", "end")):
                        if event == "start" and element.tag == WORD_NS + "fldSimple":
                            field_stack.append({"fragments": [element.get(WORD_NS + "instr", "")],
                                "paragraph": index, "start": len(value), "simple": True,
                                "xml_node": root.getroottree().getpath(element)})
                        if event == "start" and element.tag == WORD_NS + "fldChar":
                            marker = element.get(WORD_NS + "fldCharType", "")
                            if marker == "begin":
                                field_stack.append({"fragments": [], "paragraph": index, "start": len(value),
                                    "simple": False, "xml_node": root.getroottree().getpath(element)})
                            elif marker == "end" and field_stack:
                                field = field_stack.pop()
                                part_fields.append({**field, "end": len(value), "end_paragraph": index,
                                                    "instruction": "".join(field["fragments"])})
                        if event == "start" and element.tag == WORD_NS + "instrText":
                            if field_stack:
                                field_stack[-1]["fragments"].append(element.text or "")
                            else:
                                # Preserve malformed legacy fields as an explicit unbounded XML locator.
                                part_fields.append({"instruction": element.text or "", "paragraph": index,
                                    "start": len(value), "end": len(value), "end_paragraph": index,
                                    "xml_node": root.getroottree().getpath(element), "incomplete": True})
                        if event == "start" and element.tag in {WORD_NS + "footnoteReference", WORD_NS + "endnoteReference"}:
                            note_refs.append({"id": element.get(WORD_NS + "id", ""),
                                "kind": "footnote" if element.tag == WORD_NS + "footnoteReference" else "endnote",
                                "offset": len(value), "xml_node": root.getroottree().getpath(element)})
                        if event == "start" and element.get(REL_NS + "embed") in relationships:
                            media_path = relationships[element.get(REL_NS + "embed")]
                            image_hash = hashlib.sha256(archive.read(media_path)).hexdigest()
                            embedded_images.append({"media_path": media_path, "sha256": image_hash,
                                "xml_node": root.getroottree().getpath(element), "native_offset": len(value)})
                        if event == "start":
                            value += ((element.text or "") if element.tag == WORD_NS + "t" else
                                      "\t" if element.tag == WORD_NS + "tab" else "\n" if element.tag == WORD_NS + "br" else "")
                        if event == "end" and element.tag == WORD_NS + "fldSimple" and field_stack:
                            field = field_stack.pop()
                            part_fields.append({**field, "end": len(value), "end_paragraph": index,
                                                "instruction": "".join(field["fragments"])})
                    text_chars += len(value)
                    if text_chars > MAX_TEXT_CHARS:
                        raise ValidationError({"file": "稿件文字超过本轮处理上限；原稿保留。"})
                    ancestor = paragraph.getparent()
                    while ancestor is not None and ancestor.tag not in {WORD_NS + "footnote", WORD_NS + "endnote"}:
                        ancestor = ancestor.getparent()
                    note_id = ancestor.get(WORD_NS + "id") if ancestor is not None else None
                    row = {"text": value, "location": {"part": name, "paragraph": index,
                        "note_id": note_id, "pdf_page": None, "xml_node": root.getroottree().getpath(paragraph)},
                        "fields": [], "note_refs": note_refs, "embedded_images": embedded_images}
                    paragraph_rows[index] = row
                    paragraphs.append(row)
                    if len(paragraphs) > 10000:
                        raise ValidationError({"file": "文字段落超过 10000 个处理单元，请拆分文件；原件保留。"})
                for field in part_fields:
                    paragraph_rows[field["paragraph"]]["fields"].append(field)
    except (BadZipFile, KeyError, ValueError, etree.XMLSyntaxError) as exc:
        raise ValidationError({"file": "无法解析 DOCX；原稿会保留，未修改引文域。"}) from exc
    return paragraphs


def parse_pdf(blob):
    import fitz
    try:
        with fitz.open(stream=blob, filetype="pdf") as document:
            if document.needs_pass or len(document) > MAX_PDF_PAGES:
                raise ValidationError({"file": "PDF 已加密或超过 1000 页上限。"})
            rows, text_chars = [], 0
            for index, page in enumerate(document):
                images = page.get_images(full=True)
                if page.rect.width > 20000 or page.rect.height > 20000 or any(image[2] * image[3] > 40_000_000 for image in images):
                    raise ValidationError({"file": "PDF 页面尺寸或嵌入图像超过私人解析上限；原稿保留。"})
                content = page.get_text("text")
                text_chars += len(content)
                if text_chars > MAX_TEXT_CHARS:
                    raise ValidationError({"file": "稿件文字超过本轮处理上限；原稿保留。"})
                compact = re.sub(r"\s+", "", content)
                needs_ocr = (len(compact) < 40 and bool(images)) or "(cid:" in content or content.count("\ufffd") > max(3, len(content) // 20)
                rows.append({"text": content, "native_text": content, "needs_ocr": needs_ocr, "embedded_image_count": len(images),
                    "location": {"part": "pdf", "pdf_page": index + 1, "paragraph": None}, "fields": [], "note_refs": []})
            return rows
    except (RuntimeError, ValueError) as exc:
        raise ValidationError({"file": "PDF 无法解析。"}) from exc


def parse_manuscript(blob, kind, *, paragraphs=None):
    paragraphs = paragraphs if paragraphs is not None else parse_docx(blob) if kind == "docx" else parse_pdf(blob)
    if sum(len(row["text"]) for row in paragraphs) > MAX_TEXT_CHARS:
        raise ValidationError({"file": "稿件文字超过本轮处理上限。"})
    entries, occurrences, warnings = [], [], []
    bibliography_sections, note_bodies, note_entries = {}, {}, {}
    for paragraph in paragraphs:
        location = paragraph["location"]
        if location.get("note_id") is not None:
            note_kind = "footnote" if location["part"] == "word/footnotes.xml" else "endnote"
            note_bodies.setdefault((note_kind, location["note_id"]), []).append(paragraph["text"])
    for key, parts in note_bodies.items():
        value = "\n".join(parts)
        if DOI_RE.search(value) or "《" in value or re.search(r"(?:18|19|20)\d{2}", value):
            entry = {"id": str(uuid4()), "label": "", "raw": value,
                "doi": DOI_RE.search(value).group().rstrip(".,。，") if DOI_RE.search(value) else "",
                "location": {"part": f"word/{key[0]}s.xml", "note_id": key[1], "pdf_page": None},
                "identity_status": "pending", "candidates": [], "selected_edition_id": None, "kind": "note_candidate"}
            entries.append(entry)
            note_entries[key] = entry["id"]
    for paragraph in paragraphs:
        value = paragraph["text"]
        base_location = paragraph["location"]
        section_key = (base_location["part"], base_location.get("note_id"))
        in_bibliography = bibliography_sections.get(section_key, False)
        body_end = len(value)
        for match in re.finditer(r"[^\n]+", value):
            line = match.group().strip()
            if re.fullmatch(r"(?:参考文献|引用文献|参考书目|References|Bibliography)\s*[:：]?", line, re.I):
                in_bibliography = True
                bibliography_sections[section_key] = True
                body_end = min(body_end, match.start())
                continue
            number = REFERENCE_RE.match(line)
            if in_bibliography:
                if not line:
                    continue
                label = (number.group(1) or number.group(2)) if number else ""
                raw = number.group(3) if number else line
                entries.append({"id": str(uuid4()), "label": label, "raw": raw,
                    "doi": (DOI_RE.search(raw).group().rstrip(".,。，") if DOI_RE.search(raw) else ""),
                    "location": {**base_location, "start": match.start(), "end": match.end()},
                    "identity_status": "pending", "candidates": [], "selected_edition_id": None})
        if bibliography_sections.get(section_key) and body_end == len(value):
            continue
        body = value[:body_end]
        fields = [field for field in paragraph["fields"] if re.search(r"CITATION|ZOTERO|EN\.CITE|CSL_CITATION", field["instruction"], re.I)]
        citations = [match for match in CITE_RE.finditer(body) if not any(
            field["start"] <= match.start() < field["end"] for field in fields if not field.get("incomplete"))]
        for match in citations:
            labels = re.findall(r"\d+", match.group(1) or "")
            # Range citations are not silently interpreted as only their endpoints.
            if match.group(1) and "-" in match.group(1):
                labels = []
                warnings.append({"code": "citation_range_review", "message": "数字范围引文待本人拆分确认。"})
            nearby = [quote for quote in QUOTE_RE.finditer(value) if 0 <= match.start() - quote.end() <= 100]
            quote = nearby[-1] if nearby else None
            context_start, context_end = max(0, match.start() - 600), min(len(value), match.end() + 200)
            occurrences.append({"id": str(uuid4()), "raw": match.group(), "labels": labels,
                "author_date": match.group(2) or "", "location": {**base_location, "start": match.start(), "end": match.end()},
                "quote": quote.group(1) if quote else "", "context": value[context_start:context_end],
                "entry_ids": [], "note_refs": paragraph.get("note_refs", []), "findings": [], "decision": None})
        for note in paragraph["note_refs"]:
            key = (note["kind"], note["id"])
            note_text = "\n".join(note_bodies.get(key, []))
            quotes = [match for match in QUOTE_RE.finditer(body) if 0 <= note["offset"] - match.end() <= 100]
            occurrences.append({"id": str(uuid4()), "raw": "", "labels": [], "author_date": "",
                "location": {**base_location, "start": note["offset"], "end": note["offset"], "xml_node": note["xml_node"]},
                "quote": quotes[-1].group(1) if quotes else "", "context": body + "\n" + note_text,
                "note_text": note_text, "note_reference": note,
                "entry_ids": [note_entries[key]] if key in note_entries else [], "findings": [], "decision": None})
        for field_info in fields:
            field = field_info["instruction"]
            occurrences.append({"id": str(uuid4()), "raw": value, "labels": [], "author_date": "",
                "location": {**base_location, "start": field_info["start"], "end": field_info["end"],
                             "end_paragraph": field_info["end_paragraph"], "xml_node": field_info["xml_node"]},
                "quote": "", "context": value,
                "entry_ids": [], "citation_field": field, "findings": [], "decision": None})
            # Zotero CSL fields carry bibliographic identity; keep the original field untouched.
            start = field.find("{")
            if start >= 0:
                try:
                    parsed, _ = json.JSONDecoder().raw_decode(field[start:])
                except (ValueError, TypeError):
                    continue
                for cited in parsed.get("citationItems", []) if isinstance(parsed, dict) else []:
                    item = cited.get("itemData", {}) if isinstance(cited, dict) else {}
                    if not isinstance(item, dict) or not item.get("title"):
                        continue
                    entry = {"id": str(uuid4()), "label": "", "raw": str(item["title"]), "doi": str(item.get("DOI", "")),
                             "location": base_location, "identity_status": "pending", "candidates": [],
                             "selected_edition_id": None, "field_item": item}
                    entries.append(entry)
                    occurrences[-1]["entry_ids"].append(entry["id"])
    if len(entries) > 1000 or len(occurrences) > MAX_OCCURRENCES:
        raise ValidationError({"file": "引文或参考文献超过本轮上限，请拆分稿件。"})
    for occurrence in occurrences:
        if occurrence["entry_ids"]:
            continue
        for entry in entries:
            author_date = occurrence.get("author_date", "")
            year = re.search(r"(?:18|19|20)\d{2}", author_date)
            author = author_date[:year.start()].strip(" ,，;；") if year else ""
            if ((entry["label"] and entry["label"] in occurrence["labels"])
                    or (author and year.group() in entry["raw"] and author.casefold() in entry["raw"].casefold())
                    ):
                occurrence["entry_ids"].append(entry["id"])
    if not paragraphs or not any(row["text"].strip() for row in paragraphs):
        warnings.append({"code": "text_unavailable", "message": "尚未取得可检查的稿件文字；请查看本地 OCR 状态或提供可提取文字版本，不能据此认定引文无问题。"})
    if not occurrences:
        warnings.append({"code": "no_citations_parsed", "message": "未识别到支持的引文位置；不能据此认定稿件没有引文问题。"})
    return {"bibliography": entries, "occurrences": occurrences, "warnings": warnings,
            "parser": "python-docx+xml" if kind == "docx" else "pymupdf", "checker_version": CHECKER_VERSION,
            "location_notice": "DOCX 位置是 XML 部件、段落和字符范围，不是 Word 排版页码。"}


def _normalized(value):
    return re.sub(r"[\s\W_]+", "", value.casefold())


def _bibliography_identity(entry):
    """Extract explainable identity hints; absence is unknown, never an author mismatch."""
    raw = entry["raw"]
    item = entry.get("field_item") if isinstance(entry.get("field_item"), dict) else {}
    authors = []
    for author in item.get("author", []) if isinstance(item.get("author"), list) else []:
        if isinstance(author, dict):
            names = [author.get("literal"), author.get("family"), " ".join(str(author.get(key) or "") for key in ("given", "family"))]
            authors.extend(str(name).strip() for name in names if name and str(name).strip())
    issued = item.get("issued", {})
    parts = issued.get("date-parts", []) if isinstance(issued, dict) else []
    structured_year = parts[0][0] if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0] else None
    years = [str(structured_year)] if isinstance(structured_year, int) and 1000 <= structured_year <= 2999 else list(dict.fromkeys(
        re.findall(r"(?<!\d)(?:1[5-9]|20)\d{2}(?!\d)", DOI_RE.sub("", raw))))
    version = str(item.get("edition") or "").strip()
    if not version:
        match = re.search(r"第\s*[一二三四五六七八九十百0-9]+\s*版|修订版|增订版|再版|\d+(?:st|nd|rd|th)\s+(?:edition|ed\.?)(?![a-z])", raw, re.I)
        version = match.group() if match else ""
    return {"authors": list(dict.fromkeys(authors)), "author_basis": "structured_citation_field" if authors else "raw_name_observation",
        "years": years, "year_basis": "structured_citation_field" if structured_year else "raw_year_mentions",
        "version_label": version, "notice": "作者、年份和版次仅用于解释候选差异；没有出现的字段记为未知，题名相似不能确认版本。"}


def _identity_signals(identity, raw, snapshot):
    values = snapshot.get("edition") or {}
    names = []
    for row in snapshot.get("contributions", []):
        if not isinstance(row, dict) or row.get("role") != "author":
            continue
        person = row.get("person") or {}
        names.extend(str(name) for name in [row.get("name"), person.get("preferred_name"), person.get("original_name"),
            *(person.get("aliases") or [])] if isinstance(name, str) and name.strip())
    author_terms = {_normalized(name) for name in names}
    expected = {_normalized(name) for name in identity["authors"]}
    mentioned = [name for name in names if len(_normalized(name)) >= 2 and _normalized(name) in _normalized(raw)]
    latin_parts = {part.casefold() for name in names for part in re.findall(r"[A-Za-z]+", name)}
    author_match = bool(expected and (expected & author_terms or expected & latin_parts))
    author_state = ("matched" if author_match else "conflict" if author_terms else "unknown") if expected else "mentioned" if mentioned else "unknown"
    year = str(values.get("publication_year") or "")
    year_state = ("matched" if year in identity["years"] else "conflict") if identity["years"] and year else "unknown"
    version = str(values.get("version_label") or "")
    version_state = ("matched" if _normalized(identity["version_label"]) == _normalized(version) else "needs_review") if identity["version_label"] and version else "unknown"
    return {"author": {"status": author_state, "catalog_names": list(dict.fromkeys(names)), "observed_names": list(dict.fromkeys(mentioned))},
        "year": {"status": year_state, "cited_years": identity["years"], "catalog_year": values.get("publication_year")},
        "version": {"status": version_state, "cited_version": identity["version_label"], "catalog_version": version}}


def match_bibliography(entry, editions):
    from rapidfuzz.fuzz import partial_ratio
    if entry.get("identity_status") in {"user_confirmed", "private_confirmed"}:
        return entry
    raw = entry["raw"]
    item = entry.get("field_item") if isinstance(entry.get("field_item"), dict) else {}
    query = _normalized(raw + " " + str(item.get("ISBN") or ""))
    doi = entry.get("doi", "").casefold()
    identity_hints = _bibliography_identity(entry)
    entry["identity_hints"] = identity_hints
    candidates, exact_count, exact_candidate = [], 0, None
    for edition in editions:
        snapshot = edition.active_catalog_revision.snapshot or {}
        work, values = snapshot.get("work") or {}, snapshot.get("edition") or {}
        title_value = str(work.get("title") or "")
        title_key = _normalized(title_value)
        doi_match = bool(doi and doi == str(values.get("doi") or "").casefold())
        isbn_match = any(len(str(values.get(key) or "")) >= 10 and _normalized(str(values[key])) in query for key in ("isbn", "isbn10", "isbn13"))
        title_match = bool(len(title_key) >= 4 and title_key in query)
        score = partial_ratio(title_key, query) if len(title_key) >= 4 else 0
        if not (doi_match or isbn_match or title_match or score >= 82):
            continue
        identity = "identifier" if doi_match or isbn_match else "title" if title_match else "fuzzy_candidate"
        signals = _identity_signals(identity_hints, raw, snapshot)
        conflicts = [field for field, signal in signals.items() if signal["status"] in {"conflict", "needs_review"}]
        rank = 300 if doi_match or isbn_match else 200 if title_match else score
        rank += sum(20 if signal["status"] in {"matched", "mentioned"} else -20 if signal["status"] == "conflict" else 0
            for signal in signals.values())
        candidate = {"edition_id": str(edition.id), "work_id": str(edition.work_id), "title": title_value,
            "catalog_revision_id": str(edition.active_catalog_revision_id),
            "year": values.get("publication_year"), "version_label": values.get("version_label", ""),
            "basis": identity, "similarity": score if identity == "fuzzy_candidate" else None,
            "identity_signals": signals, "review_fields": conflicts,
            "citation": format_gbt_7714_2025(edition, snapshot=snapshot), "_rank": rank}
        if identity == "identifier":
            exact_count += 1
            exact_candidate = candidate
        candidates.append(candidate)
        candidates.sort(key=lambda row: -row["_rank"])
        del candidates[8:]
    entry["candidates"] = [{key: value for key, value in row.items() if key != "_rank"} for row in candidates[:8]]
    if exact_count == 1 and not exact_candidate["review_fields"]:
        entry["identity_status"], entry["selected_edition_id"] = "identifier_matched", exact_candidate["edition_id"]
        entry["selected_catalog_revision_id"] = exact_candidate["catalog_revision_id"]
    else:
        entry["identity_status"] = "needs_review" if candidates else "not_matched_in_library"
        entry["selected_edition_id"] = None
        entry.pop("selected_catalog_revision_id", None)
    return entry


def _continuous_spans(left, right):
    """Bridge only verifiable neighboring source text, never skipped prose."""
    for span in (left, right):
        if (span.page_number != span.page.index or span.page.asset_id != span.document_revision.asset_id
                or not 0 <= span.start_offset < span.end_offset <= len(span.page.text)
                or _normalized(span.page.text[span.start_offset:span.end_offset]) != _normalized(span.original_text)):
            return False
    if left.page_id == right.page_id:
        return left.end_offset <= right.start_offset and not _normalized(left.page.text[left.end_offset:right.start_offset])
    return (right.page_number == left.page_number + 1
        and not _normalized(left.page.text[left.end_offset:]) and not _normalized(right.page.text[:right.start_offset]))


def _quote_matches(edition, quote, user):
    needle = _normalized(quote)
    if not needle:
        return []
    matches, seen, window = [], set(), []
    spans = EvidenceSpan.objects.filter(document_revision_id=edition.active_catalog_revision.document_revision_id,
        is_stale=False).select_related("page", "document_revision").order_by("page_number", "start_offset", "end_offset", "id")
    for span in spans.iterator(chunk_size=200):
        if window and not _continuous_spans(window[-1], span):
            window = []
        window = [*window[-4:], span]
        # Five consecutive spans bound work and anchor count; discontinuous or
        # longer quotations remain explicit manual checks.
        for width in range(1, len(window) + 1):
            candidate = window[-width:]
            haystack = _normalized("\n".join(row.original_text for row in candidate))
            match_start = haystack.find(needle)
            previous_length = len(_normalized("\n".join(row.original_text for row in candidate[:-1])))
            if match_start < 0 or match_start + len(needle) <= previous_length:
                continue
            identity = tuple(str(row.id) for row in candidate)
            if identity not in seen:
                anchors = [{"evidence_span_id": key} for key in identity]
                ref = anchors[0] if len(anchors) == 1 else {"anchors": anchors}
                current = resolve_reference(ref, user)
                if current["source_status"] == "available":
                    matches.append(compact_reference(current))
                    seen.add(identity)
            break
        if len(matches) == 10:
            break
    return matches


def check_occurrence(occurrence, entries, user):
    findings = []
    selected = {entry["selected_edition_id"] for entry in entries if entry["id"] in occurrence["entry_ids"] and entry.get("selected_edition_id")}
    if not selected:
        if any(entry.get("selected_private_source_id") for entry in entries if entry["id"] in occurrence["entry_ids"]):
            return []
        return [{"kind": "identity", "status": "unverified", "message": "引文尚未对应到确认的馆内版本。"}]
    quote = occurrence.get("quote", "")
    for edition_id in selected:
        edition = source_queryset("edition", access_for(user)).filter(pk=edition_id).first()
        if edition is None:
            findings.append({"kind": "fulltext", "status": "unverified", "edition_id": edition_id,
                "message": "该版本没有当前可访问的原文；书目匹配不证明引文或论断。"})
            continue
        if not quote:
            findings.append({"kind": "support", "status": "unverified", "edition_id": edition_id,
                "message": "未解析出直接引文；请选择原文后核对论断范围与归属。"})
            continue
        matches = _quote_matches(edition, quote, user)
        label_match = re.search(r"(?:[pP]{1,2}\.?|第)\s*(\d{1,5})(?:\s*页)?", occurrence["context"])
        claimed_label = label_match.group(1) if label_match else None
        resolved = [resolve_reference(ref, user) for ref in matches]
        same_page = not claimed_label or any(anchor.get("printed_label") == claimed_label
            for ref in resolved for anchor in ref.get("anchors", [ref]))
        findings.append({"kind": "direct_quote", "status": "text_match" if matches else "unverified",
            "edition_id": edition_id, "references": matches, "claimed_printed_label": claimed_label,
            "page_status": "matched" if claimed_label and matches and same_page else "needs_review" if claimed_label else "not_specified",
            "match_limits": {"max_adjacent_spans": 5, "max_matches": 10},
            "message": "已找到规范化文字匹配，仍须核对上下文、版本和转引。" if matches else "未命中原文；可能存在超出连续5段的引文、OCR 差异或版本差异，不能据此判为错误。"})
    return findings


@transaction.atomic
def create_audit(user, upload, data, *, parent_id=None, purpose="manuscript"):
    from .citation_sources import ready_sources, source_ids, source_quota
    if purpose not in {"manuscript", "private_source"} or (parent_id and purpose != "manuscript"):
        raise ValidationError({"purpose": "任务类型无效。"})
    if upload is None or upload.size > MAX_UPLOAD_BYTES:
        raise ValidationError({"file": "请上传不超过 12 MiB 的 DOCX 或 PDF。"})
    name = PurePath(str(upload.name)).name
    kind = name.rsplit(".", 1)[-1].lower()
    if kind not in {"docx", "pdf"}:
        raise ValidationError({"file": "只接受 DOCX 或 PDF。"})
    blob = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(blob) > MAX_UPLOAD_BYTES or (kind == "pdf" and not blob.startswith(b"%PDF-")) or (kind == "docx" and not blob.startswith(b"PK")):
        raise ValidationError({"file": "文件大小或格式不符。"})
    request_id = identifier(data.get("request_id"), "request_id")
    # Serialize per-owner idempotency without relying on a racy pre-insert lookup.
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    digest = hashlib.sha256(blob).hexdigest()
    parent_id = identifier(parent_id) if parent_id is not None else None
    selected_sources, scope = [], "public_library"
    source_title, source_citation = "", ""
    if purpose == "private_source":
        scan = data.get("scan_ocr", False)
        if not isinstance(scan, bool):
            raise ValidationError({"scan_ocr": "需要布尔值。"})
        checks = ["citation_identification", *(["scan_ocr"] if scan else [])]
        source_title, source_citation = text(data.get("title", ""), "title", 240), text(data.get("citation", ""), "citation", 2000)
        fingerprint_data = {"purpose": purpose, "filename": name, "content_hash": digest,
            "title": source_title, "citation": source_citation, "scan_ocr": scan}
    elif parent_id:
        changed_only = data.get("check_changed_only", True)
        if not isinstance(changed_only, bool):
            raise ValidationError({"check_changed_only": "需要布尔值。"})
        fingerprint_data = {"filename": name, "content_hash": digest, "parent_id": parent_id,
            "expected_revision": data.get("expected_revision"), "check_changed_only": changed_only}
    else:
        checks = audit_options(data)
        selected_sources, scope = source_ids(data), data.get("scope", "public_library")
        if bool(selected_sources) != (scope == "private_materials"):
            raise ValidationError({"private_source_ids": "私人范围须明确选择来源；仅公开馆藏时不能附带私人来源。"})
        fingerprint_data = {"filename": name, "content_hash": digest, "project_id": data.get("project_id")}
        # Keep legacy idempotency keys valid for unchanged default requests.
        if "checks" in data or "scope" in data:
            fingerprint_data.update(checks=checks, scope=scope)
        if selected_sources:
            fingerprint_data["private_source_ids"] = selected_sources
    fingerprint = request_fingerprint(fingerprint_data, tuple(fingerprint_data))
    existing = CitationAudit.objects.filter(user=user, request_id=request_id).first()
    if existing:
        if existing.content_hash != digest:
            raise ResearchConflict("该请求标识已用于另一份稿件。")
        return same_request(existing, fingerprint)
    parent, previous = None, None
    if parent_id:
        parent = owned(CitationAudit, user, parent_id, lock=True)
        if parent.purpose != "manuscript":
            raise NotFound("私人稿件不存在。")
        expect(parent, data.get("expected_revision"))
        previous = unpack(parent)
        if parent.status in ACTIVE or not previous.get("parsed"):
            raise ResearchConflict("请先完成或取消原稿检查，并取得已解析的稿件报告后再上传新版本。")
        checks = audit_options({"checks": previous.get("checks", list(UPLOAD_CHECKS)),
            "scope": previous.get("scope", "public_library")})
        scope, selected_sources = previous.get("scope", "public_library"), previous.get("private_source_ids", [])
    elif purpose == "private_source":
        source_quota(user, len(blob))
    elif selected_sources:
        ready_sources(user, selected_sources, strict=True)
    if CitationAudit.objects.filter(user=user, status__in=ACTIVE).count() >= MAX_ACTIVE_AUDITS_PER_OWNER:
        raise ResearchConflict("本人已有两项体检排队或运行，请等待完成或取消后再上传。")
    if "scan_ocr" in checks and not audit_capabilities()["ocr"]["available"]:
        raise ValidationError({"checks": "本版本继承的本地 OCR 暂不可用，请保留新稿并稍后重试。" if parent else "本地 OCR 暂不可用，请关闭扫描页识别或稍后重试。"})
    project = source_project(user, {"project_id": str(parent.project_id)} if parent and parent.project_id else {} if parent else data)
    payload = {"request_fingerprint": fingerprint, "purpose": purpose, "filename": name, "filetype": kind, "manuscript_revision": 1,
        "bibliography": [], "occurrences": [], "warnings": [], "external_metadata": False,
        "checks": checks, "scope": scope, "private_source_ids": selected_sources, "file_size_bytes": len(blob),
        "manuscript_stats": {"file_size_bytes": len(blob)},
        "checker_version": CHECKER_VERSION, "stage": "queued", "rerun_occurrence_ids": None}
    if purpose == "private_source":
        payload.update(title=source_title, citation=source_citation, segment_count=0, matchable_segment_count=0)
    if parent:
        payload["manuscript_revision"] = previous.get("manuscript_revision", 1) + 1
        payload["version_lineage"] = {"parent_audit_id": str(parent.id), "parent_revision": parent.revision,
            "ancestor_ids": [*previous.get("version_lineage", {}).get("ancestor_ids", []), str(parent.id)],
            "check_changed_only": changed_only}
        payload["version_comparison"] = {"status": "pending", "base_audit_id": str(parent.id),
            "notice": "完成新稿解析后，按引文内容、上下文及引用书目比较；原稿与旧报告保留。"}
        # The baseline is encrypted and immutable even if the owner later edits/deletes
        # the old report. Original bytes/OCR images are never copied between versions.
        payload["version_baseline"] = deepcopy({key: previous.get(key) for key in
            ("bibliography", "occurrences", "checker_version", "checks", "scope", "private_source_ids")})
        payload["version_baseline"]["checks"] = checks
    audit = CitationAudit.objects.create(user=user, project=project, request_id=request_id, purpose=purpose, file_size_bytes=len(blob),
        content_hash=digest, task_id=str(uuid4()), original_ciphertext=encrypt_private_text(base64.b64encode(blob).decode("ascii")),
        data_ciphertext=pack(payload))
    if parent:
        previous.setdefault("version_children", []).append(str(audit.id))
        save_data(parent, previous)
    from .tasks import enqueue_citation_audit
    transaction.on_commit(lambda: enqueue_citation_audit(audit.id, audit.generation, audit.task_id))
    return audit


def audit_versions(audit, user):
    """Follow only encrypted, owner-checked links; never scan other private jobs."""
    pending, visited, result = {str(audit.id)}, set(), []
    # ponytail: bounded graph walk covers normal histories without a new index/table.
    # Extremely large families remain accessible through the existing paginated task list.
    limit = 200
    while pending and len(visited) < limit:
        batch = sorted(pending)[:limit - len(visited)]
        pending.difference_update(batch)
        visited.update(batch)
        for record in CitationAudit.objects.filter(user=user, purpose="manuscript", pk__in=batch).defer("original_ciphertext").iterator(chunk_size=10):
            payload = unpack(record)
            lineage = payload.get("version_lineage", {})
            pending.update(set([*lineage.get("ancestor_ids", []), *payload.get("version_children", [])]) - visited)
            result.append({"id": str(record.id), "revision": record.revision,
                "manuscript_revision": payload.get("manuscript_revision", 1), "filename": payload.get("filename", ""),
                "status": record.status, "created_at": record.created_at.isoformat(),
                "finished_at": record.finished_at.isoformat() if record.finished_at else None,
                "parent_audit_id": lineage.get("parent_audit_id")})
    return {"current_id": str(audit.id), "versions": sorted(result, key=lambda row: row["created_at"], reverse=True),
        "truncated": bool(pending), "notice": ("仅列出可访问的关联版本；分支使用各自稿件版本号，旧原稿与报告独立保留。删除中间版本可能断开后续关联，仍存在的版本可从体检任务列表打开。"
            + ("此处最多显示 200 个关联记录，其余可从体检任务列表打开。" if pending else ""))}


def _entry_content(row):
    return json.dumps({key: row.get(key) for key in ("raw", "label", "doi", "kind", "field_item")},
        ensure_ascii=False, sort_keys=True)


def _occurrence_content(row):
    # Positions may move after an insertion; exact wording/context and source part
    # must still agree. No fuzzy match can carry a person's decision to another quote.
    return json.dumps({"part": row.get("location", {}).get("part"), **{key: row.get(key) for key in
        ("raw", "quote", "context", "labels", "author_date", "citation_field", "note_text")}},
        ensure_ascii=False, sort_keys=True)


def _catalog_identity_current(entry, edition):
    if edition is None:
        return False
    revision_id = entry.get("selected_catalog_revision_id")
    if revision_id:
        return revision_id == str(edition.active_catalog_revision_id)
    candidate = next((item for item in entry.get("candidates", []) if item.get("edition_id") == str(edition.id)), {})
    return bool(candidate.get("citation") and candidate["citation"] == format_gbt_7714_2025(edition, snapshot=edition.active_catalog_revision.snapshot))


def _revalidate_reused_occurrences(payload, user):
    """A resumed lease cannot trust evidence that was valid when parsing finished."""
    from .citation_sources import private_identity_current, ready_sources, resolve_private_reference
    entries = {entry["id"]: entry for entry in payload["bibliography"]}
    reused = [row for row in payload.get("occurrences", []) if row.get("reused_at")
        or any(finding.get("private_references") for finding in row.get("findings", []))
        or any(entries.get(key, {}).get("selected_private_source_id") for key in row.get("entry_ids", []))]
    if not reused:
        return
    allowed = payload.get("private_source_ids", []) if payload.get("scope") == "private_materials" else []
    private_sources = ready_sources(user, allowed)
    editions = {str(edition.id): edition for edition in public_editions().filter(
        pk__in=[entry["selected_edition_id"] for entry in entries.values() if entry.get("selected_edition_id")])}
    targets = payload.get("rerun_occurrence_ids")
    for row in reused:
        current = True
        for entry_id in row.get("entry_ids", []):
            entry = entries.get(entry_id)
            if entry is None:
                current = False
                continue
            selected = entry.get("selected_edition_id")
            if selected and not _catalog_identity_current(entry, editions.get(selected)):
                current = False
                if entry.get("identity_status") != "user_confirmed":
                    entry["version_rematch"] = True
            if entry.get("selected_private_source_id") and not private_identity_current(entry, private_sources):
                current = False
        refs = [ref for finding in row.get("findings", []) for ref in finding.get("references", [])]
        if row.get("support_analysis", {}).get("reference"):
            refs.append(row["support_analysis"]["reference"])
        if any(resolve_reference(ref, user)["source_status"] != "available" for ref in refs):
            current = False
        private_refs = [ref for finding in row.get("findings", []) for ref in finding.get("private_references", [])]
        if any(resolve_private_reference(ref, user, allowed, sources=private_sources)["source_status"] != "available" for ref in private_refs):
            current = False
        if current:
            continue
        if row.get("decision"):
            row.setdefault("decision_history", []).append(deepcopy(row["decision"]))
            row["decision"] = None
        row.pop("reused_at", None)
        row.pop("checked_generation", None)
        row["version_change"] = "evidence_changed"
        row["version_revalidated_at"] = timezone.now().isoformat()
        if row.get("support_analysis"):
            row["support_analysis"].update(status="source_unavailable", suggestions=[])
        if targets is not None and row["id"] not in targets:
            targets.append(row["id"])
    comparison = payload.get("version_comparison")
    if comparison:
        remaining = sum(bool(row.get("reused_at")) for row in payload["occurrences"])
        comparison.update(reused_occurrences=remaining, rechecked_occurrences=len(payload["occurrences"]) - remaining,
            changed_occurrences=sum(row.get("version_change") != "unchanged" for row in payload["occurrences"]))


def _compare_version(parsed, payload, user, generation):
    from .citation_sources import private_identity_current, ready_sources, resolve_private_reference
    baseline = payload["version_baseline"]
    lineage = payload["version_lineage"]
    changed_only = lineage["check_changed_only"]
    old_entries, old_rows = baseline.get("bibliography") or [], baseline.get("occurrences") or []
    old_entry_counts, new_entry_counts = Counter(map(_entry_content, old_entries)), Counter(map(_entry_content, parsed["bibliography"]))
    old_entries_by_content = {_entry_content(row): row for row in old_entries}
    existing_entry_ids = {row["id"] for row in payload.get("bibliography", [])}
    existing_contents = {_occurrence_content(row) for row in payload.get("occurrences", [])}
    available_editions = {str(edition.id): edition for edition in public_editions().filter(
        pk__in=[row["selected_edition_id"] for row in old_entries if row.get("selected_edition_id")])}
    allowed = payload.get("private_source_ids", []) if payload.get("scope") == "private_materials" else []
    private_sources = ready_sources(user, allowed)
    entry_map = {}
    for entry in parsed["bibliography"]:
        key = _entry_content(entry)
        if old_entry_counts[key] != 1 or new_entry_counts[key] != 1:
            continue
        old = old_entries_by_content[key]
        entry_map[old["id"]] = entry["id"]
        if entry["id"] in existing_entry_ids:
            continue  # Current-version owner edits outrank the immutable parent snapshot.
        entry["inherited_from"] = {"audit_id": lineage["parent_audit_id"], "entry_id": old["id"]}
        entry["history"] = deepcopy(old.get("history", []))
        selected = old.get("selected_edition_id")
        if old.get("selected_private_source_id") and private_identity_current(old, private_sources):
            entry.update(deepcopy({name: old[name] for name in ("identity_status", "selected_edition_id",
                "selected_private_source_id", "selected_private_source_generation", "selected_private_source_hash") if name in old}))
        elif selected in available_editions or old.get("identity_status") == "not_requested":
            entry.update(deepcopy({name: old[name] for name in
                ("identity_status", "selected_edition_id", "selected_catalog_revision_id", "candidates", "identity_hints") if name in old}))
            if not changed_only and old.get("identity_status") != "user_confirmed" and "bibliography_identity" in payload["checks"]:
                entry["version_rematch"] = True
        elif selected or old.get("selected_private_source_id"):
            entry["history"].append({"selected_edition_id": selected, "selected_private_source_id": old.get("selected_private_source_id"), "identity_status": old.get("identity_status"),
                "reason": "new_version_requires_matching", "audit_id": lineage["parent_audit_id"]})
    old_counts, new_counts = Counter(map(_occurrence_content, old_rows)), Counter(map(_occurrence_content, parsed["occurrences"]))
    old_by_content = {_occurrence_content(row): row for row in old_rows}
    old_by_id = {row["id"]: row for row in old_entries}
    new_by_id = {row["id"]: row for row in parsed["bibliography"]}
    targets, reused = [], 0
    for row in parsed["occurrences"]:
        key = _occurrence_content(row)
        old = old_by_content.get(key)
        unique = old_counts[key] == 1 and new_counts[key] == 1
        row["version_change"] = "ambiguous" if old and not unique else "added"
        if not unique:
            targets.append(row["id"])
            continue
        linked = old.get("entry_ids", [])
        mapped = [entry_map[value] for value in linked if value in entry_map]
        complete_links = len(mapped) == len(linked)
        if old.get("entry_link") and complete_links and old_entry_counts == new_entry_counts and key not in existing_contents:
            row["entry_ids"] = mapped
        unchanged = complete_links and set(mapped) == set(row.get("entry_ids", []))
        if old.get("entry_link") and old_entry_counts != new_entry_counts:
            unchanged = False
        evidence_current = unchanged
        for old_id, new_id in zip(linked, mapped) if complete_links else []:
            selected = old_by_id[old_id].get("selected_edition_id")
            private_id = old_by_id[old_id].get("selected_private_source_id")
            if private_id and (not private_identity_current(old_by_id[old_id], private_sources)
                    or new_by_id[new_id].get("selected_private_source_id") != private_id):
                evidence_current = False
            if selected and (selected not in available_editions or new_by_id[new_id].get("selected_edition_id") != selected):
                evidence_current = False
            elif selected:
                # Legacy matches can only be reused when their saved citation agrees
                # with the current public catalog snapshot. Missing proof means recheck.
                if not _catalog_identity_current(old_by_id[old_id], available_editions[selected]):
                    evidence_current = False
                    if new_by_id[new_id].get("identity_status") != "user_confirmed":
                        new_by_id[new_id]["version_rematch"] = True
        references = [ref for finding in old.get("findings", []) for ref in finding.get("references", [])]
        if old.get("support_analysis", {}).get("reference"):
            references.append(old["support_analysis"]["reference"])
        if evidence_current and any(resolve_reference(ref, user)["source_status"] != "available" for ref in references):
            evidence_current = False
        private_refs = [ref for finding in old.get("findings", []) for ref in finding.get("private_references", [])]
        if evidence_current and any(resolve_private_reference(ref, user, allowed, sources=private_sources)["source_status"] != "available" for ref in private_refs):
            evidence_current = False
        row["version_change"] = "bibliography_changed" if not unchanged else "evidence_changed" if not evidence_current else "unchanged"
        if unchanged:
            row["inherited_from"] = {"audit_id": lineage["parent_audit_id"], "occurrence_id": old["id"]}
        if evidence_current and key not in existing_contents:
            row.update(deepcopy({name: old[name] for name in ("decision", "decision_history", "history", "link_history") if name in old}))
            if old.get("entry_link"):
                row["entry_link"] = {**deepcopy(old["entry_link"]), "entry_ids": mapped}
        # Unfinished/negative checks can change when the corpus or OCR coverage grows.
        # Recheck them even when the manuscript text itself is unchanged.
        reusable = (evidence_current and changed_only and bool(old.get("checked_at"))
            and baseline.get("checker_version") == CHECKER_VERSION and baseline.get("checks") == payload.get("checks")
            and baseline.get("scope", "public_library") == payload.get("scope", "public_library")
            and set(baseline.get("private_source_ids") or []) == set(allowed)
            and key not in existing_contents
            and not any(finding.get("status") == "unverified" for finding in old.get("findings", []))
            and all(old_by_id[value].get("identity_status") in {"user_confirmed", "private_confirmed", "identifier_matched", "not_requested"} for value in linked))
        if reusable:
            row.update(deepcopy({name: old[name] for name in ("findings", "support_analysis", "checked_at", "checker_version") if name in old}))
            row["checked_generation"] = generation
            row["reused_at"] = timezone.now().isoformat()
            reused += 1
        else:
            targets.append(row["id"])
    payload["rerun_occurrence_ids"] = targets
    payload["version_comparison"] = {"status": "completed", "base_audit_id": lineage["parent_audit_id"],
        "total_occurrences": len(parsed["occurrences"]), "changed_occurrences": sum(row["version_change"] != "unchanged" for row in parsed["occurrences"]),
        "reused_occurrences": reused, "added_occurrences": sum((new_counts - old_counts).values()),
        "removed_occurrences": sum((old_counts - new_counts).values()),
        "ambiguous_occurrences": sum(row["version_change"] == "ambiguous" for row in parsed["occurrences"]),
        "changed_bibliography_entries": sum((new_entry_counts - old_entry_counts).values()) + sum((old_entry_counts - new_entry_counts).values()),
        "rechecked_occurrences": len(targets),
        "notice": "按文字、上下文和引用书目精确比较；内容改写计为旧位置移除及新位置加入，重复歧义、书目变化和失效依据重新检查。重查数量为本轮处理范围，进度以任务状态为准。"}


def process_audit(audit_id, generation, task_id):
    claimed = CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status="queued").update(
        status="running", updated_at=timezone.now())
    if not claimed:
        return
    audit = CitationAudit.objects.select_related("user").filter(pk=audit_id, generation=generation, task_id=task_id).first()
    if audit is None:
        return
    payload = unpack(audit)
    # Rows created before explicit options retain their original OCR behavior.
    checks = payload.get("checks", list(UPLOAD_CHECKS))
    if not payload.get("parsed"):
        blob = base64.b64decode(decrypt_private_text(audit.original_ciphertext))
        if "source_paragraphs" not in payload:
            payload["source_paragraphs"] = parse_docx(blob) if payload["filetype"] == "docx" else parse_pdf(blob)
            paragraphs = payload["source_paragraphs"]
            payload["manuscript_stats"] = {"file_size_bytes": len(blob), "text_unit_count": len(paragraphs),
                "paragraph_count": len(paragraphs) if payload["filetype"] == "docx" else None,
                "char_count": sum(len(row["text"]) for row in paragraphs),
                "pdf_page_count": len(paragraphs) if payload["filetype"] == "pdf" else None,
                "embedded_image_count": sum(row.get("embedded_image_count", len(row.get("embedded_images", []))) for row in paragraphs)}
            if not _checkpoint(audit_id, generation, task_id, payload, 0, 0, "parsing"):
                return
        from .private_ocr import enrich_private_manuscript
        cache = payload.setdefault("ocr_units", {})
        def checkpoint_ocr(units, completed, total):
            payload["ocr_units"] = units
            payload["ocr_progress"] = {"processed": completed, "total": total,
                **{state: sum(row.get("status") == state for row in units.values()) for state in ("completed", "failed", "no_text")}}
            return _checkpoint(audit_id, generation, task_id, payload, completed, total, "ocr")
        if "scan_ocr" in checks:
            enriched = enrich_private_manuscript(blob=blob, kind=payload["filetype"], paragraphs=payload["source_paragraphs"],
                cache=cache, generation=generation, checkpoint=checkpoint_ocr,
                is_current=lambda: CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status="running").exists())
        else:
            needs_ocr = any(row.get("needs_ocr") or row.get("embedded_images") for row in payload["source_paragraphs"])
            enriched = (payload["source_paragraphs"], [{"code": "scan_ocr_not_requested",
                "message": "本次未选择扫描页识别；扫描页及嵌入图像未核查，请对照原稿。"}] if needs_ocr else [], False)
        if enriched is None:
            return
        paragraphs, ocr_warnings, remaining = enriched
        if remaining:
            with transaction.atomic():
                current = CitationAudit.objects.select_for_update().filter(pk=audit_id, generation=generation, task_id=task_id, status="running").first()
                if current:
                    current.status, current.task_id = "queued", str(uuid4())
                    save_data(current, payload, fields=["status", "task_id"])
                    from .tasks import enqueue_citation_audit
                    transaction.on_commit(lambda: enqueue_citation_audit(current.id, generation, current.task_id))
            return
        from .citation_sources import text_units
        if sum(len(row["text"]) for row in paragraphs) > MAX_TEXT_CHARS:
            raise ValidationError({"file": "解析文字超过本轮处理上限；原件与已取得的 OCR 结果保留。"})
        payload["text_units"] = text_units(paragraphs)
        payload["text_generation"] = generation
        if audit.purpose == "private_source":
            parsed = {"bibliography": [], "occurrences": [], "warnings": []}
            if not any(row["text"].strip() for row in paragraphs):
                parsed["warnings"].append({"code": "private_source_no_text", "message": "尚未取得可核对文字；原件保留，请对照本地 OCR 状态。"})
            payload["segment_count"] = len(payload["text_units"])
            payload["matchable_segment_count"] = sum(bool(unit["matchable"] and unit["text"].strip()) for unit in payload["text_units"])
        else:
            parsed = parse_manuscript(blob, payload["filetype"], paragraphs=paragraphs)
            _preserve_parser_decisions(parsed, payload)
            if payload.get("version_baseline"):
                _compare_version(parsed, payload, audit.user, generation)
        payload.update(parsed)
        payload["warnings"] = [*payload["warnings"], *ocr_warnings]
        payload["parsed"] = True
        payload.setdefault("manuscript_stats", {}).update(char_count=sum(len(row["text"]) for row in paragraphs),
            occurrence_count=len(payload["occurrences"]), bibliography_count=len(payload["bibliography"]))
        if not _checkpoint(audit_id, generation, task_id, payload, 0, len(payload["bibliography"]), "matching"):
            return
    if audit.purpose == "private_source":
        with transaction.atomic():
            current = CitationAudit.objects.select_for_update().filter(pk=audit_id, generation=generation, task_id=task_id, status="running").first()
            if current:
                current.status, current.finished_at = "partial" if payload["warnings"] else "completed", timezone.now()
                current.completed_units = current.total_units = len(payload.get("text_units", []))
                payload.update(stage="source_ready", source_generation=generation)
                save_data(current, payload, fields=["status", "finished_at", "completed_units", "total_units"])
        return
    from .citation_sources import check_private_occurrence, current_sources, ready_sources, source_candidate
    selected_private_ids = payload.get("private_source_ids", []) if payload.get("scope") == "private_materials" else []
    private_sources = ready_sources(audit.user, selected_private_ids)
    payload["warnings"] = [warning for warning in payload["warnings"] if warning.get("code") != "private_source_unavailable"]
    if set(selected_private_ids) != set(private_sources):
        payload["warnings"].append({"code": "private_source_unavailable", "message": "部分已选私人来源已删除、正在处理或没有可核对文字；本次报告不代表已覆盖这些来源。"})
    for entry in payload["bibliography"]:
        entry["private_candidates"] = [source_candidate(key, private_sources) for key in selected_private_ids]
    # Pending identities survive cancellation or a matching failure; retries do not
    # discard an already confirmed version or repeat completed catalog scans.
    _revalidate_reused_occurrences(payload, audit.user)
    pending_entries = [entry for entry in payload["bibliography"] if entry["identity_status"] == "pending" or entry.get("version_rematch")]
    for index, entry in enumerate(pending_entries):
        if not CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status="running").exists():
            return
        if "bibliography_identity" in checks:
            # Stream catalog rows: the full published corpus must not reside in every private worker.
            previous_selection = entry.get("selected_edition_id")
            match_bibliography(entry, public_editions().iterator(chunk_size=200))
            if entry.pop("version_rematch", False) and entry.get("selected_edition_id") != previous_selection:
                targets = payload.get("rerun_occurrence_ids")
                for row in payload["occurrences"]:
                    if entry["id"] not in row["entry_ids"]:
                        continue
                    if row.get("decision"):
                        row.setdefault("decision_history", []).append(row.pop("decision"))
                        row["decision"] = None
                    row["version_change"] = "evidence_changed"
                    if targets is not None and row["id"] not in targets:
                        targets.append(row["id"])
                comparison = payload.get("version_comparison")
                if comparison and targets is not None:
                    comparison.update(changed_occurrences=sum(row.get("version_change") != "unchanged" for row in payload["occurrences"]),
                        rechecked_occurrences=len(targets), reused_occurrences=len(payload["occurrences"]) - len(targets))
        else:
            entry["identity_status"] = "not_requested"
            entry.pop("version_rematch", None)
        if not _checkpoint(audit_id, generation, task_id, payload, index + 1, len(pending_entries), "matching"):
            return
    selected_ids = payload.get("rerun_occurrence_ids")
    selected = [row for row in payload["occurrences"] if selected_ids is None or row["id"] in selected_ids]
    total = len(selected)
    # Persist parser/matches first so cancellation and a failed model preserve completed work.
    if not _checkpoint(audit_id, generation, task_id, payload, 0, total, "checking"):
        return
    for index, occurrence in enumerate(selected):
        if not CitationAudit.objects.filter(pk=audit_id, generation=generation, task_id=task_id, status="running").exists():
            return
        if occurrence.get("checked_at"):
            occurrence.setdefault("history", []).append({"generation": occurrence.get("checked_generation", generation - 1),
                "checked_at": occurrence["checked_at"], "findings": occurrence.get("findings", []),
                "support_analysis": occurrence.get("support_analysis"), "decision": occurrence.get("decision")})
        occurrence.pop("reused_at", None)
        occurrence["findings"] = check_occurrence(occurrence, payload["bibliography"], audit.user) if "version_page" in checks else []
        if "version_page" in checks and selected_private_ids:
            # The owner grant is re-read per occurrence so a source deleted/reparsed
            # during a long task cannot keep supplying private text from a cache.
            occurrence["findings"].extend(check_private_occurrence(occurrence, payload["bibliography"], current_sources(audit.user, private_sources)))
        requested_ref = payload.get("support_requests", {}).get(occurrence["id"])
        if requested_ref:
            reference = resolve_reference(requested_ref, audit.user)
            if reference["source_status"] == "available":
                from .local_analysis import analyze_local_relations
                suggestions, model = analyze_local_relations({"proposition": occurrence["context"]},
                    [{"reference_id": "selected", "quote": reference["quote"]}])
                occurrence["support_analysis"] = {"reference": compact_reference(reference), "model": model,
                    "suggestions": suggestions, "status": "needs_review" if suggestions else "unverified"}
            else:
                occurrence["support_analysis"] = {"reference": requested_ref, "suggestions": [], "status": "source_unavailable"}
        occurrence["checker_version"] = CHECKER_VERSION
        occurrence["checked_generation"] = generation
        occurrence["checked_at"] = timezone.now().isoformat()
        # Every item is a recovery point. Human decisions are held separately.
        if not _checkpoint(audit_id, generation, task_id, payload, index + 1, total, "checking"):
            return
    payload["stage"] = "report"
    payload["report_notice"] = "没有总分；分别呈现书目身份、原文匹配、页码与论断关系。未命中不等于未收录，也不等于引文错误。"
    payload["rerun_occurrence_ids"] = None
    if payload.get("version_comparison"):
        remaining = sum(bool(row.get("reused_at")) for row in payload["occurrences"])
        payload["version_comparison"].update(reused_occurrences=remaining,
            rechecked_occurrences=len(payload["occurrences"]) - remaining)
    incomplete = bool(payload["warnings"]) or any(entry["identity_status"] in {"needs_review", "not_matched_in_library"} for entry in payload["bibliography"])
    incomplete = incomplete or any(finding["status"] == "unverified" or finding.get("page_status") == "needs_review"
        for row in payload["occurrences"] for finding in row["findings"])
    incomplete = incomplete or any(row.get("support_analysis", {}).get("status") in {"unverified", "source_unavailable", "needs_review"}
        for row in payload["occurrences"])
    with transaction.atomic():
        current = CitationAudit.objects.select_for_update().filter(pk=audit_id, generation=generation, task_id=task_id, status="running").first()
        if current:
            current.status, current.finished_at = "partial" if incomplete else "completed", timezone.now()
            save_data(current, payload, fields=["status", "finished_at"])


def _checkpoint(audit_id, generation, task_id, payload, completed, total, stage):
    with transaction.atomic():
        audit = CitationAudit.objects.select_for_update().filter(pk=audit_id, generation=generation, task_id=task_id, status="running").first()
        if audit is None:
            return False
        payload["stage"] = stage
        audit.completed_units, audit.total_units = completed, total
        save_data(audit, payload, fields=["completed_units", "total_units"])
    return True


def _preserve_parser_decisions(parsed, previous):
    entry_key = _entry_content
    old_entries = {entry_key(row): row for row in previous.get("bibliography", [])}
    old_entry_counts = Counter(entry_key(row) for row in previous.get("bibliography", []))
    new_entry_counts = Counter(entry_key(row) for row in parsed["bibliography"])
    id_map = {}
    for entry in parsed["bibliography"]:
        key = entry_key(entry)
        old = old_entries.get(key)
        if old and old_entry_counts[key] == new_entry_counts[key] == 1:
            id_map[entry["id"]] = old["id"]
            entry.update(deepcopy({name: old[name] for name in ("id", "identity_status", "selected_edition_id", "selected_catalog_revision_id", "selected_private_source_id", "selected_private_source_generation", "selected_private_source_hash", "history", "candidates", "inherited_from") if name in old}))
    occurrence_key = _occurrence_content
    old_occurrences = {occurrence_key(row): row for row in previous.get("occurrences", [])}
    old_counts = Counter(occurrence_key(row) for row in previous.get("occurrences", []))
    new_counts = Counter(occurrence_key(row) for row in parsed["occurrences"])
    available_ids = {entry["id"] for entry in parsed["bibliography"]}
    for occurrence in parsed["occurrences"]:
        occurrence["entry_ids"] = [id_map.get(value, value) for value in occurrence["entry_ids"]]
        key = occurrence_key(occurrence)
        old = old_occurrences.get(key)
        if not old or old_counts[key] != 1 or new_counts[key] != 1:
            continue
        selected = old.get("entry_link", {}).get("entry_ids", old.get("entry_ids", []))
        if not set(selected).issubset(available_ids):
            continue
        if old.get("entry_link") and old_entry_counts != new_entry_counts:
            continue
        if not old.get("entry_link") and set(selected) != set(occurrence["entry_ids"]):
            continue
        occurrence.update(deepcopy({name: old[name] for name in ("id", "decision", "decision_history", "findings", "history", "checked_at", "checked_generation", "support_analysis", "entry_link", "link_history", "inherited_from", "version_change", "reused_at") if name in old}))
        if old.get("entry_link"):
            occurrence["entry_ids"] = list(selected)
            occurrence["entry_link"]["status"] = "preserved"
    if previous.get("occurrences") or previous.get("bibliography"):
        previous.setdefault("parse_history", []).append(deepcopy({"bibliography": previous.get("bibliography", []),
            "occurrences": previous.get("occurrences", []), "at": timezone.now().isoformat()}))


@transaction.atomic
def update_audit(user, pk, data, *, purpose="manuscript"):
    # Upload, commands and automatic recovery all serialize owner before audit.
    from django.contrib.auth import get_user_model
    get_user_model().objects.select_for_update().get(pk=user.pk)
    audit = owned(CitationAudit, user, pk, lock=True)
    if audit.purpose != purpose:
        raise NotFound("私人记录类型不符。")
    expect(audit, data.get("expected_revision"))
    payload = unpack(audit)
    action = data.get("action")
    if purpose == "private_source" and action not in {"cancel", "retry"}:
        raise ValidationError({"action": "私人来源支持取消和重试；更换原件请另行上传。"})
    if action == "cancel":
        if audit.status in ACTIVE:
            payload["interrupted_generation"] = audit.generation
            audit.status, audit.finished_at = "canceled", timezone.now()
            audit.generation += 1
        return save_data(audit, payload, fields=["status", "finished_at", "generation"])
    if audit.status in ACTIVE:
        raise ResearchConflict("任务正在处理，请先取消或等候结束后修改。")
    changed_basis_ids = []
    if action == "sources":
        from .citation_sources import ready_sources, source_ids
        if "private_source_ids" not in data:
            raise ValidationError({"private_source_ids": "请明确提交完整的来源名单；空列表表示移除全部私人来源。"})
        selected = source_ids(data)
        ready_sources(user, selected, strict=True)
        removed = set(payload.get("private_source_ids", [])) - set(selected)
        removed_entries = {entry["id"] for entry in payload["bibliography"] if entry.get("selected_private_source_id") in removed}
        payload["private_source_ids"], payload["scope"] = selected, "private_materials" if selected else "public_library"
        for entry in payload["bibliography"]:
            if entry.get("selected_private_source_id") in removed:
                entry.setdefault("history", []).append({"at": timezone.now().isoformat(), "reason": "private_source_removed",
                    "selected_private_source_id": entry["selected_private_source_id"], "identity_status": entry["identity_status"]})
                for key in ("selected_private_source_id", "selected_private_source_generation", "selected_private_source_hash"):
                    entry.pop(key, None)
                entry["identity_status"] = "pending"
        for row in payload["occurrences"]:
            if removed_entries.intersection(row["entry_ids"]) or any(ref.get("source_id") in removed for finding in row.get("findings", []) for ref in finding.get("private_references", [])):
                if row.get("decision"):
                    row.setdefault("decision_history", []).append(deepcopy(row["decision"]))
                    row["decision"] = None
                row["version_change"] = "evidence_changed"
        payload["rerun_occurrence_ids"] = None
    elif action == "match_private":
        from .citation_sources import ready_sources
        entry = next((row for row in payload["bibliography"] if row["id"] == data.get("entry_id")), None)
        source_id = identifier(data.get("source_id"), "source_id")
        if entry is None:
            raise NotFound("参考文献条目不存在。")
        if payload.get("scope") != "private_materials" or source_id not in payload.get("private_source_ids", []):
            raise ValidationError({"source_id": "只能确认本次明确选择的本人私人来源。"})
        source, _ = ready_sources(user, [source_id], strict=True)[source_id]
        selection_changed = (entry.get("selected_private_source_id") != source_id
            or entry.get("selected_private_source_generation") != source.generation
            or entry.get("selected_private_source_hash") != source.content_hash or bool(entry.get("selected_edition_id")))
        entry.setdefault("history", []).append({"at": timezone.now().isoformat(),
            "selected_edition_id": entry.get("selected_edition_id"), "selected_private_source_id": entry.get("selected_private_source_id"),
            "identity_status": entry["identity_status"]})
        entry.update(identity_status="private_confirmed", selected_edition_id=None,
            selected_private_source_id=source_id, selected_private_source_generation=source.generation,
            selected_private_source_hash=source.content_hash)
        entry.pop("selected_catalog_revision_id", None)
        payload["rerun_occurrence_ids"] = [row["id"] for row in payload["occurrences"] if entry["id"] in row["entry_ids"]]
        if selection_changed:
            changed_basis_ids = payload["rerun_occurrence_ids"]
    elif action == "match":
        entry = next((row for row in payload["bibliography"] if row["id"] == data.get("entry_id")), None)
        if entry is None:
            raise NotFound("参考文献条目不存在。")
        edition = public_editions().filter(pk=identifier(data.get("edition_id"), "edition_id")).first()
        if edition is None:
            raise ValidationError({"edition_id": "馆内书目不可访问。"})
        selection_changed = (entry.get("selected_edition_id") != str(edition.id)
            or not _catalog_identity_current(entry, edition) or bool(entry.get("selected_private_source_id")))
        entry.setdefault("history", []).append({"at": timezone.now().isoformat(),
            "selected_edition_id": entry.get("selected_edition_id"), "selected_private_source_id": entry.get("selected_private_source_id"),
            "identity_status": entry["identity_status"]})
        for key in ("selected_private_source_id", "selected_private_source_generation", "selected_private_source_hash"):
            entry.pop(key, None)
        entry["selected_edition_id"], entry["identity_status"] = str(edition.id), "user_confirmed"
        entry["selected_catalog_revision_id"] = str(edition.active_catalog_revision_id)
        payload["rerun_occurrence_ids"] = [row["id"] for row in payload["occurrences"] if entry["id"] in row["entry_ids"]]
        if selection_changed:
            changed_basis_ids = payload["rerun_occurrence_ids"]
    elif action == "decision":
        if ("occurrence_id" in data) == ("occurrence_ids" in data):
            raise ValidationError({"occurrence_ids": "请选择单条或批量引文位置，不能同时提交。"})
        selected = data.get("occurrence_ids", [data.get("occurrence_id")])
        if not isinstance(selected, list) or not selected or len(selected) > MAX_OCCURRENCES:
            raise ValidationError({"occurrence_ids": "请选择 1—1000 个引文位置。"})
        identifiers = {identifier(value, "occurrence_ids") for value in selected}
        rows = [row for row in payload["occurrences"] if row["id"] in identifiers]
        if len(rows) != len(identifiers):
            raise NotFound("部分引文位置不存在；本次决定未保存。")
        decision = data.get("decision")
        if decision not in {"accepted", "ignored", "corrected", "needs_review"}:
            raise ValidationError({"decision": "决定类型无效。"})
        note = text(data.get("note", ""), "note", 4000)
        corrected = text(data.get("corrected_text", ""), "corrected_text", 4000)
        if corrected and (decision != "corrected" or len(rows) != 1):
            raise ValidationError({"corrected_text": "校正文案仅用于单条引文的已校正决定。"})
        for row in rows:
            if row.get("decision"):
                row.setdefault("decision_history", []).append(row["decision"])
            row["decision"] = {"value": decision, "note": note, "at": timezone.now().isoformat()}
            if "corrected_text" in data:
                row["decision"]["corrected_text"] = corrected
        return save_data(audit, payload)
    elif action == "link":
        row = next((row for row in payload["occurrences"] if row["id"] == data.get("occurrence_id")), None)
        entries = set(data.get("entry_ids", []))
        if row is None or "entry_ids" not in data or not entries.issubset({entry["id"] for entry in payload["bibliography"]}):
            raise ValidationError({"entry_ids": "引文或书目对应关系无效。"})
        if set(row["entry_ids"]) != entries:
            changed_basis_ids = [row["id"]]
        row.setdefault("link_history", []).append({"entry_ids": row["entry_ids"], "at": timezone.now().isoformat()})
        row["entry_ids"] = list(entries)
        row["entry_link"] = {"by": "owner", "entry_ids": list(entries), "status": "confirmed", "at": timezone.now().isoformat()}
        payload["rerun_occurrence_ids"] = [row["id"]]
    elif action == "analyze":
        row = next((row for row in payload["occurrences"] if row["id"] == data.get("occurrence_id")), None)
        if row is None:
            raise NotFound("引文位置不存在。")
        if not audit_capabilities()["analysis"]["available"]:
            raise ValidationError({"action": "本地关系分析暂不可用；已保存的原稿和检查结果保留。"})
        reference = resolve_reference(data.get("reference"), user, strict=True)
        payload.setdefault("support_requests", {})[row["id"]] = compact_reference(reference)
        payload["rerun_occurrence_ids"] = [row["id"]]
    elif action == "retry":
        if purpose == "private_source" or any(unit.get("status") in {"failed", "no_text"} for unit in payload.get("ocr_units", {}).values()):
            payload["parsed"] = False
        if not payload.get("parsed"):
            payload["rerun_occurrence_ids"] = None
        elif "occurrence_ids" in data:
            payload["rerun_occurrence_ids"] = data["occurrence_ids"]
        elif audit.status in {"failed", "canceled"}:
            previous_targets = payload.get("rerun_occurrence_ids")
            completed_generation = payload.pop("interrupted_generation", audit.generation)
            payload["rerun_occurrence_ids"] = [row["id"] for row in payload["occurrences"]
                if (previous_targets is None or row["id"] in previous_targets) and row.get("checked_generation") != completed_generation]
        else:
            payload["rerun_occurrence_ids"] = None
        if payload["rerun_occurrence_ids"] is not None and (not isinstance(payload["rerun_occurrence_ids"], list)
                or not set(payload["rerun_occurrence_ids"]).issubset({row["id"] for row in payload["occurrences"]})):
            raise ValidationError({"occurrence_ids": "重跑范围无效。"})
    else:
        raise ValidationError({"action": "请选择已开放的体检操作。"})
    # A decision belongs to the source/version and bibliography link the owner saw.
    # Rechecking another source must not retain its old accepted/corrected state.
    for row in payload["occurrences"]:
        if row["id"] in changed_basis_ids:
            if row.get("decision"):
                row.setdefault("decision_history", []).append(deepcopy(row["decision"]))
                row["decision"] = None
            row.pop("reused_at", None)
            row["version_change"] = "evidence_changed"
    if CitationAudit.objects.filter(user=user, status__in=ACTIVE).exclude(pk=audit.pk).count() >= MAX_ACTIVE_AUDITS_PER_OWNER:
        raise ResearchConflict("本人已有两项体检排队或运行，请等待完成或取消后再继续。")
    audit.status, audit.error_code, audit.finished_at = "queued", "", None
    audit.completed_units = 0
    selected_ids = payload.get("rerun_occurrence_ids")
    audit.total_units = len(selected_ids) if selected_ids is not None else len(payload.get("occurrences", []))
    payload["stage"] = "queued"
    payload["recovery_attempts"] = 0
    payload.pop("interrupted_generation", None)
    audit.generation += 1
    audit.task_id = str(uuid4())
    save_data(audit, payload, fields=["status", "error_code", "finished_at", "generation", "task_id", "completed_units", "total_units"])
    from .tasks import enqueue_citation_audit
    transaction.on_commit(lambda: enqueue_citation_audit(audit.id, audit.generation, audit.task_id))
    return audit


def original_document(audit):
    return base64.b64decode(decrypt_private_text(audit.original_ciphertext))


def refresh_bibliography_sources(payload):
    """Rehydrate public metadata on read; private raw entries and human choices remain intact."""
    from django.urls import reverse
    entries = [*payload.get("bibliography", []),
        *(entry for report in payload.get("parse_history", []) for entry in report.get("bibliography", []))]
    ids = {candidate["edition_id"] for entry in entries for candidate in entry.get("candidates", [])}
    ids.update(entry["selected_edition_id"] for entry in entries if entry.get("selected_edition_id"))
    editions = {str(row.id): row for row in public_editions().filter(pk__in=ids)}
    for entry in entries:
        candidates = list(entry.get("candidates", []))
        selected = entry.get("selected_edition_id")
        if selected and not any(candidate["edition_id"] == selected for candidate in candidates):
            candidates.append({"edition_id": selected, "basis": "owner_selected"})
        refreshed = []
        for candidate in candidates:
            edition = editions.get(candidate["edition_id"])
            if edition is None:
                refreshed.append({"edition_id": candidate["edition_id"], "source_status": "source_unavailable",
                    "title": "该馆藏版本当前不可访问", "basis": candidate.get("basis", ""),
                    "authors": [], "cover_url": None, "citation": "", "year": None, "version_label": ""})
                continue
            snapshot = edition.active_catalog_revision.snapshot or {}
            work, values = snapshot.get("work") or {}, snapshot.get("edition") or {}
            media = work.get("cover_media") or {}
            authors = [str(row.get("name") or (row.get("person") or {}).get("preferred_name") or "")
                for row in (snapshot.get("contributions", snapshot.get("contributors")) or [])
                if isinstance(row, dict) and row.get("role") == "author"]
            signals = _identity_signals(_bibliography_identity(entry), entry["raw"], snapshot)
            refreshed.append({**candidate, "source_status": "available", "work_id": str(edition.work_id),
                "title": work.get("title", ""), "authors": [value for value in authors if value],
                "year": values.get("publication_year"), "version_label": values.get("version_label", ""),
                "identity_signals": signals,
                "review_fields": [key for key, signal in signals.items() if signal["status"] in {"conflict", "needs_review"}],
                "citation": format_gbt_7714_2025(edition, snapshot=snapshot),
                "cover_url": (reverse("public-work-cover", kwargs={"work_id": edition.work_id})
                    + (f"?rendition={media['primary_rendition_id']}" if media.get("primary_rendition_id") else ""))
                    if media or work.get("cover") else None})
        entry["candidates"] = refreshed
        entry["selected_source_status"] = "available" if selected in editions else "source_unavailable" if selected else "not_selected"
