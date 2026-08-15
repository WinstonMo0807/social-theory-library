from __future__ import annotations

from datetime import datetime, time, timedelta
import hashlib
import hmac
import re
import unicodedata
import uuid

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from catalog.models import AnonymousUsageEvent, SearchQueryAggregate


SESSION_COOKIE = "library_anonymous_session"
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
        request.user.is_authenticated and getattr(request.user, "is_staff", False)
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
