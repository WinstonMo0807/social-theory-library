from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy
from hashlib import sha256
import html
import json
import math
from pathlib import Path
from statistics import mean
from typing import Iterable
from uuid import UUID

from django.db import DatabaseError

from catalog.models import (
    QueryLexiconEntry,
    QueryLexiconState,
    SemanticChunk,
    SemanticIndexVersion,
)
from catalog.services.passage_language import (
    detect_passage_language,
    language_detector_config,
)
from catalog.services.semantic_indexing import semantic_index_version_runtime
from catalog.services.semantic_search import semantic_search
from catalog.services.semantic_search_v2_config import search_v2_config_snapshot


BENCHMARK_SCHEMA_VERSION = "stl-task2b0-cross-language-benchmark-v1"
ANNOTATION_PACKAGE_VERSION = "stl-task2b0-annotation-package-v1"
DEFAULT_SPLIT_SEED = "stl-task2b0-split-v1"
DEFAULT_BLIND_SEED = "stl-task2b0-blind-v1"
POOL_SOURCE_NAMES = ("v1", "v2", "lexical", "dense")
DIRECTIONS = frozenset(
    {"zh_to_zh", "zh_to_en", "en_to_zh", "en_to_en", "mixed"}
)
QUERY_LANGUAGES = frozenset({"zh", "en", "mixed"})
QUERY_TYPES = frozenset(
    {
        "exact_scholar",
        "scholar_alias",
        "exact_theory",
        "theory_alias",
        "conceptual",
        "comparison",
        "mechanism",
        "quoted_phrase",
        "ambiguous_term",
        "mixed_language",
    }
)
SPLITS = frozenset({"diagnostic", "dev", "test"})
RELEVANT_THRESHOLD = 2
MAX_DATASET_QUERIES = 1000
MAX_POOL_TOP_K = 20


class BenchmarkDataError(ValueError):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors[:10]))


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def read_jsonl(path: str | Path) -> list[dict]:
    source = Path(path)
    records: list[dict] = []
    errors: list[str] = []
    with source.open("r", encoding="utf-8-sig") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"第 {line_number} 行不是有效 JSON：{exc.msg}")
                continue
            if not isinstance(value, dict):
                errors.append(f"第 {line_number} 行必须是 JSON object。")
                continue
            records.append(value)
    if errors:
        raise BenchmarkDataError(errors)
    return records


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )


def _direction_matches_language(direction: str, language: str) -> bool:
    if direction == "mixed":
        return language == "mixed"
    if direction.startswith("zh_"):
        return language == "zh"
    if direction.startswith("en_"):
        return language == "en"
    return False


def validate_benchmark_records(records: list[dict]) -> list[dict]:
    errors: list[str] = []
    normalized: list[dict] = []
    seen_query_ids: set[str] = set()
    if len(records) > MAX_DATASET_QUERIES:
        errors.append(f"数据集最多支持 {MAX_DATASET_QUERIES} 条 query。")

    allowed_keys = {
        "query_id",
        "query",
        "query_language",
        "direction",
        "query_type",
        "expected_entities",
        "gold_judgments",
        "notes",
        "split",
        "filters",
    }
    for index, source in enumerate(records, start=1):
        prefix = f"第 {index} 条"
        unknown = sorted(set(source) - allowed_keys)
        if unknown:
            errors.append(f"{prefix}含未知字段：{', '.join(unknown)}")
        query_id = str(source.get("query_id") or "").strip()
        query = str(source.get("query") or "").strip()
        language = str(source.get("query_language") or "").strip()
        direction = str(source.get("direction") or "").strip()
        query_type = str(source.get("query_type") or "").strip()
        notes = str(source.get("notes") or "")
        split = source.get("split")
        filters = source.get("filters") or {}
        expected_entities = source.get("expected_entities")
        judgments = source.get("gold_judgments")

        if not query_id or len(query_id) > 100:
            errors.append(f"{prefix}的 query_id 必须为 1 到 100 个字符。")
        elif any(not (char.isalnum() or char in "._-") for char in query_id):
            errors.append(f"{prefix}的 query_id 只能包含字母、数字、点、下划线和连字符。")
        elif query_id in seen_query_ids:
            errors.append(f"{prefix}的 query_id 重复：{query_id}")
        seen_query_ids.add(query_id)
        if not query or len(query) > 1200:
            errors.append(f"{prefix}的 query 必须为 1 到 1200 个字符。")
        if language not in QUERY_LANGUAGES:
            errors.append(f"{prefix}的 query_language 无效：{language}")
        if direction not in DIRECTIONS:
            errors.append(f"{prefix}的 direction 无效：{direction}")
        elif language in QUERY_LANGUAGES and not _direction_matches_language(
            direction,
            language,
        ):
            errors.append(f"{prefix}的 direction 与 query_language 不一致。")
        if query_type not in QUERY_TYPES:
            errors.append(f"{prefix}的 query_type 无效：{query_type}")
        if split is not None and split not in SPLITS:
            errors.append(f"{prefix}的 split 无效：{split}")
        if not isinstance(filters, dict):
            errors.append(f"{prefix}的 filters 必须是 object。")
            filters = {}

        if not isinstance(expected_entities, list):
            errors.append(f"{prefix}的 expected_entities 必须是 array。")
            expected_entities = []
        normalized_entities = []
        for entity_index, entity in enumerate(expected_entities, start=1):
            if not isinstance(entity, dict):
                errors.append(f"{prefix}的 expected_entities[{entity_index}] 必须是 object。")
                continue
            if set(entity) - {"entity_type", "entity_id", "label", "reviewer_note"}:
                errors.append(f"{prefix}的 expected_entities[{entity_index}] 含未知字段。")
            entity_type = str(entity.get("entity_type") or "").strip()
            entity_id = str(entity.get("entity_id") or "").strip()
            label = str(entity.get("label") or "").strip()
            if not entity_type or not entity_id or not label:
                errors.append(
                    f"{prefix}的 expected_entities[{entity_index}] 缺少 entity_type、entity_id 或 label。"
                )
            normalized_entities.append(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "label": label,
                    "reviewer_note": str(entity.get("reviewer_note") or ""),
                }
            )

        if not isinstance(judgments, list):
            errors.append(f"{prefix}的 gold_judgments 必须是 array。")
            judgments = []
        normalized_judgments = []
        seen_documents: set[str] = set()
        for judgment_index, judgment in enumerate(judgments, start=1):
            if not isinstance(judgment, dict):
                errors.append(f"{prefix}的 gold_judgments[{judgment_index}] 必须是 object。")
                continue
            allowed_judgment = {
                "work_id",
                "chunk_document_id",
                "page",
                "relevance_grade",
                "reviewer_note",
            }
            if set(judgment) - allowed_judgment:
                errors.append(f"{prefix}的 gold_judgments[{judgment_index}] 含未知字段。")
            work_id = str(judgment.get("work_id") or "").strip()
            document_id = str(judgment.get("chunk_document_id") or "").strip()
            page = judgment.get("page")
            grade = judgment.get("relevance_grade")
            if not work_id or not document_id:
                errors.append(
                    f"{prefix}的 gold_judgments[{judgment_index}] 缺少 work_id 或 chunk_document_id。"
                )
            if document_id in seen_documents:
                errors.append(
                    f"{prefix}的 gold_judgments 出现重复 chunk_document_id：{document_id}"
                )
            seen_documents.add(document_id)
            if not isinstance(page, int) or isinstance(page, bool) or page < 0:
                errors.append(f"{prefix}的 gold_judgments[{judgment_index}].page 无效。")
            if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
                errors.append(
                    f"{prefix}的 gold_judgments[{judgment_index}].relevance_grade 无效。"
                )
            normalized_judgments.append(
                {
                    "work_id": work_id,
                    "chunk_document_id": document_id,
                    "page": page,
                    "relevance_grade": grade,
                    "reviewer_note": str(judgment.get("reviewer_note") or ""),
                }
            )

        normalized.append(
            {
                "query_id": query_id,
                "query": query,
                "query_language": language,
                "direction": direction,
                "query_type": query_type,
                "expected_entities": normalized_entities,
                "gold_judgments": normalized_judgments,
                "notes": notes,
                "split": split,
                "filters": filters,
            }
        )
    if errors:
        raise BenchmarkDataError(errors)
    return normalized


def freeze_benchmark_splits(
    records: list[dict],
    *,
    seed: str = DEFAULT_SPLIT_SEED,
) -> list[dict]:
    """Assign stable per-query splits without looking at retrieval outcomes."""

    frozen = deepcopy(records)
    for record in frozen:
        if record.get("split") in SPLITS:
            continue
        digest = sha256(f"{seed}:{record['query_id']}".encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:8], "big") % 10_000
        if bucket < 4_000:
            split = "diagnostic"
        elif bucket < 7_000:
            split = "dev"
        else:
            split = "test"
        record["split"] = split
    return frozen


def dataset_inventory(records: list[dict]) -> dict:
    direction_counts = Counter(record["direction"] for record in records)
    query_type_counts = Counter(record["query_type"] for record in records)
    split_counts = Counter(str(record.get("split") or "unassigned") for record in records)
    judgment_count = sum(len(record["gold_judgments"]) for record in records)
    usable = sum(
        1
        for record in records
        if any(
            judgment["relevance_grade"] >= RELEVANT_THRESHOLD
            for judgment in record["gold_judgments"]
        )
    )
    return {
        "query_count": len(records),
        "usable_query_count": usable,
        "unjudged_or_no_positive_query_count": len(records) - usable,
        "judgment_count": judgment_count,
        "direction_counts": {
            value: direction_counts.get(value, 0) for value in sorted(DIRECTIONS)
        },
        "query_type_counts": {
            value: query_type_counts.get(value, 0) for value in sorted(QUERY_TYPES)
        },
        "split_counts": {
            value: split_counts.get(value, 0)
            for value in ["diagnostic", "dev", "test", "unassigned"]
        },
        "dataset_hash": content_hash(records),
    }


def apply_human_judgments(
    records: list[dict],
    flat_judgments: list[dict],
) -> list[dict]:
    """Merge reviewer-produced qrels without inferring or recommending grades."""

    merged = deepcopy(records)
    by_query_id = {record["query_id"]: record for record in merged}
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, judgment in enumerate(flat_judgments, start=1):
        query_id = str(judgment.get("query_id") or "").strip()
        document_id = str(judgment.get("chunk_document_id") or "").strip()
        work_id = str(judgment.get("work_id") or "").strip()
        grade = judgment.get("relevance_grade")
        page = judgment.get("page")
        if grade is None:
            continue
        if query_id not in by_query_id:
            errors.append(f"第 {index} 条 judgment 的 query_id 不在数据集中：{query_id}")
            continue
        if not document_id or not work_id:
            errors.append(f"第 {index} 条 judgment 缺少 work_id 或 chunk_document_id。")
            continue
        if not isinstance(grade, int) or isinstance(grade, bool) or grade not in {0, 1, 2, 3}:
            errors.append(f"第 {index} 条 judgment 的 relevance_grade 无效。")
            continue
        if not isinstance(page, int) or isinstance(page, bool) or page < 0:
            errors.append(f"第 {index} 条 judgment 的 page 无效。")
            continue
        key = (query_id, document_id)
        if key in seen:
            errors.append(f"重复 judgment：{query_id} / {document_id}")
            continue
        seen.add(key)
        target = by_query_id[query_id]
        target["gold_judgments"] = [
            row
            for row in target["gold_judgments"]
            if row["chunk_document_id"] != document_id
        ]
        target["gold_judgments"].append(
            {
                "work_id": work_id,
                "chunk_document_id": document_id,
                "page": page,
                "relevance_grade": grade,
                "reviewer_note": str(judgment.get("reviewer_note") or ""),
            }
        )
    if errors:
        raise BenchmarkDataError(errors)
    return validate_benchmark_records(merged)


def _language_family(value: object) -> str:
    language = str(value or "").strip().casefold()
    if language.startswith("zh"):
        return "zh"
    if language.startswith("en"):
        return "en"
    if language == "mixed":
        return "mixed"
    return "unknown"


def audit_historical_chunk_languages(*, batch_size: int = 1000) -> dict:
    stored_counts: Counter[str] = Counter()
    stored_family_counts: Counter[str] = Counter()
    detected_counts: Counter[str] = Counter()
    by_work_language: dict[str, dict] = defaultdict(
        lambda: {
            "total": 0,
            "stored": Counter(),
            "stored_family": Counter(),
            "detected": Counter(),
            "exact_mismatch_count": 0,
            "family_mismatch_count": 0,
        }
    )
    exact_mismatch = 0
    family_mismatch = 0
    special = Counter()
    try:
        rows = SemanticChunk.objects.values_list(
            "language",
            "original_text",
            "work__language",
        ).iterator(chunk_size=max(100, int(batch_size)))
        for stored_raw, text, work_language_raw in rows:
            stored = str(stored_raw or "unknown")
            detected = detect_passage_language(text)
            work_language = str(work_language_raw or "unknown")
            stored_counts[stored] += 1
            stored_family_counts[_language_family(stored)] += 1
            detected_counts[detected] += 1
            group = by_work_language[work_language]
            group["total"] += 1
            group["stored"][stored] += 1
            group["stored_family"][_language_family(stored)] += 1
            group["detected"][detected] += 1
            if stored != detected:
                exact_mismatch += 1
                group["exact_mismatch_count"] += 1
            if _language_family(stored) != _language_family(detected):
                family_mismatch += 1
                group["family_mismatch_count"] += 1
            work_family = _language_family(work_language)
            if work_family == "zh" and detected in {"en", "mixed"}:
                special[f"work_zh_detector_{detected}"] += 1
            if work_family == "en" and detected in {"zh", "mixed"}:
                special[f"work_en_detector_{detected}"] += 1
    except DatabaseError as exc:
        return {
            "available": False,
            "reason": exc.__class__.__name__,
            "total_chunks": None,
        }

    total = sum(stored_counts.values())
    return {
        "available": True,
        "detector": language_detector_config(),
        "total_chunks": total,
        "stored_language_counts": dict(sorted(stored_counts.items())),
        "stored_language_family_counts": {
            value: stored_family_counts.get(value, 0)
            for value in ("zh", "en", "mixed", "unknown")
        },
        "detected_language_counts": {
            value: detected_counts.get(value, 0)
            for value in ("zh", "en", "mixed", "unknown")
        },
        "exact_mismatch_count": exact_mismatch,
        "exact_mismatch_ratio": round(exact_mismatch / total, 6) if total else None,
        "family_mismatch_count": family_mismatch,
        "family_mismatch_ratio": round(family_mismatch / total, 6) if total else None,
        "special_cases": {
            value: special.get(value, 0)
            for value in (
                "work_zh_detector_en",
                "work_zh_detector_mixed",
                "work_en_detector_zh",
                "work_en_detector_mixed",
            )
        },
        "by_work_language": {
            language: {
                "total": values["total"],
                "stored": dict(sorted(values["stored"].items())),
                "stored_family": dict(sorted(values["stored_family"].items())),
                "detected": dict(sorted(values["detected"].items())),
                "exact_mismatch_count": values["exact_mismatch_count"],
                "family_mismatch_count": values["family_mismatch_count"],
            }
            for language, values in sorted(by_work_language.items())
        },
    }


def audit_query_lexicon_coverage() -> dict:
    try:
        state = QueryLexiconState.objects.select_related("active_generation").get(
            key="default"
        )
        rows = list(
            QueryLexiconEntry.objects.filter(
                generation_id=state.active_generation_id,
                public_active=True,
            ).values(
                "entity_type",
                "entity_id",
                "term",
                "language",
                "term_type",
                "source_kind",
                "trust_level",
            )
        )
    except (QueryLexiconState.DoesNotExist, DatabaseError) as exc:
        return {
            "available": False,
            "reason": exc.__class__.__name__,
            "scope": "public_active",
        }

    entities_by_type: dict[str, set[str]] = defaultdict(set)
    bilingual_terms: dict[tuple[str, str], set[str]] = defaultdict(set)
    canonical_count = 0
    verified_translation_count = 0
    verified_alias_count = 0
    historical_count = 0
    legacy_count = 0
    generated_count = 0
    verified_trust = {
        QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
        QueryLexiconEntry.TrustLevel.VERIFIED,
    }
    alias_types = {
        QueryLexiconEntry.TermType.ALIAS,
        QueryLexiconEntry.TermType.ABBREVIATION,
        QueryLexiconEntry.TermType.TRANSLITERATION,
    }
    for row in rows:
        entity_key = (row["entity_type"], str(row["entity_id"]))
        entities_by_type[row["entity_type"]].add(str(row["entity_id"]))
        term_type = row["term_type"]
        trust = row["trust_level"]
        source_kind = row["source_kind"]
        if term_type == QueryLexiconEntry.TermType.CANONICAL:
            canonical_count += 1
        if term_type == QueryLexiconEntry.TermType.TRANSLATION and trust in verified_trust:
            verified_translation_count += 1
        if term_type in alias_types and trust in verified_trust:
            verified_alias_count += 1
        if term_type == QueryLexiconEntry.TermType.HISTORICAL:
            historical_count += 1
        if (
            trust == QueryLexiconEntry.TrustLevel.LEGACY
            or source_kind == QueryLexiconEntry.SourceKind.LEGACY_MIXED_ALIAS
        ):
            legacy_count += 1
        if (
            trust == QueryLexiconEntry.TrustLevel.GENERATED
            or source_kind == QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
        ):
            generated_count += 1
        if term_type in {
            QueryLexiconEntry.TermType.CANONICAL,
            QueryLexiconEntry.TermType.TRANSLATION,
        } and trust in verified_trust:
            family = _language_family(row["language"])
            if family == "unknown":
                family = _language_family(detect_passage_language(row["term"]))
            if family in {"zh", "en"}:
                bilingual_terms[entity_key].add(family)

    person_count = len(entities_by_type.get(QueryLexiconEntry.EntityType.PERSON, set()))
    node_count = len(
        entities_by_type.get(QueryLexiconEntry.EntityType.KNOWLEDGE_NODE, set())
    )
    other_count = sum(
        len(values)
        for entity_type, values in entities_by_type.items()
        if entity_type
        not in {
            QueryLexiconEntry.EntityType.PERSON,
            QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        }
    )
    zh_without_en = sum(
        1 for languages in bilingual_terms.values() if languages == {"zh"}
    )
    en_without_zh = sum(
        1 for languages in bilingual_terms.values() if languages == {"en"}
    )
    both = sum(1 for languages in bilingual_terms.values() if languages == {"zh", "en"})
    return {
        "available": True,
        "scope": "public_active",
        "query_lexicon_revision": state.revision,
        "active_generation_id": str(state.active_generation_id),
        "entry_count": len(rows),
        "entity_counts": {
            "person": person_count,
            "knowledge_node": node_count,
            "other": other_count,
            "by_type": {
                entity_type: len(values)
                for entity_type, values in sorted(entities_by_type.items())
            },
        },
        "term_counts": {
            "canonical": canonical_count,
            "verified_translation": verified_translation_count,
            "verified_alias": verified_alias_count,
            "historical": historical_count,
            "legacy": legacy_count,
            "generated": generated_count,
        },
        "bilingual_coverage": {
            "entities_with_zh_and_en": both,
            "entities_with_zh_but_no_en": zh_without_en,
            "entities_with_en_but_no_zh": en_without_zh,
            "entities_with_verified_zh_or_en": len(bilingual_terms),
        },
    }


def metadata_refresh_assessment() -> dict:
    return {
        "classification": "B",
        "summary": "必须更新语义 search document，当前源码不能证明该更新保持既有 embedding 不变。",
        "database_language_recompute_possible": True,
        "safe_meilisearch_metadata_only_refresh_implemented": False,
        "current_update_path": "semantic_documents + index_semantic_asset",
        "current_update_posts_full_documents": True,
        "embedding_preservation_guaranteed": False,
        "production_refresh_allowed_by_this_task": False,
    }


def semantic_search_benchmark_audit() -> dict:
    return {
        "historical_language": audit_historical_chunk_languages(),
        "query_lexicon_coverage": audit_query_lexicon_coverage(),
        "metadata_refresh": metadata_refresh_assessment(),
        "baseline_v2a": search_v2_config_snapshot(),
    }


def _chunk_document_map(search_rows: Iterable[dict]) -> dict[str, str]:
    identifiers = []
    for row in search_rows:
        try:
            identifiers.append(UUID(str(row.get("id") or "")))
        except (TypeError, ValueError, AttributeError):
            continue
    return {
        str(identifier): document_id
        for identifier, document_id in SemanticChunk.objects.filter(
            pk__in=identifiers
        ).values_list("id", "document_id")
    }


def _source_specs() -> tuple[dict, ...]:
    return (
        {
            "name": "v1",
            "search_version": "v1",
            "strategy": "hybrid_rerank",
            "disable_query_rewrite": False,
        },
        {
            "name": "v2",
            "search_version": "v2",
            "search_profile": "precision",
            "strategy": "hybrid_rerank",
            "disable_query_rewrite": False,
        },
        {
            "name": "lexical",
            "search_version": "v1",
            "strategy": "keyword",
            "disable_query_rewrite": True,
        },
        {
            "name": "dense",
            "search_version": "v1",
            "strategy": "vector",
            "disable_query_rewrite": True,
        },
    )


def _index_version_snapshot(index_version: SemanticIndexVersion) -> dict:
    config_snapshot = (
        dict(index_version.config_snapshot)
        if isinstance(index_version.config_snapshot, dict)
        else {}
    )
    return {
        "id": str(index_version.id),
        "uid": index_version.uid,
        "status": index_version.status,
        "provider": str(getattr(index_version, "provider", "") or ""),
        "model_repo_id": str(
            getattr(index_version, "model_repo_id", "") or ""
        ),
        "model_revision": str(
            getattr(index_version, "model_revision", "") or ""
        ),
        "dimensions": getattr(index_version, "dimensions", None),
        "pooling": str(getattr(index_version, "pooling", "") or ""),
        "config_snapshot_hash": content_hash(config_snapshot),
    }


def run_shadow_query_pool(
    record: dict,
    index_version: SemanticIndexVersion,
    *,
    pool_top_k: int = 20,
    blind_seed: str = DEFAULT_BLIND_SEED,
    disabled_v2_branch_types: Iterable[str] | None = None,
) -> dict:
    """Run four independent retrieval views without changing the active index."""

    limit = min(MAX_POOL_TOP_K, max(1, int(pool_top_k)))
    runtime = semantic_index_version_runtime(index_version)
    if not runtime:
        raise RuntimeError(
            "指定 SemanticIndexVersion 没有冻结 runtime config_snapshot，"
            "无法建立可复现的 shadow pool。"
        )
    responses: dict[str, dict] = {}
    all_rows: list[dict] = []
    for spec in _source_specs():
        kwargs = {
            "filters": record.get("filters") or {},
            "limit": limit,
            "max_per_work": 0,
            "debug": True,
            "strategy": spec["strategy"],
            "search_version": spec["search_version"],
            "disable_query_rewrite": spec["disable_query_rewrite"],
            "index_uid": index_version.uid,
            "runtime_config_override": runtime,
        }
        if spec.get("search_profile"):
            kwargs["search_profile"] = spec["search_profile"]
        if spec["name"] == "v2":
            kwargs["disabled_v2_branch_types"] = tuple(
                disabled_v2_branch_types or ()
            )
            kwargs["v2_final_top_k_override"] = limit
        response = semantic_search(record["query"], **kwargs)
        if spec["name"] != "lexical" and response.get("fallback_used"):
            reason = response.get("fallback_reason") or "unknown"
            raise RuntimeError(
                f"{record['query_id']} 的 {spec['name']} retrieval 发生降级：{reason}"
            )
        responses[spec["name"]] = response
        all_rows.extend(response.get("results") or [])

    document_map = _chunk_document_map(all_rows)
    candidates: dict[str, dict] = {}
    systems: dict[str, dict] = {}
    for source_name in POOL_SOURCE_NAMES:
        response = responses[source_name]
        rows = list(response.get("results") or [])[:limit]
        systems[source_name] = {
            "search_version": response.get("search_version"),
            "search_profile": response.get("search_profile"),
            "strategy": response.get("strategy"),
            "index_uid": response.get("index_uid"),
            "result_count": len(rows),
            "timing_ms": response.get("timing_ms"),
            "stage_timings_ms": response.get("stage_timings_ms"),
            "candidate_counts": response.get("candidate_counts"),
            "query_lexicon_revision": response.get("query_lexicon_revision"),
            "expansion_branch_count": len(
                (response.get("expansion_branches") or [])[1:]
            ),
            "disabled_branch_types": response.get("disabled_branch_types") or [],
            "fallback_used": bool(response.get("fallback_used")),
            "fallback_reason": str(response.get("fallback_reason") or ""),
        }
        for rank, row in enumerate(rows, start=1):
            search_result_id = str(row.get("id") or "")
            document_id = document_map.get(search_result_id, "")
            candidate_key = document_id or search_result_id
            if not candidate_key:
                continue
            candidate = candidates.setdefault(
                candidate_key,
                {
                    "candidate_id": candidate_key,
                    "chunk_document_id": document_id,
                    "search_result_id": search_result_id,
                    "work_id": str(row.get("work_id") or ""),
                    "work_title": str(row.get("title") or ""),
                    "authors": list(row.get("authors") or []),
                    "page": row.get("page_start"),
                    "page_end": row.get("page_end"),
                    "original_passage": str(row.get("snippet") or ""),
                    "reader_url": str(row.get("reader_url") or ""),
                    "source_hits": {},
                },
            )
            debug = row.get("debug") if isinstance(row.get("debug"), dict) else {}
            candidate["source_hits"][source_name] = {
                "rank": rank,
                "sparse_branch_provenance": debug.get("sparse_branch_hits") or [],
                "dense_branch_provenance": debug.get("dense_branch_hits") or [],
            }

    ordered = []
    for candidate in candidates.values():
        blind_digest = sha256(
            f"{blind_seed}:{record['query_id']}:{candidate['candidate_id']}".encode(
                "utf-8"
            )
        ).hexdigest()
        candidate["blind_order_key"] = blind_digest
        ordered.append(candidate)
    ordered.sort(key=lambda candidate: candidate["blind_order_key"])
    for annotation_order, candidate in enumerate(ordered, start=1):
        candidate["annotation_order"] = annotation_order

    baseline = search_v2_config_snapshot()
    return {
        "query_id": record["query_id"],
        "query": record["query"],
        "query_language": record["query_language"],
        "direction": record["direction"],
        "query_type": record["query_type"],
        "split": record.get("split"),
        "expected_entities": record.get("expected_entities") or [],
        "notes": record.get("notes") or "",
        "index_version": _index_version_snapshot(index_version),
        "parameter_set_id": baseline["parameter_set_id"],
        "config_hash": baseline["config_hash"],
        "pool_sources": list(POOL_SOURCE_NAMES),
        "pool_top_k": limit,
        "candidate_count": len(ordered),
        "systems": systems,
        "candidates": ordered,
    }


def _blind_annotation_record(pool_record: dict) -> dict:
    return {
        "query_id": pool_record["query_id"],
        "query": pool_record["query"],
        "query_language": pool_record["query_language"],
        "direction": pool_record["direction"],
        "query_type": pool_record["query_type"],
        "split": pool_record.get("split"),
        "expected_entities": pool_record.get("expected_entities") or [],
        "notes": pool_record.get("notes") or "",
        "candidates": [
            {
                key: candidate.get(key)
                for key in (
                    "candidate_id",
                    "chunk_document_id",
                    "search_result_id",
                    "work_id",
                    "work_title",
                    "authors",
                    "page",
                    "page_end",
                    "original_passage",
                    "reader_url",
                    "annotation_order",
                )
            }
            for candidate in pool_record.get("candidates") or []
        ],
    }


def _render_annotation_html(pool_records: list[dict], manifest: dict) -> str:
    sections = []
    for pool_record in pool_records:
        cards = []
        for candidate in pool_record.get("candidates") or []:
            authors = "、".join(str(value) for value in candidate.get("authors") or [])
            diagnostics = html.escape(
                json.dumps(
                    candidate.get("source_hits") or {},
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            identifier = html.escape(str(candidate.get("candidate_id") or ""), quote=True)
            query_id = html.escape(str(pool_record["query_id"]), quote=True)
            work_id = html.escape(str(candidate.get("work_id") or ""), quote=True)
            page = candidate.get("page")
            cards.append(
                f"""
                <article class="candidate-card" data-query-id="{query_id}"
                  data-candidate-id="{identifier}" data-work-id="{work_id}"
                  data-page="{html.escape(str(page if page is not None else ''))}">
                  <h3>候选 {candidate.get('annotation_order')}</h3>
                  <p class="meta"><strong>{html.escape(str(candidate.get('work_title') or ''))}</strong>
                    · {html.escape(authors)} · 文件页 {html.escape(str(page if page is not None else '待核对'))}</p>
                  <p class="identifier">{identifier}</p>
                  <blockquote>{html.escape(str(candidate.get('original_passage') or ''))}</blockquote>
                  <fieldset>
                    <legend>人工 relevance grade</legend>
                    {''.join(f'<label><input type="radio" name="grade-{query_id}-{identifier}" value="{grade}"> {grade}</label>' for grade in range(4))}
                  </fieldset>
                  <label>Reviewer note<textarea class="reviewer-note"></textarea></label>
                  <details><summary>显示检索来源与 branch provenance</summary><pre>{diagnostics}</pre></details>
                </article>
                """
            )
        sections.append(
            f"""
            <section class="query-block">
              <h2>{html.escape(str(pool_record['query_id']))} · {html.escape(str(pool_record['query']))}</h2>
              <p>{html.escape(str(pool_record['direction']))} · {html.escape(str(pool_record['query_type']))} · split={html.escape(str(pool_record.get('split') or ''))}</p>
              {''.join(cards) if cards else '<p>没有可标注候选。请检查四路 retrieval 是否完整。</p>'}
            </section>
            """
        )
    manifest_json = html.escape(json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Social Theory Library 观点检索人工标注</title>
  <style>
    body {{ margin: 0 auto; max-width: 1080px; padding: 28px; color: #171717; background: #f5f2ec; font-family: system-ui, sans-serif; }}
    .notice, .query-block, .candidate-card {{ background: #fff; border: 1px solid #d8d1c7; border-radius: 8px; padding: 18px; margin: 16px 0; }}
    .candidate-card {{ background: #fbfaf7; }}
    blockquote {{ white-space: pre-wrap; line-height: 1.7; border-left: 3px solid #222; margin-left: 0; padding-left: 16px; }}
    fieldset label {{ margin-right: 18px; }}
    textarea {{ display: block; width: 100%; min-height: 72px; margin-top: 6px; }}
    .meta, .identifier {{ color: #5f5a53; }}
    pre {{ white-space: pre-wrap; word-break: break-word; }}
    button {{ padding: 10px 16px; background: #171717; color: white; border: 0; border-radius: 6px; cursor: pointer; }}
  </style>
</head>
<body data-manifest="{manifest_json}">
  <h1>跨语言观点检索人工标注</h1>
  <div class="notice">
    <p>候选顺序已经按固定 seed 盲化。页面默认隐藏检索系统、rank 与 branch provenance。</p>
    <p>没有预选 grade，也没有推荐答案。0 为不相关，1 为相关但不回答，2 为有用证据，3 为直接回答。</p>
    <button type="button" onclick="downloadJudgments()">下载当前 judgments JSONL</button>
  </div>
  {''.join(sections)}
  <script>
    function downloadJudgments() {{
      const rows = [];
      document.querySelectorAll('.candidate-card').forEach((card) => {{
        const checked = card.querySelector('input[type=radio]:checked');
        rows.push({{
          query_id: card.dataset.queryId,
          work_id: card.dataset.workId,
          chunk_document_id: card.dataset.candidateId,
          page: card.dataset.page === '' ? null : Number(card.dataset.page),
          relevance_grade: checked ? Number(checked.value) : null,
          reviewer_note: card.querySelector('.reviewer-note').value,
        }});
      }});
      const text = rows.map((row) => JSON.stringify(row)).join('\n') + '\n';
      const blob = new Blob([text], {{type: 'application/x-ndjson;charset=utf-8'}});
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'semantic-search-human-judgments.jsonl';
      link.click();
      URL.revokeObjectURL(link.href);
    }}
  </script>
</body>
</html>
"""


def write_annotation_package(
    records: list[dict],
    pool_records: list[dict],
    output_dir: str | Path,
    *,
    split_seed: str,
    blind_seed: str,
) -> dict:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    inventory = dataset_inventory(records)
    judgment_templates = []
    for pool_record in pool_records:
        for candidate in pool_record.get("candidates") or []:
            judgment_templates.append(
                {
                    "query_id": pool_record["query_id"],
                    "work_id": candidate.get("work_id") or "",
                    "chunk_document_id": candidate.get("chunk_document_id")
                    or candidate.get("candidate_id")
                    or "",
                    "page": candidate.get("page"),
                    "relevance_grade": None,
                    "reviewer_note": "",
                }
            )
    baseline = search_v2_config_snapshot()
    index_versions = {
        _canonical_json(pool_record.get("index_version") or {}): (
            pool_record.get("index_version") or {}
        )
        for pool_record in pool_records
        if pool_record.get("index_version")
    }
    query_lexicon_revisions = sorted(
        {
            value
            for pool_record in pool_records
            for value in [
                ((pool_record.get("systems") or {}).get("v2") or {}).get(
                    "query_lexicon_revision"
                )
            ]
            if value is not None
        }
    )
    disabled_v2_branch_types = sorted(
        {
            branch_type
            for pool_record in pool_records
            for branch_type in (
                ((pool_record.get("systems") or {}).get("v2") or {}).get(
                    "disabled_branch_types"
                )
                or []
            )
        }
    )
    manifest = {
        "package_version": ANNOTATION_PACKAGE_VERSION,
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "dataset": inventory,
        "split_seed": split_seed,
        "blind_seed": blind_seed,
        "pool_sources": list(POOL_SOURCE_NAMES),
        "pool_top_k_values": sorted(
            {
                int(pool_record.get("pool_top_k") or 0)
                for pool_record in pool_records
            }
        ),
        "semantic_index_versions": [
            index_versions[key] for key in sorted(index_versions)
        ],
        "query_lexicon_revisions": query_lexicon_revisions,
        "disabled_v2_branch_types": disabled_v2_branch_types,
        "query_count": len(pool_records),
        "candidate_judgment_count": len(judgment_templates),
        "gold_generation": "human_only",
        "automatic_relevance_grades": False,
        "annotation_page_blind_by_default": True,
        "parameter_set_id": baseline["parameter_set_id"],
        "config_hash": baseline["config_hash"],
        "baseline_v2a": baseline,
    }
    _write_jsonl(output / "dataset.frozen.jsonl", records)
    _write_jsonl(output / "diagnostic-pool.jsonl", pool_records)
    _write_jsonl(
        output / "annotation.jsonl",
        (_blind_annotation_record(record) for record in pool_records),
    )
    _write_jsonl(output / "qrels.template.jsonl", judgment_templates)
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "annotation.html").write_text(
        _render_annotation_html(pool_records, manifest),
        encoding="utf-8",
    )
    return manifest


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return round(ordered[rank - 1], 6)


def _score_ranking(judgments: dict[str, int], retrieved: list[str]) -> dict:
    relevant = {
        document_id
        for document_id, grade in judgments.items()
        if grade >= RELEVANT_THRESHOLD
    }

    def recall_at(limit: int) -> float:
        return (
            len(relevant.intersection(retrieved[:limit])) / len(relevant)
            if relevant
            else 0.0
        )

    precision_at_5 = sum(
        1
        for document_id in retrieved[:5]
        if judgments.get(document_id, 0) >= RELEVANT_THRESHOLD
    ) / 5
    reciprocal_rank = 0.0
    for rank, document_id in enumerate(retrieved, start=1):
        if judgments.get(document_id, 0) >= RELEVANT_THRESHOLD:
            reciprocal_rank = 1 / rank
            break

    def gain(grade: int) -> int:
        # Recall, precision and MRR use the useful-evidence threshold of 2.
        # nDCG remains genuinely graded, so grade 1 contributes weak relevance.
        return (2**grade) - 1

    dcg = sum(
        gain(judgments.get(document_id, 0)) / math.log2(rank + 1)
        for rank, document_id in enumerate(retrieved[:10], start=1)
    )
    ideal_grades = sorted(judgments.values(), reverse=True)[:10]
    ideal_dcg = sum(
        gain(grade) / math.log2(rank + 1)
        for rank, grade in enumerate(ideal_grades, start=1)
    )
    return {
        "recall_at_5": recall_at(5),
        "recall_at_20": recall_at(20),
        "precision_at_5": precision_at_5,
        "mrr": reciprocal_rank,
        "ndcg_at_10": dcg / ideal_dcg if ideal_dcg else 0.0,
    }


def _aggregate_metrics(rows: list[dict]) -> dict:
    metric_names = (
        "recall_at_5",
        "recall_at_20",
        "precision_at_5",
        "mrr",
        "ndcg_at_10",
    )
    output = {
        "query_count": len(rows),
        **{
            metric: round(mean(row[metric] for row in rows), 6) if rows else None
            for metric in metric_names
        },
    }
    latencies = [
        float(row["timing_ms"])
        for row in rows
        if isinstance(row.get("timing_ms"), (int, float))
    ]
    output.update(
        {
            "p50_latency_ms": _percentile(latencies, 0.50),
            "p95_latency_ms": _percentile(latencies, 0.95),
            "p99_latency_ms": _percentile(latencies, 0.99)
            if len(latencies) >= 20
            else None,
        }
    )
    stage_mapping = {
        "resolver_latency_ms": "query_lexicon_ms",
        "sparse_latency_ms": "sparse_retrieval_ms",
        "dense_latency_ms": "dense_retrieval_ms",
        "fusion_latency_ms": "rrf_ms",
        "rerank_latency_ms": "rerank_ms",
    }
    for output_name, stage_name in stage_mapping.items():
        values = [
            float(row["stage_timings_ms"][stage_name])
            for row in rows
            if isinstance(row.get("stage_timings_ms"), dict)
            and isinstance(row["stage_timings_ms"].get(stage_name), (int, float))
        ]
        output[output_name] = round(mean(values), 6) if values else None
        output[f"p50_{output_name}"] = _percentile(values, 0.50)
        output[f"p95_{output_name}"] = _percentile(values, 0.95)
        output[f"p99_{output_name}"] = (
            _percentile(values, 0.99) if len(values) >= 20 else None
        )
    branch_counts = [
        int(row["branch_count"])
        for row in rows
        if isinstance(row.get("branch_count"), int)
    ]
    candidate_counts = [
        int(row["candidate_count"])
        for row in rows
        if isinstance(row.get("candidate_count"), int)
    ]
    output["mean_branch_count"] = (
        round(mean(branch_counts), 6) if branch_counts else None
    )
    output["mean_candidate_count"] = (
        round(mean(candidate_counts), 6) if candidate_counts else None
    )
    output["p50_branch_count"] = _percentile(branch_counts, 0.50)
    output["p95_branch_count"] = _percentile(branch_counts, 0.95)
    output["p50_candidate_count"] = _percentile(candidate_counts, 0.50)
    output["p95_candidate_count"] = _percentile(candidate_counts, 0.95)
    return output


def _validate_scoring_pool(records: list[dict], pool_records: list[dict]) -> None:
    errors: list[str] = []
    record_by_query_id = {record["query_id"]: record for record in records}
    pool_by_query_id: dict[str, dict] = {}
    for pool_record in pool_records:
        query_id = str(pool_record.get("query_id") or "")
        if query_id in pool_by_query_id:
            errors.append(f"shadow pool 出现重复 query_id：{query_id}")
            continue
        pool_by_query_id[query_id] = pool_record
        record = record_by_query_id.get(query_id)
        if record is None:
            errors.append(f"shadow pool 的 query_id 不在数据集中：{query_id}")
            continue
        for field in ("query", "direction", "query_type", "split"):
            if pool_record.get(field) != record.get(field):
                errors.append(f"{query_id} 的 {field} 与冻结数据集不一致。")
        missing_systems = sorted(
            set(POOL_SOURCE_NAMES) - set(pool_record.get("systems") or {})
        )
        if missing_systems:
            errors.append(
                f"{query_id} 缺少 retrieval system：{', '.join(missing_systems)}"
            )

    for record in records:
        query_id = record["query_id"]
        pool_record = pool_by_query_id.get(query_id)
        if pool_record is None:
            errors.append(f"冻结数据集缺少 shadow pool：{query_id}")
            continue
        judgments = {
            judgment["chunk_document_id"]: judgment
            for judgment in record["gold_judgments"]
        }
        if not any(
            judgment["relevance_grade"] >= RELEVANT_THRESHOLD
            for judgment in judgments.values()
        ):
            errors.append(f"{query_id} 没有 2 或 3 级人工 judgment。")
        candidate_ids: set[str] = set()
        for candidate in pool_record.get("candidates") or []:
            document_id = str(
                candidate.get("chunk_document_id")
                or candidate.get("candidate_id")
                or ""
            )
            if not document_id:
                errors.append(f"{query_id} 的 candidate 缺少稳定 document id。")
                continue
            if document_id in candidate_ids:
                errors.append(f"{query_id} 的 candidate 重复：{document_id}")
            candidate_ids.add(document_id)
            if document_id not in judgments:
                errors.append(f"{query_id} 的 pooled candidate 尚未人工评分：{document_id}")
    if errors:
        raise BenchmarkDataError(errors)


def score_shadow_pool(records: list[dict], pool_records: list[dict]) -> dict:
    _validate_scoring_pool(records, pool_records)
    by_query_id = {record["query_id"]: record for record in records}
    pool_by_query_id = {record["query_id"]: record for record in pool_records}
    rows_by_system: dict[str, list[dict]] = defaultdict(list)
    for query_id, record in by_query_id.items():
        judgments = {
            judgment["chunk_document_id"]: int(judgment["relevance_grade"])
            for judgment in record["gold_judgments"]
        }
        if not any(grade >= RELEVANT_THRESHOLD for grade in judgments.values()):
            continue
        pool_record = pool_by_query_id.get(query_id)
        if pool_record is None:
            continue
        for source_name in POOL_SOURCE_NAMES:
            ranked = sorted(
                (
                    candidate
                    for candidate in pool_record.get("candidates") or []
                    if source_name in (candidate.get("source_hits") or {})
                ),
                key=lambda candidate: candidate["source_hits"][source_name]["rank"],
            )
            retrieved = [
                candidate.get("chunk_document_id")
                or candidate.get("candidate_id")
                or ""
                for candidate in ranked
            ]
            scores = _score_ranking(judgments, retrieved)
            system = (pool_record.get("systems") or {}).get(source_name) or {}
            counts = system.get("candidate_counts") or {}
            rows_by_system[source_name].append(
                {
                    **scores,
                    "query_id": query_id,
                    "direction": record["direction"],
                    "query_type": record["query_type"],
                    "split": record.get("split"),
                    "timing_ms": system.get("timing_ms"),
                    "stage_timings_ms": system.get("stage_timings_ms") or {},
                    "branch_count": system.get("expansion_branch_count"),
                    "candidate_count": counts.get("fusion_candidate_count")
                    if isinstance(counts, dict)
                    else None,
                }
            )

    systems = {}
    for source_name in POOL_SOURCE_NAMES:
        rows = rows_by_system.get(source_name, [])

        def grouped(field: str, values: Iterable[str]) -> dict:
            return {
                value: _aggregate_metrics(
                    [row for row in rows if row.get(field) == value]
                )
                for value in values
            }

        systems[source_name] = {
            "overall": _aggregate_metrics(rows),
            "by_direction": grouped("direction", sorted(DIRECTIONS)),
            "by_query_type": grouped("query_type", sorted(QUERY_TYPES)),
            "by_split": grouped("split", ["diagnostic", "dev", "test"]),
        }
    baseline = search_v2_config_snapshot()
    return {
        "benchmark_schema_version": BENCHMARK_SCHEMA_VERSION,
        "parameter_set_id": baseline["parameter_set_id"],
        "config_hash": baseline["config_hash"],
        "dataset_hash": content_hash(records),
        "judged_query_count": max(
            (len(rows) for rows in rows_by_system.values()),
            default=0,
        ),
        "systems": systems,
    }
