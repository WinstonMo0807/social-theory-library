from __future__ import annotations

import csv
from io import StringIO
import json
from pathlib import Path
import uuid

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ingestion.services.admin_foundation_backfill import (
    action_summary,
    apply_admin_foundation_backfill,
    plan_admin_foundation_backfill,
)


class Command(BaseCommand):
    help = (
        "审计并安全回填人物权威状态、旧元数据候选来源及人工审核任务。"
        "默认只预览；只有 --apply 才会写入。"
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--apply", action="store_true", help="执行报告中的增量回填。")
        mode.add_argument("--dry-run", action="store_true", help="只预览，这是默认模式。")
        parser.add_argument("--item-id", action="append", default=[], help="只检查指定 UploadItem，可重复。")
        parser.add_argument("--person-id", action="append", default=[], help="只检查指定 Person，可重复。")
        parser.add_argument(
            "--limit",
            type=int,
            default=500,
            help="人物和入库记录各自最多检查的数量，0 表示不限制。默认 500。",
        )
        parser.add_argument(
            "--format",
            choices=["text", "json", "csv"],
            default="text",
            help="报告格式。",
        )
        parser.add_argument("--output", default="", help="可选报告文件路径；不提供时写到标准输出。")

    def _validated_ids(self, values, label):
        identifiers = []
        for value in values:
            try:
                identifiers.append(str(uuid.UUID(str(value))))
            except (TypeError, ValueError, AttributeError) as exc:
                raise CommandError(f"{label} 不是有效 UUID：{value}") from exc
        return identifiers

    def _render(self, report: dict, output_format: str) -> str:
        if output_format == "json":
            return json.dumps(report, ensure_ascii=False, indent=2, default=str)
        if output_format == "csv":
            stream = StringIO()
            writer = csv.DictWriter(
                stream,
                fieldnames=["mode", "code", "target_type", "target_id", "reason", "details"],
            )
            writer.writeheader()
            for action in report["actions"]:
                writer.writerow(
                    {
                        "mode": report["mode"],
                        "code": action["code"],
                        "target_type": action["target_type"],
                        "target_id": action["target_id"],
                        "reason": action["reason"],
                        "details": json.dumps(action["details"], ensure_ascii=False, sort_keys=True),
                    }
                )
            return stream.getvalue()
        lines = [
            f"mode={report['mode']} actions={report['action_count']} limit={report['scope']['limit']}",
            "summary=" + json.dumps(report["summary"], ensure_ascii=False, sort_keys=True),
        ]
        if report.get("applied") is not None:
            lines.append("applied=" + json.dumps(report["applied"], ensure_ascii=False, sort_keys=True))
        for action in report["actions"]:
            lines.append(
                f"{action['code']} {action['target_type']}:{action['target_id']} {action['reason']}"
            )
        return "\n".join(lines)

    def handle(self, *args, **options):
        if options["limit"] < 0:
            raise CommandError("--limit 不能小于 0。")
        item_ids = self._validated_ids(options["item_id"], "--item-id")
        person_ids = self._validated_ids(options["person_id"], "--person-id")
        actions = plan_admin_foundation_backfill(
            item_ids=item_ids,
            person_ids=person_ids,
            limit=options["limit"],
        )
        mode = "apply" if options["apply"] else "dry-run"
        applied = apply_admin_foundation_backfill(actions) if options["apply"] else None
        report = {
            "schema_version": 1,
            "backfill": "admin-foundation-v1",
            "generated_at": timezone.now().isoformat(),
            "mode": mode,
            "scope": {
                "item_ids": item_ids,
                "person_ids": person_ids,
                "limit": options["limit"],
            },
            "action_count": len(actions),
            "summary": action_summary(actions),
            "applied": applied,
            "actions": [action.as_dict() for action in actions],
        }
        rendered = self._render(report, options["format"])
        if options["output"]:
            target = Path(options["output"]).expanduser().resolve()
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8", newline="")
            self.stdout.write(f"报告已写入 {target}")
            self.stdout.write(
                f"mode={mode} actions={len(actions)} applied={sum((applied or {}).values())}"
            )
        else:
            self.stdout.write(rendered)
