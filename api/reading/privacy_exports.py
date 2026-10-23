"""Render the existing owner-scoped export; never stage private files on disk."""
import csv
import io
import json
from hashlib import sha256
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

from django.http import HttpResponse
from rest_framework.exceptions import ValidationError

from . import privacy, research
from .booklist_exports import csv_cell


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, default=str, indent=2).encode("utf-8")


def snapshot_digest(payload):
    snapshot = {key: value for key, value in payload.items() if key != "downloaded_at"}
    # Source follows decorate each read with a fresh check time; compare their
    # availability, metadata and persisted history, not that read-only clock.
    snapshot["records"] = [
        {**entry, "record": {**entry["record"], "source": {
            key: value for key, value in entry["record"].get("source", {}).items() if key != "checked_at"}}}
        if entry["category"] == "source_follows" else entry for entry in payload["records"]
    ]
    return sha256(json.dumps(snapshot, ensure_ascii=False, default=str, sort_keys=True).encode()).hexdigest()


def render(payload, format_):
    if format_ == "zip":
        output = io.BytesIO()
        manifest = {key: value for key, value in payload.items() if key != "records"}
        manifest["files"] = []
        with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=6) as archive:
            for entry in payload["records"]:
                category = entry["category"]
                if category not in privacy.MODELS:
                    raise ValidationError("导出包含无法识别的资料类别，请重新准备任务。")
                name = f"{category}/{UUID(entry['id'])}.json"
                manifest["files"].append({"path": name, "id": entry["id"], "category": category, "revision": entry["revision"]})
                archive.writestr(name, json_bytes(entry))
            archive.writestr("manifest.json", json_bytes(manifest))
            archive.writestr("说明.txt", "书库私人资料导出\n按资料类型分目录；每份 JSON 保留资料编号、版本及当时可用的来源信息。\nmanifest.json 包含导出时间、文件清单、未完成项目与下载时已变化的项目。\n不包含馆藏原件、访问凭证或其他账户的私人资料。\n")
        return output.getvalue(), "application/zip"
    if format_ == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["记录状态", "资料类型", "记录编号", "版本", "标题", "更新时间", "完整记录JSON", "说明"])
        for entry in payload["records"]:
            record = entry["record"]
            data = record.get("data") if isinstance(record.get("data"), dict) else {}
            title = record.get("title") or data.get("title") or data.get("goal") or "本人资料"
            writer.writerow([csv_cell(value) for value in ["已导出", entry["category"], entry["id"], entry["revision"], title,
                record.get("updated_at", ""), json.dumps(record, ensure_ascii=False, default=str), payload["notice"]]])
        for state, entries in [("准备未完成", payload.get("failed", [])), ("下载时已变化", payload.get("unavailable_since_preparation", []))]:
            for entry in entries:
                writer.writerow([csv_cell(value) for value in [state, entry.get("category", ""), entry.get("id", ""), "", "", "", "", entry.get("reason") or entry.get("error_code", "")]])
        return output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
    raise ValidationError("请选择 ZIP、CSV 或 JSON 导出格式。")


def download(user, pk, format_):
    if format_ not in {"zip", "csv"}:
        raise ValidationError("请选择 ZIP、CSV 或 JSON 导出格式。")
    payload = privacy.download_operation(user, pk)
    content, mime = render(payload, format_)
    # Formatting must not release a snapshot whose private text/source eligibility changed meanwhile.
    if snapshot_digest(privacy.download_operation(user, pk)) != snapshot_digest(payload):
        raise research.ResearchConflict("资料或来源在准备文件时发生变化，请重新读取后下载。")
    response = HttpResponse(content, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="reader-data-{UUID(str(pk))}.{format_}"'
    response["X-Reader-Owner"] = str(user.pk)
    response["X-Privacy-Operation"] = str(pk)
    response["X-Privacy-Record-Count"] = str(len(payload["records"]))
    response["X-Privacy-Unavailable-Count"] = str(len(payload["unavailable_since_preparation"]))
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response
