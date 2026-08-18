from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from catalog.models import SemanticIndexVersion
from catalog.services.semantic_search_benchmark import (
    DEFAULT_BLIND_SEED,
    DEFAULT_SPLIT_SEED,
    dataset_inventory,
    freeze_benchmark_splits,
    read_jsonl,
    run_shadow_query_pool,
    validate_benchmark_records,
    write_annotation_package,
)
from catalog.services.semantic_search_v2 import SUPPLEMENTAL_BRANCH_TYPES
from catalog.services.semantic_search_v2_config import search_v2_config_snapshot


def _resolve_index_version(value: str) -> SemanticIndexVersion:
    row = SemanticIndexVersion.objects.filter(uid=value).first()
    if row is None:
        try:
            row = SemanticIndexVersion.objects.filter(pk=UUID(value)).first()
        except (TypeError, ValueError, AttributeError):
            row = None
    if row is None:
        raise CommandError(f"找不到索引版本：{value}")
    if row.status not in {
        SemanticIndexVersion.Status.READY,
        SemanticIndexVersion.Status.ACTIVE,
        SemanticIndexVersion.Status.RETIRED,
    }:
        raise CommandError("只有 ready、active 或 retired 的索引版本可以建立标注池。")
    return row


class Command(BaseCommand):
    help = "用 V1、V2、lexical 和 dense 四路候选建立盲化人工标注包。"

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True, help="Task 2B JSONL query 数据集")
        parser.add_argument("--index-version", help="SemanticIndexVersion UUID 或 UID")
        parser.add_argument("--output-dir", help="annotation package 输出目录")
        parser.add_argument("--pool-top-k", type=int, default=20)
        parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
        parser.add_argument("--blind-seed", default=DEFAULT_BLIND_SEED)
        parser.add_argument(
            "--disable-v2-branch",
            action="append",
            default=[],
            choices=sorted(SUPPLEMENTAL_BRANCH_TYPES),
            help="实验性关闭指定 V2 supplemental branch，可重复传入。",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只验证 schema、split 与基线配置，不执行 retrieval 或写 annotation pack。",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="允许覆盖已存在的 annotation package 目录内容。",
        )

    def handle(self, *args, **options):
        try:
            records = validate_benchmark_records(read_jsonl(options["dataset"]))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        records = freeze_benchmark_splits(
            records,
            seed=str(options["split_seed"]),
        )
        report = {
            "mode": "dry_run" if options["dry_run"] else "prepare",
            "dataset": dataset_inventory(records),
            "split_seed": str(options["split_seed"]),
            "blind_seed": str(options["blind_seed"]),
            "disabled_v2_branch_types": sorted(
                set(options["disable_v2_branch"] or [])
            ),
            "baseline_v2a": search_v2_config_snapshot(),
            "automatic_relevance_grades": False,
            "changes_active_index": False,
            "writes_search_index": False,
        }
        if options["dry_run"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return
        if not options.get("index_version"):
            raise CommandError("正式准备 annotation pack 必须提供 --index-version。")
        if not options.get("output_dir"):
            raise CommandError("正式准备 annotation pack 必须提供 --output-dir。")
        output_dir = Path(options["output_dir"]).resolve()
        if output_dir.exists() and any(output_dir.iterdir()) and not options["overwrite"]:
            raise CommandError("输出目录非空。确认内容后使用 --overwrite，或选择新目录。")
        index_version = _resolve_index_version(options["index_version"])
        pools = []
        for record in records:
            try:
                pools.append(
                    run_shadow_query_pool(
                        record,
                        index_version,
                        pool_top_k=options["pool_top_k"],
                        blind_seed=str(options["blind_seed"]),
                        disabled_v2_branch_types=options["disable_v2_branch"],
                    )
                )
            except Exception as exc:
                raise CommandError(
                    f"query {record['query_id']} 的四路 pooling 失败：{str(exc)[:1000]}"
                ) from exc
        if not any(pool.get("candidates") for pool in pools):
            raise CommandError("四路 pooling 没有得到任何可标注 candidate，未写空标注包。")
        manifest = write_annotation_package(
            records,
            pools,
            output_dir,
            split_seed=str(options["split_seed"]),
            blind_seed=str(options["blind_seed"]),
        )
        report.update(
            {
                "index_version": {
                    "id": str(index_version.id),
                    "uid": index_version.uid,
                    "status": index_version.status,
                },
                "output_dir": str(output_dir),
                "manifest": manifest,
            }
        )
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
