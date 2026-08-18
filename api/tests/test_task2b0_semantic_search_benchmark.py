from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command

from catalog.models import (
    Asset,
    DocumentType,
    Edition,
    Person,
    PersonNameVariant,
    PublicationState,
    SemanticChunk,
    Work,
)
from catalog.services.query_lexicon.sync import rebuild_query_lexicon
from catalog.services.semantic_search_benchmark import (
    BenchmarkDataError,
    _score_ranking,
    apply_human_judgments,
    audit_historical_chunk_languages,
    audit_query_lexicon_coverage,
    dataset_inventory,
    freeze_benchmark_splits,
    metadata_refresh_assessment,
    read_jsonl,
    run_shadow_query_pool,
    score_shadow_pool,
    validate_benchmark_records,
    write_annotation_package,
)
from catalog.services.semantic_search_v2 import (
    _coverage_features,
    _entity_coverage_context,
    _normalized_term_occurs,
    analyze_query,
)
from catalog.services.semantic_search_v2_config import search_v2_config_snapshot


pytestmark = pytest.mark.django_db


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "evals" / "semantic_search" / "task2a_cross_language.schema.json"
TEMPLATE_PATH = ROOT / "evals" / "semantic_search" / "task2a_cross_language.template.jsonl"


def _benchmark_record(**overrides) -> dict:
    value = {
        "query_id": "q-001",
        "query": "habitus",
        "query_language": "en",
        "direction": "en_to_zh",
        "query_type": "exact_theory",
        "expected_entities": [],
        "gold_judgments": [],
        "notes": "人工判断。",
        "split": None,
        "filters": {},
    }
    value.update(overrides)
    return value


def _search_result(identifier: str, title: str, *, branch=False) -> dict:
    return {
        "id": identifier,
        "work_id": f"work-{title}",
        "title": title,
        "authors": ["Author"],
        "page_start": 12,
        "page_end": 12,
        "snippet": f"Passage {title}",
        "reader_url": f"/reader/{identifier}",
        "debug": {
            "sparse_branch_hits": [
                {"branch_id": "verified_translation:1", "branch_type": "verified_translation", "rank": 1}
            ]
            if branch
            else [],
            "dense_branch_hits": [],
        },
    }


def _shadow_response(source: str, rows: list[dict]) -> dict:
    is_v2 = source == "v2"
    return {
        "search_version": "v2" if is_v2 else "v1",
        "search_profile": "precision" if is_v2 else None,
        "strategy": {
            "lexical": "keyword",
            "dense": "vector",
        }.get(source, "hybrid_rerank"),
        "index_uid": "semantic-test",
        "results": rows,
        "timing_ms": 20 if is_v2 else 10,
        "stage_timings_ms": {
            "query_lexicon_ms": 1,
            "sparse_retrieval_ms": 3,
            "dense_retrieval_ms": 4,
            "rrf_ms": 2,
            "rerank_ms": 5,
        }
        if is_v2
        else None,
        "candidate_counts": {"fusion_candidate_count": len(rows)} if is_v2 else None,
        "query_lexicon_revision": 4 if is_v2 else None,
        "expansion_branches": [
            {"branch_type": "original"},
            {"branch_type": "verified_translation"},
        ]
        if is_v2
        else [],
        "disabled_branch_types": [],
        "fallback_used": source == "lexical",
        "fallback_reason": "semantic_disabled" if source == "lexical" else "",
    }


def test_benchmark_schema_and_template_validate_without_gold_autofill():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    records = validate_benchmark_records(read_jsonl(TEMPLATE_PATH))

    assert schema["$id"] == "stl-task2b0-cross-language-benchmark-v1"
    assert set(schema["properties"]["direction"]["enum"]) == {
        "zh_to_zh",
        "zh_to_en",
        "en_to_zh",
        "en_to_en",
        "mixed",
    }
    assert len(records) == 10
    assert all(record["gold_judgments"] == [] for record in records)
    assert dataset_inventory(records)["usable_query_count"] == 0


def test_train_dev_test_split_is_stable_and_does_not_read_scores():
    records = [
        _benchmark_record(query_id=f"q-{index:03d}", query=f"query {index}")
        for index in range(120)
    ]
    first = freeze_benchmark_splits(records, seed="fixed-seed")
    second = freeze_benchmark_splits(list(reversed(records)), seed="fixed-seed")

    assert {row["query_id"]: row["split"] for row in first} == {
        row["query_id"]: row["split"] for row in second
    }
    assert {row["split"] for row in first} == {"diagnostic", "dev", "test"}
    assert all(record["split"] is None for record in records)


def test_shadow_pool_merges_four_sources_and_deduplicates_candidates():
    first_id = str(uuid4())
    second_id = str(uuid4())
    responses = {
        "v1": _shadow_response("v1", [_search_result(first_id, "A")]),
        "v2": _shadow_response(
            "v2",
            [_search_result(first_id, "A", branch=True), _search_result(second_id, "B")],
        ),
        "lexical": _shadow_response("lexical", [_search_result(second_id, "B")]),
        "dense": _shadow_response("dense", [_search_result(first_id, "A")]),
    }

    calls = []

    def fake_search(_query, **kwargs):
        calls.append(kwargs)
        if kwargs["search_version"] == "v2":
            return responses["v2"]
        if kwargs["strategy"] == "keyword":
            return responses["lexical"]
        if kwargs["strategy"] == "vector":
            return responses["dense"]
        return responses["v1"]

    version = SimpleNamespace(
        id=uuid4(),
        uid="semantic-test",
        status="active",
        config_snapshot={"enabled": True},
    )
    record = freeze_benchmark_splits([_benchmark_record()])[0]
    with (
        patch(
            "catalog.services.semantic_search_benchmark.semantic_index_version_runtime",
            return_value={"enabled": True},
        ),
        patch(
            "catalog.services.semantic_search_benchmark.semantic_search",
            side_effect=fake_search,
        ),
        patch(
            "catalog.services.semantic_search_benchmark._chunk_document_map",
            return_value={first_id: "doc-a", second_id: "doc-b"},
        ),
    ):
        first = run_shadow_query_pool(record, version, blind_seed="blind")
        second = run_shadow_query_pool(record, version, blind_seed="blind")

    assert first["candidate_count"] == 2
    assert [row["candidate_id"] for row in first["candidates"]] == [
        row["candidate_id"] for row in second["candidates"]
    ]
    candidate_a = next(row for row in first["candidates"] if row["candidate_id"] == "doc-a")
    assert set(candidate_a["source_hits"]) == {"v1", "v2", "dense"}
    assert candidate_a["source_hits"]["v2"]["sparse_branch_provenance"][0][
        "branch_type"
    ] == "verified_translation"
    assert first["parameter_set_id"] == "baseline_v2a"
    assert any(
        call.get("search_version") == "v2"
        and call.get("v2_final_top_k_override") == 20
        for call in calls
    )


def test_shadow_pool_refuses_index_without_frozen_runtime_snapshot():
    version = SimpleNamespace(
        id=uuid4(),
        uid="semantic-without-runtime",
        status="active",
        config_snapshot={},
    )

    with pytest.raises(RuntimeError, match="config_snapshot"):
        run_shadow_query_pool(_benchmark_record(split="dev"), version)


def test_annotation_package_is_blind_by_default_and_never_prefills_grade(tmp_path):
    records = freeze_benchmark_splits([_benchmark_record()])
    pool = {
        **records[0],
        "parameter_set_id": "baseline_v2a",
        "config_hash": "abc",
        "systems": {},
        "candidates": [
            {
                "candidate_id": "doc-a",
                "chunk_document_id": "doc-a",
                "search_result_id": str(uuid4()),
                "work_id": "work-a",
                "work_title": "A",
                "authors": ["Author"],
                "page": 12,
                "page_end": 12,
                "original_passage": "人工需要核对的原文。",
                "reader_url": "/reader/a",
                "annotation_order": 1,
                "source_hits": {"v2": {"rank": 1}},
            }
        ],
    }

    manifest = write_annotation_package(
        records,
        [pool],
        tmp_path,
        split_seed="split",
        blind_seed="blind",
    )

    blind_text = (tmp_path / "annotation.jsonl").read_text(encoding="utf-8")
    diagnostic_text = (tmp_path / "diagnostic-pool.jsonl").read_text(encoding="utf-8")
    qrels = read_jsonl(tmp_path / "qrels.template.jsonl")
    page = (tmp_path / "annotation.html").read_text(encoding="utf-8")
    assert "source_hits" not in blind_text
    assert "source_hits" in diagnostic_text
    assert qrels[0]["relevance_grade"] is None
    assert "type=\"radio\"" in page
    radio_inputs = re.findall(r"<input[^>]+type=\"radio\"[^>]*>", page)
    assert radio_inputs
    assert all("checked=" not in item for item in radio_inputs)
    assert "<details>" in page
    assert manifest["annotation_page_blind_by_default"] is True
    assert manifest["automatic_relevance_grades"] is False
    assert manifest["baseline_v2a"]["parameter_set_id"] == "baseline_v2a"
    assert manifest["semantic_index_versions"] == []


def test_group_metrics_include_direction_query_type_and_performance():
    records = validate_benchmark_records(
        [
            _benchmark_record(
                split="dev",
                gold_judgments=[
                    {
                        "work_id": "work-a",
                        "chunk_document_id": "doc-a",
                        "page": 12,
                        "relevance_grade": 3,
                        "reviewer_note": "人工确认。",
                    },
                    {
                        "work_id": "work-b",
                        "chunk_document_id": "doc-b",
                        "page": 14,
                        "relevance_grade": 1,
                        "reviewer_note": "困难负样本。",
                    },
                ],
            )
        ]
    )
    candidates = [
        {
            "candidate_id": "doc-b",
            "chunk_document_id": "doc-b",
            "source_hits": {source: {"rank": 1} for source in ("v1", "lexical")},
        },
        {
            "candidate_id": "doc-a",
            "chunk_document_id": "doc-a",
            "source_hits": {
                "v1": {"rank": 2},
                "v2": {"rank": 1},
                "lexical": {"rank": 2},
                "dense": {"rank": 1},
            },
        },
    ]
    systems = {
        source: {
            "timing_ms": 20,
            "stage_timings_ms": {
                "query_lexicon_ms": 1,
                "sparse_retrieval_ms": 2,
                "dense_retrieval_ms": 3,
                "rrf_ms": 4,
                "rerank_ms": 5,
            }
            if source == "v2"
            else {},
            "candidate_counts": {"fusion_candidate_count": 2},
            "expansion_branch_count": 1 if source == "v2" else 0,
        }
        for source in ("v1", "v2", "lexical", "dense")
    }
    result = score_shadow_pool(
        records,
        [
            {
                **records[0],
                "candidates": candidates,
                "systems": systems,
            }
        ],
    )

    assert result["judged_query_count"] == 1
    assert result["systems"]["v2"]["overall"]["recall_at_5"] == 1.0
    assert result["systems"]["v2"]["overall"]["mrr"] == 1.0
    assert result["systems"]["v1"]["overall"]["mrr"] == 0.5
    assert result["systems"]["v2"]["by_direction"]["en_to_zh"][
        "query_count"
    ] == 1
    assert result["systems"]["v2"]["by_query_type"]["exact_theory"][
        "query_count"
    ] == 1
    assert result["systems"]["v2"]["overall"]["resolver_latency_ms"] == 1.0
    assert result["systems"]["v2"]["overall"]["p99_latency_ms"] is None


def test_ndcg_uses_all_four_human_relevance_grades():
    weak_then_core = _score_ranking(
        {"weak": 1, "core": 3},
        ["weak", "core"],
    )
    irrelevant_then_core = _score_ranking(
        {"weak": 0, "core": 3},
        ["weak", "core"],
    )

    assert weak_then_core["ndcg_at_10"] > irrelevant_then_core["ndcg_at_10"]


def test_scoring_refuses_unjudged_pooled_candidates():
    records = validate_benchmark_records(
        [
            _benchmark_record(
                split="dev",
                gold_judgments=[
                    {
                        "work_id": "work-a",
                        "chunk_document_id": "doc-a",
                        "page": 12,
                        "relevance_grade": 3,
                        "reviewer_note": "人工确认。",
                    }
                ],
            )
        ]
    )
    systems = {source: {} for source in ("v1", "v2", "lexical", "dense")}
    pools = [
        {
            **records[0],
            "systems": systems,
            "candidates": [
                {
                    "candidate_id": "doc-a",
                    "chunk_document_id": "doc-a",
                },
                {
                    "candidate_id": "doc-unjudged",
                    "chunk_document_id": "doc-unjudged",
                },
            ],
        }
    ]

    with pytest.raises(BenchmarkDataError, match="尚未人工评分"):
        score_shadow_pool(records, pools)


def test_human_judgments_merge_requires_explicit_reviewer_grade():
    records = validate_benchmark_records([_benchmark_record()])
    merged = apply_human_judgments(
        records,
        [
            {
                "query_id": "q-001",
                "work_id": "work-a",
                "chunk_document_id": "doc-a",
                "page": 12,
                "relevance_grade": 3,
                "reviewer_note": "人工核对 PDF。",
            },
            {
                "query_id": "q-001",
                "work_id": "work-b",
                "chunk_document_id": "doc-b",
                "page": None,
                "relevance_grade": None,
                "reviewer_note": "尚未判断。",
            },
        ],
    )

    assert merged[0]["gold_judgments"] == [
        {
            "work_id": "work-a",
            "chunk_document_id": "doc-a",
            "page": 12,
            "relevance_grade": 3,
            "reviewer_note": "人工核对 PDF。",
        }
    ]


@pytest.mark.parametrize(
    ("term", "false_text", "true_text"),
    [
        ("capital", "capitalization is common", "capital is relational"),
        ("field", "a midfield position", "field theory"),
        ("practice", "malpractice claim", "practice and structure"),
        ("recognition", "misrecognition", "recognition matters"),
        ("structure", "infrastructure policy", "social structure"),
    ],
)
def test_entity_coverage_uses_latin_word_boundaries(term, false_text, true_text):
    assert _normalized_term_occurs(false_text, term) is False
    assert _normalized_term_occurs(true_text, term) is True


def test_entity_coverage_handles_nfkc_case_cjk_compounds_and_short_aliases():
    assert _normalized_term_occurs("ＦＩＥＬＤ theory", "field") is True
    assert _normalized_term_occurs("资本主义的历史", "资本") is True
    understanding = {
        "query_lexicon": {"query_language": "en"},
        "matched_entities": [
            {
                "canonical_entity": {"entity_type": "knowledge_node", "entity_id": "1"},
                "canonical_terms": [
                    {"term": "x", "language": "en"},
                    {"term": "field", "language": "en"},
                ],
                "verified_translations": [],
                "verified_aliases": [],
                "ambiguity": {"expansion_suppressed": False},
            }
        ],
    }
    context = _entity_coverage_context(understanding)
    assert [term["normalized_term"] for term in context[0]["terms"]] == ["field"]
    features = _coverage_features(
        SimpleNamespace(original_text="midfield only", normalized_text=""),
        ["field"],
        context,
    )
    assert features["literal_coverage"] == 0
    assert features["entity_coverage"] == 0


def test_explicit_and_intent_rewrites_are_deterministic_and_independently_disableable():
    intent_disabled = analyze_query(
        "农业组织化的出路是什么？",
        expansion_limit=3,
        explicit_rewrite="农业合作组织",
        disabled_branch_types={"intent_rewrite"},
    )
    explicit_disabled = analyze_query(
        "农业组织化的出路是什么？",
        expansion_limit=3,
        explicit_rewrite="农业合作组织",
        disabled_branch_types={"explicit_rewrite"},
    )

    assert any(
        branch["branch_type"] == "explicit_rewrite"
        for branch in intent_disabled["expansion_branches"]
    )
    assert all(
        branch["branch_type"] != "intent_rewrite"
        for branch in intent_disabled["expansion_branches"]
    )
    assert all(
        branch["branch_type"] != "explicit_rewrite"
        for branch in explicit_disabled["expansion_branches"]
    )
    assert any(
        branch["branch_type"] == "intent_rewrite"
        for branch in explicit_disabled["expansion_branches"]
    )


def test_baseline_v2a_config_id_and_hash_are_stable():
    first = search_v2_config_snapshot()
    second = search_v2_config_snapshot()

    assert first == second
    assert first["parameter_set_id"] == "baseline_v2a"
    assert len(first["config_hash"]) == 64
    assert first["branch_controls"]["uses_llm_rewrite"] is False


def test_historical_language_audit_executes_detector_against_saved_chunks(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    work = Work.objects.create(
        document_type=DocumentType.BOOK,
        title="Language Audit",
        language="zh-CN",
    )
    edition = Edition.objects.create(
        work=work,
        state=PublicationState.PUBLISHED,
        is_primary=True,
        public_slug="language-audit",
    )
    asset = Asset.objects.create(
        edition=edition,
        kind=Asset.Kind.NORMALIZED,
        file=SimpleUploadedFile("language.pdf", b"%PDF-1.4\n%%EOF"),
        sha256="a" * 64,
        status=Asset.Status.READY,
        is_current=True,
    )
    text = "This passage is written entirely in English and contains enough text."
    SemanticChunk.objects.create(
        asset=asset,
        work=work,
        order=0,
        page_start=1,
        page_end=1,
        original_text=text,
        normalized_text=text.casefold(),
        language="zh-CN",
        document_type=DocumentType.BOOK,
        parser_version="test",
        chunk_version="test",
        document_id=sha256(b"language-audit").hexdigest(),
        content_hash=sha256(text.encode()).hexdigest(),
    )

    result = audit_historical_chunk_languages()

    assert result["total_chunks"] == 1
    assert result["stored_language_family_counts"]["zh"] == 1
    assert result["detected_language_counts"]["en"] == 1
    assert result["family_mismatch_count"] == 1
    assert result["special_cases"]["work_zh_detector_en"] == 1


def test_query_lexicon_bilingual_coverage_audit_reads_active_generation():
    person = Person.objects.create(
        preferred_name="Pierre Bourdieu",
        authority_status=Person.AuthorityStatus.VERIFIED,
    )
    PersonNameVariant.objects.create(
        person=person,
        name="布迪厄",
        language="zh-CN",
        variant_type=PersonNameVariant.VariantType.TRANSLATION,
        source_kind=PersonNameVariant.SourceKind.EDITORIAL,
        displayable=True,
        is_verified=True,
    )
    cache.clear()
    rebuild_query_lexicon()

    result = audit_query_lexicon_coverage()

    assert result["available"] is True
    assert result["entity_counts"]["person"] == 1
    assert result["term_counts"]["verified_translation"] >= 1
    assert result["bilingual_coverage"]["entities_with_zh_and_en"] >= 1


def test_metadata_refresh_audit_does_not_claim_embedding_preservation():
    result = metadata_refresh_assessment()

    assert result["classification"] == "B"
    assert result["safe_meilisearch_metadata_only_refresh_implemented"] is False
    assert result["embedding_preservation_guaranteed"] is False
    assert result["production_refresh_allowed_by_this_task"] is False


def test_prepare_command_dry_run_validates_template_without_search(capsys):
    call_command(
        "prepare_semantic_search_benchmark",
        dataset=str(TEMPLATE_PATH),
        dry_run=True,
    )
    output = json.loads(capsys.readouterr().out)

    assert output["dataset"]["query_count"] == 10
    assert output["dataset"]["usable_query_count"] == 0
    assert output["automatic_relevance_grades"] is False
    assert output["baseline_v2a"]["parameter_set_id"] == "baseline_v2a"


def test_score_command_defaults_to_dev_and_requires_explicit_test(tmp_path, capsys):
    records = validate_benchmark_records(
        [
            _benchmark_record(
                query_id=f"q-{split}",
                query=f"query {split}",
                split=split,
                gold_judgments=[
                    {
                        "work_id": f"work-{split}",
                        "chunk_document_id": f"doc-{split}",
                        "page": 1,
                        "relevance_grade": 3,
                        "reviewer_note": "人工确认。",
                    }
                ],
            )
            for split in ("dev", "test")
        ]
    )
    systems = {
        source: {
            "timing_ms": 1,
            "stage_timings_ms": {},
            "candidate_counts": {},
            "expansion_branch_count": 0,
        }
        for source in ("v1", "v2", "lexical", "dense")
    }
    pools = [
        {
            **record,
            "systems": systems,
            "candidates": [
                {
                    "candidate_id": f"doc-{record['split']}",
                    "chunk_document_id": f"doc-{record['split']}",
                    "source_hits": {
                        source: {"rank": 1}
                        for source in ("v1", "v2", "lexical", "dense")
                    },
                }
            ],
        }
        for record in records
    ]
    dataset_path = tmp_path / "dataset.jsonl"
    pool_path = tmp_path / "pool.jsonl"
    dataset_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )
    pool_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in pools),
        encoding="utf-8",
    )

    call_command(
        "score_semantic_search_benchmark",
        dataset=str(dataset_path),
        pool=str(pool_path),
    )
    output = json.loads(capsys.readouterr().out)

    assert output["included_splits"] == ["dev"]
    assert output["judged_query_count"] == 1
