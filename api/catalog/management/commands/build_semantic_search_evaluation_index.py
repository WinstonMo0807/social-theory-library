from __future__ import annotations

import json

import httpx
from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_evaluation_environment import (
    DEFAULT_EVALUATION_DOCUMENT_BATCH_SIZE,
    EvaluationEnvironmentError,
    build_evaluation_meilisearch_index,
)


class Command(BaseCommand):
    help = "只在隔离 evaluation UID 中建立 Meilisearch 语义索引，不激活该版本。"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", required=True)
        parser.add_argument(
            "--resume",
            action="store_true",
            help="允许在同一 evaluation UID 上恢复幂等 upsert。",
        )
        parser.add_argument(
            "--document-batch-size",
            type=int,
            default=DEFAULT_EVALUATION_DOCUMENT_BATCH_SIZE,
            help="每次提交给隔离 Meilisearch 的文档数，默认 128。",
        )

    def handle(self, *args, **options):
        try:
            result = build_evaluation_meilisearch_index(
                snapshot_id=options["snapshot_id"],
                resume=options["resume"],
                document_batch_size=options["document_batch_size"],
            )
        except (EvaluationEnvironmentError, httpx.HTTPError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
