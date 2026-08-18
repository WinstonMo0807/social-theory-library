from __future__ import annotations

import json

import httpx
from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_evaluation_environment import (
    EvaluationEnvironmentError,
    audit_evaluation_environment,
    write_evaluation_manifest,
)


class Command(BaseCommand):
    help = "只读核对 evaluation DB、QueryLexicon、语义版本、Meilisearch 和四路 smoke retrieval。"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", required=True)
        parser.add_argument("--bundle-dir")
        parser.add_argument("--smoke-query")
        parser.add_argument(
            "--smoke-query-language",
            default="zh",
            choices=["zh", "en", "mixed"],
        )
        parser.add_argument("--output", help="可选 snapshot manifest JSON 路径")
        parser.add_argument(
            "--require-ready",
            action="store_true",
            help="环境未满足 pilot 前置条件时返回失败。",
        )

    def handle(self, *args, **options):
        try:
            report = audit_evaluation_environment(
                snapshot_id=options["snapshot_id"],
                bundle_dir=options.get("bundle_dir"),
                smoke_query=options.get("smoke_query"),
                smoke_query_language=options["smoke_query_language"],
            )
            if options.get("output"):
                write_evaluation_manifest(report, options["output"])
        except (EvaluationEnvironmentError, httpx.HTTPError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if options["require_ready"] and not report["ready_for_pilot"]:
            raise CommandError(
                "evaluation 环境尚未满足 pilot 条件。报告已生成，请检查缺失项。"
            )
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
