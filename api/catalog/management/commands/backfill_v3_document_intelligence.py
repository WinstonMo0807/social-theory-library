from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Asset, DocumentRevision, Page
from catalog.services.claims.pipeline import schedule_document_claim_extraction
from catalog.services.document_intelligence import synchronize_document_revision


BASELINE_COMMIT = "4b97a3484db0c3918f5b0fef8bfc75c35bd0dcee"


class Command(BaseCommand):
    help = (
        "按资产批次回填 3.0 DocumentRevision/EvidenceSpan，或按 EvidenceSpan "
        "批次建立非阻断 Claim shadow demand。"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--phase",
            choices=["document", "claims"],
            required=True,
        )
        parser.add_argument("--batch-size", type=int, default=4)
        parser.add_argument("--asset-id", action="append", default=[])
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--span-offset", type=int, default=0)
        parser.add_argument("--span-limit", type=int, default=250)

    def _assets(self, options):
        queryset = (
            Asset.objects.filter(
                kind=Asset.Kind.NORMALIZED,
                status=Asset.Status.READY,
                is_current=True,
                pages__isnull=False,
            )
            .select_related("edition__work")
            .distinct()
            .order_by("created_at", "id")
        )
        if options["asset_id"]:
            queryset = queryset.filter(pk__in=options["asset_id"])
        return queryset

    def handle(self, *args, **options):
        batch_size = max(1, min(int(options["batch_size"]), 50))
        if options["phase"] == "document":
            return self._documents(options, batch_size)
        return self._claims(options, batch_size)

    def _documents(self, options, batch_size):
        queryset = self._assets(options).exclude(
            document_revisions__is_active=True
        )
        eligible = queryset.count()
        selected = list(queryset[:batch_size])
        self.stdout.write(
            f"document eligible={eligible} selected={len(selected)} batch_size={batch_size}"
        )
        for asset in selected:
            ocr_pages = asset.pages.filter(text_source=Page.TextSource.OCR).count()
            self.stdout.write(
                f"  {asset.id} pages={asset.pages.count()} ocr_pages={ocr_pages} "
                f"work={asset.edition.work.title}"
            )
            if options["dry_run"]:
                continue
            pending_ocr_pages = (
                (asset.validation_details or {}).get("ocr_required_page_indexes") or []
            )
            result = synchronize_document_revision(
                asset,
                parser_name="v2.9.2-page-passage-backfill",
                parser_version=BASELINE_COMMIT,
                extraction_method=(
                    "legacy_mixed_ocr" if ocr_pages else "legacy_native_text"
                ),
                extraction_version="v2.9.2-baseline",
                ocr_provider="paddleocr" if ocr_pages else "",
                ocr_model="legacy-unrecorded" if ocr_pages else "",
                ocr_version="legacy-unrecorded" if ocr_pages else "",
                pending_ocr_pages=pending_ocr_pages,
                schedule_claims=False,
            )
            self.stdout.write(
                f"    revision={result['revision']} evidence={result['evidence_spans']} "
                f"critical_pages={len(result['critical_pages'])}"
            )
        if not options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(f"已回填 {len(selected)} 个 DocumentRevision 批次项。")
            )

    def _claims(self, options, batch_size):
        span_offset = max(0, int(options["span_offset"]))
        span_limit = max(1, min(int(options["span_limit"]), 5000))
        queryset = DocumentRevision.objects.filter(
            is_active=True,
            asset__in=self._assets(options),
            evidence_spans__is_stale=False,
        ).select_related("asset__edition__work").distinct().order_by(
            "asset__created_at", "asset_id"
        )
        eligible = queryset.count()
        selected = list(queryset[:batch_size])
        self.stdout.write(
            f"claims eligible_revisions={eligible} selected={len(selected)} "
            f"span_offset={span_offset} span_limit={span_limit}"
        )
        if span_offset and not options["asset_id"] and len(selected) > 1:
            raise CommandError(
                "使用 --span-offset 时请指定 --asset-id，避免对多个文档产生含糊批次。"
            )
        for revision in selected:
            total = revision.evidence_spans.filter(is_stale=False).count()
            self.stdout.write(
                f"  {revision.asset_id} revision={revision.revision} "
                f"evidence={total} work={revision.asset.edition.work.title}"
            )
            if options["dry_run"]:
                continue
            result = schedule_document_claim_extraction(
                revision,
                span_offset=span_offset,
                span_limit=span_limit,
            )
            self.stdout.write(
                f"    scheduled={result['scheduled']} states={result['states']} "
                f"publication_blocking={result['publication_blocking']}"
            )
        if not options["dry_run"]:
            self.stdout.write(
                self.style.SUCCESS(f"已处理 {len(selected)} 个 Claim shadow 调度批次项。")
            )
