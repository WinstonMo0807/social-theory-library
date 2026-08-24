import uuid

from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.services.semantic_indexing import recover_semantic_index_jobs, run_semantic_index_job
from catalog.services.recommendations import current_snapshot, ensure_default_policies
from catalog.services.analytics import aggregate_search_queries
from catalog.models import ResearchRun, SearchEvaluationRun
from catalog.services.search_evaluation import (
    SearchEvaluationExecutionError,
    SearchEvaluationValidationError,
    execute_evaluation,
)
from catalog.services.query_lexicon.sync import process_pending_events
from catalog.services.query_lexicon.operations import run_query_lexicon_reconciliation as run_ql_reconciliation


def _claim_research_task(run_id, task_id: str) -> tuple[bool, str]:
    """Bind legacy blank rows and verify the preassigned Celery owner."""

    task_id = str(task_id or "").strip()
    if not task_id:
        run = ResearchRun.objects.only("status").get(pk=run_id)
        return False, run.status
    now = timezone.now()
    with transaction.atomic():
        run = ResearchRun.objects.select_for_update(of=("self",)).get(pk=run_id)
        if (
            run.status == ResearchRun.Status.QUEUED
            and run.is_current
            and not str(run.task_id or "").strip()
        ):
            run.task_id = task_id
        if run.status == ResearchRun.Status.QUEUED and run.is_current and str(run.task_id or "").strip() == task_id:
            # Refresh the row at the moment the Worker actually claims it. A
            # legitimately queued task may have waited longer than the stale
            # threshold while still being owned by Celery.
            run.updated_at = now
            run.save(update_fields=["task_id", "updated_at"])
        return (
            run.status == ResearchRun.Status.QUEUED
            and run.is_current
            and str(run.task_id or "").strip() == task_id,
            run.status,
        )


def _write_research_task_terminal(
    run_id,
    task_id: str,
    *,
    status_value: str,
    error_code: str,
    error_message: str,
    diagnostic_detail: str,
) -> str | None:
    now = timezone.now()
    with transaction.atomic():
        run = ResearchRun.objects.select_for_update(of=("self",)).filter(pk=run_id).first()
        if run is None:
            return None
        if (
            run.status not in {ResearchRun.Status.QUEUED, ResearchRun.Status.RUNNING}
            or not run.is_current
            or str(run.task_id or "").strip() != task_id
        ):
            return run.status
        diagnostics = dict(run.diagnostics or {})
        errors = list(diagnostics.get("errors") or [])
        errors.append(
            {
                "code": error_code,
                "detail": diagnostic_detail,
                "provider": "research_orchestrator",
            }
        )
        diagnostics["errors"] = errors
        run.status = status_value
        run.diagnostics = diagnostics
        run.error_code = error_code
        run.error_message = error_message[:2000]
        run.finished_at = now
        run.save(
            update_fields=[
                "status",
                "diagnostics",
                "error_code",
                "error_message",
                "finished_at",
                "updated_at",
            ]
        )
        return run.status


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    soft_time_limit=40,
    time_limit=50,
)
def execute_research_run(self, run_id):
    from catalog.services.research.orchestrator import ResearchOrchestrator

    task_id = str(self.request.id or "")
    owned, current_status = _claim_research_task(run_id, task_id)
    if not owned:
        return {
            "id": str(run_id),
            "status": current_status,
            "ignored": "owner_mismatch",
        }
    try:
        run = ResearchOrchestrator().execute(str(run_id), task_id=task_id)
    except SoftTimeLimitExceeded:
        current_status = _write_research_task_terminal(
            run_id,
            task_id,
            status_value=ResearchRun.Status.DEGRADED,
            error_code="research_timeout",
            error_message="外部研究超过 40 秒预算。",
            diagnostic_detail="外部研究超过 40 秒预算，已保留馆内候选并进入降级状态。",
        )
        return {"id": str(run_id), "status": current_status}
    except Exception as exc:
        _write_research_task_terminal(
            run_id,
            task_id,
            status_value=ResearchRun.Status.FAILED,
            error_code="research_task_failed",
            error_message=str(exc)[:2000],
            diagnostic_detail="Research Worker 在进入或执行研究服务时失败。",
        )
        raise
    return {"id": str(run.id), "status": run.status}


@shared_task(bind=True, ignore_result=True, soft_time_limit=20, time_limit=25)
def heartbeat_claim_executor(self):
    """A heartbeat consumed by the default NAS Celery worker."""

    from catalog.models import CapabilityExecutor
    from catalog.services.claims.pipeline import dispatch_ready_claim_extraction_demands
    from catalog.services.projection_refresh import dispatch_ready_projection_demands
    from common.ai_runtime import (
        AICapability,
        profile_environment_status,
        runtime_profile,
    )
    from common.task_runtime import register_executor_heartbeat

    # This task is itself consumed by the default NAS queue, so a successful
    # heartbeat proves that bounded projection orchestration has an executor.
    capabilities = ["cpu_light", "projection"]
    model_revisions = {}
    profile_summary = {"enabled": False, "profile_key": "", "provider": "none", "model": ""}
    try:
        profile = runtime_profile(AICapability.CLAIM_EXTRACTION)
        environment = profile_environment_status(profile)
        available = bool(
            profile.enabled
            and profile.model
            and environment["endpoint_configured"]
            and environment["credential_configured"]
        )
        if available:
            capabilities.append("llm_small")
            revision = (
                profile.reasoning.get("model_revision")
                if isinstance(profile.reasoning, dict)
                else ""
            )
            model_revisions[AICapability.CLAIM_EXTRACTION] = str(
                revision or profile.model
            )[:300]
        profile_summary = {
            "enabled": available,
            "profile_key": profile.key,
            "provider": profile.provider,
            "model": profile.model,
        }
    except (RuntimeError, TypeError, ValueError):
        pass
    hostname = str(getattr(self.request, "hostname", "") or "default")[:120]
    executor = register_executor_heartbeat(
        executor_id=f"nas-celery:{hostname}",
        display_name=f"NAS Celery {hostname}",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=capabilities,
        model_revisions=model_revisions,
        concurrency=1,
        metadata={
            "transport": "celery",
            "queue": "celery",
            "claim_extraction": profile_summary,
            "task_kinds": [
                "projection_refresh",
                *(["claim_extraction"] if "llm_small" in capabilities else []),
            ],
            "task_profiles": (
                {"claim_extraction": [profile_summary["profile_key"]]}
                if "llm_small" in capabilities and profile_summary["profile_key"]
                else {}
            ),
        },
        ttl_seconds=90,
    )
    claim_dispatched = (
        dispatch_ready_claim_extraction_demands(limit=10)
        if "llm_small" in capabilities
        else {"candidates": 0, "dispatched": 0}
    )
    projection_dispatched = dispatch_ready_projection_demands(limit=10)
    return {
        "executor_id": executor.executor_id,
        "capabilities": executor.capabilities,
        "dispatch": {
            "claim_extraction": claim_dispatched,
            "projection": projection_dispatched,
        },
    }


@shared_task(bind=True, ignore_result=True, soft_time_limit=150, time_limit=180)
def execute_claim_extraction_demand(self, demand_id, lease_token, executor_id):
    """Execute one previously leased EvidenceSpan claim extraction demand."""

    from catalog.models import CapabilityDemand, DocumentRevision, EvidenceSpan
    from catalog.services.claims.pipeline import (
        _scheduled_runtime_identity,
        dispatch_ready_claim_extraction_demands,
        extract_claims_shadow,
        resolve_claim_extraction_prompt,
        schedule_document_claim_extraction,
    )
    from common.task_runtime import complete_demand, release_demand, renew_demand_lease

    try:
        lease = renew_demand_lease(
            demand_id,
            lease_token,
            executor_id=executor_id,
            lease_seconds=240,
        )
        demand = CapabilityDemand.objects.get(pk=lease.demand_id)
        payload = dict(demand.payload or {})
        if payload.get("task_kind") != "claim_extraction":
            raise ValueError("capability demand task_kind is not claim_extraction")
        span = EvidenceSpan.objects.select_related(
            "document_revision__asset__edition__work",
            "page__asset",
        ).get(pk=payload.get("evidence_span_id"))
        revision = span.document_revision
        prompt = resolve_claim_extraction_prompt(key=str(payload.get("prompt_key") or "claim_extraction"))
        runtime = _scheduled_runtime_identity()
        prompt_changed = any(
            str(payload.get(field) or "") != str(prompt[value] or "")
            for field, value in (
                ("prompt_content_hash", "content_hash"),
                ("prompt_schema_hash", "schema_hash"),
            )
        )
        runtime_changed = any(
            str(payload.get(field) or "") != str(runtime[field] or "")
            for field in ("profile_key", "provider", "model", "model_revision")
        )
        if prompt_changed or runtime_changed:
            complete_demand(
                demand.id,
                lease.lease_token,
                executor_id=executor_id,
            )
            replacement = schedule_document_claim_extraction(revision)
            return {
                "demand_id": str(demand.id),
                "status": "superseded_configuration",
                "replacement": replacement,
            }

        result = extract_claims_shadow(
            span,
            prompt_key=prompt["key"],
            prompt_version=prompt["version"],
            model_revision=str(payload.get("model_revision") or ""),
        )
        if result.get("status") in {"completed", "skipped"}:
            complete_demand(
                demand.id,
                lease.lease_token,
                executor_id=executor_id,
            )
            unfinished = CapabilityDemand.objects.filter(
                payload__task_kind="claim_extraction",
                payload__document_revision_id=str(revision.id),
            ).exclude(
                state__in=[
                    CapabilityDemand.State.COMPLETED,
                    CapabilityDemand.State.CANCELED,
                ]
            ).exists()
            if not unfinished:
                from catalog.services.claims.indexing import index_document_revision_claims

                result["claim_index"] = index_document_revision_claims(revision)
            result["next_dispatch"] = dispatch_ready_claim_extraction_demands(limit=1)
        else:
            release_demand(
                demand.id,
                lease.lease_token,
                executor_id=executor_id,
                error_code=str(result.get("error_code") or "claim_extraction_degraded"),
                error_message=str(result.get("message") or "claim extraction degraded"),
                retry=True,
                retry_after_seconds=60,
            )
        return {"demand_id": str(demand.id), **result}
    except SoftTimeLimitExceeded:
        try:
            release_demand(
                demand_id,
                lease_token,
                executor_id=executor_id,
                error_code="claim_extraction_timeout",
                error_message="Claim extraction exceeded its task time budget.",
                retry=True,
                retry_after_seconds=120,
            )
        except (CapabilityDemand.DoesNotExist, ValueError):
            pass
        return {
            "demand_id": str(demand_id),
            "status": "degraded",
            "error_code": "claim_extraction_timeout",
            "publication_blocking": False,
        }
    except (CapabilityDemand.DoesNotExist, DocumentRevision.DoesNotExist, EvidenceSpan.DoesNotExist, RuntimeError, TypeError, ValueError) as exc:
        try:
            release_demand(
                demand_id,
                lease_token,
                executor_id=executor_id,
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                retry=True,
                retry_after_seconds=60,
            )
        except (CapabilityDemand.DoesNotExist, ValueError):
            pass
        return {
            "demand_id": str(demand_id),
            "status": "degraded",
            "error_code": exc.__class__.__name__,
            "publication_blocking": False,
        }


@shared_task(bind=True, ignore_result=True, soft_time_limit=840, time_limit=900)
def execute_projection_demand(self, demand_id, lease_token, executor_id):
    """Run one leased projection coordinator without replacing specialist jobs."""

    from catalog.models import CapabilityDemand
    from catalog.services.projection_refresh import run_projection_refresh_job
    from common.task_runtime import complete_demand, release_demand, renew_demand_lease

    try:
        lease = renew_demand_lease(
            demand_id,
            lease_token,
            executor_id=executor_id,
            lease_seconds=900,
        )
        demand = CapabilityDemand.objects.get(pk=lease.demand_id)
        payload = dict(demand.payload or {})
        if payload.get("task_kind") != "projection_refresh":
            raise ValueError("capability demand task_kind is not projection_refresh")
        job = run_projection_refresh_job(
            str(payload.get("processing_job_id") or demand.owner_key),
            task_id=str(self.request.id or ""),
        )
        if job.status == "failed":
            release_demand(
                demand.id,
                lease.lease_token,
                executor_id=executor_id,
                error_code=job.error_code or "projection_refresh_failed",
                error_message=job.error_message or "Projection refresh failed.",
                # This demand represents one ProcessingJob attempt. A later
                # coordinator reconciliation creates the next attempt demand,
                # so the failed attempt must not remain independently
                # dispatchable and race the same durable job.
                retry=False,
            )
        else:
            # A RUNNING parent means the coordinator safely delegated semantic
            # writes to durable SemanticIndexJob rows. Their completion hooks
            # own freshness from this point onward.
            complete_demand(
                demand.id,
                lease.lease_token,
                executor_id=executor_id,
            )
        return {
            "demand_id": str(demand.id),
            "job_id": str(job.id),
            "status": job.status,
        }
    except Exception as exc:
        try:
            demand = CapabilityDemand.objects.get(pk=demand_id)
            if demand.state == CapabilityDemand.State.CLAIMED:
                from ingestion.models import ProcessingJob

                payload = dict(demand.payload or {})
                processing_job = ProcessingJob.objects.filter(
                    pk=payload.get("processing_job_id") or demand.owner_key,
                    job_type=ProcessingJob.JobType.PROJECTION_REFRESH,
                ).first()
                retry_same_attempt = not (
                    processing_job is not None
                    and processing_job.status == ProcessingJob.Status.FAILED
                )
                release_demand(
                    demand_id,
                    lease_token,
                    executor_id=executor_id,
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                    # A coordinator exception already persisted the durable
                    # ProcessingJob attempt as failed. Leave that demand
                    # terminal so reconciliation creates exactly one next
                    # attempt demand. Failures before the job runs may safely
                    # retry the same lease demand.
                    retry=retry_same_attempt,
                    retry_after_seconds=60,
                )
        except (CapabilityDemand.DoesNotExist, ValueError):
            pass
        return {
            "demand_id": str(demand_id),
            "status": "failed",
            "error_code": exc.__class__.__name__,
        }


@shared_task(ignore_result=True, soft_time_limit=20, time_limit=25)
def run_scheduled_health_probes():
    from catalog.services.system_health import run_due_health_probes

    try:
        return run_due_health_probes()
    except SoftTimeLimitExceeded:
        return {
            "due": None,
            "executed": None,
            "runs": [],
            "skipped": "time_budget",
        }


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def execute_health_recovery(self, recovery_id):
    from catalog.services.system_health import execute_recovery

    recovery = execute_recovery(
        str(recovery_id),
        task_id=str(self.request.id or ""),
    )
    return {"id": str(recovery.id), "status": recovery.status, "attempt": recovery.attempt}


@shared_task(
    bind=True,
    ignore_result=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def build_semantic_index(self, job_id):
    job = run_semantic_index_job(str(job_id), task_id=str(self.request.id or ""))
    return {"id": str(job.id), "status": job.status, "stats": job.stats}


@shared_task(ignore_result=True)
def recover_semantic_index_queue():
    return recover_semantic_index_jobs()


@shared_task(ignore_result=True)
def recover_projection_queue():
    from catalog.services.projection_refresh import reconcile_projection_runtime

    return reconcile_projection_runtime(limit=50)


@shared_task(ignore_result=True)
def process_query_lexicon_events():
    return process_pending_events()


@shared_task(ignore_result=True)
def recover_query_lexicon_events():
    return {
        "events": process_pending_events(),
        "reconciliation": recover_query_lexicon_reconciliation_jobs(),
    }


@shared_task(bind=True, ignore_result=True)
def run_query_lexicon_reconciliation(self, job_id, task_id=""):
    job = run_ql_reconciliation(job_id=str(job_id), task_id=str(task_id or self.request.id or ""))
    return {"job_id": str(job.id), "status": job.status, "stats": job.stats}


@shared_task(
    bind=True,
    autoretry_for=(OSError, ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
    ignore_result=True,
)
def run_projection_refresh(self, job_id):
    from catalog.services.projection_refresh import run_projection_refresh_job

    task_id = str(self.request.id or "")
    job = run_projection_refresh_job(str(job_id), task_id=task_id)
    return {"job_id": str(job.id), "status": job.status, "stats": job.stats}


def recover_query_lexicon_reconciliation_jobs(*, limit: int = 20):
    from django.utils import timezone
    from ingestion.models import ProcessingJob
    from catalog.services.query_lexicon.operations import _job_payload

    jobs = ProcessingJob.objects.filter(
        job_type=ProcessingJob.JobType.QUERY_LEXICON_RECONCILE,
        status=ProcessingJob.Status.FAILED,
        error_code="queue_unavailable",
    ).order_by("created_at")[:limit]
    queued = 0
    for job in jobs:
        job.status = ProcessingJob.Status.PENDING
        job.task_id = str(uuid.uuid4())
        job.error_code = ""
        job.error_message = ""
        job.started_at = None
        job.finished_at = None
        job.save(update_fields=["status", "task_id", "error_code", "error_message", "started_at", "finished_at", "updated_at"])
        run_query_lexicon_reconciliation.apply_async(
            args=[str(job.id), job.task_id],
            task_id=job.task_id,
            queue=settings.QUERY_LEXICON_TASK_QUEUE,
        )
        queued += 1
    return {"candidates": len(jobs), "requeued": queued}


@shared_task(ignore_result=True)
def rotate_due_recommendations():
    """Keep every public placement on the same durable three-day snapshot."""

    refreshed = []
    for policy in ensure_default_policies():
        if not policy.enabled:
            continue
        snapshot = current_snapshot(policy)
        if snapshot is not None:
            refreshed.append({"placement": policy.placement, "snapshot": str(snapshot.id)})
    return refreshed


@shared_task(ignore_result=True)
def aggregate_anonymous_searches():
    return aggregate_search_queries()


@shared_task(bind=True, ignore_result=True)
def run_search_evaluation(self, run_id):
    run = SearchEvaluationRun.objects.select_related("evaluation_set", "index_version").get(pk=run_id)
    if run.status == SearchEvaluationRun.Status.COMPLETED:
        return {"id": str(run.id), "status": run.status}
    if run.index_version_id is None:
        run.status = SearchEvaluationRun.Status.FAILED
        run.error_message = "候选索引版本已不存在，无法运行评估。"
        run.save(update_fields=["status", "error_message", "updated_at"])
        return {"id": str(run.id), "status": run.status}
    try:
        completed = execute_evaluation(
            run.evaluation_set,
            run.index_version,
            semantic_ratio=run.semantic_ratio,
            actor=run.created_by,
            existing_run=run,
        )
    except SearchEvaluationValidationError as exc:
        run.refresh_from_db()
        run.status = SearchEvaluationRun.Status.FAILED
        run.error_message = "检索评估预检未通过。"
        run.config_snapshot = {**run.config_snapshot, "validation_plan": exc.plan}
        run.save(
            update_fields=["status", "error_message", "config_snapshot", "updated_at"]
        )
        return {"id": str(run.id), "status": run.status}
    except SearchEvaluationExecutionError as exc:
        return {"id": str(exc.run.id), "status": exc.run.status}
    return {"id": str(completed.id), "status": completed.status}
