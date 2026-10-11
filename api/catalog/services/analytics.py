from __future__ import annotations

from datetime import date, datetime, time, timedelta
import hashlib
import hmac
import re
import unicodedata
import uuid

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from catalog.models import AnonymousUsageEvent, SearchQueryAggregate
from common.capabilities import Capability, has_capability


SESSION_COOKIE = "library_anonymous_session"
PAGE_VIEW_SCOPES = frozenset({
    "home", "explore", "works", "reader", "scholars", "theories", "theory-schools",
    "subdisciplines", "topics", "recommendations", "concepts", "about",
})
BOT_RE = re.compile(r"bot|spider|crawler|slurp|headless|monitor|uptime", re.IGNORECASE)
SENSITIVE_RE = re.compile(
    r"(?:[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b1[3-9]\d{9}\b|\b\d{17}[\dXx]\b|"
    r"(?:api[_-]?key|token|password|密码|身份证|手机号)\s*[:=])",
    re.IGNORECASE,
)


def normalize_query(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return " ".join(value.casefold().split())[:500]


def is_bot_request(request) -> bool:
    return bool(BOT_RE.search(request.META.get("HTTP_USER_AGENT", "")))


def session_identity(request) -> tuple[str, str | None]:
    raw = str(request.COOKIES.get(SESSION_COOKIE) or "").strip()
    replacement = None
    try:
        uuid.UUID(raw)
    except (ValueError, AttributeError):
        raw = str(uuid.uuid4())
        replacement = raw
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        raw.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest, replacement


def record_usage_event(
    request,
    *,
    event_type: str,
    work=None,
    asset=None,
    query: str = "",
    result_count: int | None = None,
    metadata: dict | None = None,
) -> tuple[AnonymousUsageEvent | None, str | None]:
    if is_bot_request(request) or (
        request.user.is_authenticated and (
            getattr(request.user, "is_staff", False)
            or has_capability(request.user, Capability.ACCESS_BACK_OFFICE)
        )
    ):
        return None, None
    session_hash, replacement = session_identity(request)
    normalized = normalize_query(query)
    event_metadata = dict(metadata or {})
    if normalized:
        event_metadata["excluded_from_aggregate"] = bool(SENSITIVE_RE.search(normalized))
    retention_days = max(1, int(getattr(settings, "ANONYMOUS_EVENT_RETENTION_DAYS", 90)))
    event = AnonymousUsageEvent.objects.create(
        event_type=event_type,
        session_hash=session_hash,
        work=work,
        asset=asset,
        normalized_query=normalized,
        result_count=max(0, int(result_count)) if result_count is not None else None,
        metadata=event_metadata,
        expires_at=timezone.now() + timedelta(days=retention_days),
    )
    return event, replacement


def usage_analytics_period(params, *, now):
    """Keep the existing rolling ranges; explicit dates use the library timezone."""
    start_raw, end_raw = params.get("start_date"), params.get("end_date")
    if start_raw is not None or end_raw is not None:
        try:
            start_day, end_day = date.fromisoformat(start_raw), date.fromisoformat(end_raw)
        except (TypeError, ValueError):
            raise ValueError("请同时填写有效的开始和结束日期。") from None
        days = (end_day - start_day).days + 1
        if not 1 <= days <= 365 or end_day > timezone.localtime(now).date():
            raise ValueError("日期范围须为过去的1至365天，开始日期不能晚于结束日期。")
        since = timezone.make_aware(datetime.combine(start_day, time.min))
        until = min(now, timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min)))
    else:
        try:
            days = min(365, max(1, int(params.get("days", "30"))))
        except (TypeError, ValueError):
            raise ValueError("统计天数必须是整数。") from None
        since, until = now - timedelta(days=days), now
    return {"days": days, "since": since, "until": until, "previous_since": since - (until - since), "custom_dates": start_raw is not None}


def usage_analytics_trends(*, period, counts, sessions, now):
    """Aggregate retained events without replacing missing page-view history with reads."""
    since, until, previous_since = period["since"], period["until"], period["previous_since"]
    retention_days = max(1, int(getattr(settings, "ANONYMOUS_EVENT_RETENTION_DAYS", 90)))
    retention_since = now - timedelta(days=retention_days)
    events = AnonymousUsageEvent.objects.filter(created_at__gte=since, created_at__lt=until)
    previous_events = AnonymousUsageEvent.objects.filter(created_at__gte=previous_since, created_at__lt=since)
    previous_counts = dict(previous_events.values("event_type").annotate(count=Count("id")).values_list("event_type", "count"))
    previous_sessions = previous_events.values("session_hash").distinct().count()
    first_page_view = AnonymousUsageEvent.objects.filter(event_type=AnonymousUsageEvent.EventType.PAGE_VIEW).order_by("created_at").values_list("created_at", flat=True).first()
    daily = {
        row["day"]: row for row in events.annotate(day=TruncDate("created_at")).values("day").annotate(
            page_views=Count("id", filter=Q(event_type=AnonymousUsageEvent.EventType.PAGE_VIEW)),
            searches=Count("id", filter=Q(event_type=AnonymousUsageEvent.EventType.SEARCH_SUBMIT)),
            reader_opens=Count("id", filter=Q(event_type=AnonymousUsageEvent.EventType.READER_OPEN)),
        )
    }
    first_day = timezone.localtime(since).date()
    last_day = timezone.localtime(until - timedelta(microseconds=1)).date()
    page_view_day = timezone.localtime(first_page_view).date() if first_page_view else None
    retention_day = timezone.localtime(retention_since).date()
    trend = []
    for offset in range((last_day - first_day).days + 1):
        day = first_day + timedelta(days=offset)
        row = daily.get(day, {})
        within_retention = day >= retention_day
        trend.append({
            "date": day.isoformat(),
            "page_views": row.get("page_views", 0) if within_retention and page_view_day and day >= page_view_day else None,
            "searches": row.get("searches", 0) if within_retention else None,
            "reader_opens": row.get("reader_opens", 0) if within_retention else None,
        })
    comparisons = {}
    for key, current, previous in (
        ("page_views", counts.get("page_view", 0), previous_counts.get("page_view", 0)),
        ("anonymous_sessions", sessions, previous_sessions),
        ("search_submit", counts.get("search_submit", 0), previous_counts.get("search_submit", 0)),
        ("reader_open", counts.get("reader_open", 0), previous_counts.get("reader_open", 0)),
    ):
        status = "available"
        if previous_since < retention_since:
            status = "outside_retention"
        elif key == "page_views" and (first_page_view is None or first_page_view > previous_since):
            status = "page_view_history_incomplete"
        elif previous == 0:
            status = "no_previous_records"
        comparisons[key] = {
            "current": current, "previous": previous,
            "change_percent": round((current - previous) * 100 / previous, 1) if status == "available" else None,
            "status": status,
        }
    return {
        "range": {
            "start": since.isoformat(), "end": until.isoformat(), "previous_start": previous_since.isoformat(),
            "previous_end": since.isoformat(), "timezone": timezone.get_current_timezone_name(),
            "start_date": timezone.localtime(since).date().isoformat(),
            "end_date": last_day.isoformat(),
            "custom_dates": period["custom_dates"], "checked_at": now.isoformat(),
        },
        "trend": trend,
        "comparisons": comparisons,
        "coverage": {
            "retention_days": retention_days, "retained_since": retention_since.isoformat(),
            "page_views_first_recorded_at": first_page_view.isoformat() if first_page_view else None,
            "range_within_retention": since >= retention_since,
            "comparison_within_retention": previous_since >= retention_since,
            "page_views_backfilled": False,
        },
    }


def aggregate_search_queries(*, day=None) -> dict:
    day = day or timezone.localdate()
    start = timezone.make_aware(
        datetime.combine(day, time.min)
    )
    end = start + timedelta(days=1)
    events = AnonymousUsageEvent.objects.filter(
        event_type=AnonymousUsageEvent.EventType.SEARCH_SUBMIT,
        created_at__gte=start,
        created_at__lt=end,
    ).exclude(normalized_query="")
    rows = events.values("normalized_query").annotate(
        search_count=Count("id"),
        unique_sessions=Count("session_hash", distinct=True),
        zero_result_count=Count("id", filter=Q(result_count=0)),
    )
    updated = 0
    for row in rows:
        excluded = bool(
            SENSITIVE_RE.search(row["normalized_query"])
            or row["unique_sessions"] < 2
            or events.filter(
                normalized_query=row["normalized_query"],
                metadata__excluded_from_aggregate=True,
            ).exists()
        )
        clicks = AnonymousUsageEvent.objects.filter(
            event_type=AnonymousUsageEvent.EventType.SEARCH_RESULT_CLICK,
            created_at__gte=start,
            created_at__lt=end,
            normalized_query=row["normalized_query"],
        ).count()
        SearchQueryAggregate.objects.update_or_create(
            period_start=day,
            period="day",
            normalized_query=row["normalized_query"],
            defaults={
                "search_count": row["search_count"],
                "unique_sessions": row["unique_sessions"],
                "click_count": clicks,
                "zero_result_count": row["zero_result_count"],
                "excluded": excluded,
            },
        )
        updated += 1
    deleted, _ = AnonymousUsageEvent.objects.filter(expires_at__lt=timezone.now()).delete()
    return {"day": day.isoformat(), "queries": updated, "expired_events_deleted": deleted}
