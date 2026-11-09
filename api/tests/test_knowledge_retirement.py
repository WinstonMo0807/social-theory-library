"""Retire model producers while retaining projections and human history."""
from uuid import uuid4
import pytest
from django.core.management import call_command
from django.utils import timezone
from datetime import timedelta
from catalog import models as m
from catalog.services.knowledge_retirement import cancel_legacy_demand
from tests.test_knowledge_core import source

pytestmark=pytest.mark.django_db


def test_old_sources_do_not_schedule_or_persist_model_results(source):
    from catalog.services.claims.pipeline import schedule_document_claim_extraction,extract_claims_shadow,persist_claim_candidates
    from catalog.services.research.library_synthesis import schedule_library_synthesis,persist_library_synthesis_candidate
    assert schedule_document_claim_extraction(source)["status"]=="retired"
    assert extract_claims_shadow(None)["status"]=="retired"
    assert schedule_library_synthesis(None,upload_item=None)["status"]=="retired"
    with pytest.raises(ValueError,match="退役"):
        persist_claim_candidates(None,[],prompt_key="",prompt_version="",provider="",model="",model_revision="")
    with pytest.raises(ValueError,match="退役"):
        persist_library_synthesis_candidate(None,{},provider="",model="",model_revision="")
    assert not m.CapabilityDemand.objects.exists() and not m.DerivedClaim.objects.exists()


def test_retirement_only_cancels_old_leases_and_blocks_remote_writeback():
    from common.remote_worker import complete_remote_demand,RemoteWorkerProtocolError
    executor=m.CapabilityExecutor.objects.create(executor_id="retirement-test",kind="remote_gpu",current_load=1)
    token=uuid4()
    old=m.CapabilityDemand.objects.create(owner_type="legacy",owner_key="history",capability="llm_small",idempotency_key="legacy",
        state="claimed",claimed_by=executor,lease_token=token,lease_expires_at=timezone.now()+timedelta(minutes=5),payload={"task_kind":"claim_extraction"})
    projection=m.CapabilityDemand.objects.create(owner_type="processing_job",owner_key="projection",capability="projection",
        idempotency_key="projection",state="ready",payload={"task_kind":"projection_refresh"})
    with pytest.raises(RemoteWorkerProtocolError,match="停止写回"):
        complete_remote_demand(old.pk,executor_id=executor.executor_id,lease_token=token,completion_id="late",result={})
    call_command("retire_legacy_knowledge_tasks",apply=True)
    old.refresh_from_db();executor.refresh_from_db();projection.refresh_from_db()
    assert old.state=="canceled" and old.lease_token is None and executor.current_load==0
    assert projection.state=="ready" and m.CapabilityDemand.objects.count()==2
    assert not cancel_legacy_demand(old.pk)


def test_default_heartbeat_keeps_publication_projection(monkeypatch):
    from catalog.tasks import heartbeat_claim_executor
    monkeypatch.setattr("catalog.services.projection_refresh.dispatch_ready_projection_demands",lambda **kwargs:{"dispatched":2})
    result=heartbeat_claim_executor.run()
    assert result["dispatch"]["projection"]["dispatched"]==2
    assert set(result["capabilities"])=={"projection","cpu_light"}
