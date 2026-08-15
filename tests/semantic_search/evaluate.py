"""Evaluate library semantic-search strategies through the public API."""

from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import statistics
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


STRATEGIES = ("legacy", "keyword", "vector", "hybrid", "hybrid_rerank")


def request_json(url: str, token: str = "") -> dict:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=90) as response:
        return json.loads(response.read().decode("utf-8"))


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile_value * len(ordered)) - 1))
    return ordered[index]


def relevant_ids(case: dict) -> tuple[list[str], set[str]]:
    passages = [str(value) for value in case.get("relevant_passage_ids", []) if value]
    works = {str(value) for value in case.get("relevant_work_ids", []) if value}
    return passages, works


def relevance_sequence(case: dict, results: list[dict]) -> list[int]:
    passages, works = relevant_ids(case)
    passage_set = set(passages)
    return [
        1 if str(result.get("id")) in passage_set or str(result.get("work_id")) in works else 0
        for result in results
    ]


def reciprocal_rank(sequence: list[int]) -> float:
    for rank, value in enumerate(sequence, start=1):
        if value:
            return 1 / rank
    return 0.0


def ndcg_at_10(case: dict, results: list[dict]) -> float:
    passages, works = relevant_ids(case)
    if not passages and not works:
        return 0.0
    grades = {passage_id: max(1, len(passages) - index) for index, passage_id in enumerate(passages)}
    values = []
    for result in results[:10]:
        grade = grades.get(str(result.get("id")), 1 if str(result.get("work_id")) in works else 0)
        values.append(grade)
    dcg = sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(values))
    ideal = sorted([*grades.values(), *([1] * len(works))], reverse=True)[:10]
    idcg = sum((2**grade - 1) / math.log2(rank + 2) for rank, grade in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def duplicate_rate(results: list[dict], top_n: int = 10) -> float:
    work_ids = [str(item.get("work_id")) for item in results[:top_n] if item.get("work_id")]
    return (len(work_ids) - len(set(work_ids))) / len(work_ids) if work_ids else 0.0


def evaluate_strategy(base_url: str, token: str, cases: list[dict], strategy: str) -> dict:
    latencies = []
    scored = []
    details = []
    errors = []
    for case in cases:
        params = {"q": case["query"], "limit": 40, "strategy": strategy, "debug": 1}
        for key, values in case.get("filters", {}).items():
            params[key] = values
        url = f"{base_url.rstrip('/')}/catalog/semantic-search/?{urlencode(params, doseq=True)}"
        started = time.perf_counter()
        try:
            payload = request_json(url, token)
        except (HTTPError, URLError, TimeoutError) as exc:
            errors.append({"id": case["id"], "error": str(exc)})
            continue
        latency = (time.perf_counter() - started) * 1000
        latencies.append(latency)
        results = payload.get("results", [])
        sequence = relevance_sequence(case, results)
        relevant_passages, relevant_works = relevant_ids(case)
        is_scored = bool(relevant_passages or relevant_works)
        irrelevant = {str(value) for value in case.get("irrelevant_passage_ids", []) if value}
        row = {
            "id": case["id"],
            "type": case["type"],
            "count": len(results),
            "latency_ms": round(latency, 2),
            "same_work_duplicate_rate_at_10": duplicate_rate(results),
            "known_irrelevant_rate_at_10": (
                sum(1 for item in results[:10] if str(item.get("id")) in irrelevant) / min(10, len(results))
                if results and irrelevant else 0.0
            ),
            "no_result_correct": bool(case.get("expect_no_results") and not results),
        }
        if is_scored:
            total_relevant = len(set(relevant_passages)) + len(relevant_works)
            row.update(
                {
                    "recall_at_10": min(1.0, sum(sequence[:10]) / max(1, total_relevant)),
                    "recall_at_20": min(1.0, sum(sequence[:20]) / max(1, total_relevant)),
                    "mrr": reciprocal_rank(sequence),
                    "ndcg_at_10": ndcg_at_10(case, results),
                }
            )
            scored.append(row)
        details.append(row)
    mean = lambda key: statistics.fmean(row[key] for row in scored) if scored else None
    return {
        "strategy": strategy,
        "queries": len(details),
        "scored_queries": len(scored),
        "recall_at_10": mean("recall_at_10"),
        "recall_at_20": mean("recall_at_20"),
        "mrr": mean("mrr"),
        "ndcg_at_10": mean("ndcg_at_10"),
        "same_work_duplicate_rate_at_10": statistics.fmean(
            row["same_work_duplicate_rate_at_10"] for row in details
        ) if details else 0.0,
        "known_irrelevant_rate_at_10": statistics.fmean(
            row["known_irrelevant_rate_at_10"] for row in details
        ) if details else 0.0,
        "average_latency_ms": statistics.fmean(latencies) if latencies else None,
        "p95_latency_ms": percentile(latencies, 0.95) if latencies else None,
        "errors": errors,
        "details": details,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="评估书库观点检索质量")
    parser.add_argument("--dataset", default=str(Path(__file__).with_name("queries.json")))
    parser.add_argument("--output", default="tmp/semantic-search-evaluation.json")
    parser.add_argument("--api-url", default=os.getenv("LIBRARY_API_URL", "http://127.0.0.1:8000/api"))
    parser.add_argument("--token", default=os.getenv("LIBRARY_ADMIN_TOKEN", ""))
    args = parser.parse_args()
    cases = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    output = {
        "api_url": args.api_url,
        "dataset": str(Path(args.dataset).resolve()),
        "generated_at_unix": int(time.time()),
        "strategies": [],
        "indexing_snapshot": None,
    }
    for strategy in STRATEGIES:
        output["strategies"].append(evaluate_strategy(args.api_url, args.token, cases, strategy))
    if args.token:
        try:
            output["indexing_snapshot"] = request_json(
                f"{args.api_url.rstrip('/')}/catalog/admin/semantic-index/",
                args.token,
            )
        except (HTTPError, URLError, TimeoutError) as exc:
            output["indexing_snapshot_error"] = str(exc)
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入 {target.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
