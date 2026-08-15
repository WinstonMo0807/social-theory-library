from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import SearchEvaluationSet, SemanticIndexVersion
from catalog.services.search_evaluation import (
    SearchEvaluationExecutionError,
    SearchEvaluationValidationError,
    build_evaluation_plan,
    execute_evaluation,
)


VARIANTS = [
    {
        "name": "V1",
        "search_version": "v1",
        "search_profile": None,
        "rerank_top_k": None,
        "requires_reranker": False,
    },
    {
        "name": "V2-A",
        "search_version": "v2",
        "search_profile": "fast",
        "rerank_top_k": None,
        "requires_reranker": False,
    },
    {
        "name": "V2-B",
        "search_version": "v2",
        "search_profile": "balanced",
        "rerank_top_k": None,
        "requires_reranker": True,
    },
    {
        "name": "V2-C",
        "search_version": "v2",
        "search_profile": "precision",
        "rerank_top_k": None,
        "requires_reranker": True,
    },
    *[
        {
            "name": f"V2-C-rerank-{top_k}",
            "search_version": "v2",
            "search_profile": "precision",
            "rerank_top_k": top_k,
            "requires_reranker": True,
        }
        for top_k in (8, 12, 16, 24, 32)
    ],
]


def _resolve_evaluation_set(value: str) -> SearchEvaluationSet:
    row = SearchEvaluationSet.objects.filter(name=value).first()
    if row is None:
        try:
            row = SearchEvaluationSet.objects.filter(pk=UUID(value)).first()
        except (TypeError, ValueError, AttributeError):
            row = None
    if row is None:
        raise CommandError(f"找不到评估集：{value}")
    return row


def _resolve_index_version(value: str) -> SemanticIndexVersion:
    row = SemanticIndexVersion.objects.filter(uid=value).first()
    if row is None:
        try:
            row = SemanticIndexVersion.objects.filter(pk=UUID(value)).first()
        except (TypeError, ValueError, AttributeError):
            row = None
    if row is None:
        raise CommandError(f"找不到索引版本：{value}")
    return row


def _variant_payload(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": variant["name"],
        "search_version": variant["search_version"],
        "search_profile": variant["search_profile"],
        "rerank_top_k": variant["rerank_top_k"],
    }


class Command(BaseCommand):
    help = "用同一人工评估集比较观点检索 V1、V2-A/B/C 与 rerank Top K。"

    def add_arguments(self, parser):
        parser.add_argument("--evaluation-set", required=True, help="评估集 UUID 或名称")
        parser.add_argument("--index-version", required=True, help="索引版本 UUID 或 UID")
        parser.add_argument("--semantic-ratio", type=float, default=0.72)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="只执行依赖与人工标注预检，不生成评估运行。",
        )

    def handle(self, *args, **options):
        semantic_ratio = float(options["semantic_ratio"])
        if not 0 <= semantic_ratio <= 1:
            raise CommandError("--semantic-ratio 必须在 0 到 1 之间。")
        evaluation_set = _resolve_evaluation_set(options["evaluation_set"])
        index_version = _resolve_index_version(options["index_version"])
        dry_run = bool(options["dry_run"])
        report: dict[str, Any] = {
            "generated_at": timezone.now().isoformat(),
            "mode": "dry_run" if dry_run else "execute",
            "evaluation_set": {
                "id": str(evaluation_set.id),
                "name": evaluation_set.name,
            },
            "index_version": {
                "id": str(index_version.id),
                "uid": index_version.uid,
                "status": index_version.status,
            },
            "semantic_ratio": semantic_ratio,
            "judgment_scale": {
                "0": "不相关",
                "1": "同主题但未回应",
                "2": "具有实质证据价值",
                "3": "直接回应问题",
            },
            "variants": [],
        }

        base_plan = build_evaluation_plan(
            evaluation_set,
            index_version,
            semantic_ratio=semantic_ratio,
            verify_index=True,
        )
        report["preflight"] = base_plan
        if dry_run or not base_plan["can_execute"]:
            reason = (
                "dry-run 只完成预检，尚未产生真实精度与延迟数据。"
                if base_plan["can_execute"]
                else "预检未通过，真实比较待核实。"
            )
            report["variants"] = [
                {
                    **_variant_payload(variant),
                    "status": "待核实",
                    "reason": reason,
                }
                for variant in VARIANTS
            ]
            self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
            return

        for variant in VARIANTS:
            payload = _variant_payload(variant)
            try:
                run = execute_evaluation(
                    evaluation_set,
                    index_version,
                    semantic_ratio=semantic_ratio,
                    search_version=variant["search_version"],
                    search_profile=variant["search_profile"],
                    rerank_top_k=variant["rerank_top_k"],
                )
            except SearchEvaluationValidationError as exc:
                report["variants"].append(
                    {
                        **payload,
                        "status": "待核实",
                        "reason": "评估预检未通过。",
                        "blockers": exc.plan.get("blockers", []),
                    }
                )
                continue
            except SearchEvaluationExecutionError as exc:
                report["variants"].append(
                    {
                        **payload,
                        "status": "待核实",
                        "reason": str(exc),
                        "run_id": str(exc.run.id),
                    }
                )
                continue

            fallback_rate = float(run.metrics.get("rerank_fallback_rate") or 0)
            applied_rate = float(run.metrics.get("reranker_applied_rate") or 0)
            if variant["requires_reranker"] and fallback_rate > 0:
                status = "待核实"
                reason = "Reranker 发生降级，本次指标不能代表该精排变体。"
            elif variant["requires_reranker"] and applied_rate < 1:
                status = "待核实"
                reason = "Reranker 未对全部查询实际生效，本次指标不能代表该精排变体。"
            else:
                status = "completed"
                reason = ""
            report["variants"].append(
                {
                    **payload,
                    "status": status,
                    "reason": reason,
                    "run_id": str(run.id),
                    "metrics": run.metrics,
                }
            )

        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
