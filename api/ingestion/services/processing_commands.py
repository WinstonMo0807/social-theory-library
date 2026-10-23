"""Receipts and safe transitions over the existing task implementations."""
from hashlib import sha256
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from catalog.models import Asset, Edition, SemanticIndexJob
from catalog.services.editorial_issues import EditConflict
from common.capabilities import Capability, has_capability
from ingestion.models import AuditEvent, ProcessingJob

ACTION = "processing.workspace.command"


class ProcessingCommandSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    job_id = serializers.UUIDField()
    source = serializers.ChoiceField(choices=["processing_job", "semantic_index_job"])
    action = serializers.ChoiceField(choices=["pause", "resume", "retry", "cancel"])
    expected_version = serializers.CharField(max_length=64)

    def validate(self, value):
        if set(self.initial_data) != set(self.fields):
            raise serializers.ValidationError("请提交当前任务的完整操作参数。")
        return value


def task_version(job):
    # Heartbeats/progress do not invalidate a command for the same worker delivery.
    values = [str(job.pk), job.task_id, job.status, getattr(job, "attempt", getattr(job, "attempts", 0)),
              str(job.pause_requested_at), str(job.asset_id), str(getattr(job, "edition_id", "")),
              (job.stats or {}).get("retry_replacement_id", "")]
    return sha256(json.dumps(values).encode()).hexdigest()


def task_actions(job, actor):
    if not has_capability(actor, Capability.RETRY_JOBS): return []
    if (job.stats or {}).get("retry_replacement_id"): return []
    if isinstance(job, SemanticIndexJob):
        # These are the inherited semantic store, never a substitute for Discovery.
        if job.operation not in {"build", "rebuild"}: return []
        return (["pause"] if job.status in {"queued", "running"} and not job.pause_requested_at else []) + (["resume"] if job.status == "paused" else []) + (["cancel"] if job.status in {"queued", "paused"} else []) + (["retry"] if job.status in {"failed", "partial"} and job.asset_id else [])
    kind, state = job.job_type, job.status
    actions = []
    if kind in {"ocr", "external_enrichment"}:
        if state in {"pending", "running"} and not job.pause_requested_at: actions.append("pause")
        if state == "paused": actions.append("resume")
    if state in {"pending", "paused"}: actions.append("cancel")
    if kind == "ocr" and state == "failed" and job.stats.get("requested_mode") in {"all_pages", "selected_pages"}: actions.append("cancel")
    if state == "failed" and kind in {"ocr", "page_labels", "external_enrichment", "r2_staging"}: actions.append("retry")
    if kind == "editorial_assistance" or kind == "text_extraction" and job.stats.get("operation") == "outline_rebuild":
        if state in {"running", "failed"}: actions.append("cancel")
        if state == "failed": actions.append("retry")
    return actions


def command_actor(request):
    expected = request.headers.get("X-Editor-Owner")
    if expected is not None and expected != str(request.user.pk): raise PermissionDenied("登录账户已变化，请重新读取任务。")
    actor = get_object_or_404(get_user_model().objects.select_for_update(), pk=request.user.pk, is_active=True)
    if actor.token_version != request.user.token_version or not has_capability(actor, Capability.RETRY_JOBS):
        raise PermissionDenied("当前会话不能修改处理任务。")
    return actor


def lock_task(source, identifier, actor, *, action=None):
    model = SemanticIndexJob if source == "semantic_index_job" else ProcessingJob
    target = get_object_or_404(model.objects.select_related("asset"), pk=identifier)
    # Follow each existing worker's parent -> task lock order.
    if isinstance(target, ProcessingJob) and target.job_type == "editorial_assistance":
        from catalog.services.curation_projects import lock_issue
        lock_issue(target.stats.get("issue_id"), actor, allow_archived=action == "cancel")
    elif isinstance(target, ProcessingJob) and target.job_type == "text_extraction" and target.stats.get("operation") == "outline_rebuild":
        get_object_or_404(Asset.objects.select_for_update(), pk=target.asset_id)
    else:
        edition_id = getattr(target, "edition_id", None) or (target.asset.edition_id if target.asset_id else None)
        if edition_id: get_object_or_404(Edition.objects.select_for_update(), pk=edition_id)
    return get_object_or_404(model.objects.select_for_update(of=("self",)).select_related("asset"), pk=identifier)


def command_receipt(row):
    return {"owner_id": str(row.actor_id), "request_id": row.request_id, "state": "cancelled" if row.after.get("cancelled") else "applied",
            "job_id": row.object_id or None, "source": row.after.get("source", ""), "action": row.after.get("action", ""),
            "next_url": row.after.get("next_url", ""), "result": row.after.get("result", {})}


@transaction.atomic
def run_processing_command(request, handler):
    actor = command_actor(request)
    request.user = actor
    # OCR creation already owns its request_id contract and receipt shape.
    identifier = request.data.get("request_id") if request.data.get("action") in {"pause", "resume", "retry", "cancel"} else None
    data, signature, job = None, "", None
    if identifier:
        if request.headers.get("X-Editor-Owner") != str(actor.pk): raise PermissionDenied("请从当前账户的任务页面提交操作。")
        serializer = ProcessingCommandSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = sha256(json.dumps(request.data, sort_keys=True).encode()).hexdigest()
        prior = AuditEvent.objects.filter(actor=actor, action=ACTION, request_id=str(data["request_id"])).first()
        if prior:
            if not prior.after.get("cancelled") and prior.after.get("signature") != signature: raise EditConflict("此编号已用于其他任务操作。")
            return Response(command_receipt(prior))
        job = lock_task(data["source"], data["job_id"], actor, action=data["action"])
        if task_version(job) != data["expected_version"]: raise EditConflict("任务状态或执行轮次已变化，请读取最新进度后操作。")
        if data["action"] not in task_actions(job, actor): raise EditConflict("当前任务不支持此操作，请查看任务状态与原处理入口。")
    elif request.data.get("action") in {"pause", "resume", "retry", "cancel"}:
        source = serializers.ChoiceField(choices=["processing_job", "semantic_index_job"]).run_validation(request.data.get("source", "processing_job"))
        job_id = serializers.UUIDField().run_validation(request.data.get("job_id"))
        job = lock_task(source, job_id, actor, action=request.data["action"])
        if request.data["action"] not in task_actions(job, actor): raise EditConflict("当前任务不支持此操作，请读取最新状态。")
    if isinstance(job, ProcessingJob) and job.job_type == "editorial_assistance":
        from catalog.services.curation_projects import require_issue_access
        require_issue_access(job.stats.get("issue_id"), actor)
    response = handler()
    if response.status_code >= 400:
        # Legacy handlers sometimes discover unsupported retries after a write.
        transaction.set_rollback(True)
        return response
    if job is not None and request.data.get("action") == "retry":
        replacement = str(response.data.get("job_id") or "")
        if replacement and replacement != str(job.pk):
            # Keep the failed attempt and its error, but retry its successor next time.
            job.refresh_from_db(fields=["stats"])
            job.stats = {**(job.stats or {}), "retry_replacement_id": replacement}
            job.save(update_fields=["stats", "updated_at"])
    if data is None: return response
    next_id = str(response.data.get("job_id") or job.pk)
    row = AuditEvent.objects.create(actor=actor, action=ACTION, object_type=data["source"], object_id=str(job.pk), request_id=str(data["request_id"]),
        after={"signature": signature, "source": data["source"], "action": data["action"], "result": response.data,
               "next_url": f"/admin/processing?task_id={next_id}&task_source={data['source']}"})
    return Response(command_receipt(row), status=response.status_code)
