from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.utils import timezone

from catalog.models import (
    CanonicalObjectRevision,
    CapabilityDemand,
    CapabilityExecutor,
    DomainChangeEvent,
    HealthIncident,
    IntelligenceFeedback,
    ProjectionState,
    Work,
)
from catalog.services.processing_center_diagnostics import processing_center_diagnostics


pytestmark = pytest.mark.django_db


def _section(snapshot, key):
    return next(row for row in snapshot["sections"] if row["key"] == key)


def test_projection_diagnostic_explains_revision_lag_and_exposes_only_bounded_refresh():
    work = Work.objects.create(title="投影诊断样本")
    CanonicalObjectRevision.objects.create(
        object_type="work",
        object_id=work.id,
        current_revision=4,
    )
    change = DomainChangeEvent.objects.create(
        object_type="work",
        object_id=work.id,
        canonical_revision=4,
        change_kind=DomainChangeEvent.ChangeKind.UPDATE,
        changed_fields=["title", "description"],
        idempotency_key=f"diagnostic-change:{uuid4()}",
    )
    ProjectionState.objects.create(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.SEMANTIC,
        source_revision=4,
        projected_revision=2,
        status=ProjectionState.Status.STALE,
    )
    ProjectionState.objects.create(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.CLAIM_INDEX,
        source_revision=4,
        projected_revision=1,
        status=ProjectionState.Status.STALE,
    )

    snapshot = processing_center_diagnostics()
    items = _section(snapshot, "projections")["items"]
    semantic = next(row for row in items if row["details"]["projection_type"] == "semantic")
    claim_index = next(row for row in items if row["details"]["projection_type"] == "claim_index")

    assert semantic["details"]["source_revision"] == 4
    assert semantic["details"]["projected_revision"] == 2
    assert semantic["details"]["revision_lag"] == 2
    assert semantic["details"]["unprocessed_domain_change"] == str(change.id)
    assert semantic["safe_actions"] == [
        {
            "key": "bounded_projection_refresh",
            "label": "安全刷新相关投影",
            "endpoint": f"/catalog/admin/projection-status/work/{work.id}/refresh/",
            "method": "POST",
            "body": {"force": False},
        }
    ]
    assert claim_index["safe_actions"] == []
    assert "没有与该投影类型匹配" in claim_index["guidance"]


def test_missing_capability_uses_fresh_heartbeat_and_preserves_waiting_task():
    now = timezone.now()
    CapabilityExecutor.objects.create(
        executor_id="gpu-laptop",
        display_name="RTX 4070",
        kind=CapabilityExecutor.Kind.REMOTE_GPU,
        capabilities=["llm_large"],
        status=CapabilityExecutor.Status.ONLINE,
        last_heartbeat_at=now - timedelta(minutes=4),
        heartbeat_expires_at=now - timedelta(minutes=3),
    )
    demand = CapabilityDemand.objects.create(
        owner_type="ResearchRun",
        owner_key=str(uuid4()),
        capability="llm_large",
        state=CapabilityDemand.State.WAITING_FOR_CAPABILITY,
        publication_blocking=False,
        idempotency_key=f"diagnostic-demand:{uuid4()}",
    )

    snapshot = processing_center_diagnostics()
    items = _section(snapshot, "capabilities")["items"]

    assert len(items) == 1
    assert items[0]["details"]["capability"] == "llm_large"
    assert items[0]["details"]["waiting_count"] == 1
    assert items[0]["publication_blocking"] is False
    assert items[0]["safe_actions"] == []
    assert "不阻断发布" not in items[0]["reason"]
    demand.refresh_from_db()
    assert demand.state == CapabilityDemand.State.WAITING_FOR_CAPABILITY
    assert snapshot["executors"][0]["heartbeat_fresh"] is False


def test_capability_diagnostic_matches_task_kind_and_profile_not_coarse_capability():
    now = timezone.now()
    CapabilityExecutor.objects.create(
        executor_id="small-claims-only",
        kind=CapabilityExecutor.Kind.NAS,
        capabilities=["llm_small"],
        status=CapabilityExecutor.Status.ONLINE,
        last_heartbeat_at=now,
        heartbeat_expires_at=now + timedelta(minutes=2),
        metadata={
            "task_kinds": ["claim_extraction"],
            "task_profiles": {"claim_extraction": ["local-v1"]},
        },
    )
    CapabilityDemand.objects.create(
        owner_type="ResearchRun",
        owner_key=str(uuid4()),
        capability="llm_small",
        state=CapabilityDemand.State.WAITING_FOR_CAPABILITY,
        publication_blocking=False,
        idempotency_key=f"diagnostic-kind-profile:{uuid4()}",
        payload={
            "task_kind": "claim_extraction",
            "profile_key": "cloud-v2",
        },
    )

    snapshot = processing_center_diagnostics()
    items = _section(snapshot, "capabilities")["items"]

    assert len(items) == 1
    assert items[0]["details"]["capability"] == "llm_small"
    assert items[0]["details"]["task_kind"] == "claim_extraction"
    assert items[0]["details"]["task_profile"] == "cloud-v2"
    assert "capability、task kind 与 profile" in items[0]["reason"]
    assert snapshot["executors"][0]["task_profiles"] == {
        "claim_extraction": ["local-v1"]
    }


def test_provider_diagnostics_are_degraded_without_exposing_alias_values_or_blocking_publication():
    profile_document = {
        "version": "ai-runtime-profiles-v2",
        "source": "database",
        "active": {"claim_extraction": "claims-primary"},
        "profiles": [
            {
                "key": "claims-primary",
                "capability": "claim_extraction",
                "provider": "openai_compatible",
                "model": "private-model-name",
                "enabled": True,
                "endpoint_alias": "private-endpoint",
                "credential_alias": "private-credential",
            }
        ],
    }
    incident = HealthIncident.objects.create(
        incident_key=f"provider-diagnostic:{uuid4()}",
        capability="external_research",
        probe_key="authority.openalex",
        status=HealthIncident.Status.OPEN,
        severity=HealthIncident.Severity.WARNING,
        error_code="provider_timeout",
        error_message="OpenAlex 最近一次请求超时。",
        affected_features=["学者身份候选"],
        safe_recovery_actions=["rerun_probe"],
    )

    with (
        patch(
            "catalog.services.processing_center_diagnostics.current_profile_document",
            return_value=profile_document,
        ),
        patch(
            "catalog.services.processing_center_diagnostics.profile_environment_status",
            return_value={
                "endpoint_configured": False,
                "credential_configured": False,
                "restart_may_be_required": True,
            },
        ),
    ):
        snapshot = processing_center_diagnostics()

    items = _section(snapshot, "providers")["items"]
    config_item = next(row for row in items if row["id"].startswith("provider:claim_extraction"))
    incident_item = next(row for row in items if row["id"] == f"provider-incident:{incident.id}")

    assert config_item["publication_blocking"] is False
    assert config_item["safe_actions"] == []
    assert "private-endpoint" not in str(config_item)
    assert "private-credential" not in str(config_item)
    assert incident_item["safe_actions"][0]["body"]["incident_id"] == str(incident.id)
    assert incident_item["safe_actions"][0]["body"]["recovery_action"] == "rerun_probe"
    assert snapshot["page_load_performs_live_probes"] is False


def test_functional_health_endpoint_includes_persisted_processing_diagnostics(api_client, admin_user):
    work = Work.objects.create(title="Processing Center API 样本")
    ProjectionState.objects.create(
        object_type="work",
        object_id=work.id,
        projection_type=ProjectionState.ProjectionType.FULLTEXT,
        source_revision=2,
        projected_revision=1,
        status=ProjectionState.Status.STALE,
        stale_reason="作品标题 revision 已变化。",
    )
    IntelligenceFeedback.objects.create(
        reviewed_by=admin_user,
        task_profile_key="claim_extraction",
        provider="local",
        prompt_key="claim_extraction",
        candidate_type="derived_claim",
        candidate_id="processing-calibration-sample",
        decision=IntelligenceFeedback.Decision.ACCEPT_WITH_EDIT,
    )
    api_client.force_authenticate(admin_user)

    response = api_client.get("/api/catalog/admin/functional-health/")

    assert response.status_code == 200
    diagnostics = response.data["diagnostics"]
    assert diagnostics["version"] == "processing-center-diagnostics-v1"
    assert diagnostics["summary"]["stale_projection_count"] >= 1
    assert diagnostics["page_load_performs_live_probes"] is False
    assert diagnostics["feedback_calibration"] == [
        {
            "task_profile_key": "claim_extraction",
            "provider": "local",
            "prompt_key": "claim_extraction",
            "decisions": {"accept_with_edit": 1},
            "total": 1,
            "acceptance_rate": 1.0,
        }
    ]
