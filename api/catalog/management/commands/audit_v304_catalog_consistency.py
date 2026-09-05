import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from catalog.services.catalog_consistency_audit import catalog_consistency_report


class Command(BaseCommand):
    help = (
        "Read-only 3.0.4 audit for candidate, formal catalog, QueryLexicon "
        "and derived-intelligence consistency."
    )

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--output", default="")
        parser.add_argument("--fail-on-errors", action="store_true")
        parser.add_argument("--schema-only", action="store_true", help="Inspect source/schema compatibility and row inventory without data checks.")
        parser.add_argument("--database-read-only", action="store_true", help="Use a PostgreSQL read-only repeatable-read transaction for production auditing.")

    def handle(self, *args, **options):
        if options["database_read_only"]:
            if connection.vendor != "postgresql" or connection.in_atomic_block:
                raise CommandError("数据库只读快照模式需要独立的 PostgreSQL 事务。")
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
                report = catalog_consistency_report(example_limit=options["limit"], schema_only=options["schema_only"])
        else:
            report = catalog_consistency_report(example_limit=options["limit"], schema_only=options["schema_only"])
        payload = json.dumps(report, ensure_ascii=False, indent=2)
        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output).expanduser().resolve()
            if path.exists():
                raise CommandError("输出文件已存在；审计命令不会覆盖既有报告。")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload + "\n", encoding="utf-8")
            self.stdout.write(str(path))
        else:
            self.stdout.write(payload)
        if options["fail_on_errors"] and report["summary"]["error_count"]:
            raise CommandError("3.0.4 一致性审计发现阻断性问题。")
