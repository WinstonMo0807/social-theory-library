"""Recover a lost physical keyword index from verified, retained projections.

Never clears an existing index. A ProcessingJob cursor survives interruption;
vectors require the original artifacts and are accurately left not ready.
"""
from collections import defaultdict
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone
from catalog import models as m
from ingestion.models import ProcessingJob
from catalog.services.discovery_indexing import index_writer, ensure_index, wait_index_task
from catalog.services.discovery_projection import meili, DiscoveryIndexError, validate_discovery_results
from catalog.services.discovery_sources import get_source, source_units
from catalog.services.discovery_scope import chunk_fields


class Command(BaseCommand):
    help = "Restore a missing Meilisearch keyword index; retains canonical sources and old IDs."

    def add_arguments(self, parser):
        parser.add_argument("--generation", required=True)
        parser.add_argument("--initialize-missing", action="store_true")
        parser.add_argument("--batch-size", type=int, default=200)
        parser.add_argument("--batches", type=int, default=5)

    def handle(self, *args, **options):
        if not 1 <= options["batch_size"] <= 500 or not 1 <= options["batches"] <= 100:
            raise CommandError("Use batch-size 1–500 and batches 1–100.")
        generation = m.SemanticIndexVersion.discovery_objects.get(pk=options["generation"])
        with index_writer() as acquired:
            if not acquired:
                raise CommandError("An index writer is running. Retry after it completes.")
            job = ProcessingJob.objects.filter(job_type="discovery_index", stats__action="restore_projection",
                stats__generation_id=str(generation.pk)).order_by("-created_at").first()
            if not job:
                if not options["initialize_missing"]:
                    raise CommandError("First invocation requires --initialize-missing; the physical index must be absent.")
                try:
                    meili("GET", f"/indexes/{generation.uid}")
                except DiscoveryIndexError as exc:
                    if exc.code != "index_missing":
                        raise CommandError("Cannot establish index loss; nothing changed.") from exc
                else:
                    raise CommandError("Physical index exists. Nothing changed; use normal rebuild/repair.")
                with transaction.atomic():
                    job = ProcessingJob.objects.create(job_type="discovery_index", engine="discovery-projection-recovery",
                        status="running", started_at=timezone.now(), stats={"action": "restore_projection",
                        "generation_id": str(generation.pk), "cursor": "", "restored": 0, "skipped": 0})
                    m.DiscoveryDocument.objects.filter(generation=generation).update(keyword_ready=False, vector_ready=False, indexed_at=None)
                    m.DiscoverySourceState.objects.filter(generation=generation).update(indexed_at=None, completed_count=0)
            if job.status == "succeeded":
                self.stdout.write(str({"job_id": str(job.pk), "status": job.status, **job.stats}))
                return
            ensure_index(generation)
            units = {}
            try:
                for _ in range(options["batches"]):
                    rows = m.DiscoveryDocument.objects.filter(generation=generation).order_by("pk")
                    if job.stats["cursor"]:
                        rows = rows.filter(pk__gt=job.stats["cursor"])
                    batch = list(rows[:options["batch_size"]])
                    if not batch:
                        self.finish(job, generation)
                        break
                    channels = defaultdict(list)
                    for doc in batch:
                        channels[doc.channel].append({"id": str(doc.pk)})
                    valid = set()
                    for channel, references in channels.items():
                        valid.update(v["id"] for v in validate_discovery_results(channel, references,
                            list({d.access_status for d in batch}), require_keyword=False))
                    payload, ids = [], []
                    for doc in batch:
                        if str(doc.pk) not in valid:
                            continue
                        key = (doc.source_type, str(doc.source_id))
                        if key not in units:
                            source, header = get_source(*key)
                            units[key] = (header, {str(u["unit_id"]): u for u in source_units(key[0], source, header)}) if header else (None, {})
                        header, source_map = units[key]
                        unit = source_map.get(str(doc.payload.get("unit_id")))
                        if not header or not unit or unit["text"][doc.start_offset:doc.end_offset] != doc.text:
                            continue
                        row = {"id": str(doc.pk), "channel": doc.channel, "source_type": doc.source_type,
                            "source_id": str(doc.source_id), "source_revision": doc.source_revision, "scope_token": doc.scope_token,
                            "access_status": doc.access_status, "input_hash": doc.input_hash, "title": header["title"],
                            "aliases": header.get("aliases", []), "authors": doc.payload.get("authors", []),
                            "normalized_text": doc.normalized_text, "language": doc.payload.get("language", "unknown"),
                            "_vectors": {"discovery": []}}
                        if generation.config_snapshot.get("scope_fields_version") == 1:
                            row.update(chunk_fields(header, unit, {"start": doc.start_offset, "end": doc.end_offset}))
                        payload.append(row)
                        ids.append(doc.pk)
                    if payload:
                        wait_index_task(meili("POST", f"/indexes/{generation.uid}/documents", payload))
                        m.DiscoveryDocument.objects.filter(pk__in=ids).update(keyword_ready=True, vector_ready=False, indexed_at=timezone.now())
                    job.stats = {**job.stats, "cursor": str(batch[-1].pk), "restored": job.stats["restored"]+len(ids),
                        "skipped": job.stats["skipped"]+len(batch)-len(ids)}
                    job.status, job.error_message = "running", ""
                    job.save(update_fields=["stats", "status", "error_message", "updated_at"])
                    self.stdout.write(str({"job_id": str(job.pk), **job.stats}))
            except Exception as exc:
                job.status, job.error_message = "failed", "关键词投影恢复中断，已写入批次保留。重新执行相同命令可继续。"
                job.save(update_fields=["status", "error_message", "updated_at"])
                raise CommandError(str(exc)) from exc

    def finish(self, job, generation):
        actual = meili("GET", f"/indexes/{generation.uid}/stats").get("numberOfDocuments")
        if actual != job.stats["restored"]:
            raise CommandError("Physical index count differs from restored rows; retain the cursor and inspect before completion.")
        counts = {(r["source_type"], r["source_id"], r["source_revision"]): r["count"] for r in
            m.DiscoveryDocument.objects.filter(generation=generation, keyword_ready=True)
            .values("source_type", "source_id", "source_revision").annotate(count=Count("pk"))}
        for state in m.DiscoverySourceState.objects.filter(generation=generation):
            count = counts.get((state.source_type, state.source_id, state.source_revision), 0)
            state.completed_count = count
            state.indexed_at = timezone.now() if count == state.expected_count and count else None
            state.save(update_fields=["completed_count", "indexed_at", "updated_at"])
        job.status, job.finished_at = "succeeded", timezone.now()
        job.save(update_fields=["status", "finished_at", "updated_at"])
        self.stdout.write(str({"status": job.status, **job.stats}))
