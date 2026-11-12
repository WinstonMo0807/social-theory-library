"""Authenticated single-user Streamable HTTP; no account/OAuth impersonation.

The NAS stores only a random bearer token's SHA-256 digest and expiry. Requests
re-read that file, so removing/rotating a token revokes it without a restart.
Credentials never enter tool arguments, URLs, responses or request logs.
"""
import asyncio
import hashlib
import json
import math
import os
from pathlib import Path
import secrets
import time

MAX_BODY = 2_000_000


class ProtectedMCP:
    def __init__(self, app, config_path):
        self.app = app
        self.config_path = Path(config_path)
        self.capacity = asyncio.Semaphore(2)
        self.read_config()  # fail before listening if auth has not been configured

    def read_config(self):
        raw = self.config_path.read_bytes()
        if len(raw) > 32768:
            raise ValueError("MCP authentication configuration is too large")
        config = json.loads(raw)
        digest = config.get("token_sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("MCP requires a SHA-256 bearer digest")
        if (not config.get("allowed_hosts") or not isinstance(config.get("expires_at"), (int, float))
                or not math.isfinite(config["expires_at"])):
            raise ValueError("MCP requires explicit hosts and token expiry")
        return config

    async def response(self, send, status, code):
        body = json.dumps({"error": code}, separators=(",", ":")).encode()
        headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store"),
                   (b"x-content-type-options", b"nosniff")]
        if status == 401:
            headers.append((b"www-authenticate", b'Bearer realm="STL MCP"'))
        if status == 429:
            headers.append((b"retry-after", b"2"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if scope.get("path") != "/mcp":
            return await self.response(send, 404, "not_found")
        try:
            config = self.read_config()
        except (OSError, ValueError, TypeError):
            return await self.response(send, 503, "authentication_unavailable")
        headers = scope.get("headers", [])
        values = {}
        for name in (b"authorization", b"host", b"origin", b"content-length"):
            matches = [value for key, value in headers if key.lower() == name]
            if len(matches) > 1:
                return await self.response(send, 400, "ambiguous_headers")
            values[name] = matches[0] if matches else b""
        authorization = values[b"authorization"]
        if not authorization.startswith(b"Bearer ") or not 20 <= len(authorization) <= 512:
            return await self.response(send, 401, "unauthorized")
        digest = hashlib.sha256(authorization[7:]).hexdigest()
        if time.time() >= config["expires_at"] or not secrets.compare_digest(digest, config["token_sha256"]):
            return await self.response(send, 401, "unauthorized")
        host = values[b"host"].decode("ascii", errors="replace").casefold()
        if host not in config["allowed_hosts"]:
            return await self.response(send, 421, "untrusted_host")
        origin = values[b"origin"].decode("ascii", errors="replace")
        if origin and origin not in config.get("allowed_origins", []):
            return await self.response(send, 403, "untrusted_origin")
        content_length = values[b"content-length"]
        if content_length and (len(content_length) > 10 or not content_length.isdigit() or int(content_length) > MAX_BODY):
            return await self.response(send, 413, "request_too_large")
        if scope.get("method") not in {"GET", "POST", "DELETE"}:
            return await self.response(send, 405, "method_not_allowed")
        if self.capacity.locked():
            return await self.response(send, 429, "busy")
        # The SDK separately bounds chunked bodies. Session/JSON parsing happens
        # only after token, host and Origin checks, with no browser cookie auth.
        async with self.capacity:
            return await self.app(scope, receive, send)


def create_app():
    from server import mcp
    from mcp.server.transport_security import TransportSecuritySettings
    path = os.environ["STL_MCP_HTTP_AUTH_FILE"]
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    application = mcp.streamable_http_app(streamable_http_path="/mcp", json_response=True, stateless_http=True,
        max_request_body_size=MAX_BODY, transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=config["allowed_hosts"], allowed_origins=config.get("allowed_origins", [])))
    return ProtectedMCP(application, path)


if __name__ == "__main__":
    import uvicorn
    # No container host port is published; the existing Nginx terminates this
    # internal HTTP hop behind Cloudflare's HTTPS endpoint.
    uvicorn.run(create_app(), host="0.0.0.0", port=18982, workers=1, proxy_headers=False, access_log=False)
