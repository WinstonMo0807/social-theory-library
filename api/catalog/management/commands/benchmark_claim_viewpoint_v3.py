from __future__ import annotations

import json
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from catalog.models import (
    ClaimBenchmarkJudgment,
    SearchEvaluationQuery,
    SearchEvaluationSet,
)
from catalog.services.claim_benchmark import (
    aggregate_claim_benchmark,
    record_claim_benchmark_report,
    score_claim_query,
    viewpoint_ranking_gate,
)
from catalog.services.viewpoint_search import viewpoint_search


def _evaluation_set(value: str):
    if not value:
        return None
    row = SearchEvaluationSet.objects.filter(name=value).first()
    if row is None:
        try:
            row = SearchEvaluationSet.objects.filter(pk=UUID(value)).first()
        except (TypeError, ValueError, AttributeError):
            row = None
    if row is None:
        raise CommandError(f"找不到评估集：{value}")
    return row


def _prediction(row: dict) -> dict:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    locator = evidence.get("locator") if isinstance(evidence.get("locator"), dict) else {}
    work = row.get("work") if isinstance(row.get("work"), dict) else {}
    return {
        "evidence_span_id": str(evidence.get("id") or ""),
        "work_id": str(work.get("id") or ""),
        "page": locator.get("page") or row.get("page"),
        "relation": row.get("stance"),
        "attribution": row.get("attribution"),
    }


class Command(BaseCommand):
    help = "用人工 EvidenceSpan gold 比较 Semantic V2 baseline 与 Claim shadow，不修改默认排序。"

    def add_arguments(self, parser):
        parser.add_argument("--evaluation-set", default="")
        parser.add_argument("--limit", type=int, default=40)

    def handle(self, *args, **options):
        evaluation_set = _evaluation_set(str(options["evaluation_set"] or "").strip())
        limit = max(1, min(int(options["limit"]), 100))
        judgments = ClaimBenchmarkJudgment.objects.select_related(
            "query", "query__evaluation_set", "evidence_span"
        ).order_by("query__evaluation_set__name", "query__order", "-relevance")
        if evaluation_set is not None:
            judgments = judgments.filter(query__evaluation_set=evaluation_set)
        query_ids = list(judgments.values_list("query_id", flat=True).distinct())
        queries = (
            SearchEvaluationQuery.objects.filter(pk__in=query_ids)
            .select_related("evaluation_set")
            .prefetch_related("claim_judgments")
            .order_by("evaluation_set__name", "order", "created_at")
        )

        baseline_metrics = []
        candidate_metrics = []
        errors = []
        query_reports = []
        for query in queries:
            gold = [
                {
                    "evidence_span_id": str(row.evidence_span_id),
                    "work_id": str(row.work_id),
                    "page": row.evidence_span.page_number,
                    "relation": row.expected_relation,
                    "attribution": row.expected_attribution,
                    "relevance": row.relevance,
                    "locator_verified": row.locator_verified,
                }
                for row in query.claim_judgments.all()
            ]
            try:
                result = viewpoint_search(
                    query.query_text,
                    filters=query.filters if isinstance(query.filters, dict) else {},
                    limit=limit,
                    debug=True,
                )
            except Exception as exc:
                errors.append(
                    {
                        "query_id": str(query.id),
                        "error_code": exc.__class__.__name__,
                        "message": str(exc)[:500],
                    }
                )
                continue
            baseline = score_claim_query(
                gold=gold,
                predictions=[_prediction(row) for row in result["baseline"]["results"]],
                k=limit,
            )
            candidate = score_claim_query(
                gold=gold,
                predictions=[_prediction(row) for row in result["shadow"]["results"]],
                k=limit,
            )
            baseline_metrics.append(baseline)
            candidate_metrics.append(candidate)
            query_reports.append(
                {
                    "query_id": str(query.id),
                    "evaluation_set": query.evaluation_set.name,
                    "query": query.query_text,
                    "gold": len(gold),
                    "baseline": baseline.payload(),
                    "candidate": candidate.payload(),
                    "claim_index_backend": result["shadow"].get("claim_index_backend"),
                }
            )

        baseline = aggregate_claim_benchmark(baseline_metrics)
        candidate = aggregate_claim_benchmark(candidate_metrics)
        gate = viewpoint_ranking_gate(baseline=baseline, candidate=candidate)
        report = {
            "generated_at": timezone.now().isoformat(),
            "evaluation_set": (
                {"id": str(evaluation_set.id), "name": evaluation_set.name}
                if evaluation_set is not None
                else None
            ),
            "gold_query_count": len(query_ids),
            "completed_query_count": len(query_reports),
            "errors": errors,
            "baseline": baseline,
            "claim_shadow": candidate,
            "gate": gate,
            "default_ranking_changed": False,
            "queries": query_reports,
        }
        report["benchmark_run"] = record_claim_benchmark_report(report)
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
