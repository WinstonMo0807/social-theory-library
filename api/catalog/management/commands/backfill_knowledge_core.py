"""Bounded, repeatable backfill. Never calls models or alters old records."""
from uuid import uuid5
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
        parser.add_argument("--after", default="")
        parser.add_argument("--batch-size", type=int, default=100)

    def handle(self, *args, **options):
        size = options["batch_size"]
        if not 1 <= size <= 500:
            raise CommandError("batch-size须为1至500")
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
            for model in [m.Person, m.KnowledgeNode, m.Topic, m.Discipline, m.Subdiscipline, m.TheorySchool]:
                mapped = m.KnowledgeLegacyMapping.objects.filter(source_type=model._meta.label_lower, target_type="entity").values("source_id")
                rows = model.objects.exclude(pk__in=mapped).order_by("pk")[:size]
                count = sum(1 for row in rows if entity_for_legacy(row))
                self.stdout.write(f"{model.__name__}: {count}")
        if options["claims"]:
            rows = m.CuratedClaim.objects.filter(status__in=["confirmed", "published", "approved"]).exclude(
                pk__in=m.KnowledgeLegacyMapping.objects.filter(source_type="catalog.curatedclaim", target_type="assertion").values("source_id"))
            for claim in rows.order_by("id")[:size]:
                with transaction.atomic():
                    statement, _ = m.Assertion.objects.get_or_create(pk=uuid5(claim.pk, "assertion-v1"), defaults={
                        "text": claim.proposition, "category": claim.kind, "conditions": claim.qualifiers,
                        "status": claim.status, "source_quality": "legacy_evidence_pending", "created_by": claim.created_by,
                        "origin": {"legacy_type": "catalog.curatedclaim", "legacy_id": str(claim.pk),
                            "published_by": str(claim.published_by_id or ""), "published_at": str(claim.published_at or ""),
                            "editorial_note": claim.editorial_note}})
                    if claim.work_id:
                        m.AssertionSource.objects.get_or_create(assertion=statement, work=claim.work,
                            defaults={"provenance": {"legacy_source_only": True, "revision_gap": True}})
                    m.KnowledgeLegacyMapping.objects.get_or_create(source_type="catalog.curatedclaim", source_id=claim.pk,
                        target_type="assertion", defaults={"target_id": statement.pk, "quality": "manual_status_preserved",
                            "provenance": {"source_quality_independent_of_human_decision": True}})
                self.stdout.write(f"CuratedClaim {claim.pk} -> {statement.pk}")
