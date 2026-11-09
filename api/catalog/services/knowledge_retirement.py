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
