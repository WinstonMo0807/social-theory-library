from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from catalog.services.semantic_search_benchmark import (
    SPLITS,
    apply_human_judgments,
    freeze_benchmark_splits,
    read_jsonl,
    score_shadow_pool,
    validate_benchmark_records,
)


class Command(BaseCommand):
    help = "用人工 qrels 计算四路 shadow 结果的分组检索与性能指标。"

    def add_arguments(self, parser):
        parser.add_argument("--dataset", required=True, help="含人工 gold_judgments 的 JSONL")
        parser.add_argument("--pool", required=True, help="annotation package 的 diagnostic-pool.jsonl")
        parser.add_argument(
            "--judgments",
            help="annotation.html 下载的人工 judgments JSONL；未评分的 null 行会被忽略。",
        )
        parser.add_argument("--output", help="可选 JSON 指标路径")
        parser.add_argument(
            "--frozen-dataset-output",
            help="可选写出已合并人工 judgments 的冻结数据集 JSONL。",
        )
        parser.add_argument(
            "--split",
            action="append",
            choices=sorted(SPLITS),
            help="要评分的 split，可重复传入。默认只评分 dev，test 必须显式选择。",
        )

    def handle(self, *args, **options):
        try:
            records = validate_benchmark_records(read_jsonl(options["dataset"]))
            records = freeze_benchmark_splits(records)
            if options.get("judgments"):
                records = apply_human_judgments(
                    records,
                    read_jsonl(options["judgments"]),
                )
            pools = read_jsonl(options["pool"])
            included_splits = sorted(set(options.get("split") or ["dev"]))
            selected_records = [
                record
                for record in records
                if record.get("split") in included_splits
            ]
            selected_query_ids = {
                record["query_id"] for record in selected_records
            }
            selected_pools = [
                pool
                for pool in pools
                if pool.get("query_id") in selected_query_ids
            ]
            report = score_shadow_pool(selected_records, selected_pools)
            report["included_splits"] = included_splits
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        if report["judged_query_count"] == 0:
            raise CommandError("没有包含 2 或 3 级人工 judgment 的可评分 query。")
        if options.get("frozen_dataset_output"):
            target = Path(options["frozen_dataset_output"]).resolve()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(
                    "".join(
                        json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
                        for record in records
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                raise CommandError(str(exc)) from exc
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if options.get("output"):
            target = Path(options["output"]).resolve()
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(text, encoding="utf-8")
            except OSError as exc:
                raise CommandError(str(exc)) from exc
        self.stdout.write(text.rstrip())
