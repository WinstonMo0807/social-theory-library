"""Receipts and safe transitions over the existing task implementations."""
from hashlib import sha256
import json

from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError
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
    action = serializers.ChoiceField(choices=["pause", "resume", "retry", "cancel", "recover", "configure_followup", "retry_followup"])
    expected_version = serializers.CharField(max_length=64)
    page_indexes = serializers.ListField(child=serializers.IntegerField(min_value=1), min_length=1, max_length=20000, required=False)
    align_concepts = serializers.BooleanField(required=False)

    def validate(self, value):
        if set(self.initial_data) - set(self.fields):
            raise serializers.ValidationError("请提交当前任务的完整操作参数。")
        if "page_indexes" in value and (value["action"] != "retry" or value["source"] != "processing_job"):
            raise serializers.ValidationError("仅原 OCR 任务的失败重试可以指定页序。")
        if (value["action"] == "configure_followup") != ("align_concepts" in value):
            raise serializers.ValidationError("调整后续操作时必须明确是否进行概念对齐，此设置不能附带在其他操作中。")
        return value


def task_version(job):
    # Heartbeats/progress do not invalidate a command for the same worker delivery.
    values = [str(job.pk), job.task_id, job.status, getattr(job, "attempt", getattr(job, "attempts", 0)),
              str(job.pause_requested_at), str(job.asset_id), str(getattr(job, "edition_id", "")),
              (job.stats or {}).get("retry_replacement_id", ""), (job.stats or {}).get("after_processing"), (job.stats or {}).get("concept_retry_job_id"),
              ((job.stats or {}).get("concept_alignment") or {}).get("state")]
    return sha256(json.dumps(values).encode()).hexdigest()


def task_actions(job, actor):
    if not has_capability(actor, Capability.RETRY_JOBS): return []
    if (job.stats or {}).get("retry_replacement_id"): return []
    if isinstance(job, SemanticIndexJob):
        # These are the inherited semantic store, never a substitute for Discovery.
        if job.operation not in {"build", "rebuild"}: return []
        return (["pause"] if job.status in {"queued", "running"} and not job.pause_requested_at else []) + (["resume"] if job.status == "paused" else []) + (["cancel"] if job.status in {"queued", "paused"} else []) + (["retry"] if job.status in {"failed", "partial"} and job.asset_id else [])
    kind, state = job.job_type, job.status
    from .processing_recovery import recovery_state
    recover = ["recover"] if has_capability(actor, Capability.VIEW_SYSTEM_STATUS) and recovery_state(job)["can_recover"] else []
    if kind == "discovery_index":
        return recover + (["retry"] if state == "failed" else ["resume", "cancel"] if state == "paused" else ["cancel"] if state == "pending" else [])
    if kind == "text_extraction" and job.stats.get("operation") == "concept_alignment":
        if not has_capability(actor, Capability.VIEW_SYSTEM_STATUS): return []
        return recover + (["cancel"] if state in {"pending", "running", "failed"} else []) + (["retry"] if state in {"failed", "canceled"} else [])
    actions = []
    if kind == "ocr" and has_capability(actor, Capability.VIEW_SYSTEM_STATUS):
        from .processing_followup import followup_state
        if state == "succeeded" and followup_state(job)["state"] == "failed" and not job.stats.get("concept_retry_job_id"):
            actions.append("retry_followup")
        if followup_state(job)["can_configure"]:
            actions.append("configure_followup")
    if kind in {"ocr", "external_enrichment"}:
        if state in {"pending", "running"} and not job.pause_requested_at: actions.append("pause")
        if state == "paused": actions.append("resume")
    if state in {"pending", "paused"}: actions.append("cancel")
    if kind == "ocr" and state == "failed" and job.stats.get("requested_mode") in {"all_pages", "selected_pages"}: actions.append("cancel")
    if state == "failed" and kind in {"ocr", "page_labels", "external_enrichment", "r2_staging"}: actions.append("retry")
    if kind == "editorial_assistance" or kind == "text_extraction" and job.stats.get("operation") == "outline_rebuild":
        if state in {"running", "failed"}: actions.append("cancel")
        if state == "failed": actions.append("retry")
    return actions + recover


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
    if (request.data.get("action") in {"recover", "configure_followup", "retry_followup"} or request.data.get("action") == "retry" and "page_indexes" in request.data) and not has_capability(actor, Capability.VIEW_SYSTEM_STATUS):
        raise PermissionDenied("当前账户不能调整处理队列中的任务。")
    if request.data.get("action") in {"recover", "configure_followup", "retry_followup"} and not request.data.get("request_id"):
        raise ValidationError("此操作必须使用当前页面的固定请求编号。")
    if request.data.get("action") == "retry" and "page_indexes" in request.data and not request.data.get("request_id"):
        raise ValidationError("选择失败页重试必须使用固定请求编号。")
    # OCR creation already owns its request_id contract and receipt shape.
    identifier = request.data.get("request_id") if request.data.get("action") in {"pause", "resume", "retry", "cancel", "recover", "configure_followup", "retry_followup"} else None
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
    if data is not None and "page_indexes" in data and (not isinstance(job, ProcessingJob) or job.job_type != "ocr"):
        raise ValidationError("只有原 OCR 任务的失败重试可以选择页序。")
    if data is not None and data["action"] == "retry_followup":
        from .concept_retry import queue_concept_retry
        try:
            child = queue_concept_retry(job, actor)
        except ValueError as exc:
            raise EditConflict(str(exc)) from exc
        response = Response({"job_id": str(child.pk), "status": child.status}, status=202)
    elif isinstance(job, ProcessingJob) and job.job_type == "text_extraction" and job.stats.get("operation") == "concept_alignment" and request.data.get("action") in {"retry", "cancel"}:
        from .concept_retry import concept_job_action
        try:
            child = concept_job_action(job, action=request.data["action"], actor=actor)
        except ValueError as exc:
            raise EditConflict(str(exc)) from exc
        response = Response({"job_id": str(child.pk), "status": child.status}, status=202)
    elif data is not None and data["action"] == "configure_followup":
        from .processing_followup import configure_followup
        response = Response(configure_followup(job, enabled=data["align_concepts"], actor=actor))
    elif data is not None and data["action"] == "recover":
        from .processing_recovery import recover_processing_task
        response = Response(recover_processing_task(job, actor), status=202)
    elif data is not None and "page_indexes" in data:
        from .catalog_ocr import retry_ocr_job
        try:
            job = retry_ocr_job(job, actor=actor, page_indexes=data["page_indexes"])
        except ValueError as exc:
            raise EditConflict(str(exc)) from exc
        response = Response({"job_id": str(job.pk), "status": job.status}, status=202)
    else:
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
