"""Create configured work through the existing OCR and outline services."""
from hashlib import sha256
import json

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from catalog.models import Asset, Edition
from catalog.services.document_outline import queue_outline_rebuild
from catalog.services.editorial_issues import EditConflict
from ingestion.models import AuditEvent, ProcessingJob
from ingestion.ocr_workspace_views import OCRTaskOptionsSerializer
from .catalog_ocr import source_problem, start_catalog_ocr
from .processing_commands import ACTION, command_actor, command_receipt


class ProcessingCreationSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["create"])
    request_id = serializers.UUIDField()
    task_type = serializers.ChoiceField(choices=["ocr", "outline"])
    asset_id = serializers.UUIDField()
    source_version = serializers.CharField(max_length=100)
    confirmed = serializers.BooleanField()
    page_indexes = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=20000, required=False)
    task_options = OCRTaskOptionsSerializer(required=False)

    def validate(self, data):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("任务包含不支持的参数。")
        if not data["confirmed"]:
            raise serializers.ValidationError("请先确认文件、处理范围及结果用途。")
        if data["task_type"] != "ocr" and ("page_indexes" in data or "task_options" in data):
            raise serializers.ValidationError("页面识别策略只用于 OCR 任务。")
        return data


@transaction.atomic
def create_processing_task(request):
    actor = command_actor(request)
    if request.headers.get("X-Editor-Owner") != str(actor.pk):
        raise PermissionDenied("请从当前账户的任务页面提交操作。")
    serializer = ProcessingCreationSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    signature = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
    prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
    if prior:
        if not prior.after.get("cancelled") and prior.after.get("signature") != signature:
            raise EditConflict("原请求编号不能更换文件、任务类型或设置。")
        return command_receipt(prior)
    target = get_object_or_404(Asset, pk=data["asset_id"])
    # Same parent -> file order as OCR, publication and file replacement.
    get_object_or_404(Edition.objects.select_for_update(), pk=target.edition_id)
    asset = get_object_or_404(Asset.objects.select_for_update(), pk=target.pk)
    problem = source_problem(asset)
    if problem or asset.updated_at.isoformat() != data["source_version"]:
        raise EditConflict(problem or "文件已经变化，请重新读取并确认处理范围。")
    reused = False
    try:
        if data["task_type"] == "ocr":
            job, reused = start_catalog_ocr({**data, "edition_id": str(asset.edition_id)}, actor)
            message = "识别任务已登记，按所选范围逐页保存；完成状态以任务记录为准。"
        else:
            document_id = str(asset.document_revisions.filter(is_active=True).values_list("pk", flat=True).first() or "")
            job = ProcessingJob.objects.filter(asset=asset, job_type="text_extraction", stats__operation="outline_rebuild",
                status__in=["pending", "running"]).order_by("-created_at").first()
            if job:
                if job.stats.get("source_sha256") != asset.sha256 or str(job.stats.get("document_revision_id") or "") != document_id:
                    raise EditConflict("此文件的旧目录任务尚未结束，请先核对并取消旧任务。")
                reused = True
            else:
                job = queue_outline_rebuild(asset.pk, actor=actor, request_id=data["request_id"])
            message = "已找到当前文件的进行中目录任务。" if reused else "目录提取任务已登记。结果保存为候选，采用后才更新读者目录。"
    except ValueError as error:
        raise EditConflict(str(error)) from error
    row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type="processing_job", object_id=str(job.pk),
        request_id=str(data["request_id"]), after={"signature": signature, "source": "processing_job", "action": "create",
            "result": {"job_id": str(job.pk), "status": job.status, "reused": reused, "message": message},
            "next_url": f"/admin/processing?task_id={job.pk}&task_source=processing_job"})
    return command_receipt(row)
