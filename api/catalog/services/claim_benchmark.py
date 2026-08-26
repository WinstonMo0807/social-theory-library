from __future__ import annotations

import math
from hashlib import sha256
import json
from dataclasses import asdict, dataclass
from statistics import mean
from typing import Any, Iterable

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from catalog.models import SiteSetting
from common.capabilities import Capability, has_capability


RELEVANT_THRESHOLD = 2
BENCHMARK_RUN_KEY_PREFIX = "claim_viewpoint_benchmark_run_"
BENCHMARK_ACTIVATION_KEY = "claim_viewpoint_benchmark_activation"
GOLD_MINIMUM_QUERY_COUNT = 10
GOLD_REQUIRED_RELATIONS = ("direct", "support", "oppose", "qualify")


def claim_benchmark_gold_summary(*, evaluation_set_id=None) -> dict[str, Any]:
    """Describe the human gold corpus without running or activating a benchmark."""

    from django.db.models import Count, Q

    from catalog.models import ClaimBenchmarkJudgment

    rows = ClaimBenchmarkJudgment.objects.all()
    if evaluation_set_id:
        rows = rows.filter(query__evaluation_set_id=evaluation_set_id)

    relation_counts = {
        relation: 0
        for relation, _label in ClaimBenchmarkJudgment.Relation.choices
    }
    for row in rows.order_by().values("expected_relation").annotate(total=Count("id")):
        relation_counts[str(row["expected_relation"])] = int(row["total"])

    gold_query_count = rows.values("query_id").distinct().count()
    relevant_query_count = (
        rows.filter(relevance__gte=RELEVANT_THRESHOLD)
        .values("query_id")
        .distinct()
        .count()
    )
    judgment_count = rows.count()
    stale_evidence_count = rows.filter(
        Q(evidence_span__is_stale=True)
        | Q(document_revision__is_active=False)
    ).count()
    unverified_relevant_locator_count = rows.filter(
        relevance__gte=RELEVANT_THRESHOLD,
        locator_verified=False,
    ).count()
    missing_required_relations = [
        relation
        for relation in GOLD_REQUIRED_RELATIONS
        if relation_counts.get(relation, 0) == 0
    ]

    blockers: list[dict[str, Any]] = []
    if gold_query_count < GOLD_MINIMUM_QUERY_COUNT:
        blockers.append(
            {
                "code": "insufficient_gold_queries",
                "required": GOLD_MINIMUM_QUERY_COUNT,
                "actual": gold_query_count,
            }
        )
    if relevant_query_count < gold_query_count:
        blockers.append(
            {
                "code": "queries_without_relevant_gold",
                "count": gold_query_count - relevant_query_count,
            }
        )
    if missing_required_relations:
        blockers.append(
            {
                "code": "missing_required_stance_coverage",
                "relations": missing_required_relations,
            }
        )
    if unverified_relevant_locator_count:
        blockers.append(
            {
                "code": "unverified_relevant_locators",
                "count": unverified_relevant_locator_count,
            }
        )
    if stale_evidence_count:
        blockers.append(
            {
                "code": "stale_or_superseded_evidence",
                "count": stale_evidence_count,
            }
        )

    return {
        "gold_query_count": gold_query_count,
        "relevant_gold_query_count": relevant_query_count,
        "judgment_count": judgment_count,
        "verified_locator_count": rows.filter(locator_verified=True).count(),
        "stance_coverage": {
            "counts": relation_counts,
            "required": list(GOLD_REQUIRED_RELATIONS),
            "missing_required": missing_required_relations,
        },
        "benchmark_ready": not blockers,
        "blockers": blockers,
        "policy": {
            "minimum_gold_queries": GOLD_MINIMUM_QUERY_COUNT,
            "relevant_threshold": RELEVANT_THRESHOLD,
            "requires_verified_relevant_locators": True,
            "requires_active_evidence": True,
        },
        "ranking": {
            "default": "semantic_v2_baseline",
            "claim_mode": "shadow",
            "changed": False,
        },
        "management_endpoint": "/api/catalog/admin/claim-benchmark/judgments/",
    }


@dataclass(frozen=True, slots=True)
class ClaimQueryMetrics:
    recall_at_k: float
    ndcg_at_k: float
    reciprocal_rank: float
    wrong_work_rate: float
    locator_accuracy: float
    opposing_evidence_recall: float
    qualification_recall: float
    attribution_error_rate: float
    claim_stance_accuracy: float
    relevant_gold_count: int
    result_count: int

    def payload(self) -> dict[str, Any]:
        return asdict(self)


def _key(row: dict[str, Any]) -> str:
    return str(row.get("evidence_span_id") or row.get("id") or "")


def _gain(relevance: int) -> int:
    return 0 if relevance < RELEVANT_THRESHOLD else (2 ** (relevance - 1)) - 1


def score_claim_query(
    *,
    gold: Iterable[dict[str, Any]],
    predictions: Iterable[dict[str, Any]],
    k: int = 20,
) -> ClaimQueryMetrics:
    gold_rows = [dict(row) for row in gold]
    predicted_rows = [dict(row) for row in predictions][:k]
    gold_by_span = {_key(row): row for row in gold_rows if _key(row)}
    relevant = {
        key: row
        for key, row in gold_by_span.items()
        if int(row.get("relevance") or 0) >= RELEVANT_THRESHOLD
    }
    retrieved_keys = [_key(row) for row in predicted_rows]
    recalled = sum(1 for key in set(retrieved_keys) if key in relevant)
    recall = recalled / len(relevant) if relevant else 0.0

    dcg = sum(
        _gain(int(gold_by_span.get(key, {}).get("relevance") or 0)) / math.log2(rank + 1)
        for rank, key in enumerate(retrieved_keys, start=1)
    )
    ideal = sorted((int(row.get("relevance") or 0) for row in gold_rows), reverse=True)[:k]
    ideal_dcg = sum(_gain(grade) / math.log2(rank + 1) for rank, grade in enumerate(ideal, start=1))
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0

    reciprocal_rank = 0.0
    for rank, key in enumerate(retrieved_keys, start=1):
        if key in relevant:
            reciprocal_rank = 1 / rank
            break

    relevant_works = {str(row.get("work_id") or "") for row in relevant.values() if row.get("work_id")}
    wrong_work_count = sum(
        1
        for row in predicted_rows
        if str(row.get("work_id") or "") not in relevant_works
    )
    wrong_work_rate = wrong_work_count / len(predicted_rows) if predicted_rows else 0.0

    matched_pairs = [
        (prediction, gold_by_span[_key(prediction)])
        for prediction in predicted_rows
        if _key(prediction) in gold_by_span
    ]
    locator_pairs = [pair for pair in matched_pairs if bool(pair[1].get("locator_verified"))]
    locator_accuracy = (
        sum(
            1
            for prediction, expected in locator_pairs
            if int(prediction.get("page") or 0) == int(expected.get("page") or 0)
        )
        / len(locator_pairs)
        if locator_pairs
        else 0.0
    )

    def relation_recall(relation: str) -> float:
        expected = {
            key for key, row in relevant.items() if str(row.get("relation") or "") == relation
        }
        if not expected:
            return 0.0
        found = {
            _key(row)
            for row in predicted_rows
            if str(row.get("relation") or "") == relation and _key(row) in expected
        }
        return len(found) / len(expected)

    attribution_pairs = [
        pair
        for pair in matched_pairs
        if str(pair[1].get("attribution") or "uncertain") != "uncertain"
    ]
    attribution_error_rate = (
        sum(
            1
            for prediction, expected in attribution_pairs
            if str(prediction.get("attribution") or "uncertain") != str(expected.get("attribution"))
        )
        / len(attribution_pairs)
        if attribution_pairs
        else 0.0
    )
    stance_pairs = [
        pair for pair in matched_pairs if str(pair[1].get("relation") or "")
    ]
    stance_accuracy = (
        sum(
            1
            for prediction, expected in stance_pairs
            if str(prediction.get("relation") or "") == str(expected.get("relation") or "")
        )
        / len(stance_pairs)
        if stance_pairs
        else 0.0
    )
    return ClaimQueryMetrics(
        recall_at_k=recall,
        ndcg_at_k=ndcg,
        reciprocal_rank=reciprocal_rank,
        wrong_work_rate=wrong_work_rate,
        locator_accuracy=locator_accuracy,
        opposing_evidence_recall=relation_recall("oppose"),
        qualification_recall=relation_recall("qualify"),
        attribution_error_rate=attribution_error_rate,
        claim_stance_accuracy=stance_accuracy,
        relevant_gold_count=len(relevant),
        result_count=len(predicted_rows),
    )


def aggregate_claim_benchmark(rows: Iterable[ClaimQueryMetrics]) -> dict[str, Any]:
    metrics = list(rows)
    if not metrics:
        return {"ready": False, "query_count": 0, "reason": "没有可用的人工 Claim gold judgment。"}
    numeric_fields = (
        "recall_at_k",
        "ndcg_at_k",
        "reciprocal_rank",
        "wrong_work_rate",
        "locator_accuracy",
        "opposing_evidence_recall",
        "qualification_recall",
        "attribution_error_rate",
        "claim_stance_accuracy",
    )
    output = {
        field: round(mean(getattr(row, field) for row in metrics), 6)
        for field in numeric_fields
    }
    output.update(
        {
            "ready": True,
            "query_count": len(metrics),
            "relevant_gold_count": sum(row.relevant_gold_count for row in metrics),
        }
    )
    return output


def viewpoint_ranking_gate(
    *,
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    minimum_queries: int = 10,
    regression_tolerance: float = 0.02,
) -> dict[str, Any]:
    """Conservative shadow-mode gate. It never mutates the live ranking flag."""

    blockers: list[dict[str, Any]] = []
    if int(candidate.get("query_count") or 0) < minimum_queries:
        blockers.append(
            {
                "metric": "query_count",
                "required": minimum_queries,
                "actual": int(candidate.get("query_count") or 0),
            }
        )
    higher_is_better = ("recall_at_k", "ndcg_at_k", "reciprocal_rank", "locator_accuracy")
    for metric in higher_is_better:
        baseline_value = float(baseline.get(metric) or 0)
        candidate_value = float(candidate.get(metric) or 0)
        if candidate_value + regression_tolerance < baseline_value:
            blockers.append({"metric": metric, "baseline": baseline_value, "candidate": candidate_value})
    baseline_wrong_work = float(baseline.get("wrong_work_rate") or 0)
    candidate_wrong_work = float(candidate.get("wrong_work_rate") or 0)
    if candidate_wrong_work > baseline_wrong_work + regression_tolerance:
        blockers.append(
            {
                "metric": "wrong_work_rate",
                "baseline": baseline_wrong_work,
                "candidate": candidate_wrong_work,
            }
        )
    thresholds = {
        "opposing_evidence_recall": max(0.50, float(baseline.get("opposing_evidence_recall") or 0) + 0.10),
        "qualification_recall": max(0.40, float(baseline.get("qualification_recall") or 0) + 0.10),
        "claim_stance_accuracy": 0.75,
        "locator_accuracy": 0.90,
    }
    for metric, required in thresholds.items():
        actual = float(candidate.get(metric) or 0)
        if actual < required:
            blockers.append({"metric": metric, "required": round(required, 6), "actual": actual})
    attribution_error = float(candidate.get("attribution_error_rate") or 0)
    if attribution_error > 0.15:
        blockers.append({"metric": "attribution_error_rate", "required_max": 0.15, "actual": attribution_error})
    return {
        "passed": not blockers,
        "default_ranking_change_allowed": not blockers,
        "blockers": blockers,
        "policy": {
            "minimum_queries": minimum_queries,
            "regression_tolerance": regression_tolerance,
            "shadow_mode_until_passed": True,
        },
    }


def benchmark_report_hash(report: dict[str, Any]) -> str:
    encoded = json.dumps(
        report,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@transaction.atomic
def record_claim_benchmark_report(
    report: dict[str, Any],
    *,
    actor=None,
) -> dict[str, Any]:
    """Persist an immutable benchmark decision input in PostgreSQL."""

    report_hash = benchmark_report_hash(report)
    run_key = f"{BENCHMARK_RUN_KEY_PREFIX}{report_hash[:40]}"
    payload = {
        "report_hash": report_hash,
        "recorded_at": timezone.now().isoformat(),
        "evaluation_set": report.get("evaluation_set"),
        "gold_query_count": int(report.get("gold_query_count") or 0),
        "completed_query_count": int(report.get("completed_query_count") or 0),
        "errors": list(report.get("errors") or []),
        "baseline": dict(report.get("baseline") or {}),
        "claim_shadow": dict(report.get("claim_shadow") or {}),
        "gate": dict(report.get("gate") or {}),
    }
    row, created = SiteSetting.objects.get_or_create(
        key=run_key,
        defaults={"value": payload, "public": False, "updated_by": actor},
    )
    if not created and str((row.value or {}).get("report_hash")) != report_hash:
        # A content-addressed run key must never be silently overwritten.
        raise ValueError("Benchmark report hash collision or immutable run mismatch.")
    return {"report_hash": report_hash, "run_key": run_key, "created": created}


@transaction.atomic
def activate_claim_viewpoint_ranking(
    report_hash: str,
    *,
    actor,
) -> dict[str, Any]:
    if not has_capability(actor, Capability.MANAGE_GLOBAL_PROJECTION):
        raise PermissionError("只有超级管理员可以激活 Viewpoint Ranking。")
    normalized_hash = str(report_hash or "").strip().lower()
    if len(normalized_hash) != 64 or any(ch not in "0123456789abcdef" for ch in normalized_hash):
        raise ValueError("Benchmark report hash 无效。")
    run_key = f"{BENCHMARK_RUN_KEY_PREFIX}{normalized_hash[:40]}"
    run = SiteSetting.objects.select_for_update().filter(key=run_key).first()
    if run is None or str((run.value or {}).get("report_hash")) != normalized_hash:
        raise ValueError("找不到对应的 PostgreSQL benchmark run。")
    run_payload = dict(run.value or {})
    gate = dict(run_payload.get("gate") or {})
    if not gate.get("passed") or not gate.get("default_ranking_change_allowed"):
        raise ValueError("该 benchmark run 未通过切换门槛。")
    if int(run_payload.get("completed_query_count") or 0) < 10:
        raise ValueError("该 benchmark run 的人工 gold query 数不足。")
    if run_payload.get("errors"):
        raise ValueError("该 benchmark run 含未解决错误，不能激活。")
    activation = {
        "active": True,
        "report_hash": normalized_hash,
        "run_key": run_key,
        "activated_at": timezone.now().isoformat(),
        "activated_by": str(getattr(actor, "pk", "")),
    }
    SiteSetting.objects.update_or_create(
        key=BENCHMARK_ACTIVATION_KEY,
        defaults={"value": activation, "public": False, "updated_by": actor},
    )
    return activation


def claim_viewpoint_activation_state() -> dict[str, Any]:
    """Require both an operator flag and a verified PostgreSQL decision."""

    if not bool(getattr(settings, "VIEWPOINT_CLAIM_BENCHMARK_GATE_PASSED", False)):
        return {"active": False, "reason": "deployment_flag_disabled"}
    activation = SiteSetting.objects.filter(key=BENCHMARK_ACTIVATION_KEY).first()
    value = dict(activation.value or {}) if activation else {}
    report_hash = str(value.get("report_hash") or "")
    run_key = str(value.get("run_key") or "")
    if not value.get("active") or not report_hash or not run_key:
        return {"active": False, "reason": "postgres_activation_missing"}
    run = SiteSetting.objects.filter(key=run_key).first()
    run_value = dict(run.value or {}) if run else {}
    gate = dict(run_value.get("gate") or {})
    valid = all(
        (
            run is not None,
            run_value.get("report_hash") == report_hash,
            bool(gate.get("passed")),
            bool(gate.get("default_ranking_change_allowed")),
            int(run_value.get("completed_query_count") or 0) >= 10,
            not run_value.get("errors"),
        )
    )
    if not valid:
        return {"active": False, "reason": "postgres_benchmark_gate_invalid"}
    return {
        "active": True,
        "reason": "verified_benchmark_activation",
        "report_hash": report_hash,
        "activated_at": value.get("activated_at"),
    }
