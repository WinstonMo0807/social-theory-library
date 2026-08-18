from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from catalog.services.query_lexicon.sync import (
    dry_run_reconciliation,
    rebuild_query_lexicon,
)


class Command(BaseCommand):
    help = "核对或重建可派生的 QueryLexicon。"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--entity-type")
        parser.add_argument("--entity-id")
        parser.add_argument("--normalization-version")
        parser.add_argument("--source-registry-version")

    def handle(self, *args, **options):
        entity_type = (options.get("entity_type") or "").strip() or None
        entity_id = (options.get("entity_id") or "").strip() or None
        if entity_id and not entity_type:
            raise CommandError("--entity-id 必须与 --entity-type 同时使用。")
        kwargs = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "normalization_version": (
                (options.get("normalization_version") or "").strip() or None
            ),
            "source_registry_version": (
                (options.get("source_registry_version") or "").strip() or None
            ),
        }
        try:
            result = (
                dry_run_reconciliation(**kwargs)
                if options["dry_run"]
                else rebuild_query_lexicon(**kwargs)
            )
        except (ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
        )
