"""Contract checks only; synthetic replies do not establish model quality."""
from copy import deepcopy
from unittest.mock import patch

import pytest
from django.test import override_settings

from catalog.services.retrieval import deep_pipeline as pipeline


def test_context_annotations_keep_relevance_order_and_original_text():
    rows = [{"id": "a", "text": "first source", "deep_rank": 1},
            {"id": "b", "text": "second source", "deep_rank": 2}]
    payload = {"status": "completed", "model": "Purdy0228/ConvMemory-v2-Evidence-Reranker",
               "artifact_id": "context-bundle", "generation": "generation-1", "results": [
                   {"index": 0, "id": "a", "context_score": .1, "context_rank": 2,
                    "context": "must not replace original"},
                   {"index": 1, "id": "b", "context_score": .9, "context_rank": 1}]}
    with override_settings(STL_DEEP_RETRIEVAL_CONVMEMORY_ENABLED=True,
                           STL_DEEP_RETRIEVAL_CONVMEMORY_URL="http://inference/context-organize",
                           STL_DEEP_RETRIEVAL_CONVMEMORY_MODEL="ConvMemory-v2",
                           STL_DEEP_RETRIEVAL_CONVMEMORY_ARTIFACT="context-bundle",
                           STL_DEEP_RETRIEVAL_GENERATION="generation-1"):
        with patch.object(pipeline, "_post_deep_service", return_value=payload):
            result, state, _ = pipeline._convmemory_organize("question", deepcopy(rows))
        assert state["status"] == "completed"
        assert [(row["id"], row["text"], row["deep_rank"]) for row in result] == [
            (row["id"], row["text"], row["deep_rank"]) for row in rows]
        assert result[0]["deep_context"]["context_rank"] == 2
        payload["generation"] = "wrong-generation"
        with patch.object(pipeline, "_post_deep_service", return_value=payload):
            result, state, _ = pipeline._convmemory_organize("question", deepcopy(rows))
        assert state["status"] == "degraded"
        assert result == rows


@pytest.mark.parametrize("values", [
    [{"index": 0, "relevance_score": 1}],
    [{"index": 0, "relevance_score": 1}, {"index": 0, "relevance_score": 0}],
    [{"index": 0, "relevance_score": float("nan")}, {"index": 1, "relevance_score": 0}],
])
def test_incomplete_or_nonfinite_deep_order_is_rejected(values):
    with pytest.raises(ValueError):
        pipeline._parse_order({"results": values}, [{"id": "a"}, {"id": "b"}])


def test_unready_bge_retains_baseline_order():
    baseline = [{"id": "a", "source_revision": "1"}, {"id": "b", "source_revision": "1"}]
    with override_settings(STL_DEEP_RETRIEVAL_ENABLED=True), \
            patch.object(pipeline, "_query_variants", return_value=([], {"status": "completed"})), \
            patch.object(pipeline, "_eg2_candidates", return_value=([baseline[1]], {"status": "completed"}, [])), \
            patch.object(pipeline, "_bge_rerank", side_effect=lambda q, rows: (rows, {"status": "degraded"}, [])), \
            patch.object(pipeline, "_attach_adjacent_context", side_effect=lambda rows, access: (rows, {"status": "completed"}, [])), \
            patch.object(pipeline, "_convmemory_organize", side_effect=lambda q, rows: (rows, {"status": "disabled"}, [])), \
            patch.object(pipeline, "validate_discovery_results", side_effect=lambda channel, rows, access: rows):
        result = pipeline.run_deep_pipeline("question", baseline, ["public"])
    assert result["ranking_applied"] is False
    assert result["status"] == "degraded"
    assert result["rows"] == baseline
