"""Fresh-read writes for existing non-concurrency API regression scenarios.

Version-conflict/security tests deliberately use APIClient directly, so this
helper cannot auto-repair a stale or absent version in those assertions.
"""
import re
from urllib.parse import urlsplit


def editorial_request(client, method, path, *args, **kwargs):
    guarded = re.fullmatch(
        r"/api/catalog/admin/(?:scholars|topics|disciplines|subdisciplines|theory-system/(?:nodes|reading-paths))/[^/]+/",
        urlsplit(path).path,
    )
    if guarded and "HTTP_IF_MATCH" not in kwargs:
        current = client.get(path)
        if current.status_code == 200:
            data = current.data if hasattr(current, "data") else current.json()
            kwargs["HTTP_IF_MATCH"] = data["edit_version"]
    return getattr(client, method)(path, *args, **kwargs)
