"""Existing capability leases; one dedicated heavy queue."""
from celery import shared_task
from django.utils import timezone
from catalog.models import CurationRun
from common.task_runtime import register_executor_heartbeat, claim_specific_demand, complete_demand, release_demand


@shared_task(name="catalog.knowledge.refresh_compilations", ignore_result=True, queue="intelligence")
def refresh_compilations():
    from catalog.services.knowledge_compilation import reconcile_pending
    reconcile_pending()


@shared_task(name="catalog.intelligence.refresh_source", ignore_result=True, queue="intelligence")
def refresh_source(job_id, task_id):
    from catalog.services.knowledge_source_updates import execute_source_update
    execute_source_update(job_id, task_id)


@shared_task(name="catalog.intelligence.structure", ignore_result=True, queue="structure")
def execute_structure(job_id):
    import os,time
    from django.db import transaction
    from catalog.models import CapabilityDemand
    from ingestion.models import ProcessingJob
    from catalog.services.document_structure import structure_job, parse_pdf, complete_structure
    from ingestion.services.files import materialize_field_file
    job = ProcessingJob.objects.get(pk=job_id)
    if job.status in {"succeeded","canceled"}: return
    executor_id = "stl-structure-single"
    register_executor_heartbeat(executor_id=executor_id,capabilities=["document_parse"],kind="nas",
        concurrency=1,ttl_seconds=3600,metadata={"task_kinds":["document_structure"]})
    lease = claim_specific_demand(demand_id=job.stats["demand_id"],executor_id=executor_id,lease_seconds=3600)
    if not lease: return
    cleanup=None
    try:
        demand = CapabilityDemand.objects.get(pk=lease.demand_id)
        job,revision = structure_job(demand)
        job.status="running";job.started_at=timezone.now();job.save()
        path,cleanup = materialize_field_file(revision.asset.file)
        start=time.monotonic()
        parsed=parse_pdf(path,checksum=revision.source_checksum,pages=job.stats["input"]["pages"],
            artifacts_path=os.getenv("STL_DOCLING_ARTIFACTS", ""))
        # Complete under the same lease guard used by remote computation.
        with transaction.atomic():
            demand = CapabilityDemand.objects.select_for_update().get(pk=demand.pk)
            if demand.state != "claimed" or demand.lease_token != lease.lease_token or demand.lease_expires_at <= timezone.now():
                raise ValueError("结构执行租约已失效。")
            complete_structure(demand,parsed,elapsed_ms=round((time.monotonic()-start)*1000),executor_id=executor_id)
            complete_demand(demand.pk,lease.lease_token,executor_id=executor_id)
    except Exception as exc:
        if CapabilityDemand.objects.filter(pk=lease.demand_id,state="claimed",lease_token=lease.lease_token).exists():
            ProcessingJob.objects.filter(pk=job_id).exclude(status="canceled").update(status="failed",error_code="structure_failed",error_message=str(exc)[:1200])
        try: release_demand(lease.demand_id,lease.lease_token,executor_id=executor_id,error_code="structure_failed",error_message=str(exc)[:1200],retry=False)
        except ValueError: pass
    finally:
        if cleanup: cleanup()


@shared_task(name="catalog.intelligence.execute", ignore_result=True, queue="intelligence")
def execute_curation(run_id, version):
    from catalog.services.intelligence import execute
    from catalog.services.knowledge_compilation import run_configuration, AgentStagePending
    from ingestion.services.ai_client import AIProviderRateLimited
    from catalog.services.intelligence_remote import RemoteStagePending
    run = CurationRun.objects.filter(pk=run_id, version=version).exclude(status="canceled").first()
    if not run:
        return
    config = run_configuration(run)
    executor_id = "stl-intelligence-single"
    register_executor_heartbeat(executor_id=executor_id, capabilities=["llm_large","document_parse"], kind="nas",
        concurrency=1, ttl_seconds=int(config.timeout)+180, metadata={"task_kinds":["curation_run"]})
    lease = claim_specific_demand(demand_id=run.demand_id, executor_id=executor_id, lease_seconds=int(config.timeout)+180)
    if not lease:
        # A duplicate queue delivery must not change a completed stage's state.
        from catalog.models import CapabilityDemand
        if CapabilityDemand.objects.filter(pk=run.demand_id, state__in=["completed", "canceled"]).exists():
            return
        # Another delivery may own the live lease. It must remain running.
        if CapabilityDemand.objects.filter(pk=run.demand_id, state="claimed", lease_expires_at__gt=timezone.now()).exists():
            return
        CurationRun.objects.filter(pk=run_id,version=version).update(status="waiting_resource", updated_at=timezone.now())
        return
    try:
        execute(run,config,lease)
        complete_demand(lease.demand_id,lease.lease_token,executor_id=executor_id)
    except (RemoteStagePending, AgentStagePending):
        complete_demand(lease.demand_id,lease.lease_token,executor_id=executor_id)
    except Exception as exc:
        waiting = isinstance(exc,AIProviderRateLimited)
        CurationRun.objects.filter(pk=run_id,version=version).exclude(status="canceled").update(
            status="waiting_resource" if waiting else "failed",
            error={"code":getattr(exc,"code",type(exc).__name__),"message":str(exc)[:1200]},updated_at=timezone.now())
        try:
            release_demand(lease.demand_id,lease.lease_token,executor_id=executor_id,
                error_code="resource_busy" if waiting else "curation_failed",error_message=str(exc)[:1200],retry=False)
        except ValueError:
            pass  # A newer lease owns recovery.
