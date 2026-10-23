"""Bounded exports of recorded successful OCR pages or the task's outline revision."""
from hashlib import sha256
import json
from tempfile import SpooledTemporaryFile
from uuid import UUID

from django.db.models import Count, Max
from django.db.models.functions import Length
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.editorial_read import AdminPrivateResponseMixin
from catalog.models import Asset, DocumentOutlineRevision
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from common.permissions import IsLibraryStaff
from ingestion.services.processing_center import task_querysets

MAX_BYTES = 64 * 1024 * 1024
OUTLINE_FIELDS = ("id", "parent_id", "title", "level", "pdf_page", "printed_label", "calibration_status", "visible")


class ProcessingResultQuerySerializer(serializers.Serializer):
    download = serializers.ChoiceField(choices=["", "txt", "jsonl"], default="")
    page_from = serializers.IntegerField(min_value=1, max_value=20000, default=1)
    page_to = serializers.IntegerField(min_value=1, max_value=20000, required=False)
    expected_version = serializers.RegexField(r"^[a-f0-9]{64}$", required=False)

    def validate(self, data):
        if data.get("page_to", 20000) < data["page_from"]:
            raise serializers.ValidationError("结束页不能早于开始页。")
        if data["download"] and not data.get("expected_version"):
            raise serializers.ValidationError("请先读取当前可导出结果。")
        return data


class ProcessingResultManifestSerializer(serializers.Serializer):
    owner_id = serializers.CharField()
    task_id = serializers.UUIDField()
    kind = serializers.ChoiceField(choices=["ocr", "outline"])
    asset_id = serializers.UUIDField(allow_null=True)
    revision_id = serializers.UUIDField(allow_null=True)
    title = serializers.CharField()
    task_status = serializers.CharField()
    count = serializers.IntegerField()
    total_recorded = serializers.IntegerField()
    page_count = serializers.IntegerField()
    version = serializers.CharField()
    checked_at = serializers.DateTimeField()
    notice = serializers.CharField()
    formats = serializers.ListField(child=serializers.CharField())


def result_asset(job):
    asset = job.asset
    if asset is None or job.edition_id is None or asset.edition_id != job.edition_id:
        raise EditConflict("本任务没有能够核对的馆藏文件，请从原材料页查看结果。")
    stats = job.stats or {}
    source_id = stats.get("requested_asset_id") or stats.get("text_source_asset_id") or str(asset.pk)
    try: source_id = UUID(str(source_id))
    except (ValueError, TypeError): raise EditConflict("原任务没有有效的源文件编号。")
    source = Asset.objects.filter(pk=source_id, edition_id=job.edition_id).first()
    if source is None or stats.get("source_sha256") and source.sha256 != stats["source_sha256"]:
        raise EditConflict("原文件身份已变化，无法将当前内容认作本次处理结果。")
    if str(asset.pk) != str(source.pk):
        details = asset.validation_details or {}
        if (asset.source_asset_id != source.pk or asset.sha256 != source.sha256 or stats.get("staging_asset_id") != str(asset.pk)
                or details.get("text_stage_key") != f"ocr-job:{job.pk}" or details.get("text_source_asset_id") != str(source.pk)):
            raise EditConflict("暂存结果不属于这次任务，不能导出其他任务的文字。")
    return asset


def result_source(job, actor, data):
    stats = job.stats or {}
    if job.job_type != "ocr" and not (job.job_type == "text_extraction" and stats.get("operation") == "outline_rebuild"):
        raise ValidationError("此导出入口只处理原OCR成功页与本次章节目录。其他任务请使用其原结果入口。")
    asset = result_asset(job)
    if not 1 <= asset.page_count <= 20000:
        raise ValidationError("原文件页数未核实或超过本入口上限，请在材料页先核对。")
    start, end = data["page_from"], data.get("page_to", asset.page_count or 20000)
    if asset.page_count > 0 and (start > asset.page_count or end > asset.page_count):
        raise ValidationError("所选范围超出本次文件的PDF页数。")
    revision = None
    notice = "导出已保存结果，不改变文字、目录或公开版本。"
    if job.job_type == "ocr":
        recorded = stats.get("completed_page_indexes") or []
        if not isinstance(recorded, list) or len(recorded) > 20000 or any(type(value) is not int or not 1 <= value <= asset.page_count for value in recorded):
            raise EditConflict("成功页记录与原文件不一致，请先从文字工作台核对。")
        done = sorted(set(recorded))
        selected = [value for value in done if start <= value <= end]
        rows = asset.pages.filter(index__in=selected).order_by("index")
        snapshot = rows.aggregate(count=Count("pk"), updated=Max("updated_at"), max_chars=Max(Length("text")))
        if (snapshot["max_chars"] or 0) > 1000000:
            raise ValidationError("单页文字超过一百万字，请先在原文字工作台核对异常页面，或调整导出范围。")
        if snapshot["count"] != len(selected):
            raise EditConflict("部分成功页记录已不存在，请在原文字工作台核对，不能导出不完整的成功清单。")
        count, total, kind = len(selected), len(done), "ocr"
        notice = "仅导出本任务明确记录的成功页及这些页当前保存的文字；每页保留PDF页序、文字来源与更新时间。未完成页和未应用的校订草稿不包含在内。"
        if not done: notice = "本任务没有可核对的成功页编号，不能把当前文件全文当作本次成功结果。请从原文字工作台查看已有内容。"
        identity = {"asset": str(asset.pk), "sha": asset.sha256, "selected": selected, "pages": snapshot}
    else:
        revision_id = stats.get("result_revision_id")
        if revision_id:
            try: revision_id = UUID(str(revision_id))
            except (ValueError, TypeError): raise EditConflict("本任务没有有效的目录修订编号。")
        revision = DocumentOutlineRevision.objects.filter(pk=revision_id, asset=asset).first() if revision_id else None
        if revision_id and (revision is None or revision.source_checksum != stats.get("source_sha256", asset.sha256)
                or str(revision.document_revision_id or "") != str(stats.get("document_revision_id") or "")):
            raise EditConflict("本次目录修订与原文件不一致，请从目录工作台核对。")
        nodes = revision.nodes if revision else []
        if len(nodes) > 20000: raise ValidationError("目录条目过多，请先在原目录工作台整理后导出。")
        rows = [{key: row.get(key) for key in OUTLINE_FIELDS} for row in nodes
            if type(row.get("pdf_page")) is int and start <= row["pdf_page"] <= end or row.get("pdf_page") is None and start == 1 and end == asset.page_count]
        count, total, kind = len(rows), len(nodes), "outline"
        notice = "导出本任务实际保存的目录修订，包括待核对或未定位条目；候选目录不代表已正式采用或发布。" if revision else "本任务还没有保存目录修订，不会用其他任务或旧目录代替。"
        identity = {"asset": str(asset.pk), "revision": str(revision.pk) if revision else None, "updated": revision.updated_at if revision else None, "nodes": rows}
    version = sha256(json.dumps({"task": str(job.pk), "range": [start, end], "result": identity}, sort_keys=True, default=str).encode()).hexdigest()
    manifest = {"owner_id": str(actor.pk), "task_id": str(job.pk), "kind": kind, "asset_id": str(asset.pk),
        "revision_id": str(revision.pk) if revision else None, "title": asset.edition.work.title, "task_status": job.status,
        "count": count, "total_recorded": total, "page_count": asset.page_count, "version": version,
        "checked_at": timezone.now(), "notice": notice, "formats": ["txt", "jsonl"] if count else []}
    return manifest, rows


def export_file(manifest, rows, file_format):
    output = SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b")
    size = 0
    def write(value):
        nonlocal size
        encoded = value.encode("utf-8"); size += len(encoded)
        if size > MAX_BYTES: raise ValidationError("导出结果超过64MiB，请缩小PDF页序范围后分批导出。")
        output.write(encoded)
    try:
        if file_format == "jsonl": write(json.dumps({"type": "manifest", **{key: value for key, value in manifest.items() if key not in {"owner_id", "formats"}}}, ensure_ascii=False, default=str) + "\n")
        else: write(f"{manifest['title']}\n任务 {manifest['task_id']}\n文件 {manifest['asset_id']}\n读取时间 {manifest['checked_at'].isoformat()}\n{manifest['notice']}\n本次导出 {manifest['count']} 项\n\n")
        if manifest["kind"] == "ocr":
            records = rows.values("index", "printed_label", "text", "text_source", "is_text_manual", "updated_at").iterator(chunk_size=20)
            for row in records:
                if file_format == "jsonl": write(json.dumps({"type": "page", **row}, ensure_ascii=False, default=str) + "\n")
                else: write(f"--- PDF 第 {row['index']} 页 · 印刷页 {row['printed_label'] or '未标注'} ---\n文字来源 {row['text_source']} · 人工文字 {'是' if row['is_text_manual'] else '否'} · 更新于 {row['updated_at'].isoformat()}\n{row['text']}\n\n")
        else:
            for row in rows:
                if file_format == "jsonl": write(json.dumps({"type": "outline_node", **row}, ensure_ascii=False, default=str) + "\n")
                else: write(f"{row.get('title') or ''}\tPDF {row.get('pdf_page') or '未定位'}\t印刷页 {row.get('printed_label') or '未标注'}\t{row.get('calibration_status') or '未记录核对状态'}\n")
        output.seek(0)
        return output
    except Exception:
        output.close()
        raise


class ProcessingResultView(AdminPrivateResponseMixin, APIView):
    permission_classes = [IsLibraryStaff]

    @extend_schema(parameters=[ProcessingResultQuerySerializer], responses={200: ProcessingResultManifestSerializer, (200, "text/plain"): OpenApiTypes.BINARY, (200, "application/x-ndjson"): OpenApiTypes.BINARY})
    def get(self, request, task_id):
        if request.headers.get("X-Editor-Owner") != str(request.user.pk) or not has_capability(request.user, Capability.VIEW_SYSTEM_STATUS):
            raise PermissionDenied("请使用有任务查看权限的当前账户导出。")
        data = ProcessingResultQuerySerializer(data=request.query_params); data.is_valid(raise_exception=True)
        data = data.validated_data
        jobs, _, _, _ = task_querysets({"task_source": "processing_job", "task_id": str(task_id)}, request.user)
        job = get_object_or_404(jobs.select_related("asset__edition__work"), pk=task_id)
        manifest, rows = result_source(job, request.user, data)
        if not data["download"]: return Response(ProcessingResultManifestSerializer(manifest).data)
        if data["expected_version"] != manifest["version"]: raise EditConflict("结果范围已变化，请重新读取后导出。")
        if not manifest["count"]: raise ValidationError(manifest["notice"])
        output = export_file(manifest, rows, data["download"])
        try:
            fresh = get_object_or_404(jobs.select_related("asset__edition__work"), pk=task_id)
            current, _ = result_source(fresh, request.user, data)
            if current["version"] != manifest["version"]: raise EditConflict("导出期间结果发生变化，请重新读取范围后重试。")
        except Exception:
            output.close()
            raise
        response = FileResponse(output, as_attachment=True, filename=f"stl-task-{task_id}-{manifest['kind']}.{data['download']}",
            content_type="text/plain; charset=utf-8" if data["download"] == "txt" else "application/x-ndjson; charset=utf-8")
        response["X-Content-Type-Options"] = "nosniff"
        return response
