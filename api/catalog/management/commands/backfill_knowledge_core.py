"""Bounded, repeatable backfill. Never calls models or alters old records."""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from catalog import models as m
from catalog.services.knowledge_core import entity_for_legacy
from catalog.services.knowledge_sources import build_structure, migrate_span


class Command(BaseCommand):
    help = "回填指定修订原文与旧知识ID；每批独立事务，可按输出游标恢复。"

    def add_arguments(self, parser):
        parser.add_argument("--revision")
        parser.add_argument("--identities", action="store_true")
        parser.add_argument("--claims", action="store_true")
        parser.add_argument("--relations", action="store_true")
        parser.add_argument("--page-dependencies", action="store_true")
        parser.add_argument("--retrieval", action="store_true")
        parser.add_argument("--review-fingerprints", action="store_true")
        parser.add_argument("--generation")
        parser.add_argument("--after", default="")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        size = options["batch_size"]
        if not 1 <= size <= 500:
            raise CommandError("batch-size须为1至500")
        if options["review_fingerprints"]:
            from catalog.services.intelligence_changes import refresh_fingerprints
            rows=m.ChangeSet.objects.order_by("id")
            if options["after"]: rows=rows.filter(id__gt=options["after"])
            count,last=0,None
            for changeset in rows[:size]:
                with transaction.atomic():
                    changeset=m.ChangeSet.objects.select_for_update().get(pk=changeset.pk)
                    refresh_fingerprints(changeset)
                count+=1;last=str(changeset.pk)
            self.stdout.write(str({"changesets":count,"next_after":last}))
        if options["retrieval"]:
            from catalog.services.retrieval.locators import index_anchor
            from catalog.services.discovery_projection import active_generation, validate_discovery_results
            generation = m.SemanticIndexVersion.discovery_objects.get(pk=options["generation"]) if options["generation"] else active_generation()
            if not generation:
                raise CommandError("没有可迁移的检索generation")
            rows = m.DiscoveryDocument.objects.filter(generation=generation, channel="passages", keyword_ready=True).order_by("id")
            if options["after"]:
                rows = rows.filter(id__gt=options["after"])
            batch = list(rows.select_related("document_revision")[:size])
            valid = {r["id"] for r in validate_discovery_results("passages", [{"id":str(r.pk)} for r in batch], list({r.access_status for r in batch}))}
            counts = {}
            for row in batch:
                mapping = index_anchor(row) if str(row.pk) in valid else None
                quality = mapping.quality if mapping else "source_not_current_public"
                counts[quality] = counts.get(quality, 0) + 1
            self.stdout.write(str({"retrieval":counts,"next_after":str(batch[-1].pk) if batch else None}))
        if options["page_dependencies"]:
            from catalog.services.knowledge_workspace import sync_dependencies
            rows = m.KnowledgePage.objects.order_by("id")
            if options["after"]:
                rows = rows.filter(id__gt=options["after"])
            last, count = None, 0
            for page in rows[:size]:
                # Preserve existing baselines and stale flags on repeated batches.
                sync_dependencies(page, changed_blocks=set())
                last, count = str(page.pk), count + 1
            self.stdout.write(str({"page_dependencies": count, "next_after": last}))
        if options["revision"]:
            revision = m.DocumentRevision.objects.get(pk=options["revision"])
            structure = build_structure(revision)
            spans = revision.evidence_spans.order_by("id")
            if options["after"]:
                spans = spans.filter(id__gt=options["after"])
            counts = {}
            last = None
            for span in spans[:size]:
                mapping = migrate_span(span)
                counts[mapping.quality] = counts.get(mapping.quality, 0) + 1
                last = str(span.pk)
            self.stdout.write(str({"structure_id": str(structure.pk), "evidence": counts, "next_after": last}))
        if options["identities"]:
            for model in [m.Person, m.KnowledgeNode, m.Topic, m.Discipline, m.Subdiscipline, m.TheorySchool, m.Concept]:
                mapped = m.KnowledgeLegacyMapping.objects.filter(source_type=model._meta.label_lower, target_type="entity").values("source_id")
                rows = model.objects.exclude(pk__in=mapped).order_by("pk")[:size]
                count = sum(1 for row in rows if entity_for_legacy(row))
                self.stdout.write(f"{model.__name__}: {count}")
        if options["claims"]:
            from catalog.services.knowledge_migration import migrate_curated_claim
            mapped=m.KnowledgeLegacyMapping.objects.filter(source_type="catalog.curatedclaim",target_type="assertion",
                provenance__migration_version=2).values("source_id")
            rows=m.CuratedClaim.objects.exclude(pk__in=mapped).order_by("id")
            if options["after"]: rows=rows.filter(pk__gt=options["after"])
            count,last=0,None
            for claim in rows[:size]:
                migrate_curated_claim(claim)
                count+=1;last=str(claim.pk)
            self.stdout.write(str({"curated_claims":count,"next_after":last}))
        if options["relations"]:
            from catalog.services.knowledge_migration import migrate_relation
            for model in [m.PersonNodeRelation, m.WorkNodeRelation, m.KnowledgeRelation]:
                mapped = m.KnowledgeLegacyMapping.objects.filter(source_type=model._meta.label_lower, target_type="assertion", provenance__migration_version=2).values("source_id")
                rows = model.objects.filter(status__in=["confirmed", "approved", "published"]).exclude(pk__in=mapped).order_by("pk")[:size]
                count = sum(1 for row in rows if migrate_relation(row))
                self.stdout.write(f"{model.__name__}: {count}")
