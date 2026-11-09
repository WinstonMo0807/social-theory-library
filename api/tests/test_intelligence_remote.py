"""Remote stages use the same source, configuration, lease and durable receipt."""
from uuid import uuid4
import pytest
from rest_framework.exceptions import ValidationError
from tests.test_knowledge_core import source
from catalog import models as m
from catalog.services import intelligence, intelligence_remote as remote
from catalog.services.knowledge_sources import digest
from common.remote_worker import bind_remote_lease_context,build_remote_job,complete_remote_demand,RemoteWorkerProtocolError
from common.task_runtime import register_executor_heartbeat,claim_specific_demand
from ingestion.services.ai_client import AIClient,AIConfiguration,AIResult

pytestmark=pytest.mark.django_db


def stage(source,admin_user,monkeypatch,settings):
    settings.INTELLIGENCE_EXECUTION="remote"
    config=AIConfiguration(provider="openai_compatible",base_url="http://127.0.0.1:1/v1",api_key="",metadata_model="fixture",
        classifier_model="",vision_model="",timeout=5,max_concurrency=1,max_input_chars=16000,allowed_hosts=("127.0.0.1",),
        model="fixture",profile_key="curation-fixture")
    monkeypatch.setattr(remote,"configuration",lambda *a:config)
    scheduled=[]
    monkeypatch.setattr(intelligence,"schedule",lambda run:scheduled.append(run.version))
    run=m.CurationRun.objects.create(work=source.asset.edition.work,edition=source.asset.edition,
        document_revision=source,created_by=admin_user,request_id=uuid4(),profile_key=config.profile_key)
    intelligence.prepare(run)
    data={"ranges":[{"page_number":1,"start":0,"end":2,"text":"前言"}]}
    with pytest.raises(remote.RemoteStagePending):
        intelligence._model_artifact(run,2,"window:0",data,"分析",intelligence.ANALYSIS_SCHEMA,config,None)
    run.refresh_from_db();assert run.status=="waiting_remote"
    artifact=run.artifacts.get(stage=2)
    register_executor_heartbeat(executor_id="curation-test",capabilities=["llm_large"],kind="remote_gpu",concurrency=1,
        model_revisions={"llm_large":{"provider":"stl-managed","model":"configured-provider","revision":"managed-v1"}},
        metadata={"task_kinds":["curation_stage"]})
    lease=claim_specific_demand(demand_id=artifact.execution_request["demand_id"],executor_id="curation-test",lease_seconds=300)
    assert lease
    bind_remote_lease_context(lease)
    job=build_remote_job(lease)
    assert "api_key" not in str(job) and "127.0.0.1" not in str(job)
    return run,artifact,lease,job,config,scheduled


def test_remote_stage_receipt_resume_and_empty_cache(source,admin_user,monkeypatch,settings):
    run,artifact,lease,job,config,scheduled=stage(source,admin_user,monkeypatch,settings)
    calls=[]
    def transport(self,**kwargs):
        calls.append(kwargs)
        return AIResult({"summary":"","questions":[],"entities":[],"assertions":[]},config.provider,config.model,"fixture",1,1,{})
    monkeypatch.setattr(AIClient,"generate_json",transport)
    fingerprint=digest(job["prompt"]+"\n<source_data>"+job["input"]+"</source_data>")
    args=(lease.demand_id,"curation-test",lease.lease_token,fingerprint)
    receipt=remote.model_transport(*args)
    assert remote.model_transport(*args)==receipt and len(calls)==1 and calls[0]["strict"]
    result={**job["runtime"],"artifact_id":str(artifact.pk),"output_hash":receipt["output_hash"]}
    complete=dict(executor_id="curation-test",lease_token=lease.lease_token,completion_id="stage-once",result=result)
    assert complete_remote_demand(lease.demand_id,**complete).artifact_ids==[str(artifact.pk)]
    assert complete_remote_demand(lease.demand_id,**complete).idempotent_replay
    assert scheduled==[2]
    run.refresh_from_db()
    cached=intelligence._model_artifact(run,2,"window:0",artifact.input_manifest,"分析",intelligence.ANALYSIS_SCHEMA,config,None)
    assert cached.pk==artifact.pk and len(calls)==1
    assert not m.ChangeSet.objects.exists()


def test_remote_stage_rejects_changed_input_cancel_and_forged_result(source,admin_user,monkeypatch,settings):
    run,artifact,lease,job,config,_=stage(source,admin_user,monkeypatch,settings)
    with pytest.raises(ValidationError):
        remote.model_transport(lease.demand_id,"curation-test",lease.lease_token,"wrong-window")
    with pytest.raises(RemoteWorkerProtocolError):
        complete_remote_demand(lease.demand_id,executor_id="curation-test",lease_token=lease.lease_token,
            completion_id="forged",result={**job["runtime"],"artifact_id":str(artifact.pk),"output_hash":"forged"})
    intelligence.control_run(run.pk,admin_user,"cancel")
    with pytest.raises(ValidationError):
        remote.model_transport(lease.demand_id,"curation-test",lease.lease_token,"wrong-window")
    assert m.CapabilityDemand.objects.get(pk=lease.demand_id).state=="canceled"
