"""Read-only standard Discovery A/B comparison; never activate an index.

Only ranking changes between variants. Expanded sessions and Ask are not part
of this first comparison. Human grades are deliberately not inferred here.
"""
from time import perf_counter

from catalog.discovery_index_models import DiscoveryDocument
from catalog.models import SemanticIndexVersion
from catalog.services.discovery_context import rerank_contexts
from catalog.services.discovery_inference import rerank, DiscoveryInferenceError
from catalog.services.discovery_projection import (
    current_scopes, discovery_candidates, validate_discovery_results, DiscoveryIndexError,
)
from catalog.services.discovery_sessions import _rrf, _deduplicate, _rerank, _diverse_prefix, MAX_MATERIALIZED, PIPELINE_VERSION
from catalog.services.discovery_sources import fingerprint
from catalog.services.semantic_search_benchmark import _score_ranking
from catalog.services.discovery_material import MATERIAL_ROLES, metadata_last, publication_metadata_hint

SCHEMA = "discovery-context-comparison-v1"
ACCESS = ["public", "inherit"]  # Anonymous-public benchmark; never export private evidence.


def evidence_key(row):
    return fingerprint([row["asset_id"], row["document_revision_id"],
        row.get("evidence_span_id") or row.get("page_id"), row["start_offset"], row["end_offset"], row["text"]])


def compare_query(query, generation, *, context_first=False):
    """Reuse actual recall/fusion/dedup/rerank/diversity, with no session writes."""
    scopes = fingerprint(current_scopes("passages", ACCESS, query.filters))
    started = perf_counter()
    result = discovery_candidates(query.query_text, "passages", query.filters, ACCESS, limit=100,
        expanded=False, request_context={"generation": generation})
    rows = _rrf([(result.get("sparse", []), 1.0), (result.get("dense", []), 1.0)])[:MAX_MATERIALIZED]
    rows = _deduplicate(validate_discovery_results("passages", rows, ACCESS))
    recall_ms = (perf_counter() - started) * 1000
    identifiers = [row["id"] for row in rows]
    # The external search must not return a different generation's document.
    if DiscoveryDocument.objects.filter(pk__in=identifiers, generation=generation).count() != len(identifiers):
        raise DiscoveryIndexError("generation_mismatch")
    artifact = generation.config_snapshot.get("reranker_artifact", "")
    if not artifact or result.get("reranker_artifact") != artifact or str(result.get("version")) != str(generation.pk):
        raise DiscoveryIndexError("generation_mismatch")
    frozen = fingerprint(rows)
    windows = rerank_contexts(rows[:20], ACCESS)
    variants = {}
    baseline_rows = []
    for name in (("context", "baseline") if context_first else ("baseline", "context")):
        started = perf_counter()
        warnings = list(result.get("warnings", []))
        diagnostics = []
        ranked = []
        if name == "baseline":
            ranked, extra = _rerank(query.query_text, rows, 20, artifact)
            warnings.extend(extra)
            baseline_rows = ranked
        else:
            try:
                if rows:
                    response = rerank(query.query_text, [row["text"] for row in rows[:20]],
                                      top_n=min(20, len(rows)), expected_artifact=artifact, contexts=windows)
                    order = [item["index"] for item in response["results"]]
                    if sorted(order) != list(range(min(20, len(rows)))):
                        raise DiscoveryInferenceError("invalid_response")
                    ranked = [rows[index] for index in order] + rows[20:]
                    diagnostics = response["results"]
            except DiscoveryInferenceError as exc:
                warnings.append({"code": exc.code, "message": "上下文变体未完成，不计作质量通过。"})
        if not any(warning.get('code') == 'reranker_unavailable' for warning in warnings):
            ranked = _diverse_prefix(ranked, eligible_count=20)
        variants[name] = {"order": [evidence_key(row) for row in ranked], "warnings": warnings,
                          "ranking_ms": round((perf_counter() - started) * 1000, 3),
                          "model_diagnostics": diagnostics}
    # Keep recall and model scores fixed while testing the publishing-page hypothesis.
    # Limit this experiment to the same 20 candidates; never promote unreranked tails.
    baseline_scored = not any(warning.get('code') == 'reranker_unavailable'
                              for warning in variants['baseline']['warnings'])
    metadata_ranked = (_diverse_prefix(metadata_last(baseline_rows[:20])) + baseline_rows[20:]
                       if baseline_scored else baseline_rows)
    variants["baseline_metadata_last"] = {
        "order": [evidence_key(row) for row in metadata_ranked],
        "warnings": list(variants["baseline"]["warnings"]),
        "ranking_ms": None, "model_diagnostics": [], "experimental_heuristic": True,
    }
    fresh = validate_discovery_results("passages", rows, ACCESS)
    if (fingerprint(fresh) != frozen or rerank_contexts(fresh[:20], ACCESS) != windows or
            fingerprint(current_scopes("passages", ACCESS, query.filters)) != scopes or
            not SemanticIndexVersion.discovery_objects.filter(pk=generation.pk, uid=generation.uid,
                config_snapshot=generation.config_snapshot, status__in=["active", "ready"]).exists()):
        raise DiscoveryIndexError("sources_changed", "比较期间来源/索引改变，结果不能用于评分。")
    pooled = set(key for variant in variants.values() for key in variant["order"][:20])
    candidates = []
    for row in rows:
        key = evidence_key(row)
        if key not in pooled:
            continue
        candidates.append({"candidate_id": key, "chunk_document_id": key, "work_id": row["work_id"],
            "work_title": row.get("title", ""), "authors": row.get("authors", []), "page": row["pdf_page"],
            "original_passage": row["text"], "reader_url": row.get("reader_url", ""),
            "asset_id": row["asset_id"], "document_revision_id": row["document_revision_id"],
            "evidence_span_id": row.get("evidence_span_id"), "page_id": row.get("page_id"),
            "start_offset": row["start_offset"], "end_offset": row["end_offset"], "source_revision": row["source_revision"]})
        candidates[-1]["material_hint"] = publication_metadata_hint(row["text"])
    candidates.sort(key=lambda row: fingerprint([str(query.pk), row["candidate_id"], SCHEMA]))
    contexts_by_key = {evidence_key(row): window for row, window in zip(rows[:20], windows)}
    for position, candidate in enumerate(candidates, 1):
        candidate["annotation_order"] = position
        candidate["context_blocks"] = contexts_by_key.get(candidate["candidate_id"], {}).get("blocks", [])
    return {"query_id": str(query.pk), "query": query.query_text, "filters": query.filters,
        "query_language": "", "direction": "", "query_type": "unclassified", "split": "diagnostic",
        "variants": variants, "candidates": candidates, "recall_ms": round(recall_ms, 3),
        "pool_count": len(rows), "candidate_pool_hash": frozen, "scope_hash": scopes,
        "source_refs": [{"id": row["id"], "source_revision": row["source_revision"]} for row in rows],
        "contexts": contexts_by_key,
        "comparison_usable": bool(rows) and not any(v["warnings"] for v in variants.values())}


def verify_comparison_sources(comparison):
    fresh = validate_discovery_results("passages", comparison["source_refs"], ACCESS)
    windows = {evidence_key(row): window for row, window in zip(fresh[:20], rerank_contexts(fresh[:20], ACCESS))}
    if (fingerprint(fresh) != comparison["candidate_pool_hash"] or windows != comparison["contexts"] or
            fingerprint(current_scopes("passages", ACCESS, comparison["filters"])) != comparison["scope_hash"]):
        raise DiscoveryIndexError("sources_changed", "整批评测结束时来源已变化，未导出可评分报告。")


def score_comparison(report, judgments):
    """Reuse existing ranking metrics, with complete explicit human labels.

    Scores cover the pooled top 20, not whole-library recall or stance quality.
    The report fingerprint binds grades to the evidence actually reviewed.
    """
    if report.get("schema") != SCHEMA:
        raise ValueError("不是当前Discovery比较报告。")
    snapshot = report.get("report_hash")
    if snapshot != fingerprint({k: v for k, v in report.items() if k != "report_hash"}):
        raise ValueError("报告指纹不匹配。")
    labels = {}
    candidates = {(row["query_id"], item["candidate_id"]): item
                  for row in report["queries"] for item in row["candidates"]}
    for judgment in judgments:
        key = (judgment.get("query_id"), judgment.get("chunk_document_id"))
        grade = judgment.get("relevance_grade")
        if grade is None:
            continue
        if key not in candidates or key in labels or type(grade) is not int or not 0 <= grade <= 3:
            raise ValueError("人工评分存在重复、未知候选或非法等级。")
        if (judgment.get("report_hash") != snapshot or judgment.get("locator_verified") is not True or
                not str(judgment.get("reviewer_note") or "").strip()):
            raise ValueError("评分需要报告指纹、已核对PDF定位及人工说明。")
        if (judgment.get("work_id") != candidates[key].get("work_id") or
                judgment.get("page") != candidates[key].get("page")):
            raise ValueError("人工评分的作品或页码与候选不匹配。")
        if judgment.get("material_role") not in MATERIAL_ROLES:
            raise ValueError("请人工选择材料类型；无法判断时可明确选择unknown。")
        labels[key] = grade
    if set(labels) != set(candidates):
        raise ValueError("候选尚未全部人工评分；不能把漏标项当作不相关。")
    scores = []
    roles = {(j.get("query_id"), j.get("chunk_document_id")): j.get("material_role") for j in judgments}
    for row in report["queries"]:
        if not row["comparison_usable"]:
            raise ValueError("报告包含失败、降级或空候选，不能评分为成功比较。")
        grades = {key: value for (qid, key), value in labels.items() if qid == row["query_id"]}
        if not any(value >= 2 for value in grades.values()):
            scores.append({"query_id": row["query_id"], "status": "no_known_positive", "metrics": None})
            continue
        scores.append({"query_id": row["query_id"], "status": "scored",
            "metrics": {name: {**_score_ranking(grades, variant["order"][:20]),
                "precision_at_3": sum(grades.get(key, 0) >= 2 for key in variant["order"][:3]) / 3,
                "precision_at_10": sum(grades.get(key, 0) >= 2 for key in variant["order"][:10]) / 10}
                for name, variant in row["variants"].items()}})
    return {"report_hash": snapshot, "scope": "human-judged pooled top20 only; not corpus recall or attribution",
            "queries": scores, "automatic_activation": False,
            "top3_material_roles": {row["query_id"]: {name: [roles[(row["query_id"], key)] for key in variant["order"][:3]]
                for name, variant in row["variants"].items()} for row in report["queries"]}}


def report_metadata(generation):
    return {"schema": SCHEMA, "pipeline": PIPELINE_VERSION, "generation_id": str(generation.pk),
        "index_uid": generation.uid, "index_config_hash": fingerprint(generation.config_snapshot),
        "embedding_artifact": generation.config_snapshot.get("embedding_artifact"),
        "reranker_artifact": generation.config_snapshot.get("reranker_artifact"), "access_statuses": ACCESS,
        "context_policy": "adjacent-evidence-v1", "rerank_top_k": 20, "mode": "standard_passages_only",
        "automatic_activation": False, "quality_verified": False}
