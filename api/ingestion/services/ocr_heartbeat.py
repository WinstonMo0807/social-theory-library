"""Worker lease and service activity are distinct from completed-page progress."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
import threading
import time
import httpx
from django.conf import settings
from django.db import close_old_connections, connections, transaction
from django.utils import timezone
from ingestion.models import ProcessingJob

request_identity = ContextVar("ocr_request_identity", default="")
logger = logging.getLogger(__name__)


def record_heartbeat(job_id, task_id, activity=None):
    with transaction.atomic():
        job = ProcessingJob.objects.select_for_update().filter(pk=job_id, task_id=task_id, status="running").first()
        if job is None:
            return False
        job.heartbeat_at = timezone.now()
        fields = ["heartbeat_at"]
        if activity:
            job.stats = {**job.stats, "service_activity": activity, "service_checked_at": job.heartbeat_at.isoformat()}
            fields.append("stats")
        job.save(update_fields=fields)
        return True


@contextmanager
def ocr_request_lease(job, identity):
    token = request_identity.set(identity)
    stop = threading.Event()
    record_heartbeat(job.pk, job.task_id)
    # The HTTP client also has a deadline; a hung worker cannot renew forever.
    deadline = time.monotonic() + settings.OCR_REQUEST_TIMEOUT_SECONDS + 30
    def heartbeat():
        try:
            while not stop.wait(15) and time.monotonic() < deadline:
                close_old_connections()
                activity = "unavailable"
                try:
                    with httpx.Client(trust_env=False, timeout=3) as client:
                        response = client.get(settings.PADDLEOCR_SERVICE_URL.rstrip("/") + "/v1/requests/" + identity)
                        if response.status_code == 200:
                            state = response.json().get("state")
                            if state in {"queued", "running", "completed", "failed"}:
                                activity = state
                except (httpx.HTTPError, ValueError):
                    pass  # Worker heartbeat still proves the worker is alive, not model progress.
                if not record_heartbeat(job.pk, job.task_id, activity):
                    break
        except Exception:
            logger.exception("OCR worker heartbeat failed for job %s", job.pk)
        finally:
            connections.close_all()
    thread = threading.Thread(target=heartbeat, name="ocr-heartbeat", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)
        request_identity.reset(token)
