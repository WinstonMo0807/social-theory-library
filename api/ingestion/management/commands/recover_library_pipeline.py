from django.core.management.base import BaseCommand

from catalog.services.semantic_indexing import recover_semantic_index_jobs
from ingestion.services.dispatch import recover_ingestion_dispatches


class Command(BaseCommand):
    help = "重新派发因 API、Redis 或 worker 重启而遗留的入库和语义索引任务。"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        ingestion = recover_ingestion_dispatches(limit=max(1, options["limit"]))
        semantic = recover_semantic_index_jobs()
        self.stdout.write(
            self.style.SUCCESS(
                "入库候选 {candidates}，已重新派发 {scheduled}，重置中断任务 {reset}；"
                "语义索引已重新派发 {semantic_requeued}。".format(
                    **ingestion,
                    semantic_requeued=semantic["requeued"],
                )
            )
        )
