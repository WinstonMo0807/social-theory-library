from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from catalog.models import Asset
from catalog.services.query_lexicon.candidates import (
    REJECTION_FUNNEL_KEYS,
    scan_asset_for_query_lexicon_candidates,
)


class Command(BaseCommand):
    help = "只读审计或显式提取 PDF QueryLexicon 候选。"

    def add_arguments(self, parser):
        parser.add_argument("--asset-id", action="append", default=[])
        parser.add_argument("--work-id")
        parser.add_argument("--all-ready", action="store_true")
        parser.add_argument("--commit", action="store_true")
        parser.add_argument("--queue", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        asset_ids = [str(value).strip() for value in options["asset_id"] if str(value).strip()]
        work_id = str(options.get("work_id") or "").strip()
        selectors = int(bool(asset_ids)) + int(bool(work_id)) + int(bool(options["all_ready"]))
        if selectors != 1:
            raise CommandError("必须且只能指定 --asset-id、--work-id 或 --all-ready。")
        if options["commit"] and options["queue"]:
            raise CommandError("--commit 与 --queue 不能同时使用。")
        if options["force"] and not options["queue"]:
            raise CommandError("--force 只用于重试失败的 --queue 任务。")

        assets = Asset.objects.select_related("edition__work").filter(
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        )
        if asset_ids:
            assets = assets.filter(pk__in=asset_ids)
        elif work_id:
            assets = assets.filter(edition__work_id=work_id)
        assets = list(assets.order_by("edition__work__title", "created_at"))
        if not assets:
            raise CommandError("没有找到符合条件的当前就绪规范 PDF。")

        results = []
        unique_pair_fingerprints = set()
        mode = "dry_run"
        if options["queue"]:
            from ingestion.services.processing import (
                queue_query_lexicon_candidate_job,
            )

            mode = "queue"
            for asset in assets:
                job = queue_query_lexicon_candidate_job(
                    asset,
                    force=bool(options["force"]),
                )
                results.append(
                    {
                        "asset_id": str(asset.id),
                        "work_id": str(asset.edition.work_id),
                        "work_title": asset.edition.work.title,
                        "job_id": str(job.id),
                        "job_status": job.status,
                        "idempotency_key": job.idempotency_key,
                    }
                )
        else:
            mode = "commit" if options["commit"] else "dry_run"
            for asset in assets:
                result = scan_asset_for_query_lexicon_candidates(
                    asset,
                    commit=bool(options["commit"]),
                    create_review_task=bool(options["commit"]),
                )
                unique_pair_fingerprints.update(
                    result.pop("_unique_pair_fingerprints", [])
                )
                results.append(result)

        summary = {
            "mode": mode,
            "asset_count": len(assets),
            "results": results,
        }
        if mode != "queue":
            rejection_funnel = {
                key: sum(
                    int((row.get("rejection_funnel") or {}).get(key) or 0)
                    for row in results
                )
                for key in REJECTION_FUNNEL_KEYS
            }
            summary.update(
                {
                    "explicit_pair_observations": sum(
                        int(row.get("explicit_pair_observations") or 0)
                        for row in results
                    ),
                    "unique_pair_count": len(unique_pair_fingerprints),
                    "detected_pair_count": sum(
                        int(row.get("detected_pair_count") or 0) for row in results
                    ),
                    "candidate_count": sum(
                        int(row.get("candidate_count") or 0) for row in results
                    ),
                    "linked_candidate_count": sum(
                        int(row.get("linked_candidate_count") or 0) for row in results
                    ),
                    "ambiguous_candidate_count": sum(
                        int(row.get("ambiguous_candidate_count") or 0) for row in results
                    ),
                    "unresolved_pair_count": sum(
                        rejection_funnel[key]
                        for key in (
                            "no_canonical_anchor_match",
                            "target_not_admin_resolvable",
                            "low_trust_generated_only_match",
                        )
                    ),
                    "rejection_funnel": rejection_funnel,
                }
            )
        self.stdout.write(
            json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2)
        )
