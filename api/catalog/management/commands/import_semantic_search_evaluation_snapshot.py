from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_evaluation_environment import (
    EvaluationEnvironmentError,
    import_evaluation_bundle,
)


class Command(BaseCommand):
    help = "把 search-only bundle 导入全新 evaluation PostgreSQL，并重新派生 QueryLexicon。"

    def add_arguments(self, parser):
        parser.add_argument("--snapshot-id", required=True)
        parser.add_argument("--bundle-dir", required=True)
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        try:
            result = import_evaluation_bundle(
                bundle_dir=options["bundle_dir"],
                snapshot_id=options["snapshot_id"],
                batch_size=options["batch_size"],
            )
        except (EvaluationEnvironmentError, OSError, ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
