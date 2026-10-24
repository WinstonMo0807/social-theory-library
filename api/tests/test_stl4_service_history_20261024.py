"""Deferred M26 pagination, scope and read-only acceptance definitions."""
from datetime import timedelta
from unittest.mock import patch
import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from catalog.models import HealthCheckRun

pytestmark = pytest.mark.django_db
URL = "/api/catalog/admin/local-services/history/"


def test_history_pages_saved_records_without_any_probe_and_keeps_removed_service(admin_user):
    earlier = timezone.now() - timedelta(hours=1)
    for index in range(31):
        HealthCheckRun.objects.create(probe_key="local-services:retired-service", capability="generation", started_at=earlier + timedelta(seconds=index),
            summary="此原始摘要不应进入展示", details={"service_status": "partial", "safe_detail": "仅合成的安全检查说明"})
    HealthCheckRun.objects.create(probe_key="unrelated-private-probe", details={"safe_detail": "别的检查不要混入"})
    client = APIClient(); client.force_authenticate(user=admin_user)
    with patch("catalog.local_services._check", side_effect=AssertionError("GET must never probe")):
        first = client.get(URL, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
        assert first.status_code == 200 and first.data["count"] == 31 and len(first.data["results"]) == 24
        second = client.get(URL, {"page": 2, "as_of": first.data["as_of"]}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
        assert len(second.data["results"]) == 7
        assert set(row["id"] for row in first.data["results"]).isdisjoint(row["id"] for row in second.data["results"])
        assert first["Cache-Control"] == "private, no-store"
        assert "此原始摘要不应进入展示" not in str(first.data) and "别的检查不要混入" not in str(first.data)
        filtered = client.get(URL, {"service_id": "retired-service", "status": "partial"}, HTTP_X_EDITOR_OWNER=str(admin_user.pk))
        assert filtered.data["count"] == 31


def test_history_rejects_invalid_queries_and_unauthorized_access(admin_user):
    client = APIClient(); client.force_authenticate(user=admin_user)
    assert client.get(URL + "?page=1&page=2").status_code == 400
    assert client.get(URL, {"as_of": (timezone.now() + timedelta(days=1)).isoformat()}).status_code == 400
    assert client.get(URL, HTTP_X_EDITOR_OWNER="different-account").status_code == 403
    assert APIClient().get(URL).status_code in (401, 403)
