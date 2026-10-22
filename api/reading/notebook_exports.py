"""Explicit, bounded downloads of the owner's original reading records."""
import html
import json
import re
from hashlib import sha256

from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError

from catalog.models import Edition
from catalog.services.citations import citation_bundle
from catalog.services.publication_eligibility import public_edition_q
from . import notebook, privacy, research
from .booklist_exports import bib, clean, pdf_bytes


def project(user, data):
    records = []
    for target in data["targets"]:
        row = privacy.verify_target(user, target)
        value = notebook.record(user, target["category"], row)
        raw = value["source"]
        current = research.resolve_reference(research.compact_reference(raw), AnonymousUser()) if raw.get("source_status") == "available" else {"source_status": "unavailable"}
        edition = Edition.objects.filter(public_edition_q(), pk=current["edition_id"]).select_related("active_catalog_revision").first() if current["source_status"] == "available" else None
        label = current.get("printed_label") or ""
        bundle = citation_bundle(edition, label, snapshot=edition.active_catalog_revision.snapshot) if edition else {}
        if data["format"] in {"ris", "bibtex"} and not edition:
            raise ValidationError("所选记录含不可核对的来源。请重新选择，或用 PDF/Markdown 保留本人记录；不会编造文献信息。")
        records.append({"category": value["category"], "id": value["id"], "revision": value["revision"],
            "kind": value["kind"], "title": value["work"]["title"], "pdf_page": value["pdf_page"], "printed_label": label,
            "label": value["label"], "source_available": bool(edition), "citation": bundle.get("gbt7714-2025", "当前来源不可核对"),
            "csl": bundle.get("csl", {}), "reference": research.compact_reference(current) if edition else None,
            "saved_quote": value["saved_quote"] if data["include_quotes"] else "",
            "body": value["body"] if data["include_notes"] else "", "tags": value["tags"] if data["include_notes"] else [],
            "created_at": value["created_at"].isoformat(), "updated_at": value["updated_at"].isoformat()})
    if len(json.dumps(records, ensure_ascii=False)) > 200000:
        raise ValidationError("本次文字超过20万字符，请分批导出，或使用隐私与资料的完整 JSON 导出。")
    return records


def digest(records):
    return sha256(json.dumps(records, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def content_lines(row):
    lines = [row["citation"], f"PDF 第 {row['pdf_page']} 页" + (f" · 书内页码 {row['printed_label']}" if row["printed_label"] else "")]
    if row["label"]:
        lines += ["书签名称", row["label"]]
    if row["saved_quote"]:
        lines += ["保存时的原文摘录（个人记录，不代表当前原文核验）", row["saved_quote"]]
    if row["body"]:
        lines += ["本人笔记", row["body"]]
    if row["tags"]:
        lines += ["标签：" + "、".join(row["tags"])]
    lines += ["当前来源可访问" if row["source_available"] else "当前来源不可核对，保留本人记录", "最后编辑：" + row["updated_at"]]
    return lines


def markdown_text(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", html.escape(str(value), quote=False))


def download(user, data):
    records = project(user, data)
    format_ = data["format"]
    if format_ == "pdf":
        lines = ["笔记、摘录与书签", "仅本次明确选择的本人记录；不包含原始 PDF", ""]
        for index, row in enumerate(records, 1):
            lines += [f"{index}. {row['title']}", *content_lines(row), ""]
        body, mime, extension = pdf_bytes(lines), "application/pdf", "pdf"
    elif format_ == "markdown":
        lines = ["# 笔记、摘录与书签", "", "仅本次明确选择的本人记录；不包含原始 PDF。", ""]
        for index, row in enumerate(records, 1):
            lines += [f"## {index}. {markdown_text(row['title'])}", ""]
            # Treat all authored text as inert text, including backticks and HTML.
            content = "\n\n".join(content_lines(row))
            fence = "`" * max(3, 1 + max((len(match) for match in re.findall(r"`+", content)), default=0))
            lines += [fence + "text", content, fence, ""]
        body, mime, extension = "\n".join(lines).encode(), "text/markdown; charset=utf-8", "md"
    else:
        entries = []
        for row in records:
            csl = row["csl"]
            authors = [author.get("literal") or " ".join(filter(None, [author.get("family"), author.get("given")])) for author in csl.get("author", [])]
            year = ((csl.get("issued") or {}).get("date-parts") or [[""]])[0][0]
            note = "\n".join(content_lines(row)[1:])
            if format_ == "bibtex":
                fields = {"title": csl.get("title", row["title"]), "author": " and ".join(authors), "year": year,
                    "publisher": csl.get("publisher", ""), "journal": csl.get("container-title", ""), "doi": csl.get("DOI", ""), "note": note}
                kind = "article" if csl.get("type") == "article-journal" else "book" if csl.get("type") == "book" else "misc"
                entries.append("@" + kind + "{stl" + row["category"] + row["id"].replace("-", "") + ",\n" + ",\n".join(f"  {key} = {{{bib(value)}}}" for key, value in fields.items() if value) + "\n}")
            else:
                fields = [("TY", "JOUR" if csl.get("type") == "article-journal" else "BOOK" if csl.get("type") == "book" else "GEN"),
                    ("TI", csl.get("title", row["title"])), *[("AU", value) for value in authors], ("PY", year),
                    ("PB", csl.get("publisher", "")), ("JO", csl.get("container-title", "")), ("DO", csl.get("DOI", "")), ("N1", note)]
                entries.append("\r\n".join(f"{key}  - {clean(value)}" for key, value in fields if value) + "\r\nER  -\r\n")
        body = "\n\n".join(entries).encode()
        mime, extension = ("application/x-bibtex; charset=utf-8", "bib") if format_ == "bibtex" else ("application/x-research-info-systems; charset=utf-8", "ris")
    # Recheck after rendering too: neither changed notes nor newly withdrawn
    # public metadata should be downloaded under an old displayed version.
    if digest(project(user, data)) != digest(records):
        raise research.ResearchConflict("记录或原来源在准备导出时改变，请重新读取后选择。")
    response = HttpResponse(body, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="stl-reading-records.{extension}"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
