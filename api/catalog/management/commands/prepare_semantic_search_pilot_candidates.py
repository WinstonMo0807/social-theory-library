from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_evaluation_environment import (
    EvaluationEnvironmentError,
    prepare_pilot_query_candidates,
)


class Command(BaseCommand):
    help = "从隔离评测馆藏提出 pilot query 候选，不生成 gold 或 passage 推荐。"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", required=True)
        parser.add_argument("--output", required=True)
        parser.add_argument("--limit", type=int, default=60)
        parser.add_argument("--per-direction-minimum", type=int, default=5)

    def handle(self, *args, **options):
        try:
            report = prepare_pilot_query_candidates(
                snapshot_id=options["snapshot_id"],
                output_path=options["output"],
                limit=options["limit"],
                per_direction_minimum=options["per_direction_minimum"],
            )
        except (EvaluationEnvironmentError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
