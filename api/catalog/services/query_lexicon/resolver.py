from __future__ import annotations

from collections import defaultdict

from django.conf import settings

from catalog.models import QueryLexiconEntry, QueryLexiconState
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.registry import EntityKey, describe_entity
from catalog.services.query_lexicon.sync import (
    QueryLexiconInvariantError,
    _validate_state,
)


PUBLIC_ACTIVE = "public_active"
ADMIN_RESOLVABLE = "admin_resolvable"
RESOLVER_SCOPES = {PUBLIC_ACTIVE, ADMIN_RESOLVABLE}


def _match_payload(row, *, scope: str, entity_cache: dict) -> dict | None:
    key = EntityKey(row.entity_type, row.entity_id)
    cache_key = (row.entity_type, str(row.entity_id))
    if cache_key not in entity_cache:
        entity_cache[cache_key] = describe_entity(key)
    entity = entity_cache[cache_key]
    if entity is None:
        return None
    match = {
        "entity": entity,
        "matched_term": row.term,
        "normalized_term": row.normalized_term,
        "term_type": row.term_type,
        "language": row.language,
        "source_kind": row.source_kind,
        "trust_level": row.trust_level,
        "source_ref": row.source_ref,
        "displayable": row.displayable,
    }
    if scope == ADMIN_RESOLVABLE:
        match["provenance"] = row.provenance
    return match


def resolve_terms(
    terms,
    *,
    entity_types: list[str] | tuple[str, ...] | None = None,
    scope: str = PUBLIC_ACTIVE,
    expected_revision: int | None = None,
    max_results_per_term: int | None = None,
    include_scope_diagnostics: bool = False,
) -> dict:
    """Resolve a bounded set of exact terms under one consistent revision."""

    if scope not in RESOLVER_SCOPES:
        raise ValueError(f"未知 QueryLexicon resolver scope：{scope}")
    selected_types = sorted(set(str(value) for value in (entity_types or [])))
    invalid_types = set(selected_types) - set(QueryLexiconEntry.EntityType.values)
    if invalid_types:
        raise ValueError(f"未知 QueryLexicon entity type：{sorted(invalid_types)[0]}")
    originals: dict[str, str] = {}
    for term in terms:
        normalized = normalize_term(term)
        if normalized and normalized not in originals:
            originals[normalized] = str(term)
        if len(originals) > 5000:
            raise ValueError("一次 QueryLexicon batch resolver 最多处理 5000 个术语。")
    if not originals:
        return {"revision": None, "results": {}}
    limit = max_results_per_term or settings.QUERY_LEXICON_RESOLVER_MAX_RESULTS
    limit = max(1, min(int(limit), 500))

    for _attempt in range(3):
        before = QueryLexiconState.objects.select_related("active_generation").get(
            key="default"
        )
        _validate_state(before)
        if expected_revision is not None and before.revision != expected_revision:
            raise QueryLexiconInvariantError(
                f"QueryLexicon revision 已变化，期望 {expected_revision}，实际 {before.revision}。"
            )
        base_queryset = QueryLexiconEntry.objects.filter(
            generation_id=before.active_generation_id,
            normalized_term__in=originals,
        )
        if selected_types:
            base_queryset = base_queryset.filter(entity_type__in=selected_types)
        diagnostic_rows = []
        if include_scope_diagnostics:
            diagnostic_rows = list(
                base_queryset.values(
                    "normalized_term",
                    "public_active",
                    "admin_resolvable",
                    "trust_level",
                    "term_type",
                )[:50001]
            )
            if len(diagnostic_rows) > 50000:
                raise ValueError("QueryLexicon batch resolver 诊断超过 50000 行。")
        queryset = base_queryset
        queryset = (
            queryset.filter(public_active=True)
            if scope == PUBLIC_ACTIVE
            else queryset.filter(admin_resolvable=True)
        )
        rows = list(
            queryset.order_by(
                "normalized_term",
                "entity_type",
                "entity_id",
                "source_ref",
            )[: 50001]
        )
        if len(rows) > 50000:
            raise ValueError("QueryLexicon batch resolver 匹配超过 50000 行。")
        after = QueryLexiconState.objects.only(
            "revision",
            "active_generation_id",
            "normalization_version",
            "source_registry_version",
        ).get(key="default")
        if (
            before.revision != after.revision
            or before.active_generation_id != after.active_generation_id
            or before.normalization_version != after.normalization_version
            or before.source_registry_version != after.source_registry_version
        ):
            continue

        rows_by_term = defaultdict(list)
        for row in rows:
            rows_by_term[row.normalized_term].append(row)
        diagnostics_by_term = defaultdict(list)
        for row in diagnostic_rows:
            diagnostics_by_term[row["normalized_term"]].append(row)
        entity_cache = {}
        results = {}
        for normalized, original in originals.items():
            term_rows = rows_by_term.get(normalized, [])
            truncated = len(term_rows) > limit
            matches = []
            for row in term_rows[:limit]:
                payload = _match_payload(row, scope=scope, entity_cache=entity_cache)
                if payload is not None:
                    matches.append(payload)
            results[normalized] = {
                "term": original,
                "normalized_term": normalized,
                "scope": scope,
                "entity_types": selected_types,
                "revision": before.revision,
                "normalization_version": before.normalization_version,
                "source_registry_version": before.source_registry_version,
                "ambiguous": truncated or len(matches) > 1,
                "truncated": truncated,
                "matches": matches,
            }
            if include_scope_diagnostics:
                all_rows = diagnostics_by_term.get(normalized, [])
                high_rows = [
                    row
                    for row in all_rows
                    if row["trust_level"]
                    in {
                        QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
                        QueryLexiconEntry.TrustLevel.VERIFIED,
                    }
                    and row["term_type"] != QueryLexiconEntry.TermType.SEARCH_VARIANT
                ]
                results[normalized]["scope_diagnostics"] = {
                    "derived_row_count": len(all_rows),
                    "admin_resolvable_row_count": sum(
                        bool(row["admin_resolvable"]) for row in all_rows
                    ),
                    "public_active_row_count": sum(
                        bool(row["public_active"]) for row in all_rows
                    ),
                    "high_trust_row_count": len(high_rows),
                    "high_trust_admin_resolvable_count": sum(
                        bool(row["admin_resolvable"]) for row in high_rows
                    ),
                    "high_trust_not_admin_resolvable_count": sum(
                        not bool(row["admin_resolvable"]) for row in high_rows
                    ),
                }
        return {"revision": before.revision, "results": results}
    raise QueryLexiconInvariantError("QueryLexicon 状态在批量解析期间持续变化，请重试。")


def resolve_term(
    term: str,
    *,
    entity_type: str | None = None,
    scope: str = PUBLIC_ACTIVE,
    expected_revision: int | None = None,
    max_results: int | None = None,
) -> dict:
    """Resolve one exact normalized term without ranking or forced disambiguation."""

    normalized = normalize_term(term)
    if not normalized:
        raise ValueError("term 不能为空。")
    if scope not in RESOLVER_SCOPES:
        raise ValueError(f"未知 QueryLexicon resolver scope：{scope}")
    if entity_type and entity_type not in QueryLexiconEntry.EntityType.values:
        raise ValueError(f"未知 QueryLexicon entity type：{entity_type}")
    limit = max_results or settings.QUERY_LEXICON_RESOLVER_MAX_RESULTS
    limit = max(1, min(int(limit), 500))

    for _attempt in range(3):
        before = QueryLexiconState.objects.select_related("active_generation").get(
            key="default"
        )
        _validate_state(before)
        if expected_revision is not None and before.revision != expected_revision:
            raise QueryLexiconInvariantError(
                f"QueryLexicon revision 已变化，期望 {expected_revision}，实际 {before.revision}。"
            )
        queryset = QueryLexiconEntry.objects.filter(
            generation_id=before.active_generation_id,
            normalized_term=normalized,
        )
        if scope == PUBLIC_ACTIVE:
            queryset = queryset.filter(public_active=True)
        else:
            queryset = queryset.filter(admin_resolvable=True)
        if entity_type:
            queryset = queryset.filter(entity_type=entity_type)
        rows = list(
            queryset.order_by("entity_type", "entity_id", "source_ref")[: limit + 1]
        )
        after = QueryLexiconState.objects.only(
            "revision",
            "active_generation_id",
            "normalization_version",
            "source_registry_version",
        ).get(key="default")
        if (
            before.revision != after.revision
            or before.active_generation_id != after.active_generation_id
            or before.normalization_version != after.normalization_version
            or before.source_registry_version != after.source_registry_version
        ):
            continue

        truncated = len(rows) > limit
        rows = rows[:limit]
        matches = []
        entity_cache = {}
        for row in rows:
            match = _match_payload(row, scope=scope, entity_cache=entity_cache)
            if match is not None:
                matches.append(match)
        return {
            "term": term,
            "normalized_term": normalized,
            "scope": scope,
            "entity_type": entity_type,
            "revision": before.revision,
            "normalization_version": before.normalization_version,
            "source_registry_version": before.source_registry_version,
            "ambiguous": truncated or len(matches) > 1,
            "truncated": truncated,
            "matches": matches,
        }
    raise QueryLexiconInvariantError("QueryLexicon 状态在解析期间持续变化，请重试。")
