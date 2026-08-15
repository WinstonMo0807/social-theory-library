from unittest.mock import patch

import pytest


@pytest.mark.django_db
def test_readiness_reports_database_and_migrations_ready(api_client):
    response = api_client.get("/api/ready/")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "ready"
    assert payload["database"] is True
    assert payload["pending_migrations"] == 0


@pytest.mark.django_db
def test_readiness_rejects_pending_migrations_without_exposing_names(api_client):
    with patch("config.urls.MigrationExecutor") as executor:
        executor.return_value.loader.graph.leaf_nodes.return_value = [("accounts", "latest")]
        executor.return_value.migration_plan.return_value = [object()]
        response = api_client.get("/api/ready/")
        payload = response.json()

    assert response.status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["database"] is True
    assert payload["pending_migrations"] == 1
    assert "accounts" not in response.content.decode("utf-8")
