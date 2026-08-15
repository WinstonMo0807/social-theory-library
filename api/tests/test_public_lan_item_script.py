import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "verify_public_lan_item.py"
SPEC = importlib.util.spec_from_file_location("verify_public_lan_item", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeEntryClient:
    def __init__(self, label, base, timeout, insecure_tls=False):
        self.label = label
        self.base = base

    def request(self, path, **kwargs):
        if path == "health/":
            return 200, {"version": "2.6.0"}, {}
        if path == "ready/":
            return 200, {"ready": True}, {}
        if path == "auth/me/":
            return 200, {"id": "admin-1", "email": "owner@example.com", "role": "admin"}, {}
        if path == "ingestion/queue-health/":
            return 200, {"ready": True, "worker": {"ok": True}}, {}
        if path == "auth/login/":
            return 200, {"session": "cookie"}, {}
        raise AssertionError(f"unexpected request: {path}")

    def login(self, email, password):
        return {
            "login": "cookie",
            "user": {"id": "admin-1", "email": email, "role": "admin"},
        }

    def find_item(self, item_id, source_filename):
        return {
            "id": item_id or "item-1",
            "source_filename": source_filename or "测试.pdf",
            "status": "needs_review",
            "stage_progress": 88,
            "updated_at": "2026-08-05T08:00:00Z",
            "edition": "edition-1",
            "asset": "asset-original-1",
            "review_data": {
                "work_id": "work-1",
                "public_slug": "",
                "normalized_asset_id": "asset-normalized-1",
                "page_count": 120,
                "title": "测试文献",
            },
        }


def _args():
    return SimpleNamespace(
        public_base="https://books.example.com",
        lan_base="http://192.168.5.6:18080",
        timeout=5.0,
        insecure_tls=False,
        email="owner@example.com",
        password_env="LIBRARY_ACCEPTANCE_ADMIN_PASSWORD",
        item_id="item-1",
        source_filename="",
        expect_status="needs_review",
    )


def test_api_root_keeps_explicit_api_path():
    assert MODULE._api_root("https://books.example.com") == "https://books.example.com/api"
    assert MODULE._api_root("https://books.example.com/api/") == "https://books.example.com/api"


def test_public_and_lan_acceptance_compares_one_database_record(monkeypatch):
    monkeypatch.setenv("LIBRARY_ACCEPTANCE_ADMIN_PASSWORD", "secret-password")
    with patch.object(MODULE, "EntryClient", FakeEntryClient):
        result = MODULE.verify(_args())

    assert result["ok"] is True
    assert result["entries"]["公网"]["item"] == result["entries"]["内网"]["item"]


def test_public_and_lan_acceptance_rejects_different_records(monkeypatch):
    monkeypatch.setenv("LIBRARY_ACCEPTANCE_ADMIN_PASSWORD", "secret-password")

    class MismatchedEntryClient(FakeEntryClient):
        def find_item(self, item_id, source_filename):
            row = super().find_item(item_id, source_filename)
            if self.label == "内网":
                row["updated_at"] = "2026-08-05T08:01:00Z"
            return row

    with patch.object(MODULE, "EntryClient", MismatchedEntryClient):
        with pytest.raises(MODULE.AcceptanceError, match="updated_at"):
            MODULE.verify(_args())
