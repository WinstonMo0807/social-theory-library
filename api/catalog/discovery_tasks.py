"""Celery entry points for reader searches; shared workers own model clients."""
from billiard.exceptions import SoftTimeLimitExceeded
from celery import shared_task
from django.utils import timezone


@shared_task(bind=True, name="catalog.tasks.run_discovery_search", soft_time_limit=600, time_limit=660)
def run_discovery_search(self, session_id, generation):
    from catalog.services.discovery_sessions import execute_session, fail_session
    task_id = str(self.request.id or "")
    try:
        execute_session(session_id, generation, task_id)
    except SoftTimeLimitExceeded:
        fail_session(session_id, generation, task_id, "task_timeout")
    except Exception:
        fail_session(session_id, generation, task_id)
        raise


@shared_task(bind=True, name="catalog.tasks.run_discovery_deep", soft_time_limit=600, time_limit=660)
def run_discovery_deep(self, session_id, generation):
    """Supplement a materialized Discovery session after its first screen."""
    from catalog.services.discovery_sessions import execute_deep_session, fail_deep_session

    task_id = str(self.request.id or "")
    try:
        execute_deep_session(session_id, generation, task_id)
    except SoftTimeLimitExceeded:
        fail_deep_session(session_id, generation, task_id, "deep_task_timeout")
    except Exception:
        fail_deep_session(session_id, generation, task_id, "deep_task_failed")
        raise


@shared_task(name="catalog.tasks.expire_discovery_sessions")
def expire_discovery_sessions():
    from catalog.discovery_models import DiscoverySearchSession
    from catalog.services.discovery_sessions import close_stale_sessions
    closed = close_stale_sessions()
    # Small batches bound maintenance locks and avoid retaining query history.
    identifiers = list(DiscoverySearchSession.objects.filter(expires_at__lt=timezone.now())
                       .order_by("expires_at").values_list("id", flat=True)[:200])
    if identifiers:
        DiscoverySearchSession.objects.filter(pk__in=identifiers).delete()
    return {"expired": len(identifiers), "stale_closed": closed}
