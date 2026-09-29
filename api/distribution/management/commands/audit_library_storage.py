import json
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from distribution.storage_audit import inspect_storage


class Command(BaseCommand):
    help = "只读统计配置中的NAS目录，区分逻辑字节/硬链接/实际分配，不自动清理。"

    def add_arguments(self, parser):
        parser.add_argument("--max-entries", type=int, default=100000)

    def handle(self, *args, **options):
        limit = options["max_entries"]
        if not 1 <= limit <= 1000000:
            raise CommandError("--max-entries必须在1到1000000之间。")
        roots = {"originals": settings.NAS_ORIGINAL_ROOT, "public": settings.NAS_PUBLIC_ROOT,
                 "incoming": settings.NAS_INCOMING_ROOT, "backups": settings.NAS_BACKUP_ROOT}
        self.stdout.write(json.dumps(inspect_storage(roots, max_entries=limit), ensure_ascii=False))
