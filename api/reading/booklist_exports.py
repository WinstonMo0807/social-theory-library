"""Small, explicit owner downloads; no files, notes or progress become public."""
import csv
import io
import json
import unicodedata
import time

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError

from catalog.services.citations import citation_bundle
from . import booklists, privacy, research
from .models import Annotation


def clean(value):
    return " ".join(str(value or "").split())


def csv_cell(value):
    text = str(value or "")
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


def bib(value):
    escapes = {"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "%": "\\%", "&": "\\&", "_": "\\_", "#": "\\#", "$": "\\$", "^": "\\textasciicircum{}", "~": "\\textasciitilde{}"}
    return "".join(escapes.get(char, char) for char in clean(value))


def pdf_bytes(lines):
    import fitz
    # Built-in CJK font: no downloaded fonts, network resources or HTML execution.
    wrapped = []
    for text in lines:
        for line in str(text).splitlines() or [""]:
            chunk, width = "", 0
            for char in line:
                size = 2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1
                if width + size > 78:
                    wrapped.append(chunk)
                    chunk, width = "", 0
                chunk += char
                width += size
            wrapped.append(chunk)
    with fitz.open() as document:
        for start in range(0, len(wrapped), 43):
            page = document.new_page(width=595, height=842)
            for index, line in enumerate(wrapped[start:start + 43]):
                page.insert_text((44, 52 + index * 17), line, fontname="china-s", fontsize=11, color=(.16, .15, .14))
            page.insert_text((280, 812), str(start // 43 + 1), fontsize=9)
        return document.tobytes(garbage=4, deflate=True)


def download(request, row, data):
    deadline = time.monotonic() + 22
    def bounded():
        if time.monotonic() > deadline:
            raise ValidationError("本次导出准备超时，请减少作品、笔记或封面后重试。")
    if booklists.version(row) != data["expected_version"]:
        raise research.ResearchConflict("书单已修改，请重新读取后导出。")
    items = row.items.filter(removed_at__isnull=True).select_related("work").order_by("order", "created_at", "id")
    if data.get("item_ids"):
        items = items.filter(pk__in=data["item_ids"])
        if items.count() != len(data["item_ids"]):
            raise research.ResearchConflict("所选作品已变化，请重新选择。")
    if items.count() > 200:
        raise ValidationError("一次最多导出200部作品，请分批选择；完整原始资料可到隐私与资料导出。")
    records, editions, note_versions, progress_versions, note_sources = [], {}, {}, {}, {}
    for item in items:
        bounded()
        edition = booklists.public_editions().filter(work_id=item.work_id).select_related("work", "active_catalog_revision").first()
        editions[str(item.work_id)] = edition
        bundle = citation_bundle(edition, snapshot=edition.active_catalog_revision.snapshot) if edition else {}
        csl = bundle.get("csl") or {}
        record = {"id": str(item.work_id), "title": csl.get("title") or "来源暂不可用",
            "authors": [author.get("literal", "") for author in csl.get("author", [])], "publisher": csl.get("publisher", ""),
            "year": ((csl.get("issued") or {}).get("date-parts") or [[""]])[0][0], "doi": csl.get("DOI", ""),
            "journal": csl.get("container-title", ""), "type": csl.get("type", ""), "citation": bundle.get("gbt7714-2025", "来源暂不可用"),
            "version": str((edition.active_catalog_revision.snapshot.get("edition") or {}).get("version_label") or "") if edition else "",
            "isbn": str((edition.active_catalog_revision.snapshot.get("edition") or {}).get("isbn") or "") if edition else "",
            "pages": str((edition.active_catalog_revision.snapshot.get("edition") or {}).get("page_range") or "") if edition else "",
            "added": item.created_at.isoformat(), "progress": "", "notes": ""}
        if data["include_progress"]:
            current = booklists.readable_progress_for_user(request.user).filter(asset__edition__work_id=item.work_id).order_by("-updated_at", "-id").first() if edition else None
            ratio = current.progress_ratio if current else None
            if current:
                progress_versions[str(current.pk)] = current.updated_at.isoformat()
            record["progress"] = f"{max(0, min(100, round(ratio * 100)))}%" if ratio is not None else "未记录"
        if data["include_notes"]:
            notes = list(Annotation.objects.filter(user=request.user, asset__edition__work_id=item.work_id).select_related("page", "asset__edition").order_by("created_at", "id")[:201])
            if len(notes) > 200 or len(note_versions) + len(notes) > 1000:
                raise ValidationError("本次最多导出1000条笔记，单部作品最多200条；请减少选择或到隐私与资料导出完整笔记。")
            values = []
            for note in notes:
                bounded()
                exported = privacy.annotation_export(request.user, note)
                if (exported.get("source") or {}).get("source_status") == "available":
                    reference = research.compact_reference(exported["source"])
                    note_sources[json.dumps(reference, sort_keys=True)] = reference
                note_versions[str(note.pk)] = note.updated_at.isoformat()
                values.append(f"第{note.page.index}页\n{exported.get('quote', '')}\n{exported.get('body_text') or ''}")
            record["notes"] = "\n\n".join(values)
        records.append(record)
    if sum(len(str(value)) for record in records for value in record.values()) > 200000:
        raise ValidationError("本次导出正文过多，请减少作品或在隐私与资料中生成完整导出。")
    if booklists.version(booklists.owned(request.user, row.pk)) != data["expected_version"]:
        raise research.ResearchConflict("书单在准备导出时发生变化，请重新导出。")
    format_ = data["format"]
    if format_ == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["题名", "作者", "出版年", "出版者", "DOI", "加入时间", "阅读状态", "私人笔记"])
        for record in records:
            writer.writerow([csv_cell(record[key] if key != "authors" else "、".join(record[key])) for key in ("title", "authors", "year", "publisher", "doi", "added", "progress", "notes")])
        body, mime = output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    elif format_ == "bibtex":
        chunks = []
        for record in records:
            fields = {"title": record["title"], "author": " and ".join(record["authors"]), "year": record["year"],
                "publisher": record["publisher"], "doi": record["doi"],
                "booktitle" if record["type"] == "chapter" else "journal": record["journal"],
                "pages": record["pages"], "isbn": record["isbn"], "edition": record["version"],
                "note": "\n".join(filter(None, [record["progress"], record["notes"]]))}
            kind = {"article-journal": "article", "book": "book", "chapter": "incollection", "report": "techreport"}.get(record["type"], "misc")
            chunks.append("@" + kind + "{stl" + record["id"].replace("-", "") + ",\n" + ",\n".join(f"  {key} = {{{bib(value)}}}" for key, value in fields.items() if value) + "\n}")
        body, mime = "\n\n".join(chunks).encode(), "application/x-bibtex; charset=utf-8"
    elif format_ == "ris":
        chunks = []
        for record in records:
            fields = [("TY", {"article-journal": "JOUR", "book": "BOOK", "chapter": "CHAP", "thesis": "THES", "report": "RPRT", "periodical": "JFULL"}.get(record["type"], "GEN")),
                ("TI", record["title"]), *[("AU", author) for author in record["authors"]], ("PY", record["year"]),
                ("PB", record["publisher"]), ("DO", record["doi"]), ("T2", record["journal"]),
                ("SP", record["pages"]), ("SN", record["isbn"]), ("ET", record["version"]),
                ("N1", "\n".join(filter(None, [record["progress"], record["notes"]])))]
            chunks.append("\r\n".join(f"{key}  - {clean(value)}" for key, value in fields if value) + "\r\nER  -\r\n")
        body, mime = "\r\n".join(chunks).encode(), "application/x-research-info-systems; charset=utf-8"
    else:
        from .booklist_pdf import render
        body, mime = render(row.title, row.description, records, editions, include_covers=data.get("include_covers", False), deadline=deadline), "application/pdf"
    bounded()
    if booklists.version(booklists.owned(request.user, row.pk)) != data["expected_version"]:
        raise research.ResearchConflict("书单在生成文件时发生变化，请重新导出。")
    current = {str(work): (str(pk), str(revision)) for work, pk, revision in booklists.public_editions().filter(work_id__in=editions).values_list("work_id", "pk", "active_catalog_revision_id")}
    captured = {work: (str(edition.pk), str(edition.active_catalog_revision_id)) for work, edition in editions.items() if edition}
    if current != captured:
        raise research.ResearchConflict("公开来源在生成文件时发生变化，请重新导出当前版本。")
    if note_versions != {str(pk): updated.isoformat() for pk, updated in Annotation.objects.filter(user=request.user, pk__in=note_versions).values_list("pk", "updated_at")}:
        raise research.ResearchConflict("所选笔记已修改或删除，请重新读取后导出。")
    if progress_versions != {str(pk): updated.isoformat() for pk, updated in booklists.readable_progress_for_user(request.user).filter(pk__in=progress_versions).values_list("pk", "updated_at")}:
        raise research.ResearchConflict("所选阅读记录已变化或不可访问，请重新读取后导出。")
    for reference in note_sources.values():
        bounded()
        if research.resolve_reference(reference, request.user).get("source_status") != "available":
            raise research.ResearchConflict("笔记引用的原文在生成文件时已变化或不可访问，请重新导出。")
    bounded()
    response = HttpResponse(body, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="booklist-{row.pk}.{ "bib" if format_ == "bibtex" else format_ }"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
