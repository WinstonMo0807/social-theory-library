from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_benchmark import semantic_search_benchmark_audit


class Command(BaseCommand):
    help = "只读审计历史 chunk language 与 active QueryLexicon 双语覆盖。"

    def add_arguments(self, parser):
        parser.add_argument("--output", help="可选 JSON 报告路径")

    def handle(self, *args, **options):
        report = semantic_search_benchmark_audit()
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if options.get("output"):
            target = Path(options["output"]).resolve()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(text.rstrip())
