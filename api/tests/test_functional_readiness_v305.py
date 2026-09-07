from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from catalog.models import Edition, HealthCheckRun, HealthIncident, Work
from catalog.services.system_health import (
    HEALTH_CHECKS, _active_revision_probe, _external_public_probe, _workbench_probe,
    functional_health_snapshot, run_health_probe,
)
from .test_publication_invariants_v305 import published_edition


pytestmark = pytest.mark.django_db


def test_workbench_probe_exercises_real_builder_without_changing_catalog(admin_user):
    from catalog.services.cataloging_sessions import open_cataloging_session

    session, _created = open_cataloging_session(actor=admin_user, source_type="manual", title="探针样本")
    before = (Work.objects.count(), Edition.objects.count(), session.edition.field_decisions.count())
    result = _workbench_probe()
    assert result.functional is True
    assert (Work.objects.count(), Edition.objects.count(), session.edition.field_decisions.count()) == before


def test_workbench_500_becomes_failed_probe_and_incident(admin_user):
    Edition.objects.create(work=Work.objects.create(title="已有书目", document_type="book"))
    with patch("catalog.services.admin_workflow.build_edition_workflow", side_effect=TypeError("missing catalog_state")):
        run = run_health_probe("catalog_workbench", actor=admin_user)
    assert run.status == "failed"
    assert HealthIncident.objects.filter(probe_key="catalog_workbench", status="open").exists()


def test_bad_active_pointer_is_not_hidden_by_database_connectivity():
    edition, _revision = published_edition("当前书目")
    _other, foreign = published_edition("其他版本")
    Edition.objects.filter(pk=edition.pk).update(active_catalog_revision=foreign)
    result = _active_revision_probe()
    assert result.functional is False
    assert result.details["invalid_pointers"] == 1


def test_external_edge_does_not_authorize_application_rollback(settings):
    settings.PUBLIC_DEPLOYMENT_MODE = True
    settings.PUBLIC_WEB_URL = "https://example.test"
    with patch("catalog.services.system_health.http_service_health", return_value={"reachable": False}):
        result = _external_public_probe()
    assert result.error_code == "external_edge_unavailable"
    assert result.details["application_rollback_allowed"] is False
    assert HEALTH_CHECKS.get("external_public").safe_recovery_actions == ("rerun_probe",)


def test_external_200_without_valid_api_payload_is_not_healthy(settings):
    settings.PUBLIC_DEPLOYMENT_MODE = True
    settings.PUBLIC_WEB_URL = "https://example.test"
    with patch("catalog.services.system_health.http_service_health", return_value={"reachable": True, "functional": False}):
        result = _external_public_probe()
    assert result.functional is False


def test_readiness_http_explicitly_limits_its_claim(api_client):
    result = api_client.get("/api/ready/")
    assert result.status_code == 200
    assert result.json()["application_functional"] == "not_evaluated"
    assert result.json()["external_access"] == "not_evaluated"


def test_layer_snapshot_reports_unprobed_or_stale_results_as_unknown():
    HealthCheckRun.objects.create(probe_key="database", capability="catalog_core", status="healthy", source="manual",
                                  started_at=timezone.now() - timedelta(hours=1))
    with patch("catalog.services.processing_center_diagnostics.processing_center_diagnostics", return_value={}):
        result = functional_health_snapshot()
    layers = {row["key"]: row for row in result["layers"]}
    assert set(layers) == {"infrastructure", "application", "external"}
    database = next(row for row in layers["infrastructure"]["checks"] if row["key"] == "database")
    assert database["status"] == "unknown"
    assert result["page_load_performs_live_probes"] is False


def test_empty_database_cannot_pass_release_functional_gate():
    from io import StringIO
    from django.core.management import call_command
    from django.core.management.base import CommandError

    output = StringIO()
    with pytest.raises(CommandError, match="尚未全部"):
        call_command("check_functional_readiness", stdout=output)
    assert '"status": "SKIPPED"' in output.getvalue()
    assert '"canonical_mutated": false' in output.getvalue()
    assert not HealthCheckRun.objects.exists()
