"""Share immutable Django imports between workers without reducing concurrency."""
import gc
import os

preload_app = os.environ.get("GUNICORN_PRELOAD", "1") == "1"


def pre_fork(server, worker):
    if preload_app:
        from django.db import connections
        connections.close_all()
        gc.collect()
        gc.freeze()


def post_fork(server, worker):
    if preload_app:
        from django.db import connections
        connections.close_all()
    gc.enable()
