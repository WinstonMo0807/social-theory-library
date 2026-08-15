from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from statistics import mean
from uuid import UUID

import httpx
from django.db import transaction
from django.utils import timezone

from catalog.models import (
    SearchEvaluationQuery,
    SearchEvaluationResult,
    SearchEvaluationRun,
    SearchEvaluationSet,
    SemanticChunk,
    SemanticIndexVersion,
)
from catalog.services.semantic_indexing import semantic_index_document_count
from catalog.services.semantic_search import current_semantic_runtime, semantic_search


MAX_EVALUATION_QUERIES = 50
RESULT_LIMIT = 20
RELEVANT_THRESHOLD = 2
DIRECT_RESPONSE_GRADE = 3
SEARCH_VERSIONS = {"v1", "v2"}
SEARCH_PROFILES = {"fast", "balanced", "precision"}
RERANK_TOP_K_VALUES = {8, 12, 16, 24, 32}
EVALUATABLE_INDEX_STATUSES = {
    SemanticIndexVersion.Status.READY,
    SemanticIndexVersion.Status.ACTIVE,
    SemanticIndexVersion.Status.RETIRED,
}


class SearchEvaluationError(RuntimeError):
    pass


class SearchEvaluationValidationError(SearchEvaluationError):
    def __init__(self, plan: dict):
        super().__init__("检索评估预检未通过。")
        self.plan = plan


class SearchEvaluationExecutionError(SearchEvaluationError):
    def __init__(self, run: SearchEvaluationRun, message: str):
        super().__init__(message)
        self.run = run


@dataclass(frozen=True, slots=True)
class QueryMetrics:
    recall_at_20: float
    ndcg_at_10: float
    reciprocal_rank: float
    precision_at_5: float
    top5_useful_passage_rate: float
    top3_direct_response_rate: float
    result_count: int
    latency_ms: int


def _normalized_search_options(
    *,
    search_version: str | None,
    search_profile: str | None,
    rerank_top_k: int | None,
) -> dict:
    version = str(search_version or "").strip().lower()
    profile = str(search_profile or "").strip().lower()
    if version and version not in SEARCH_VERSIONS:
        raise ValueError("search_version 只支持 v1 或 v2。")
    if profile and profile not in SEARCH_PROFILES:
        raise ValueError("search_profile 只支持 fast、balanced 或 precision。")
    if rerank_top_k is not None:
        rerank_top_k = int(rerank_top_k)
        if rerank_top_k not in RERANK_TOP_K_VALUES:
            raise ValueError("rerank_top_k 只支持 8、12、16、24 或 32。")
    return {
        "search_version": version or None,
        "search_profile": profile or None,
        "rerank_top_k": rerank_top_k,
    }


def _search_options_from_run(run: SearchEvaluationRun | None) -> dict:
    snapshot = run.config_snapshot if run and isinstance(run.config_snapshot, dict) else {}
    return _normalized_search_options(
        search_version=snapshot.get("search_version"),
        search_profile=snapshot.get("search_profile"),
        rerank_top_k=snapshot.get("rerank_top_k"),
    )


def _index_configuration(version: SemanticIndexVersion) -> dict:
    return {
        "provider": version.provider,
        "model_repo_id": version.model_repo_id,
        "model_revision": version.model_revision,
        "dimensions": version.dimensions,
        "pooling": version.pooling,
    }


def _runtime_index_configuration(runtime: dict) -> dict:
    return {
        "provider": str(runtime.get("provider") or ""),
        "model_repo_id": str(runtime.get("model_repo_id") or runtime.get("model") or ""),
        "model_revision": str(runtime.get("model_revision") or ""),
        "dimensions": runtime.get("dimensions"),
        "pooling": str(runtime.get("pooling") or ""),
    }


def build_evaluation_plan(
    evaluation_set: SearchEvaluationSet,
    index_version: SemanticIndexVersion,
    *,
    semantic_ratio: float,
    verify_index: bool = True,
    search_version: str | None = None,
    search_profile: str | None = None,
    rerank_top_k: int | None = None,
) -> dict:
    search_options = _normalized_search_options(
        search_version=search_version,
        search_profile=search_profile,
        rerank_top_k=rerank_top_k,
    )
    runtime = (
        dict(index_version.config_snapshot)
        if isinstance(index_version.config_snapshot, dict)
        and index_version.config_snapshot
        else current_semantic_runtime()
    )
    queries = list(
        evaluation_set.queries.prefetch_related("judgments").order_by("order", "created_at")
    )
    blockers: list[dict] = []
    warnings: list[dict] = []

    if not evaluation_set.is_active:
        blockers.append({"code": "evaluation_set_inactive", "detail": "评估集已停用。"})
    if not queries:
        blockers.append({"code": "evaluation_set_empty", "detail": "评估集没有查询。"})
    if len(queries) > MAX_EVALUATION_QUERIES:
        blockers.append(
            {
                "code": "evaluation_set_too_large",
                "detail": f"同步评估最多支持 {MAX_EVALUATION_QUERIES} 条查询。",
            }
        )
    unjudged_query_ids = []
    for query in queries:
        if not any(
            judgment.relevance >= RELEVANT_THRESHOLD
            for judgment in query.judgments.all()
        ):
            unjudged_query_ids.append(str(query.id))
    if unjudged_query_ids:
        blockers.append(
            {
                "code": "missing_relevant_judgments",
                "detail": "每条查询至少需要一个人工标注为 2 或 3 级的有效证据段落。",
                "query_ids": unjudged_query_ids,
            }
        )

    if index_version.status not in EVALUATABLE_INDEX_STATUSES:
        blockers.append(
            {
                "code": "index_not_evaluatable",
                "detail": "只有等待切换、生产使用中或已停用但仍保留的索引可以评估。",
                "status": index_version.status,
            }
        )
    runtime_configuration = _runtime_index_configuration(runtime)
    version_configuration = _index_configuration(index_version)
    if runtime_configuration != version_configuration:
        blockers.append(
            {
                "code": "index_runtime_mismatch",
                "detail": "候选索引的模型配置与当前有效查询模型不一致，无法可靠生成查询向量。",
                "index_configuration": version_configuration,
                "runtime_configuration": runtime_configuration,
            }
        )
    if not runtime.get("enabled") or runtime.get("engine") != "meilisearch_hybrid":
        blockers.append(
            {
                "code": "semantic_runtime_disabled",
                "detail": "当前有效配置未启用 Meilisearch 混合检索。",
            }
        )

    actual_document_count = None
    if verify_index and index_version.status in EVALUATABLE_INDEX_STATUSES:
        try:
            actual_document_count = semantic_index_document_count(index_version.uid)
        except (httpx.HTTPError, RuntimeError, TimeoutError, TypeError, ValueError) as exc:
            blockers.append(
                {
                    "code": "candidate_index_unreachable",
                    "detail": f"无法只读检查候选索引：{str(exc)[:500]}",
                }
            )
    if actual_document_count == 0:
        blockers.append(
            {
                "code": "candidate_index_empty",
                "detail": "候选索引没有可评估文档。",
            }
        )
    if (
        actual_document_count is not None
        and index_version.document_count
        and actual_document_count != index_version.document_count
    ):
        warnings.append(
            {
                "code": "index_document_count_changed",
                "detail": "索引当前文档数与版本记录不同，请在解释评估结果时核对。",
                "recorded": index_version.document_count,
                "actual": actual_document_count,
            }
        )

    return {
        "can_execute": not blockers,
        "evaluation_set_id": str(evaluation_set.id),
        "evaluation_set": evaluation_set.name,
        "query_count": len(queries),
        "judgment_count": sum(query.judgments.count() for query in queries),
        "index_version_id": str(index_version.id),
        "index_uid": index_version.uid,
        "index_status": index_version.status,
        "recorded_document_count": index_version.document_count,
        "actual_document_count": actual_document_count,
        "semantic_ratio": round(float(semantic_ratio), 6),
        "result_limit": RESULT_LIMIT,
        "relevant_threshold": RELEVANT_THRESHOLD,
        "judgment_scale": {
            "0": "不相关",
            "1": "同主题但未回应",
            "2": "具有实质证据价值",
            "3": "直接回应问题",
        },
        **search_options,
        "blockers": blockers,
        "warnings": warnings,
        "changes_active_index": False,
        "writes_search_index": False,
    }


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return int(ordered[rank - 1])


def score_query(
    *,
    judgments: dict[str, int],
    retrieved_document_ids: list[str],
    latency_ms: int,
) -> QueryMetrics:
    relevant_ids = {
        document_id
        for document_id, grade in judgments.items()
        if grade >= RELEVANT_THRESHOLD
    }
    top_twenty = retrieved_document_ids[:20]
    recalled = len(relevant_ids.intersection(top_twenty))
    recall = recalled / len(relevant_ids) if relevant_ids else 0.0

    def gain(grade: int) -> int:
        # Grade 1 is the most useful hard negative for opinion retrieval.  It is
        # topically similar but does not help answer the question, so it receives
        # no ranking gain.
        return 0 if grade < RELEVANT_THRESHOLD else (2 ** (grade - 1)) - 1

    dcg = sum(
        gain(judgments.get(document_id, 0)) / math.log2(rank + 1)
        for rank, document_id in enumerate(retrieved_document_ids[:10], start=1)
    )
    ideal_grades = sorted(judgments.values(), reverse=True)[:10]
    ideal_dcg = sum(
        gain(grade) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, start=1)
    )
    ndcg = dcg / ideal_dcg if ideal_dcg else 0.0

    reciprocal_rank = 0.0
    for rank, document_id in enumerate(retrieved_document_ids, start=1):
        if judgments.get(document_id, 0) >= RELEVANT_THRESHOLD:
            reciprocal_rank = 1 / rank
            break

    precision_at_5 = sum(
        1
        for document_id in retrieved_document_ids[:5]
        if judgments.get(document_id, 0) >= RELEVANT_THRESHOLD
    ) / 5
    top5_useful_passage_rate = float(
        any(
            judgments.get(document_id, 0) >= RELEVANT_THRESHOLD
            for document_id in retrieved_document_ids[:5]
        )
    )
    top3_direct_response_rate = float(
        any(
            judgments.get(document_id, 0) == DIRECT_RESPONSE_GRADE
            for document_id in retrieved_document_ids[:3]
        )
    )
    return QueryMetrics(
        recall_at_20=recall,
        ndcg_at_10=ndcg,
        reciprocal_rank=reciprocal_rank,
        precision_at_5=precision_at_5,
        top5_useful_passage_rate=top5_useful_passage_rate,
        top3_direct_response_rate=top3_direct_response_rate,
        result_count=len(retrieved_document_ids),
        latency_ms=max(0, int(latency_ms)),
    )


def _chunk_map(search_rows: list[dict]) -> dict[str, SemanticChunk]:
    identifiers = []
    for row in search_rows:
        try:
            identifiers.append(UUID(str(row.get("id"))))
        except (TypeError, ValueError, AttributeError):
            continue
    return {
        str(chunk.id): chunk
        for chunk in SemanticChunk.objects.filter(pk__in=identifiers)
    }


def _result_score(debug: dict) -> float | None:
    for key in ("reranker_score", "rrf_score"):
        value = debug.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _channel_score(debug: dict, key: str) -> float | None:
    value = debug.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _evaluation_snapshot(queries: list[SearchEvaluationQuery]) -> tuple[list[dict], str]:
    rows = [
        {
            "query_id": str(query.id),
            "query_text": query.query_text,
            "normalized_query": query.normalized_query,
            "filters": query.filters or {},
            "judgments": [
                {
                    "chunk_document_id": judgment.chunk_document_id,
                    "relevance": int(judgment.relevance),
                }
                for judgment in sorted(
                    query.judgments.all(),
                    key=lambda item: (item.chunk_document_id, str(item.id)),
                )
            ],
        }
        for query in queries
    ]
    canonical = json.dumps(
        rows,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return rows, sha256(canonical.encode("utf-8")).hexdigest()


def execute_evaluation(
    evaluation_set: SearchEvaluationSet,
    index_version: SemanticIndexVersion,
    *,
    semantic_ratio: float,
    actor=None,
    existing_run: SearchEvaluationRun | None = None,
    search_version: str | None = None,
    search_profile: str | None = None,
    rerank_top_k: int | None = None,
) -> SearchEvaluationRun:
    stored_options = _search_options_from_run(existing_run)
    supplied_options = _normalized_search_options(
        search_version=search_version,
        search_profile=search_profile,
        rerank_top_k=rerank_top_k,
    )
    search_options = {
        key: supplied_options[key]
        if supplied_options[key] is not None
        else stored_options[key]
        for key in supplied_options
    }
    plan = build_evaluation_plan(
        evaluation_set,
        index_version,
        semantic_ratio=semantic_ratio,
        verify_index=True,
        **search_options,
    )
    if not plan["can_execute"]:
        raise SearchEvaluationValidationError(plan)

    runtime = (
        dict(index_version.config_snapshot)
        if isinstance(index_version.config_snapshot, dict)
        and index_version.config_snapshot
        else current_semantic_runtime()
    )
    queries = list(
        evaluation_set.queries.prefetch_related("judgments").order_by(
            "order", "created_at"
        )
    )
    evaluation_snapshot, evaluation_snapshot_hash = _evaluation_snapshot(queries)
    config_snapshot = {
        "index_uid": index_version.uid,
        "index_configuration": _index_configuration(index_version),
        "runtime_configuration": _runtime_index_configuration(runtime),
        "embedder_name": runtime.get("embedder_name"),
        "result_limit": RESULT_LIMIT,
        "relevant_threshold": RELEVANT_THRESHOLD,
        "judgment_scale": plan["judgment_scale"],
        "evaluation_snapshot": evaluation_snapshot,
        "evaluation_snapshot_hash": evaluation_snapshot_hash,
        **search_options,
        "active_index_changed": False,
    }
    if existing_run is None:
        run = SearchEvaluationRun.objects.create(
            evaluation_set=evaluation_set,
            index_version=index_version,
            status=SearchEvaluationRun.Status.RUNNING,
            engine="meilisearch_hybrid",
            semantic_ratio=semantic_ratio,
            query_count=plan["query_count"],
            completed_query_count=0,
            started_at=timezone.now(),
            created_by=actor,
            config_snapshot=config_snapshot,
        )
    else:
        with transaction.atomic():
            run = SearchEvaluationRun.objects.select_for_update().get(pk=existing_run.pk)
            if run.status == SearchEvaluationRun.Status.COMPLETED:
                return run
            run.results.all().delete()
            run.evaluation_set = evaluation_set
            run.index_version = index_version
            run.status = SearchEvaluationRun.Status.RUNNING
            run.engine = "meilisearch_hybrid"
            run.semantic_ratio = semantic_ratio
            run.query_count = plan["query_count"]
            run.completed_query_count = 0
            run.started_at = timezone.now()
            run.finished_at = None
            run.error_message = ""
            run.metrics = {}
            run.config_snapshot = config_snapshot
            run.save(
                update_fields=[
                    "evaluation_set",
                    "index_version",
                    "status",
                    "engine",
                    "semantic_ratio",
                    "query_count",
                    "completed_query_count",
                    "started_at",
                    "finished_at",
                    "error_message",
                    "metrics",
                    "config_snapshot",
                    "updated_at",
                ]
            )

    query_metrics = []
    try:
        for query in queries:
            search_kwargs = {
                "filters": query.filters or {},
                "limit": RESULT_LIMIT,
                "debug": True,
                "strategy": "hybrid_rerank",
                "index_uid": index_version.uid,
                "semantic_ratio_override": semantic_ratio,
                "runtime_config_override": runtime,
            }
            if search_options["search_version"]:
                search_kwargs["search_version"] = search_options["search_version"]
            if search_options["search_profile"]:
                search_kwargs["search_profile"] = search_options["search_profile"]
            if search_options["rerank_top_k"] is not None:
                search_kwargs["rerank_top_k_override"] = search_options["rerank_top_k"]
            response = semantic_search(query.query_text, **search_kwargs)
            if response.get("fallback_used"):
                reason = response.get("fallback_reason") or "unknown"
                raise SearchEvaluationError(
                    f"候选索引查询发生关键词降级，评估已停止：{reason}。"
                )
            rows = list(response.get("results") or [])[:RESULT_LIMIT]
            chunks = _chunk_map(rows)
            judgments = {
                judgment.chunk_document_id: int(judgment.relevance)
                for judgment in query.judgments.all()
            }
            retrieved_document_ids = []
            latency_ms = max(0, int(round(float(response.get("timing_ms") or 0))))
            stored_results = []
            for rank, row in enumerate(rows, start=1):
                chunk = chunks.get(str(row.get("id")))
                document_id = chunk.document_id if chunk else ""
                if document_id:
                    retrieved_document_ids.append(document_id)
                debug = row.get("debug") if isinstance(row.get("debug"), dict) else {}
                stored_results.append(
                    SearchEvaluationResult(
                        run=run,
                        query=query,
                        retrieved_chunk=chunk,
                        retrieved_document_id=document_id,
                        rank=rank,
                        keyword_score=_channel_score(debug, "keyword_score"),
                        semantic_score=_channel_score(debug, "vector_score"),
                        final_score=_result_score(debug),
                        relevance_grade=judgments.get(document_id),
                        latency_ms=latency_ms,
                        metadata={
                            "search_result_id": str(row.get("id") or ""),
                            "work_id": str(row.get("work_id") or ""),
                            "title": str(row.get("title") or ""),
                            "page_start": row.get("page_start"),
                            "page_end": row.get("page_end"),
                            "debug": debug,
                        },
                    )
                )
            with transaction.atomic():
                SearchEvaluationResult.objects.bulk_create(stored_results)
            scored = score_query(
                judgments=judgments,
                retrieved_document_ids=retrieved_document_ids,
                latency_ms=latency_ms,
            )
            query_metrics.append(
                {
                    "query_id": str(query.id),
                    "result_count": len(rows),
                    "mapped_result_count": len(retrieved_document_ids),
                    "recall_at_20": round(scored.recall_at_20, 6),
                    "ndcg_at_10": round(scored.ndcg_at_10, 6),
                    "reciprocal_rank": round(scored.reciprocal_rank, 6),
                    "precision_at_5": round(scored.precision_at_5, 6),
                    "top5_useful_passage_rate": round(
                        scored.top5_useful_passage_rate,
                        6,
                    ),
                    "top3_direct_response_rate": round(
                        scored.top3_direct_response_rate,
                        6,
                    ),
                    "search_version": response.get("search_version"),
                    "search_profile": response.get("search_profile"),
                    "reranker": response.get("reranker"),
                    "reranker_applied": bool(
                        isinstance(response.get("reranker"), dict)
                        and response["reranker"].get("applied")
                    ),
                    "rerank_fallback": bool(response.get("rerank_fallback")),
                    "latency_ms": scored.latency_ms,
                }
            )
            run.completed_query_count = len(query_metrics)
            run.save(update_fields=["completed_query_count", "updated_at"])

        latencies = [row["latency_ms"] for row in query_metrics]
        metrics = {
            "recall_at_20": round(mean(row["recall_at_20"] for row in query_metrics), 6),
            "ndcg_at_10": round(mean(row["ndcg_at_10"] for row in query_metrics), 6),
            "mrr": round(mean(row["reciprocal_rank"] for row in query_metrics), 6),
            "precision_at_5": round(
                mean(row["precision_at_5"] for row in query_metrics),
                6,
            ),
            "top5_useful_passage_rate": round(
                mean(row["top5_useful_passage_rate"] for row in query_metrics),
                6,
            ),
            "top3_direct_response_rate": round(
                mean(row["top3_direct_response_rate"] for row in query_metrics),
                6,
            ),
            "zero_result_rate": round(
                mean(1 if row["result_count"] == 0 else 0 for row in query_metrics),
                6,
            ),
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "query_count": len(query_metrics),
            "rerank_fallback_rate": round(
                mean(1 if row["rerank_fallback"] else 0 for row in query_metrics),
                6,
            ),
            "reranker_applied_rate": round(
                mean(1 if row["reranker_applied"] else 0 for row in query_metrics),
                6,
            ),
        }
        run.status = SearchEvaluationRun.Status.COMPLETED
        run.metrics = metrics
        run.completed_query_count = len(query_metrics)
        run.finished_at = timezone.now()
        run.config_snapshot = {
            **run.config_snapshot,
            "query_metrics": query_metrics,
        }
        run.save(
            update_fields=[
                "status",
                "metrics",
                "completed_query_count",
                "finished_at",
                "config_snapshot",
                "updated_at",
            ]
        )
        return run
    except Exception as exc:
        run.status = SearchEvaluationRun.Status.FAILED
        run.error_message = str(exc)[:4000]
        run.completed_query_count = len(query_metrics)
        run.finished_at = timezone.now()
        run.config_snapshot = {
            **run.config_snapshot,
            "query_metrics": query_metrics,
        }
        run.save(
            update_fields=[
                "status",
                "error_message",
                "completed_query_count",
                "finished_at",
                "config_snapshot",
                "updated_at",
            ]
        )
        raise SearchEvaluationExecutionError(run, str(exc)) from exc


def prepare_evaluation_run(
    evaluation_set: SearchEvaluationSet,
    index_version: SemanticIndexVersion,
    *,
    semantic_ratio: float,
    actor=None,
    search_version: str | None = None,
    search_profile: str | None = None,
    rerank_top_k: int | None = None,
) -> SearchEvaluationRun:
    """Validate and persist a pending run without doing model or search work in the HTTP request."""

    search_options = _normalized_search_options(
        search_version=search_version,
        search_profile=search_profile,
        rerank_top_k=rerank_top_k,
    )
    plan = build_evaluation_plan(
        evaluation_set,
        index_version,
        semantic_ratio=semantic_ratio,
        verify_index=True,
        **search_options,
    )
    if not plan["can_execute"]:
        raise SearchEvaluationValidationError(plan)
    return SearchEvaluationRun.objects.create(
        evaluation_set=evaluation_set,
        index_version=index_version,
        status=SearchEvaluationRun.Status.PENDING,
        engine="meilisearch_hybrid",
        semantic_ratio=semantic_ratio,
        query_count=plan["query_count"],
        completed_query_count=0,
        created_by=actor,
        config_snapshot={
            "index_uid": index_version.uid,
            "queued": True,
            "relevant_threshold": RELEVANT_THRESHOLD,
            "judgment_scale": plan["judgment_scale"],
            **search_options,
            "active_index_changed": False,
        },
    )
