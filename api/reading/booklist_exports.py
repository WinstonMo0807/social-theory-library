"""Small, explicit owner downloads; no files, notes or progress become public."""
import csv
import io
import unicodedata

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
    if booklists.version(row) != data["expected_version"]:
        raise research.ResearchConflict("书单已修改，请重新读取后导出。")
    items = row.items.filter(removed_at__isnull=True).select_related("work").order_by("order", "created_at", "id")
    if data.get("item_ids"):
        items = items.filter(pk__in=data["item_ids"])
        if items.count() != len(data["item_ids"]):
            raise research.ResearchConflict("所选作品已变化，请重新选择。")
    if items.count() > 200:
        raise ValidationError("一次最多导出200部作品，请分批选择；完整原始资料可到隐私与资料导出。")
    records = []
    for item in items:
        edition = booklists.public_editions().filter(work_id=item.work_id).select_related("work", "active_catalog_revision").first()
        bundle = citation_bundle(edition, snapshot=edition.active_catalog_revision.snapshot) if edition else {}
        csl = bundle.get("csl") or {}
        record = {"id": str(item.work_id), "title": csl.get("title") or "来源暂不可用",
            "authors": [author.get("literal", "") for author in csl.get("author", [])], "publisher": csl.get("publisher", ""),
            "year": ((csl.get("issued") or {}).get("date-parts") or [[""]])[0][0], "doi": csl.get("DOI", ""),
            "journal": csl.get("container-title", ""), "type": csl.get("type", ""), "citation": bundle.get("gbt7714-2025", "来源暂不可用"),
            "added": item.created_at.isoformat(), "progress": "", "notes": ""}
        if data["include_progress"]:
            current = booklists.project_item(request, item)
            ratio = current["progress_ratio"]
            record["progress"] = f"{max(0, min(100, round(ratio * 100)))}%" if ratio is not None else "未记录"
        if data["include_notes"]:
            notes = Annotation.objects.filter(user=request.user, asset__edition__work_id=item.work_id).order_by("created_at", "id")
            if notes.count() > 200:
                raise ValidationError("单部作品的笔记超过200条，请到隐私与资料导出完整笔记。")
            values = []
            for note in notes:
                exported = privacy.annotation_export(request.user, note)
                values.append(f"第{note.page.index}页\n{exported.get('quote', '')}\n{exported.get('body_text') or ''}")
            record["notes"] = "\n\n".join(values)
        records.append(record)
    if sum(len(str(value)) for record in records for value in record.values()) > 200000:
        raise ValidationError("本次导出正文过多，请减少作品或在隐私与资料中生成完整导出。")
    if booklists.version(booklists.owned(request.user, row.pk)) != data["expected_version"]:
        raise research.ResearchConflict("书单在准备导出时发生变化，请重新导出。")
    format_ = data["format"]
    lines = [row.title, row.description, "私人书单 · 仅本次显式下载", ""]
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
                "publisher": record["publisher"], "doi": record["doi"], "journal": record["journal"],
                "note": "\n".join(filter(None, [record["progress"], record["notes"]]))}
            kind = "article" if record["type"] == "article-journal" else "book" if record["type"] else "misc"
            chunks.append("@" + kind + "{stl" + record["id"].replace("-", "") + ",\n" + ",\n".join(f"  {key} = {{{bib(value)}}}" for key, value in fields.items() if value) + "\n}")
        body, mime = "\n\n".join(chunks).encode(), "application/x-bibtex; charset=utf-8"
    elif format_ == "ris":
        chunks = []
        for record in records:
            fields = [("TY", "JOUR" if record["type"] == "article-journal" else "BOOK" if record["type"] else "GEN"),
                ("TI", record["title"]), *[("AU", author) for author in record["authors"]], ("PY", record["year"]),
                ("PB", record["publisher"]), ("DO", record["doi"]), ("JO", record["journal"]),
                ("N1", "\n".join(filter(None, [record["progress"], record["notes"]])))]
            chunks.append("\r\n".join(f"{key}  - {clean(value)}" for key, value in fields if value) + "\r\nER  -\r\n")
        body, mime = "\r\n".join(chunks).encode(), "application/x-research-info-systems; charset=utf-8"
    else:
        for index, record in enumerate(records):
            lines.extend([f"{index + 1}. {record['citation']}", record["progress"], record["notes"], ""])
        body, mime = pdf_bytes(lines), "application/pdf"
    response = HttpResponse(body, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="booklist-{row.pk}.{ "bib" if format_ == "bibtex" else format_ }"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
