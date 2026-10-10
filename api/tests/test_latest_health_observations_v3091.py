from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from catalog.models import HealthCheckRun
from catalog.services.system_health import _latest_runs

pytestmark = pytest.mark.django_db


def test_latest_health_records_do_not_materialize_historical_payloads():
    now = timezone.now()
    rows = [
        HealthCheckRun(
            probe_key=probe,
            capability="search",
            status="healthy",
            source="manual",
            started_at=now - timedelta(minutes=offset + 1),
            details={"historical_payload": "x" * 1024},
        )
        for probe in ("semantic", "query_lexicon")
        for offset in range(32)
    ]
    HealthCheckRun.objects.bulk_create(rows)
    newest = {
        probe: HealthCheckRun.objects.create(
            probe_key=probe,
            capability="search",
            status="degraded",
            source="manual",
            started_at=now,
            details={"current": probe},
        )
        for probe in ("semantic", "query_lexicon")
    }
    with patch.object(HealthCheckRun, "from_db", wraps=HealthCheckRun.from_db) as hydrated:
        latest = _latest_runs()
    assert {key: row.pk for key, row in latest.items()} == {
        key: row.pk for key, row in newest.items()
    }
    assert hydrated.call_count == len(newest)
    assert all(row.details == {"current": key} for key, row in latest.items())
