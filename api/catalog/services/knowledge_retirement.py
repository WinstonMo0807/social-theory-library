"""Controlled retirement of the two superseded knowledge AI producers.

Historical candidates/evidence stay readable. Reader research, catalogue
metadata import and publication projections are deliberately outside this set.
"""
from django.db import transaction
from django.utils import timezone
from catalog.models import CapabilityDemand

RETIRED_TASKS=frozenset({"claim_extraction","library_synthesis"})
MESSAGE="旧知识生成任务已退役，请从 Intelligence 创建指定版本的策展任务；历史产物保留。"


def retired_result():
    return {"status":"retired","reason":"knowledge_producer_retired","message":MESSAGE,
        "scheduled":0,"created":0,"publication_blocking":False,"next_url":"/admin/intelligence"}


@transaction.atomic
def cancel_legacy_demand(demand_id):
    from common.task_runtime import _release_executor_load
    demand=CapabilityDemand.objects.select_for_update().get(pk=demand_id)
    if demand.payload.get("task_kind") not in RETIRED_TASKS:
        raise ValueError("此任务不属于本次退役范围。")
    if demand.state in {"completed","canceled"}:
        return False
    if demand.state=="claimed":
        _release_executor_load(demand)
    demand.state="canceled"
    demand.claimed_by=None;demand.lease_token=None;demand.lease_expires_at=None
    demand.last_error_code="knowledge_producer_retired";demand.last_error_message=MESSAGE
    demand.payload={**demand.payload,"retirement":{"at":timezone.now().isoformat(),"history_retained":True}}
    demand.save()
    return True


@transaction.atomic
def cancel_legacy_batch(size=100):
    """Lock a bounded batch; release live leases individually, idle rows in bulk."""
    rows=list(CapabilityDemand.objects.select_for_update().filter(payload__task_kind__in=RETIRED_TASKS)
        .exclude(state__in=["completed","canceled"]).order_by("id")[:size])
    idle=[row.pk for row in rows if row.state!="claimed"]
    count=sum(cancel_legacy_demand(row.pk) for row in rows if row.state=="claimed")
    count+=CapabilityDemand.objects.filter(pk__in=idle).update(state="canceled",claimed_by=None,lease_token=None,
        lease_expires_at=None,last_error_code="knowledge_producer_retired",last_error_message=MESSAGE,updated_at=timezone.now())
    return count


@transaction.atomic
def cancel_legacy_processing_batch(size=100):
    from ingestion.models import ProcessingJob
    ids = list(ProcessingJob.objects.select_for_update().filter(job_type="text_extraction", stats__operation="concept_alignment")
        .exclude(status__in=["succeeded", "canceled"]).order_by("id").values_list("pk", flat=True)[:size])
    return ProcessingJob.objects.filter(pk__in=ids).update(status="canceled", task_id="", finished_at=timezone.now(),
        error_code="knowledge_producer_retired", error_message=MESSAGE, updated_at=timezone.now())
