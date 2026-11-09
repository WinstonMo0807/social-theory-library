"""Existing capability leases; one dedicated heavy queue."""
from celery import shared_task
from django.utils import timezone
from catalog.models import CurationRun
from common.task_runtime import register_executor_heartbeat, claim_specific_demand, complete_demand, release_demand


@shared_task(name="catalog.intelligence.execute", ignore_result=True, queue="intelligence")
def execute_curation(run_id, version):
    from catalog.services.intelligence import execute
    from catalog.services.intelligence_provider import configuration
    from ingestion.services.ai_client import AIProviderRateLimited
    run = CurationRun.objects.filter(pk=run_id, version=version).exclude(status="canceled").first()
    if not run:
        return
    config = configuration(run.profile_key)
    executor_id = "stl-intelligence-single"
    register_executor_heartbeat(executor_id=executor_id, capabilities=["llm_large","document_parse"], kind="nas",
        concurrency=1, ttl_seconds=int(config.timeout)+180, metadata={"task_kinds":["curation_run"]})
    lease = claim_specific_demand(demand_id=run.demand_id, executor_id=executor_id, lease_seconds=int(config.timeout)+180)
    if not lease:
        CurationRun.objects.filter(pk=run_id,version=version).update(status="waiting_resource")
        return
    try:
        execute(run,config,lease)
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
