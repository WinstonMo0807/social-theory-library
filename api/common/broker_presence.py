"""Read queued and unacknowledged deliveries before recovering durable jobs.

This is an at-least-once recovery guard, not an exactly-once claim. The existing
database ownership checks remain authoritative when a delivery races this read.
"""
import json
import logging

from django.conf import settings

logger = logging.getLogger(__name__)
MAX_MESSAGES = 20000


def delivery_id(raw, *, unacked=False):
    message = json.loads(raw)
    if unacked:
        message = message[0]
    headers = message.get("headers") or {}
    return str(headers.get("id") or (message.get("properties") or {}).get("correlation_id") or "")


def broker_delivery_ids():
    """None means unknown: never assume a failed/bounded read is an empty queue."""
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return frozenset()
    from config.celery import app

    queues = {app.conf.task_default_queue or "celery"}
    queues.update(row["queue"] for row in settings.CELERY_TASK_ROUTES.values() if "queue" in row)
    try:
        with app.connection_for_read(connect_timeout=2) as connection:
            if connection.transport.driver_type != "redis":
                return None
            with connection.channel() as channel:
                keys = [channel._q_for_pri(queue, priority)
                        for queue in sorted(queues) for priority in channel.priority_steps]
                client = channel.client
                with client.pipeline() as pipe:
                    for key in keys:
                        pipe.llen(key)
                    pipe.hlen(channel.unacked_key)
                    if sum(pipe.execute()) > MAX_MESSAGES:
                        return None
                with client.pipeline() as pipe:
                    for key in keys:
                        pipe.lrange(key, 0, MAX_MESSAGES)
                    pipe.hvals(channel.unacked_key)
                    rows = pipe.execute()
                if sum(map(len, rows)) > MAX_MESSAGES:
                    return None
                return frozenset(
                    delivery_id(raw, unacked=index == len(keys))
                    for index, messages in enumerate(rows) for raw in messages
                )
    except Exception as exc:
        # Broker exceptions can contain credential-bearing URLs. Log the class only.
        logger.warning("Delivery presence unavailable (%s); pending recovery deferred", type(exc).__name__)
        return None
