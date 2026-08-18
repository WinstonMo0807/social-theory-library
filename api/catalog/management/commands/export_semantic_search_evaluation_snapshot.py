from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_evaluation_environment import (
    EvaluationEnvironmentError,
    export_evaluation_bundle,
)


class Command(BaseCommand):
    help = "在 PostgreSQL 只读事务中导出不含账户和读者私有数据的搜索评测 bundle。"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", required=True)
        parser.add_argument("--index-version", required=True, help="源 SemanticIndexVersion UUID 或 UID")
        parser.add_argument("--output-dir", required=True)
        parser.add_argument(
            "--source-kind",
            required=True,
            choices=["backup_restore", "read_replica", "production_readonly"],
        )
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        try:
            result = export_evaluation_bundle(
                output_dir=options["output_dir"],
                snapshot_id=options["snapshot_id"],
                index_version_value=options["index_version"],
                source_kind=options["source_kind"],
                batch_size=options["batch_size"],
            )
        except (EvaluationEnvironmentError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
