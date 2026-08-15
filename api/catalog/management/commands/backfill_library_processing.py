from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import (
    Asset,
    OcrStatus,
    PageLabelStatus,
    PublicationState,
    SemanticIndexVersion,
)
from catalog.services.semantic_indexing import (
    dispatch_semantic_version_batch,
    stage_semantic_index_version,
)
from catalog.services.semantic_search import current_semantic_runtime, semantic_model_health
from ingestion.models import ProcessingJob
from ingestion.services.extract import extract_native_pages, ocr_required_page_indexes
from ingestion.services.files import materialize_field_file
from ingestion.services.processing import queue_ocr_job, queue_page_label_job


class Command(BaseCommand):
    help = "按受控批次补做馆藏 OCR、页码映射或版本化语义索引。"

    def add_arguments(self, parser):
        parser.add_argument(
            "--phase",
            choices=["ocr", "page-labels", "semantic"],
            required=True,
        )
        parser.add_argument("--batch-size", type=int, default=1)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--published-only", action="store_true")
        parser.add_argument("--include-failed", action="store_true")
        parser.add_argument(
            "--reclassify-native",
            action="store_true",
            help="重新检查原生文字层，给扫描页或缺失 ToUnicode 的页面建立 OCR 目标清单。",
        )
        parser.add_argument("--include-needs-review", action="store_true")
        parser.add_argument("--asset-id", action="append", default=[])
        parser.add_argument("--stage-new-version", action="store_true")
        parser.add_argument("--semantic-version", default="")
        parser.add_argument("--retry-failed-version", action="store_true")

    def _assets(self, options):
        queryset = Asset.objects.filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).select_related("edition", "edition__work").order_by("created_at", "id")
        if options["published_only"]:
            queryset = queryset.filter(edition__state=PublicationState.PUBLISHED)
        if options["asset_id"]:
            queryset = queryset.filter(pk__in=options["asset_id"])
        return queryset

    def handle(self, *args, **options):
        batch_size = max(1, min(int(options["batch_size"]), 20))
        phase = options["phase"]
        if phase == "ocr":
            return self._ocr(options, batch_size)
        if phase == "page-labels":
            return self._page_labels(options, batch_size)
        return self._semantic(options, batch_size)

    def _active_job_asset_ids(self, job_type):
        return ProcessingJob.objects.filter(
            job_type=job_type,
            status__in=[ProcessingJob.Status.PENDING, ProcessingJob.Status.RUNNING],
            asset_id__isnull=False,
        ).values_list("asset_id", flat=True)

    def _ocr(self, options, batch_size):
        if options["reclassify_native"]:
            return self._reclassify_ocr(options, batch_size)
        statuses = [OcrStatus.PENDING]
        if options["include_failed"]:
            statuses.append(OcrStatus.FAILED)
        queryset = self._assets(options).filter(
            edition__ocr_status__in=statuses
        ).exclude(pk__in=self._active_job_asset_ids(ProcessingJob.JobType.OCR))
        total = queryset.count()
        selected = list(queryset[:batch_size])
        self.stdout.write(
            f"OCR eligible={total} selected={len(selected)} batch_size={batch_size}"
        )
        for asset in selected:
            self.stdout.write(f"  {asset.id} {asset.edition.work.title}")
        if options["dry_run"]:
            return
        for asset in selected:
            queue_ocr_job(
                asset,
                force=asset.edition.ocr_status == OcrStatus.FAILED,
            )
        self.stdout.write(self.style.SUCCESS(f"已排队 {len(selected)} 个 OCR 任务。"))

    def _reclassify_ocr(self, options, batch_size):
        queryset = self._assets(options).filter(
            edition__ocr_status=OcrStatus.NOT_REQUIRED,
        ).exclude(pk__in=self._active_job_asset_ids(ProcessingJob.JobType.OCR))
        total = queryset.count()
        selected = list(queryset[:batch_size])
        self.stdout.write(
            f"OCR reclassify eligible={total} selected={len(selected)} batch_size={batch_size}"
        )
        queued = 0
        for asset in selected:
            cleanup = None
            try:
                path, cleanup = materialize_field_file(asset.file)
                pages, _needs_ocr = extract_native_pages(path)
                targets = ocr_required_page_indexes(pages)
                reason_counts = {}
                for page in pages:
                    for reason in page.ocr_reasons:
                        reason_counts[reason] = reason_counts.get(reason, 0) + 1
                self.stdout.write(
                    f"  {asset.id} {asset.edition.work.title} "
                    f"targets={len(targets)}/{len(pages)} reasons={reason_counts}"
                )
                if options["dry_run"] or not targets:
                    continue
                asset.validation_details = {
                    **(asset.validation_details or {}),
                    "ocr_required_page_indexes": targets,
                    "ocr_reason_counts": reason_counts,
                    "ocr_detection_version": "per-page-v1",
                    "ocr_reclassified_at": timezone.now().isoformat(),
                }
                asset.extraction_method = "pending_ocr"
                asset.save(
                    update_fields=[
                        "validation_details",
                        "extraction_method",
                        "updated_at",
                    ]
                )
                asset.edition.ocr_status = OcrStatus.PENDING
                asset.edition.save(update_fields=["ocr_status", "updated_at"])
                queue_ocr_job(asset, force=False)
                queued += 1
            except Exception as exc:
                self.stderr.write(f"  {asset.id} 检查失败：{str(exc)[:500]}")
            finally:
                if cleanup:
                    cleanup()
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"已重新分类并排队 {queued} 个 OCR 任务。"))

    def _page_labels(self, options, batch_size):
        statuses = [PageLabelStatus.PENDING]
        if options["include_needs_review"]:
            statuses.append(PageLabelStatus.NEEDS_REVIEW)
        queryset = self._assets(options).filter(
            edition__ocr_status__in=[OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED],
            edition__page_label_status__in=statuses,
            pages__isnull=False,
        ).exclude(
            pk__in=self._active_job_asset_ids(ProcessingJob.JobType.PAGE_LABELS)
        ).distinct()
        total = queryset.count()
        selected = list(queryset[:batch_size])
        self.stdout.write(
            f"page-labels eligible={total} selected={len(selected)} batch_size={batch_size}"
        )
        for asset in selected:
            self.stdout.write(f"  {asset.id} {asset.edition.work.title}")
        if options["dry_run"]:
            return
        for asset in selected:
            queue_page_label_job(asset, force=options["include_needs_review"])
        self.stdout.write(self.style.SUCCESS(f"已排队 {len(selected)} 个页码任务。"))

    def _semantic(self, options, batch_size):
        assets = self._assets(options)
        active_processing = assets.filter(
            edition__ocr_status__in=[OcrStatus.PENDING, OcrStatus.RUNNING]
        ).count()
        if active_processing:
            raise CommandError(
                f"仍有 {active_processing} 个资产等待或正在 OCR。请先完成 OCR，再建立候选语义索引。"
            )

        version_id = str(options["semantic_version"] or "").strip()
        if version_id:
            if options["dry_run"]:
                version = SemanticIndexVersion.objects.get(pk=version_id)
                counts = {
                    status: version.jobs.filter(status=status).count()
                    for status in (
                        "paused",
                        "queued",
                        "running",
                        "completed",
                        "partial",
                        "failed",
                    )
                }
                self.stdout.write(f"semantic version={version.uid} jobs={counts}")
                return
            result = dispatch_semantic_version_batch(
                version_id,
                batch_size=batch_size,
                retry_failed=options["retry_failed_version"],
            )
            self.stdout.write(self.style.SUCCESS(f"候选索引批次：{result}"))
            return

        if not options["stage_new_version"]:
            raise CommandError(
                "语义阶段需要 --stage-new-version，或用 --semantic-version 指定已有候选版本。"
            )
        runtime = current_semantic_runtime()
        if runtime.get("provider") == "huggingFace":
            revision = str(runtime.get("model_revision") or "")
            if not re.fullmatch(r"[0-9a-f]{40}", revision):
                raise CommandError("Hugging Face 生产 revision 必须是 40 位完整 commit。")
            health = semantic_model_health(runtime)
            if not health.get("available"):
                raise CommandError(health.get("reason") or "本地 Hugging Face 模型不完整。")
        eligible_assets = assets.filter(
            edition__ocr_status__in=[OcrStatus.NOT_REQUIRED, OcrStatus.SUCCEEDED]
        )
        eligible = eligible_assets.count()
        self.stdout.write(
            f"semantic eligible={eligible} model={runtime.get('model_repo_id')} "
            f"revision={runtime.get('model_revision')}"
        )
        if options["dry_run"]:
            return
        version = stage_semantic_index_version(
            runtime,
            batch_size=batch_size,
            auto_dispatch=True,
            asset_queryset=eligible_assets,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"已建立候选索引 {version.uid}，状态 {version.status}，首批最多 {batch_size} 个任务。"
            )
        )
