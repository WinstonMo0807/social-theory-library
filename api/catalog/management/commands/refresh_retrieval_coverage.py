import json
from uuid import UUID

from django.core.management.base import BaseCommand
from catalog.services.retrieval.coverage import backfill_receipts


class Command(BaseCommand):
    help = "核验一批历史索引就绪回执；默认预演，不重建索引。用 after 接续。"

    def add_arguments(self, parser):
        parser.add_argument("--after", type=UUID)
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        self.stdout.write(json.dumps(backfill_receipts(after=options["after"],
            batch_size=options["batch_size"], apply=options["apply"]), ensure_ascii=False))
