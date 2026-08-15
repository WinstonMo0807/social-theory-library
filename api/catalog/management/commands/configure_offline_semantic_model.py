from __future__ import annotations

import json
import re

from django.core.management.base import BaseCommand, CommandError

from catalog.models import SiteSetting
from catalog.services.semantic_search import (
    SEMANTIC_RUNTIME_KEY,
    current_semantic_runtime,
    semantic_model_health,
)
from ingestion.models import AuditEvent


class Command(BaseCommand):
    help = "把已预置的固定 Hugging Face snapshot 写入实际语义运行配置。"

    def add_arguments(self, parser):
        parser.add_argument("--repo-id", required=True)
        parser.add_argument("--revision", required=True)
        parser.add_argument("--model-local-path", default="/models")
        parser.add_argument("--dimensions", type=int, default=384)
        parser.add_argument("--pooling", default="useModel")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--require-files", action="store_true")

    def handle(self, *args, **options):
        revision = str(options["revision"]).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", revision):
            raise CommandError("revision 必须是 40 位小写 commit hash。")
        stored = SiteSetting.objects.filter(key=SEMANTIC_RUNTIME_KEY).first()
        before = stored.value if stored and isinstance(stored.value, dict) else {}
        value = {
            **before,
            "engine": "meilisearch_hybrid",
            "provider": "huggingFace",
            "model": str(options["repo_id"]),
            "model_repo_id": str(options["repo_id"]),
            "model_local_path": str(options["model_local_path"]),
            "model_revision": revision,
            "dimensions": max(1, int(options["dimensions"])),
            "pooling": str(options["pooling"]),
            "offline_mode": True,
        }
        runtime = {**current_semantic_runtime(), **value}
        health = semantic_model_health(runtime)
        if options["require_files"] and not health.get("available"):
            raise CommandError(health.get("reason") or "固定模型 snapshot 不完整。")
        output = {
            "configuration": value,
            "model_health": health,
            "changed": before != value,
            "dry_run": bool(options["dry_run"]),
        }
        if options["dry_run"]:
            self.stdout.write(json.dumps(output, ensure_ascii=False, indent=2, default=str))
            return
        setting, _created = SiteSetting.objects.update_or_create(
            key=SEMANTIC_RUNTIME_KEY,
            defaults={"value": value, "public": False, "updated_by": None},
        )
        AuditEvent.objects.create(
            actor=None,
            action="semantic_offline_model_configured",
            object_type="SiteSetting",
            object_id=str(setting.id),
            before=before,
            after=value,
        )
        self.stdout.write(
            self.style.SUCCESS(
                json.dumps(output, ensure_ascii=False, indent=2, default=str)
            )
        )
