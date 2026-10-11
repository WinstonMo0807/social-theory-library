from datetime import datetime, timedelta, timezone as datetime_timezone
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import AnonymousUsageEvent, SearchQueryAggregate
from catalog.analytics_serializers import AdminUsageAnalyticsSerializer
from catalog.services.analytics import SESSION_COOKIE


pytestmark = pytest.mark.django_db
NOW = datetime(2026, 10, 11, 12, tzinfo=datetime_timezone.utc)


@pytest.fixture
def snapshot(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: NOW)
    with timezone.override("Asia/Shanghai"), override_settings(ANONYMOUS_EVENT_RETENTION_DAYS=90):
        yield


@pytest.fixture
def client(snapshot):
    result = APIClient()
    result.force_authenticate(get_user_model().objects.create_user(
        username="usage-trend-admin", email="usage-trend-admin@example.test", role="admin",
    ))
    return result


def event(kind, when, session="a", **kwargs):
    row = AnonymousUsageEvent.objects.create(
        event_type=kind, session_hash=session * 64,
        expires_at=when + timedelta(days=90), **kwargs,
    )
    AnonymousUsageEvent.objects.filter(pk=row.pk).update(created_at=when)
    return row


def test_rolling_comparisons_count_equal_windows_and_distinct_sessions_without_writes(client):
    event("page_view", NOW - timedelta(days=20))
    for day, session in ((9, "a"), (10, "b"), (2, "a"), (1, "a"), (3, "c")):
        event("reader_open", NOW - timedelta(days=day), session)
    for day, session in ((9, "a"), (1, "a"), (1, "d")):
        event("search_submit", NOW - timedelta(days=day), session, normalized_query="文化资本")
    before = list(AnonymousUsageEvent.objects.order_by("id").values_list("id", "created_at", "expires_at"))
    response = client.get("/api/catalog/admin/usage-analytics/?days=7")
    assert response.status_code == 200
    data = response.data
    contract = AdminUsageAnalyticsSerializer(data=data)
    assert contract.is_valid(), contract.errors
    assert data["events"]["reader_open"] == 3 and data["events"]["search_submit"] == 2
    assert data["anonymous_sessions"] == 3
    assert data["comparisons"]["reader_open"] == {"current": 3, "previous": 2, "change_percent": 50.0, "status": "available"}
    assert data["comparisons"]["search_submit"]["change_percent"] == 100.0
    assert data["comparisons"]["anonymous_sessions"]["change_percent"] == 50.0
    assert data["range"]["previous_end"] == data["range"]["start"]
    assert data["range"]["end"] == NOW.isoformat()
    assert "no-store" in response["Cache-Control"] and "private" in response["Cache-Control"]
    assert before == list(AnonymousUsageEvent.objects.order_by("id").values_list("id", "created_at", "expires_at"))


def test_daily_trend_uses_library_midnight_and_leaves_unmeasured_page_views_empty(client):
    event("page_view", datetime(2026, 10, 9, 17, 1, tzinfo=datetime_timezone.utc))
    event("search_submit", datetime(2026, 10, 10, 15, 59, 59, tzinfo=datetime_timezone.utc))
    event("search_submit", datetime(2026, 10, 10, 16, 1, tzinfo=datetime_timezone.utc))
    data = client.get("/api/catalog/admin/usage-analytics/?days=7").data
    by_day = {row["date"]: row for row in data["trend"]}
    assert data["range"]["timezone"] == "Asia/Shanghai"
    assert by_day["2026-10-09"]["page_views"] is None
    assert by_day["2026-10-10"]["page_views"] == 1
    assert by_day["2026-10-10"]["searches"] == 1
    assert by_day["2026-10-11"]["page_views"] == 0
    assert by_day["2026-10-11"]["searches"] == 1
    assert data["comparisons"]["page_views"]["status"] == "page_view_history_incomplete"
    assert data["comparisons"]["page_views"]["change_percent"] is None
    assert data["coverage"]["page_views_backfilled"] is False


def test_exact_range_boundaries_do_not_double_count_or_include_future_events(client):
    for instant in (NOW - timedelta(days=14), NOW - timedelta(days=7), NOW, NOW + timedelta(seconds=1)):
        event("search_submit", instant)
    data = client.get("/api/catalog/admin/usage-analytics/?days=7").data
    assert data["events"]["search_submit"] == 1
    assert data["comparisons"]["search_submit"]["previous"] == 1
    assert sum(row["searches"] for row in data["trend"]) == 1
    assert AnonymousUsageEvent.objects.count() == 4


def test_custom_calendar_dates_have_matching_previous_period_and_query_bounds(client):
    for day in (27, 28, 30):
        event("search_submit", datetime(2026, 9, day, 15, 30, tzinfo=datetime_timezone.utc))
    for day in (1, 2, 3):
        event("search_submit", datetime(2026, 10, day, 15, 30, tzinfo=datetime_timezone.utc))
    event("search_submit", datetime(2026, 10, 3, 16, tzinfo=datetime_timezone.utc))
    for day in ("2026-09-30", "2026-10-01", "2026-10-04"):
        SearchQueryAggregate.objects.create(period_start=day, normalized_query="上期与本期", search_count=1, unique_sessions=2)
    response = client.get("/api/catalog/admin/usage-analytics/?start_date=2026-10-01&end_date=2026-10-03")
    assert response.status_code == 200
    data = response.data
    assert data["period_days"] == 3 and data["range"]["custom_dates"] is True
    assert data["range"]["start_date"] == "2026-10-01" and data["range"]["end_date"] == "2026-10-03"
    assert data["comparisons"]["search_submit"]["current"] == 3
    assert data["comparisons"]["search_submit"]["previous"] == 2
    assert data["comparisons"]["search_submit"]["change_percent"] == 50.0
    assert [row["date"] for row in data["trend"]] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    assert data["top_queries"][0]["search_count"] == 1


@pytest.mark.parametrize("query", [
    "start_date=2026-10-01", "end_date=2026-10-03", "start_date=bad&end_date=2026-10-03",
    "start_date=2026-10-03&end_date=2026-10-01", "start_date=2026-10-01&end_date=2026-10-12",
    "start_date=2024-01-01&end_date=2026-10-03", "days=bad",
])
def test_invalid_or_future_calendar_range_is_rejected_without_changing_events(client, query):
    assert client.get("/api/catalog/admin/usage-analytics/?" + query).status_code == 400
    assert AnonymousUsageEvent.objects.count() == 0


def test_zero_previous_period_and_missing_page_view_history_do_not_invent_percentages(client):
    event("reader_open", NOW - timedelta(days=1))
    data = client.get("/api/catalog/admin/usage-analytics/?days=7").data
    assert data["comparisons"]["reader_open"] == {"current": 1, "previous": 0, "change_percent": None, "status": "no_previous_records"}
    assert data["events"]["page_view"] == 0
    assert all(row["page_views"] is None for row in data["trend"])
    assert data["coverage"]["page_views_first_recorded_at"] is None


def test_long_range_marks_unretained_dates_and_comparison_without_deleting_history(client):
    event("search_submit", NOW - timedelta(days=1))
    event("search_submit", NOW - timedelta(days=100))
    data = client.get("/api/catalog/admin/usage-analytics/?days=365").data
    assert data["coverage"]["range_within_retention"] is False
    assert data["coverage"]["comparison_within_retention"] is False
    assert data["trend"][0]["searches"] is None
    assert all(row["change_percent"] is None and row["status"] == "outside_retention" for row in data["comparisons"].values())
    assert AnonymousUsageEvent.objects.count() == 2


def test_new_public_page_event_keeps_only_coarse_category_and_reuses_anonymous_cookie(snapshot):
    visitor = APIClient()
    visitor.cookies[SESSION_COOKIE] = str(uuid.uuid4())
    for scope in ("home", "explore"):
        response = visitor.post("/api/catalog/usage-events/", {"event_type": "page_view", "scope": scope, "source": "private-address-not-stored"}, format="json", HTTP_USER_AGENT="Mozilla/5.0")
        assert response.status_code == 202 and response.data["accepted"]
    rows = list(AnonymousUsageEvent.objects.order_by("created_at", "id"))
    assert len(rows) == 2 and rows[0].session_hash == rows[1].session_hash
    assert {row.metadata["scope"] for row in rows} == {"home", "explore"}
    assert all(row.metadata["source"] == "public" and row.normalized_query == "" and row.work_id is None and row.asset_id is None for row in rows)
    assert not any(field.name in {"ip", "ip_address", "user"} for field in AnonymousUsageEvent._meta.fields)


def test_page_events_refuse_private_scope_and_payload_identifiers(snapshot):
    visitor = APIClient()
    for payload in (
        {"scope": "/account/notes/private"}, {"scope": "admin"}, {"scope": "https://private.invalid"},
        {"scope": "explore", "query": "private query"}, {"scope": "works", "work_id": str(uuid.uuid4())},
        {"scope": "reader", "asset_id": str(uuid.uuid4())}, {"scope": "home", "result_count": 1},
    ):
        assert visitor.post("/api/catalog/usage-events/", {"event_type": "page_view", **payload}, format="json").status_code == 400
    assert AnonymousUsageEvent.objects.count() == 0


def test_staff_roles_and_robots_are_not_counted_by_the_new_page_tracker(snapshot):
    visitor = APIClient()
    for role in ("admin", "editor", "reviewer"):
        visitor.force_authenticate(get_user_model().objects.create_user(username="usage-" + role, email="usage-" + role + "@example.test", role=role, is_staff=False))
        response = visitor.post("/api/catalog/usage-events/", {"event_type": "page_view", "scope": "home"}, format="json", HTTP_USER_AGENT="Mozilla/5.0")
        assert response.status_code == 202 and response.data["accepted"] is False
    visitor.force_authenticate(None)
    assert visitor.post("/api/catalog/usage-events/", {"event_type": "page_view", "scope": "home"}, format="json", HTTP_USER_AGENT="HeadlessChrome").data["accepted"] is False
    assert AnonymousUsageEvent.objects.count() == 0
