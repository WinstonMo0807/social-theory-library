"""Portable read-only inspection after restoring the existing database."""
import json
import platform
from importlib.metadata import PackageNotFoundError, version
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models import Count
from catalog import models as m
from catalog.services.knowledge_runtime import run_metrics


class Command(BaseCommand):
    help = "只读检查知识迁移、任务回执和计算依赖；不显示密钥、不调用模型、不启动队列或重索引。"

    def add_arguments(self, parser):
        parser.add_argument("--run-id", type=UUID)

    def handle(self, *args, **options):
        with transaction.atomic():
            if connection.vendor == "postgresql":
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL transaction_read_only = on")
                    cursor.execute("SET LOCAL statement_timeout = '5s'")
            executor = MigrationExecutor(connection)
            pending = [f"{migration.app_label}.{migration.name}" for migration, backward in
                executor.migration_plan(executor.loader.graph.leaf_nodes()) if not backward]
            dependencies = {}
            for package in ("Django", "djangorestframework", "celery", "docetl", "litellm", "docling"):
                try:
                    dependencies[package] = version(package)
                except PackageNotFoundError:
                    dependencies[package] = None
            result = {"schema":"stl-knowledge-runtime-v1", "read_only":True,
                "platform":{"system":platform.system(), "machine":platform.machine(), "python":platform.python_version()},
                "database_vendor":connection.vendor, "pending_migrations":pending,
                "dependencies":dependencies, "execution":settings.INTELLIGENCE_EXECUTION,
                "context_tokens":settings.INTELLIGENCE_CONTEXT_TOKENS,
                "provider_global_concurrency":getattr(settings,"AI_PROVIDER_GLOBAL_CONCURRENCY",1)}
            if pending:
                result["status"] = "migration_required"
            else:
                result["status"] = "schema_current"
                result["run_states"] = dict(m.CurationRun.objects.values("status").annotate(
                    count=Count("pk")).values_list("status","count"))
                if options["run_id"]:
                    run = m.CurationRun.objects.filter(pk=options["run_id"]).first()
                    if not run:
                        raise CommandError("指定编纂任务不存在。")
                    result["run"] = {"id":str(run.pk), "status":run.status, "stage":run.stage,
                        "revision_id":str(run.document_revision_id), "execution_mode":run.execution_mode,
                        "coverage":{k:run.coverage.get(k) for k in ("total_windows", "completed_windows",
                            "total_characters", "read_characters", "missing_text_pages", "analysis_complete")},
                        "metrics":run_metrics(run)}
        self.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
