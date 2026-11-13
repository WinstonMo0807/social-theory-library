"""Bounded remote stages with server-managed Provider transport and receipts.

The worker executes DocETL without receiving Provider credentials. Each transport
request is limited to the already stored window and current task lease.
"""
import json
import time
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from catalog import models as m
from catalog.services.knowledge_sources import digest, require_revision_access
from catalog.services.intelligence_provider import configuration, identity, SYSTEM, TASK, PROMPT_VERSION
from common.task_runtime import queue_or_wait
from ingestion.services.ai_client import AIClient


class RemoteStagePending(Exception):
    pass


def queue_stage(run, stage, unit, data, prompt, schema, config, key, lease):
    from catalog.services.intelligence import _guard
    with transaction.atomic():
        m.CurationRun.objects.select_for_update().get(pk=run.pk)
        _guard(run,lease)
        artifact,_ = m.CurationArtifact.objects.update_or_create(run=run,stage=stage,unit=unit,defaults={
            "cache_key":key,"schema_version":PROMPT_VERSION,"status":"waiting","input_manifest":data,
            "output":{},"output_hash":"","model_identity":identity(config),"usage":{"model_calls":0},
            "execution_request":{"prompt":prompt,"schema":schema,"run_version":run.version}})
        result = queue_or_wait(owner_type="curation_artifact",owner_key=str(artifact.pk),capability="llm_large",
            idempotency_key=f"curation-stage:{artifact.pk}:{run.version}:{key}",
            payload={"task_kind":"curation_stage","artifact_id":str(artifact.pk),"run_id":str(run.pk),
                "run_version":run.version,"cache_key":key},preferred_queue="intelligence-remote",publication_blocking=False)
        artifact.execution_request={**artifact.execution_request,"demand_id":str(result.demand.pk)}
        artifact.save(update_fields=["execution_request","updated_at"])
        m.CurationRun.objects.filter(pk=run.pk,version=run.version).update(status="waiting_remote",stage=stage,
            error={"code":"waiting_remote","message":"此阶段已排队，等待独立计算节点；已完成的章节产物保留。"})
    raise RemoteStagePending()


def stage_source(demand):
    artifact = m.CurationArtifact.objects.select_related("run__document_revision","run__created_by").get(pk=demand.owner_key)
    run = artifact.run
    request = artifact.execution_request
    config = configuration(run.profile_key)
    require_revision_access(run.document_revision,run.created_by,editorial=True)
    if (demand.payload.get("task_kind") != "curation_stage" or str(artifact.pk) != demand.payload.get("artifact_id")
            or str(demand.pk) != request.get("demand_id") or request.get("run_version") != run.version
            or run.status == "canceled" or demand.payload.get("cache_key") != artifact.cache_key
            or not config.enabled or identity(config) != artifact.model_identity):
        raise ValidationError("策展任务、来源权限或模型配置已变化，旧阶段不能执行。")
    from catalog.services.knowledge_sources import current_structure
    structure = current_structure(run.document_revision)
    if not structure or structure.pk != run.structure_id:
        raise ValidationError("正文结构已变化，请恢复任务以复用仍有效的章节产物。")
    return artifact,config


def remote_job(demand):
    artifact,config=stage_source(demand)
    return {"task_kind":"curation_stage","artifact_id":str(artifact.pk),"prompt":artifact.execution_request["prompt"],
        "input":json.dumps(artifact.input_manifest,ensure_ascii=False),"output_schema":artifact.execution_request["schema"],
        "runtime":{"provider":config.provider,"model":config.model,"model_revision":digest(identity(config))},
        "transport":"stl-managed"}


def active_lease(demand_id,executor_id,lease_token,*,lock=False):
    rows=m.CapabilityDemand.objects.select_related("claimed_by")
    if lock: rows=rows.select_for_update(of=("self",))
    demand=rows.filter(pk=demand_id,state="claimed",claimed_by__executor_id=executor_id,
        lease_token=lease_token,lease_expires_at__gt=timezone.now(),payload__task_kind="curation_stage").first()
    if not demand:
        raise ValidationError("策展执行租约已失效。")
    return demand


def model_transport(demand_id,executor_id,lease_token,input_hash):
    # No model name, URL, key, prompt or source text can be supplied by a caller.
    with transaction.atomic():
        demand=active_lease(demand_id,executor_id,lease_token,lock=True)
        artifact,config=stage_source(demand)
        m.CurationRun.objects.select_for_update().get(pk=artifact.run_id)
        artifact,config=stage_source(demand)
        request=artifact.execution_request
        text=request["prompt"]+"\n<source_data>"+json.dumps(artifact.input_manifest,ensure_ascii=False)+"</source_data>"
        if digest(text) != input_hash:
            raise ValidationError("远程算子输入与已保存的完整窗口不一致。")
        if artifact.status == "computed":
            return {"data":artifact.output,"output_hash":artifact.output_hash,"usage":artifact.usage}
        lease_hash=digest(str(lease_token))
        if artifact.status == "running" and request.get("transport_lease") == lease_hash:
            raise ValidationError("此窗口模型调用尚在执行，不能重复调用。")
        artifact.status="running";artifact.execution_request={**request,"transport_lease":lease_hash}
        artifact.save(update_fields=["status","execution_request","updated_at"])
    started=time.monotonic()
    try:
        result=AIClient(config=config).generate_json(task=TASK,system_prompt=SYSTEM,
            document_text=text,schema=request["schema"],prompt_version=PROMPT_VERSION,strict=True)
        validate_result(artifact,result.data)
    except Exception as exc:
        with transaction.atomic():
            demand=active_lease(demand_id,executor_id,lease_token,lock=True)
            artifact,_=stage_source(demand)
            artifact.status="failed";artifact.error={"code":getattr(exc,"code",type(exc).__name__),"message":str(exc)[:1200]}
            artifact.usage={"model_calls":None,"cost":None}
            artifact.save(update_fields=["status","error","usage","updated_at"])
        raise
    with transaction.atomic():
        demand=active_lease(demand_id,executor_id,lease_token,lock=True)
        artifact,_=stage_source(demand)
        m.CurationRun.objects.select_for_update().get(pk=artifact.run_id)
        artifact,_=stage_source(demand)
        artifact.status="computed";artifact.output=result.data;artifact.output_hash=digest(result.data)
        artifact.usage={"model_calls":result.attempts,"tokens":result.usage,"cost":None}
        artifact.elapsed_ms=round((time.monotonic()-started)*1000);artifact.executor_id=executor_id
        artifact.error={};artifact.save()
    return {"data":artifact.output,"output_hash":artifact.output_hash,"usage":artifact.usage}


def validate_result(artifact,output):
    data=artifact.input_manifest
    if artifact.stage == 2:
        from catalog.services.intelligence import validate_analysis
        validate_analysis(output,data["ranges"])
    elif artifact.stage == 3 and "source_units" in data:
        from catalog.services.knowledge_compilation_plan import validate_synthesis
        validate_synthesis(output,data)
    elif artifact.stage == 4:
        candidates={c["id"] for c in data["bounded_candidates"]}
        seen=[c["candidate_id"] for c in output["comparisons"]]
        if set(seen) != candidates or len(seen) != len(candidates):
            raise ValidationError("身份比较没有完整覆盖限定候选。")
    elif artifact.stage == 6:
        if data.get("plan") == "page-batches-v2":
            from catalog.services.knowledge_compilation_plan import validate_wiki_batch
            validate_wiki_batch(output,data)
        else:
            from catalog.services.intelligence import validate_wiki_patch
            validate_wiki_patch(output,data)


def complete_stage(demand,result):
    # Called inside the remote completion transaction after checking the lease.
    artifact,_=stage_source(demand)
    run=m.CurationRun.objects.select_for_update().get(pk=artifact.run_id)
    artifact,_=stage_source(demand)
    if artifact.status != "computed" or result.get("output_hash") != artifact.output_hash or result.get("artifact_id") != str(artifact.pk):
        raise ValidationError("策展结果与受控Provider回执不一致，不能写入阶段产物。")
    artifact.status="succeeded" if artifact.output else "empty";artifact.save(update_fields=["status","updated_at"])
    # Resume the same run; its valid stages are reused by cache key and citations
    # are rechecked before candidates can reach ChangeSet.
    run.version+=1;run.status="waiting";run.error={};run.save()
    from catalog.services.intelligence import schedule
    schedule(run)
    return artifact
