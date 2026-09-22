"""Operate derived discovery generations without touching original documents."""
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "建立、协调或切换观点检索派生索引；保留所有旧索引及原始资料。"

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["build", "reconcile", "activate", "deactivate", "status"])
        parser.add_argument("--generation")
        parser.add_argument("--keep-ready", action="store_true", help="建立后等待明确切换")

    def handle(self, *args, **options):
        from catalog.models import SemanticIndexVersion
        from catalog.services.discovery_indexing import request_rebuild, reconcile, activate_generation, deactivate_generation
        from catalog.services.discovery_projection import DiscoveryIndexError
        try:
            if options["action"] == "build":
                job = request_rebuild(activate=not options["keep_ready"])
                self.stdout.write(f"job_id={job.pk} status={job.status}")
            elif options["action"] == "reconcile":
                self.stdout.write(str(reconcile()))
            elif options["action"] in {"activate", "deactivate"}:
                row = SemanticIndexVersion.discovery_objects.filter(pk=options.get("generation")).first()
                if row is None:
                    raise CommandError("请提供存在的派生索引 generation。")
                row = activate_generation(row) if options["action"] == "activate" else deactivate_generation(row)
                self.stdout.write(f"generation={row.pk} status={row.status}")
            else:
                for row in SemanticIndexVersion.discovery_objects.all()[:20]:
                    self.stdout.write(f"{row.pk} {row.status} documents={row.document_count} index={row.uid}")
        except DiscoveryIndexError as exc:
            raise CommandError(str(exc)) from exc
