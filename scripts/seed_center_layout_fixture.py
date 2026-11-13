"""Synthetic layout records in the already isolated local SQLite fixture only."""
import json
import os
from pathlib import Path
import socket
import sys
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
runtime = json.loads((ROOT / "output/public-visual-20261110/audit/FIXTURE_RUNTIME.json").read_text())
directory = Path(runtime["fixture_directory"]).resolve()
assert directory.name.startswith("stl-v305-e2e-") and directory.parent == Path(os.environ["TEMP"]).resolve()
assert runtime["api_url"] == "http://127.0.0.1:18111/api"
database = directory / "local_fixture.sqlite3"
assert database.is_file()

def offline(*args, **kwargs):
    raise OSError("Layout fixture cannot connect to external services")

socket.socket.connect = offline
socket.socket.connect_ex = offline
os.environ.update(
    DJANGO_SETTINGS_MODULE="config.settings", DATABASE_URL=f"sqlite:///{database.as_posix()}",
    DJANGO_SECRET_KEY="local-e2e-fixture-only-not-for-production-305", DJANGO_DEBUG="true",
    NAS_LIBRARY_ROOT=str(directory / "media"), NAS_INCOMING_ROOT=str(directory / "incoming"),
    CELERY_BROKER_URL="memory://", CELERY_TASK_ALWAYS_EAGER="false", CACHE_URL="",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)
sys.path.insert(0, str(ROOT / "api"))
import django
django.setup()
from django.conf import settings
assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
assert Path(settings.DATABASES["default"]["NAME"]).resolve() == database

from accounts.models import User
from reading import research, share_scope, privacy
from reading.models import ResearchProject, ResearchTurn, PersonalReadingPlan, CitationAudit, ReadingList
from reading.sharing_models import ReaderShare
from django.utils import timezone
from datetime import timedelta

owner = User.objects.get(email="owner-v305@example.test")
ids = {}
def uid(number):
    return UUID(f"61000000-0000-4000-8000-{number:012d}")

project, _ = ResearchProject.objects.update_or_create(id=uid(1), defaults={"user": owner,
    "data_ciphertext": research.pack({"title": "隔离排版测试研究", "question": "测试长标题与来源位置", "notes": "合成测试资料，不是真实研究。", "scope": {"kind": "library"}, "selections": [], "removed_selections": [], "comparison": {"dimensions": [], "cells": []}, "layout": {}, "use_confirmed_memories": False, "confirmed_memory_ids": []})})
turn, _ = ResearchTurn.objects.get_or_create(id=uid(2), defaults={"project": project, "status": "failed",
    "error_code": "service_unavailable", "data_ciphertext": research.pack({"question": "隔离测试问题", "scope": {}, "selected_refs": [], "replay_title": "隔离测试历史", "replay_note": "未调用模型或检索服务。", "replay_tags": []})})
plan, _ = PersonalReadingPlan.objects.get_or_create(id=uid(3), defaults={"user": owner, "project": project,
    "task_pending": False, "data_ciphertext": research.pack({"title": "隔离排版测试计划", "goal": "核对原有字段与布局", "items": [], "stages": [], "enhancement_status": "not_requested", "status": "draft"})})
booklist, _ = ReadingList.objects.get_or_create(id=uid(4), defaults={"user": owner, "title": "隔离测试书单", "description": "用于真实页面排版验证的合成记录。"})
issue = {"id": str(uid(6)), "raw": "[隔离测试引用]", "entry_ids": [], "findings": [], "decision": None}
audit, _ = CitationAudit.objects.update_or_create(id=uid(5), defaults={"user": owner, "status": "failed", "error_code": "service_unavailable",
    "data_ciphertext": research.pack({"title": "隔离测试稿件", "filename": "layout-fixture.pdf", "filetype": "pdf", "scope": "public_library", "checks": [], "bibliography": [], "occurrences": [issue], "warnings": ["合成页面状态，未执行识别或模型分析。"], "parsed": True, "stage": "report"})})
spec = {"source_kind": "research", "source_id": str(project.id), "expected_version": privacy.version(project), "questions": ["project"], "materials": [], "notes": [], "message": "仅本地测试库内的合成记录。"}
projected, bindings = share_scope.content(owner, spec)
share, _ = ReaderShare.objects.update_or_create(id=uid(7), defaults={"user": owner, "source_kind": "research", "source_id": project.id,
    "destination": "proposal", "expires_at": timezone.now() + timedelta(days=7),
    "data_ciphertext": research.pack({"specification": spec, "bindings": bindings, "content_hash": share_scope.digest(projected), "recipient_bindings": [], "sender_binding": None})})
ids.update(project=str(project.id), turn=str(turn.id), plan=str(plan.id), booklist=str(booklist.id), audit=str(audit.id), issue=issue["id"], share=str(share.id))
(ROOT / "output/public-visual-20261110/runtime/layout-fixture-ids.json").write_text(json.dumps(ids, indent=2)+"\n")
print("Created/reused 7 synthetic records in the disposable fixture; no services called.")
