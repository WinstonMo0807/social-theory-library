"""Request an allowlisted optional service; Docker access stays on the NAS host."""
import logging
import socket
import time
from urllib.parse import urlsplit

from django.conf import settings

logger = logging.getLogger(__name__)
SERVICES = {"inference", "docx", "searxng", "ocr"}


def ensure_service(name, *, url="", unix_socket=""):
    if not getattr(settings, "NAS_ON_DEMAND_ENABLED", False):
        return
    if name not in SERVICES:
        raise ValueError("Unknown optional service")
    ttl = max(900, int(settings.OCR_REQUEST_TIMEOUT_SECONDS) + 120) if name == "ocr" else 900
    def signal():
        from config.celery import app
        with app.connection_for_write(connect_timeout=2) as connection:
            if connection.transport.driver_type != "redis":
                return False
            with connection.channel() as channel:
                # Longer than the existing bounded inference/conversion requests.
                with channel.client.pipeline() as pipeline:
                    pipeline.set("stl:service-demand:" + name, "1", ex=ttl)
                    pipeline.get("stl:service-stopping:" + name)
                    return bool(pipeline.execute()[-1])
    parsed = urlsplit(url) if url else None
    deadline = time.monotonic() + 15
    while True:
        try:
            stopping = signal()
        except Exception as exc:
            logger.warning("Service demand unavailable (%s)", type(exc).__name__)
            return  # The normal client still returns its actionable failure.
        try:
            if stopping:
                raise OSError("service finishing idle shutdown")
            if unix_socket:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as probe:
                    probe.settimeout(.5)
                    probe.connect(unix_socket)
            else:
                with socket.create_connection((parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)), timeout=.5):
                    pass
            return
        except OSError:
            if time.monotonic() >= deadline:
                return
            time.sleep(.5)
