"""The maintenance screen must inspect the active pipeline without waking it."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from catalog.services.discovery_health import discovery_model_status
from catalog.services.discovery_inference import DiscoveryInferenceError
from catalog.services import backoffice, system_health


GENERATION = SimpleNamespace(model_repo_id="intfloat/multilingual-e5-small", model_revision="pinned",
    dimensions=384, uid="current-discovery", config_snapshot={"embedding_artifact": "e5", "reranker_artifact": "rerank"})
HEALTH = {"manifest_ready": True, "backend": "onnxruntime-cpu", "threads": 1, "batch_size": 1,
    "models": {"embedding": {"model": GENERATION.model_repo_id, "artifact_id": "e5", "dimensions": 384,
                             "loaded": False, "inference_completed": True},
               "reranker": {"artifact_id": "rerank", "loaded": False, "inference_completed": False}},
    "private": "not-for-response"}


def test_passive_model_check_uses_active_e5_identity_and_does_not_require_residency():
    with patch("catalog.services.discovery_health.active_generation", return_value=GENERATION), \
         patch("catalog.services.discovery_health.inference_health", return_value=HEALTH) as health:
        result = discovery_model_status()
    health.assert_called_once_with(allow_unready=True)
    assert result["model"] == GENERATION.model_repo_id and result["available"] is True
    assert result["health"]["models"]["reranker"]["inference_completed"] is False
    assert "not-for-response" not in str(result)


@pytest.mark.parametrize("case,expected", [("prepared", "prepared"), ("mismatch", "unavailable"),
    ("dimensions", "unavailable"), ("manifest", "unavailable"), ("malformed", "unavailable")])
def test_readiness_is_never_invented(case, expected):
    value = deepcopy(HEALTH)
    if case == "prepared": value["models"]["embedding"]["inference_completed"] = False
    if case == "mismatch": value["models"]["embedding"]["artifact_id"] = "other"
    if case == "dimensions": value["models"]["embedding"]["dimensions"] = 768
    if case == "manifest": value["manifest_ready"] = False
    if case == "malformed": value["models"] = []
    with patch("catalog.services.discovery_health.active_generation", return_value=GENERATION), \
         patch("catalog.services.discovery_health.inference_health", return_value=value):
        result = discovery_model_status()
    assert result["status"] == expected and result["available"] is not True


@pytest.mark.parametrize("on_demand,status", [(True, "unknown"), (False, "unavailable")])
def test_offline_service_is_not_falsely_reported_as_ready_or_definitely_asleep(settings, on_demand, status):
    settings.NAS_ON_DEMAND_ENABLED = on_demand
    with patch("catalog.services.discovery_health.active_generation", return_value=GENERATION), \
         patch("catalog.services.discovery_health.inference_health", side_effect=DiscoveryInferenceError("service_unavailable")):
        result = discovery_model_status()
    assert result["status"] == status and result["available"] is not True


def test_no_active_index_does_not_claim_verified_binding():
    with patch("catalog.services.discovery_health.active_generation", return_value=None), \
         patch("catalog.services.discovery_health.inference_health", return_value=HEALTH):
        assert discovery_model_status()["status"] == "not_ready"


def test_overview_uses_current_discovery_coverage_instead_of_empty_legacy_index(settings):
    settings.DISCOVERY_ENABLED = True
    coverage = {"vector_editions": 6, "eligible_editions": 11, "partial": True}
    with patch.object(backoffice, "_discovery_status", return_value={"status": "current", "active_generation": "current", "coverage": coverage}), \
         patch.object(backoffice, "active_semantic_index_version") as legacy:
        result = backoffice._semantic_status()
    legacy.assert_not_called()
    assert result["status"] == "partial" and "6 / 11" in result["reason"]


def test_periodic_probe_reads_active_remote_counts_and_keeps_partial_coverage_degraded(settings):
    settings.DISCOVERY_ENABLED = True
    with patch("catalog.services.discovery_projection.active_generation", return_value=GENERATION), \
         patch("catalog.services.discovery_projection.discovery_coverage", return_value={"vector_editions": 6, "partial": True}), \
         patch("catalog.services.discovery_projection.meili", return_value={"numberOfDocuments": 8042, "numberOfEmbeddedDocuments": 8042}) as remote:
        result = system_health._semantic_probe()
    assert result.functional is True and result.productive is False
    assert result.error_code == "discovery_coverage_pending"
    remote.assert_called_once_with("GET", "/indexes/current-discovery/stats", timeout=4)


def test_system_overview_never_checks_or_loads_the_legacy_model_when_discovery_is_enabled(settings):
    settings.DISCOVERY_ENABLED = True
    functions = ["_database_status", "_redis_status", "_celery_status", "_nas_status", "_query_lexicon_status",
                 "_semantic_status", "_discovery_status", "_ai_status", "_web_status", "_backup_status"]
    from contextlib import ExitStack
    with ExitStack() as stack:
        for name in functions: stack.enter_context(patch.object(backoffice, name, return_value={}))
        stack.enter_context(patch("ingestion.services.r2_staging.r2_staging_status", return_value={}))
        stack.enter_context(patch("catalog.services.discovery_health.discovery_model_status", return_value={"model": "E5"}))
        legacy = stack.enter_context(patch.object(backoffice, "semantic_model_health"))
        assert backoffice.system_status_snapshot()["embedding"]["model"] == "E5"
        legacy.assert_not_called()


@pytest.mark.django_db
@pytest.mark.parametrize("discovery", [True, False])
def test_recovery_targets_the_enabled_index_family(settings, discovery):
    from catalog.models import HealthIncident, RecoveryAction
    settings.DISCOVERY_ENABLED = discovery
    incident = HealthIncident.objects.create(incident_key="semantic:status-test", capability="search",
        probe_key="semantic", status="open", severity="warning", safe_recovery_actions=["recover_semantic_queue"])
    recovery = RecoveryAction.objects.create(incident=incident, action="recover_semantic_queue")
    with patch("catalog.services.discovery_indexing.reconcile", return_value={"pending_sources": 5}) as current, \
         patch("catalog.services.semantic_indexing.recover_semantic_index_jobs", return_value={"recovered": 0}) as legacy:
        result = system_health.execute_recovery(str(recovery.pk))
    assert result.status == "succeeded"
    assert current.call_count == int(discovery) and legacy.call_count == int(not discovery)
