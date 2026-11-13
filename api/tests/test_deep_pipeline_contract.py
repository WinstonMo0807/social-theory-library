"""Contract checks only; synthetic replies do not establish model quality."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings

from catalog.services.retrieval import deep_pipeline as pipeline


def test_deep_index_settings_use_shared_writer_and_keep_baseline_isolation():
    from catalog.services.retrieval import deep_index
    from catalog.services import discovery_indexing

    with patch.object(deep_index, "configuration", return_value=("deep-synthetic", "artifact", "generation")), \
            patch.object(discovery_indexing, "meili", return_value={}) as call, \
            patch.object(discovery_indexing, "wait_index_task"):
        assert deep_index.prepare_index() == "deep-synthetic"
    method, path, config = call.call_args.args
    assert (method, path) == ("PATCH", "/indexes/deep-synthetic/settings")
    assert config["embedders"]["discovery"]["dimensions"] == 768
    assert "baseline_generation" in config["filterableAttributes"]


def test_eg2_uses_deep_encoder_without_replacing_baseline():
    from catalog.services import discovery_inference as client

    vector = [1.0] + [0.0] * 767
    reply = {"model": "google/embeddinggemma-2", "revision": "pinned", "artifact_id": "eg2",
             "generation": "deep-1", "vectors": [vector], "dimensions": 768, "truncated": [False]}
    with override_settings(STL_DEEP_RETRIEVAL_GENERATION="deep-1"), \
            patch.object(pipeline, "_deep_meili_filter", side_effect=lambda *_: {"filter": ['scope_token IN ["fixture"]'], "limit": 120}), \
            patch.object(pipeline, "active_generation", return_value=SimpleNamespace(pk="baseline-1")), \
            patch("catalog.services.discovery_projection.meili", return_value={"hits": []}), \
            patch.object(pipeline, "validate_discovery_results", return_value=[]), \
            patch.object(client, "_call", return_value=reply) as call:
        _, state, warnings = pipeline._eg2_candidates("question", {}, ["public"],
                                                       index_uid="deep_index", embedding_artifact="eg2", dimensions=768)
        assert state["status"] == "completed" and not warnings
        assert call.call_args.args[0] == "/deep-embed"
        assert call.call_args.args[1]["generation"] == "deep-1"
        reply["generation"] = "old"
        _, state, warnings = pipeline._eg2_candidates("question", {}, ["public"],
                                                       index_uid="deep_index", embedding_artifact="eg2", dimensions=768)
        assert state["status"] == "degraded" and warnings


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
