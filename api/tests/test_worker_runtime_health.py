from unittest.mock import patch

from django.test import override_settings

from ingestion.services.health import worker_runtime_status


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_worker_runtime_status_uses_fresh_heartbeat_without_control_probe():
    heartbeat = {
        "online": True,
        "heartbeat_at": "2026-08-09T00:00:00+00:00",
        "detail": "在线",
    }
    with (
        patch(
            "ingestion.services.health.worker_heartbeat_status",
            return_value=heartbeat,
        ),
        patch("ingestion.services.health._celery_worker_control_ping") as control,
    ):
        result = worker_runtime_status()

    assert result["online"] is True
    assert result["source"] == "heartbeat"
    assert result["control_error"] == ""
    control.assert_not_called()


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_worker_runtime_status_uses_control_ping_when_heartbeat_is_stale():
    heartbeat = {
        "online": False,
        "heartbeat_at": "",
        "detail": "没有收到近期 worker 心跳",
    }
    with (
        patch(
            "ingestion.services.health.worker_heartbeat_status",
            return_value=heartbeat,
        ),
        patch(
            "ingestion.services.health._celery_worker_control_ping",
            return_value={"online": True, "worker_count": 1},
        ),
    ):
        result = worker_runtime_status(control_timeout_seconds=0.1)

    assert result["online"] is True
    assert result["source"] == "control_ping"
    assert result["worker_count"] == 1
    assert result["checked_at"]
    assert result["detail"] == "worker 控制通道可响应"


@override_settings(CELERY_TASK_ALWAYS_EAGER=False)
def test_worker_runtime_status_keeps_stale_result_when_control_probe_fails():
    heartbeat = {
        "online": False,
        "heartbeat_at": "",
        "detail": "没有收到近期 worker 心跳",
    }
    with (
        patch(
            "ingestion.services.health.worker_heartbeat_status",
            return_value=heartbeat,
        ),
        patch(
            "ingestion.services.health._celery_worker_control_ping",
            side_effect=OSError("broker unavailable"),
        ),
    ):
        result = worker_runtime_status(control_timeout_seconds=0.1)

    assert result["online"] is False
    assert result["source"] == "heartbeat"
    assert result["worker_count"] == 0
    assert "broker unavailable" in result["control_error"]
