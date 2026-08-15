from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4

from django.core.cache import cache, caches


def _release_slot(key: str, token: str) -> None:
    backend = caches["default"]
    if backend.__class__.__module__ == "django.core.cache.backends.redis":
        safe_key = backend.make_key(key)
        client = backend._cache.get_client(safe_key, write=True)
        expected = backend._cache._serializer.dumps(token)
        client.eval(
            "if redis.call('get', KEYS[1]) == ARGV[1] then "
            "return redis.call('del', KEYS[1]) else return 0 end",
            1,
            safe_key,
            expected,
        )
        return
    if cache.get(key) == token:
        cache.delete(key)


@contextmanager
def capacity_slot(namespace: str, *, limit: int, timeout: int):
    """Acquire one short-lived shared slot without holding a web worker in a queue."""

    token = uuid4().hex
    acquired_key = None
    for index in range(max(1, limit)):
        key = f"capacity:{namespace}:{index}"
        if cache.add(key, token, timeout=max(1, timeout)):
            acquired_key = key
            break
    try:
        yield acquired_key is not None
    finally:
        if acquired_key:
            _release_slot(acquired_key, token)
