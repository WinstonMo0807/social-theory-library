"""Prepare/backfill the existing current corpus, without changing active search."""
from django.core.management.base import BaseCommand, CommandError

from catalog.discovery_index_models import DiscoveryDocument
from catalog.services.discovery_indexing import index_writer
from catalog.services.discovery_inference import DiscoveryInferenceError
from catalog.services.discovery_projection import DiscoveryIndexError, active_generation
from catalog.services.retrieval.deep_index import prepare_index, project_document


class Command(BaseCommand):
    help = "准备独立EG2派生索引或补写当前原文；不激活/删除基础索引，不运行质量评测。"

    def add_arguments(self, parser):
        parser.add_argument("--prepare-only", action="store_true", help="仅创建空派生索引和设置，不编码原文")

    def handle(self, *args, **options):
        try:
            with index_writer() as acquired:
                if not acquired:
                    raise CommandError("当前已有索引写入任务，请待其完成后重试。")
                uid = prepare_index()
                written = 0
                generation = active_generation()
                if not options["prepare_only"] and generation:
                    documents = DiscoveryDocument.objects.filter(
                        generation=generation, channel="passages", keyword_ready=True, access_status="public"
                    ).order_by("pk")
                    for document in documents.iterator(chunk_size=100):
                        written += int(project_document(document))
                self.stdout.write(f"index={uid} written={written} prepare_only={options['prepare_only']}")
        except (DiscoveryIndexError, DiscoveryInferenceError) as exc:
            raise CommandError(f"{exc.code}: {exc}") from exc
