from __future__ import annotations

from datetime import datetime, timedelta
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from kombu import Connection


_CREDENTIALS_IN_URL = re.compile(r"(?P<scheme>[a-z][a-z0-9+.-]*://)(?P<credentials>[^/@\s]+)@", re.I)


def safe_service_error(exc: Exception, *, limit: int = 300) -> str:
    message = _CREDENTIALS_IN_URL.sub(r"\g<scheme>***@", str(exc))
    return f"{exc.__class__.__name__}: {message}"[:limit]


def cache_health(*, probe_key: str) -> dict:
    try:
        marker = timezone.now().isoformat()
        cache.set(probe_key, marker, timeout=20)
        if cache.get(probe_key) != marker:
            raise RuntimeError("缓存写入后未能读回探针值")
        return {"reachable": True, "detail": "可连接"}
    except Exception as exc:
        return {"reachable": False, "detail": safe_service_error(exc)}


def celery_broker_health() -> dict:
    try:
        connection = Connection(
            settings.CELERY_BROKER_URL,
            connect_timeout=2,
            transport_options={
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
            },
        )
        try:
            connection.connect()
            connection.channel().close()
        finally:
            connection.release()
        return {"reachable": True, "detail": "可连接"}
    except Exception as exc:
        return {"reachable": False, "detail": safe_service_error(exc)}


def worker_heartbeat_status(*, max_age_seconds: int = 180) -> dict:
    heartbeat = None
    try:
        heartbeat = cache.get("ingestion:worker-heartbeat")
    except Exception as exc:
        return {
            "online": False,
            "heartbeat_at": "",
            "detail": safe_service_error(exc),
        }

    heartbeat_at = None
    if heartbeat:
        try:
            heartbeat_at = datetime.fromisoformat(str(heartbeat))
            if timezone.is_naive(heartbeat_at):
                heartbeat_at = timezone.make_aware(heartbeat_at)
        except (TypeError, ValueError):
            heartbeat_at = None
    online = bool(
        settings.CELERY_TASK_ALWAYS_EAGER
        or (
            heartbeat_at
            and heartbeat_at >= timezone.now() - timedelta(seconds=max_age_seconds)
        )
    )
    return {
        "online": online,
        "heartbeat_at": heartbeat_at.isoformat() if heartbeat_at else "",
        "detail": "在线" if online else "没有收到近期 worker 心跳",
    }


def _celery_worker_control_ping(*, timeout_seconds: float = 2.0) -> dict:
    """Probe the Celery worker main process without queueing another task."""

    from config.celery import app as celery_app

    replies = celery_app.control.inspect(timeout=timeout_seconds).ping() or {}
    return {
        "online": bool(replies),
        "worker_count": len(replies),
    }


def worker_runtime_status(
    *,
    max_age_seconds: int = 180,
    control_timeout_seconds: float = 2.0,
) -> dict:
    """Report a busy worker as online even when its queued heartbeat is delayed.

    The production worker has concurrency one. A long OCR task can therefore
    delay the periodic heartbeat task even though the Celery main process and
    its running child remain healthy. Only fall back to the control channel
    when the cheap cache heartbeat is stale.
    """

    heartbeat = worker_heartbeat_status(max_age_seconds=max_age_seconds)
    if heartbeat["online"]:
        return {
            **heartbeat,
            "source": "heartbeat",
            "checked_at": heartbeat["heartbeat_at"],
            "worker_count": 1,
            "control_error": "",
        }

    try:
        control = _celery_worker_control_ping(
            timeout_seconds=control_timeout_seconds,
        )
    except Exception as exc:
        return {
            **heartbeat,
            "source": "heartbeat",
            "checked_at": "",
            "worker_count": 0,
            "control_error": safe_service_error(exc),
        }

    if control["online"]:
        checked_at = timezone.now().isoformat()
        return {
            **heartbeat,
            "online": True,
            "detail": "worker 控制通道可响应",
            "source": "control_ping",
            "checked_at": checked_at,
            "worker_count": control["worker_count"],
            "control_error": "",
        }
    return {
        **heartbeat,
        "source": "heartbeat",
        "checked_at": "",
        "worker_count": 0,
        "control_error": "",
    }


def http_service_health(url: str, path: str = "", *, timeout: int = 4) -> dict:
    if not url:
        return {"configured": False, "reachable": True, "detail": "未配置"}
    target = f"{url.rstrip('/')}{path}"
    try:
        request = Request(target, method="GET")
        with urlopen(request, timeout=timeout) as response:
            reachable = 200 <= int(response.status) < 500
        return {"configured": True, "reachable": reachable, "detail": "可连接"}
    except (OSError, URLError, ValueError) as exc:
        return {
            "configured": True,
            "reachable": False,
            "detail": safe_service_error(exc),
        }
