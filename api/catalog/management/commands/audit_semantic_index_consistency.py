from __future__ import annotations

import json
from pathlib import Path

import httpx
from django.core.management.base import BaseCommand, CommandError

from catalog.models import SemanticIndexVersion
from catalog.services.semantic_index_consistency import (
    audit_semantic_index_consistency,
    repair_semantic_index_version_metadata,
)


class Command(BaseCommand):
    help = "只读核对 SemanticIndexVersion、SemanticChunk 与 Meilisearch 文档一致性。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--index-version",
            default="",
            help="SemanticIndexVersion UUID 或 UID；省略时审计 active 版本。",
        )
        parser.add_argument("--json", default="", help="可选 JSON 报告输出路径。")
        parser.add_argument("--include-ids", action="store_true")
        parser.add_argument(
            "--repair-metadata",
            action="store_true",
            help="仅在非 active 版本且 corpus 完全一致时修正 document_count。",
        )

    def _version(self, value: str) -> SemanticIndexVersion:
        value = str(value or "").strip()
        if value:
            version = SemanticIndexVersion.objects.filter(uid=value).first()
            if version is None:
                version = SemanticIndexVersion.objects.filter(pk=value).first()
        else:
            version = (
                SemanticIndexVersion.objects.filter(
                    status=SemanticIndexVersion.Status.ACTIVE
                )
                .order_by("-activated_at", "-created_at")
                .first()
            )
        if version is None:
            raise CommandError("找不到需要审计的 SemanticIndexVersion。")
        return version

    def handle(self, *args, **options):
        version = self._version(options["index_version"])
        try:
            if options["repair_metadata"]:
                report = repair_semantic_index_version_metadata(version)
            else:
                report = audit_semantic_index_consistency(
                    version,
                    include_ids=options["include_ids"],
                )
        except (ValueError, RuntimeError, httpx.HTTPError) as exc:
            raise CommandError(str(exc)) from exc

        payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
        output = str(options["json"] or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(f"report={path}")
        else:
            self.stdout.write(payload)
