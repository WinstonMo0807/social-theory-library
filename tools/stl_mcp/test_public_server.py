"""Authentication is tested before any MCP handler or library query runs."""
import asyncio
import hashlib
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest

from public_server import ProtectedMCP


class PublicChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "auth.json"
        self.token = secrets.token_urlsafe(48)
        self.config = {"token_sha256": hashlib.sha256(self.token.encode()).hexdigest(), "expires_at": time.time() + 3600,
                       "allowed_hosts": ["books.example.test"], "allowed_origins": ["https://books.example.test"]}
        self.store()
        self.calls = 0
        self.gate = None

        async def target(scope, receive, send):
            self.calls += 1
            if self.gate:
                await self.gate.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b'{"ok":true}'})

        self.app = ProtectedMCP(target, self.path)

    def tearDown(self):
        self.directory.cleanup()

    def store(self):
        self.path.write_text(json.dumps(self.config), encoding="utf-8")

    async def request(self, token=True, headers=(), method="POST", path="/mcp"):
        sent = []
        values = [(b"host", b"books.example.test")]
        if token:
            values.append((b"authorization", b"Bearer " + (self.token if token is True else token).encode()))
        # Overrides replace one header; a list can explicitly exercise duplicates.
        if isinstance(headers, dict):
            values = [(key, value) for key, value in values if key not in headers]
            values.extend(headers.items())
        else:
            values.extend(headers)

        async def receive():
            return {"type": "http.request", "body": b"{}", "more_body": False}

        async def send(value):
            sent.append(value)

        await self.app({"type": "http", "path": path, "method": method, "headers": values}, receive, send)
        return sent[0]["status"]

    async def test_missing_and_wrong_credentials_never_enter_mcp(self):
        self.assertEqual(await self.request(token=False), 401)
        self.assertEqual(await self.request(token=secrets.token_urlsafe(48)), 401)
        self.assertEqual(self.calls, 0)

    async def test_valid_bearer_enters_handler(self):
        self.assertEqual(await self.request(), 200)
        self.assertEqual(self.calls, 1)

    async def test_expiration_and_rotation_apply_without_restart(self):
        self.config["expires_at"] = time.time() - 1
        self.store()
        self.assertEqual(await self.request(), 401)
        self.config["expires_at"] = time.time() + 3600
        new_token = secrets.token_urlsafe(48)
        self.config["token_sha256"] = hashlib.sha256(new_token.encode()).hexdigest()
        self.store()
        self.assertEqual(await self.request(), 401)
        self.assertEqual(await self.request(token=new_token), 200)

    async def test_host_origin_and_duplicate_auth_are_rejected(self):
        self.assertEqual(await self.request(headers={b"host": b"attacker.example"}), 421)
        self.assertEqual(await self.request(headers={b"origin": b"https://books.example.test.attacker.example"}), 403)
        self.assertEqual(await self.request(headers=[(b"authorization", b"Bearer " + self.token.encode())]), 400)
        self.assertEqual(self.calls, 0)

    async def test_request_limit_method_and_paths(self):
        self.assertEqual(await self.request(headers={b"content-length": b"2000001"}), 413)
        self.assertEqual(await self.request(method="PUT"), 405)
        self.assertEqual(await self.request(path="/mcp/unknown"), 404)
        self.assertEqual(self.calls, 0)

    async def test_broken_auth_config_fails_closed(self):
        self.path.write_text("{}", encoding="utf-8")
        self.assertEqual(await self.request(), 503)
        self.assertEqual(self.calls, 0)

    async def test_concurrency_is_bounded_and_capacity_recovers(self):
        self.gate = asyncio.Event()
        first = asyncio.create_task(self.request())
        second = asyncio.create_task(self.request())
        while self.calls < 2:
            await asyncio.sleep(0)
        self.assertEqual(await self.request(), 429)
        self.gate.set()
        self.assertEqual(await asyncio.gather(first, second), [200, 200])
        self.assertEqual(await self.request(), 200)


if __name__ == "__main__":
    unittest.main()
