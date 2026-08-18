from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from hashlib import sha256
import json
import re
import time

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from catalog.models import QueryLexiconEntry, QueryLexiconState
from catalog.services.passage_language import passage_language_details
from catalog.services.query_lexicon.normalization import detect_language, normalize_term
from catalog.services.query_lexicon.resolver import (
    PUBLIC_ACTIVE,
    RESOLVER_SCOPES,
)
from catalog.services.query_lexicon.sync import (
    QueryLexiconInvariantError,
    _validate_state,
)
from catalog.services.semantic_search_v2_config import (
    AMBIGUOUS_STANDALONE_TERMS,
    current_search_v2_limits,
)


SEARCH_RESOLVER_VERSION = "query-lexicon-search-resolver-v2"
_TOKEN_RE = re.compile(
    r"[a-z0-9]+(?:['’_-][a-z0-9]+)*|[\u3400-\u9fff]+",
    re.IGNORECASE,
)
_CJK_ONLY_RE = re.compile(r"^[\u3400-\u9fff]+$")
_OUTER_QUOTE_RE = re.compile(r"^[\s\"'“”‘’《》〈〉「」『』]+|[\s\"'“”‘’《》〈〉「」『』]+$")

_TRUST_PRIORITY = {
    QueryLexiconEntry.TrustLevel.AUTHORITATIVE: 5,
    QueryLexiconEntry.TrustLevel.VERIFIED: 4,
    QueryLexiconEntry.TrustLevel.UNVERIFIED: 3,
    QueryLexiconEntry.TrustLevel.LEGACY: 2,
    QueryLexiconEntry.TrustLevel.GENERATED: 1,
}
_TERM_PRIORITY = {
    QueryLexiconEntry.TermType.CANONICAL: 7,
    QueryLexiconEntry.TermType.TRANSLATION: 6,
    QueryLexiconEntry.TermType.ALIAS: 5,
    QueryLexiconEntry.TermType.ABBREVIATION: 4,
    QueryLexiconEntry.TermType.TRANSLITERATION: 3,
    QueryLexiconEntry.TermType.HISTORICAL: 2,
    QueryLexiconEntry.TermType.SEARCH_VARIANT: 1,
}
_BRANCH_PRIORITY = {
    "canonical_equivalent": 0,
    "verified_translation": 1,
    "verified_alias": 2,
    "historical": 3,
    "legacy_search_variant": 4,
    "generated_search_variant": 5,
}


def _language_family(value: object) -> str:
    language = str(value or "").strip().casefold()
    if language.startswith("zh"):
        return "zh"
    if language.startswith("en"):
        return "en"
    if language == "mixed":
        return "mixed"
    return "unknown"


def _query_language(value: str) -> str:
    details = passage_language_details(value)
    # Query classification is intentionally more sensitive than passage
    # classification. A short bilingual query such as ``Bourdieu 的 habitus``
    # should be marked mixed, while the passage detector still ignores a lone
    # citation inside a long paragraph.
    if details["cjk_count"] >= 1 and details["latin_count"] >= 1:
        return "mixed"
    detected = str(details["language"])
    if detected != "unknown":
        return detected
    return _language_family(detect_language(value))


def _is_quoted(value: str) -> bool:
    stripped = value.strip()
    pairs = (("\"", "\""), ("'", "'"), ("“", "”"), ("‘", "’"), ("《", "》"), ("〈", "〉"), ("「", "」"), ("『", "』"))
    return any(stripped.startswith(left) and stripped.endswith(right) for left, right in pairs)


def _recognition_spans(normalized_query: str, *, limit: int) -> list[str]:
    """Build a bounded set of exact lexicon probes for one short query."""

    output: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        normalized = normalize_term(value)
        if not normalized or normalized in seen or len(output) >= limit:
            return
        seen.add(normalized)
        output.append(normalized)

    add(normalized_query)
    stripped = normalize_term(_OUTER_QUOTE_RE.sub("", normalized_query))
    add(stripped)

    # Recognition is deliberately limited to the beginning of a long query.
    # Public viewpoint queries are capped at 1,200 characters, while entity
    # mentions normally occur in the first sentence.
    recognition_text = normalized_query[:160]
    tokens = list(_TOKEN_RE.finditer(recognition_text))
    for token in tokens:
        add(token.group(0))
    for width in range(2, min(6, len(tokens)) + 1):
        for start in range(0, len(tokens) - width + 1):
            add(recognition_text[tokens[start].start() : tokens[start + width - 1].end()])

    for token in tokens:
        text = token.group(0)
        if not _CJK_ONLY_RE.fullmatch(text) or len(text) < 2:
            continue
        for width in range(2, min(16, len(text)) + 1):
            for start in range(0, len(text) - width + 1):
                add(text[start : start + width])
                if len(output) >= limit:
                    return output
    return output


def _row_payload(row: QueryLexiconEntry) -> dict:
    return {
        "term": row.term,
        "normalized_term": row.normalized_term,
        "language": row.language,
        "term_type": row.term_type,
        "source_kind": row.source_kind,
        "trust_level": row.trust_level,
        "displayable": row.displayable,
    }


def _row_sort_key(row: QueryLexiconEntry, normalized_query: str) -> tuple:
    return (
        int(row.normalized_term == normalized_query),
        len(row.normalized_term),
        _TRUST_PRIORITY.get(row.trust_level, 0),
        _TERM_PRIORITY.get(row.term_type, 0),
        int(row.displayable),
        row.normalized_term,
        row.entity_type,
        str(row.entity_id),
    )


def _term_sort_key(row: QueryLexiconEntry, query_language: str) -> tuple:
    language = _language_family(row.language)
    return (
        int(language == query_language),
        _TRUST_PRIORITY.get(row.trust_level, 0),
        _TERM_PRIORITY.get(row.term_type, 0),
        int(row.displayable),
        -len(row.normalized_term),
        row.normalized_term,
    )


def _weaker_trust(left: str, right: str) -> str:
    return min(
        (left, right),
        key=lambda value: _TRUST_PRIORITY.get(value, 0),
    )


def _cache_key(
    *,
    normalized_query: str,
    scope: str,
    entity_type: str | None,
    entity_types: list[str],
    revision: int,
    limits: dict,
) -> str:
    payload = json.dumps(
        {
            "query": normalized_query,
            "scope": scope,
            "entity_type": entity_type,
            "entity_types": entity_types,
            "revision": revision,
            "limits": limits,
            "resolver_version": SEARCH_RESOLVER_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "query-lexicon:search:" + sha256(payload.encode("utf-8")).hexdigest()


def _build_branches(
    original_query: str,
    normalized_query: str,
    matched_entities: list[dict],
    *,
    query_language: str,
    max_branches: int,
    character_budget: int,
) -> list[dict]:
    branches = [
        {
            "branch_id": "original:0",
            "branch_type": "original",
            "query": original_query,
            "term": original_query,
            "language": query_language,
            "term_type": "original",
            "source_kind": "original_query",
            "trust_level": "original",
            "effective_trust_level": "original",
            "displayable": True,
            "ambiguous": False,
            "retrieval_channels": ["sparse", "dense"],
            "entities": [],
        }
    ]
    candidates: list[dict] = []
    for matched in matched_entities:
        if matched["ambiguity"]["expansion_suppressed"]:
            continue
        recognition = matched["matched_term"]
        recognition_language = _language_family(recognition["language"])
        if recognition_language == "unknown":
            recognition_language = query_language
        term_groups = (
            ("canonical_terms", "canonical_equivalent"),
            ("verified_translations", "verified_translation"),
            ("verified_aliases", "verified_alias"),
            ("historical_terms", "historical"),
            ("search_variants", "legacy_search_variant"),
        )
        for group_name, default_type in term_groups:
            for term in matched[group_name]:
                if not term["normalized_term"] or term["normalized_term"] in normalized_query:
                    continue
                target_language = _language_family(term["language"])
                branch_type = default_type
                if (
                    group_name == "canonical_terms"
                    and recognition_language in {"zh", "en"}
                    and target_language in {"zh", "en"}
                    and target_language != recognition_language
                ):
                    branch_type = "verified_translation"
                if group_name == "search_variants":
                    branch_type = (
                        "generated_search_variant"
                        if term["source_kind"]
                        == QueryLexiconEntry.SourceKind.GENERATED_SEARCH_VARIANT
                        else "legacy_search_variant"
                    )
                effective_trust = _weaker_trust(
                    recognition["trust_level"],
                    term["trust_level"],
                )
                candidates.append(
                    {
                        "branch_type": branch_type,
                        "query": term["term"],
                        "term": term["term"],
                        "normalized_term": term["normalized_term"],
                        "language": term["language"],
                        "term_type": term["term_type"],
                        "source_kind": term["source_kind"],
                        "trust_level": term["trust_level"],
                        "recognition_source_kind": recognition["source_kind"],
                        "recognition_trust_level": recognition["trust_level"],
                        "effective_trust_level": effective_trust,
                        "displayable": bool(
                            term["displayable"]
                            and branch_type
                            not in {"legacy_search_variant", "generated_search_variant"}
                        ),
                        "ambiguous": matched["ambiguity"]["is_ambiguous"],
                        "retrieval_channels": (
                            ["sparse"]
                            if branch_type
                            in {"legacy_search_variant", "generated_search_variant"}
                            else ["sparse", "dense"]
                        ),
                        "entities": [matched["canonical_entity"]],
                    }
                )

    candidates.sort(
        key=lambda row: (
            _BRANCH_PRIORITY.get(row["branch_type"], 99),
            -_TRUST_PRIORITY.get(row["effective_trust_level"], 0),
            -len(row["normalized_term"]),
            row["normalized_term"],
            row["entities"][0]["entity_type"],
            row["entities"][0]["entity_id"],
        )
    )
    used_characters = 0
    by_query: dict[str, dict] = {}
    for candidate in candidates:
        normalized = candidate["normalized_term"]
        existing = by_query.get(normalized)
        if existing is not None:
            entity = candidate["entities"][0]
            if entity not in existing["entities"]:
                existing["entities"].append(entity)
            existing["ambiguous"] = existing["ambiguous"] or candidate["ambiguous"]
            continue
        if len(branches) >= max_branches:
            break
        if used_characters + len(candidate["query"]) > character_budget:
            continue
        candidate["branch_id"] = f"{candidate['branch_type']}:{len(branches)}"
        by_query[normalized] = candidate
        branches.append(candidate)
        used_characters += len(candidate["query"])
    return branches


def _query_profile(
    original_query: str,
    normalized_query: str,
    query_language: str,
    matched_entities: list[dict],
    branches: list[dict],
) -> str:
    exact_unambiguous = any(
        matched["matched_term"]["normalized_term"]
        == normalize_term(_OUTER_QUOTE_RE.sub("", normalized_query))
        and matched["matched_term"]["trust_level"]
        in {
            QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
            QueryLexiconEntry.TrustLevel.VERIFIED,
        }
        and not matched["ambiguity"]["is_ambiguous"]
        and not matched["ambiguity"]["expansion_suppressed"]
        for matched in matched_entities
    )
    if exact_unambiguous:
        return "exact_entity"
    if _is_quoted(original_query):
        return "lexical_phrase"
    if query_language == "mixed":
        return "mixed_language"
    if any(branch["branch_type"] == "verified_translation" for branch in branches[1:]):
        return "cross_language"
    return "conceptual"


def resolve_search_query(
    original_query: str,
    *,
    entity_type: str | None = None,
    entity_types: list[str] | tuple[str, ...] | None = None,
    scope: str = PUBLIC_ACTIVE,
    expansion_limit: int | None = None,
) -> dict:
    """Resolve bounded entity mentions and equivalent terms for V2 search."""

    started = time.monotonic()
    normalized_query = normalize_term(original_query)
    if not normalized_query:
        raise ValueError("original_query 不能为空。")
    if scope not in RESOLVER_SCOPES:
        raise ValueError(f"未知 QueryLexicon resolver scope：{scope}")
    if entity_type and entity_types:
        raise ValueError("entity_type 与 entity_types 不能同时使用。")
    selected_types = sorted(
        set(
            str(value)
            for value in (
                entity_types
                if entity_types is not None
                else ([entity_type] if entity_type else [])
            )
        )
    )
    invalid_types = set(selected_types) - set(QueryLexiconEntry.EntityType.values)
    if invalid_types:
        raise ValueError(f"未知 QueryLexicon entity type：{sorted(invalid_types)[0]}")
    limits = current_search_v2_limits(expansion_limit=expansion_limit)
    limit_snapshot = limits.as_dict()
    query_language = _query_language(original_query)
    db_queries = 0

    for _attempt in range(3):
        before = QueryLexiconState.objects.select_related("active_generation").get(
            key="default"
        )
        db_queries += 1
        _validate_state(before)
        key = _cache_key(
            normalized_query=normalized_query,
            scope=scope,
            entity_type=entity_type,
            entity_types=selected_types,
            revision=before.revision,
            limits=limit_snapshot,
        )
        cached = cache.get(key)
        if isinstance(cached, dict):
            after_cached = QueryLexiconState.objects.only(
                "revision",
                "active_generation_id",
                "normalization_version",
                "source_registry_version",
            ).get(key="default")
            db_queries += 1
            if (
                before.revision != after_cached.revision
                or before.active_generation_id != after_cached.active_generation_id
                or before.normalization_version != after_cached.normalization_version
                or before.source_registry_version != after_cached.source_registry_version
            ):
                continue
            result = deepcopy(cached)
            result["cache_hit"] = True
            result["resolver_db_query_count"] = db_queries
            result["resolver_timing_ms"] = round(
                (time.monotonic() - started) * 1000,
                3,
            )
            return result

        spans = _recognition_spans(
            normalized_query,
            limit=limits.max_recognition_spans,
        )
        queryset = QueryLexiconEntry.objects.filter(
            generation_id=before.active_generation_id,
            normalized_term__in=spans,
        )
        queryset = (
            queryset.filter(public_active=True)
            if scope == PUBLIC_ACTIVE
            else queryset.filter(admin_resolvable=True)
        )
        if selected_types:
            queryset = queryset.filter(entity_type__in=selected_types)
        match_cap = limits.max_matched_entities * 32
        matched_rows = list(
            queryset.order_by("entity_type", "entity_id", "normalized_term")[: match_cap + 1]
        )
        db_queries += 1
        match_rows_truncated = len(matched_rows) > match_cap
        matched_rows = matched_rows[:match_cap]

        rows_by_entity: dict[tuple[str, str], list[QueryLexiconEntry]] = defaultdict(list)
        entities_by_mention: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for row in matched_rows:
            entity_key = (row.entity_type, str(row.entity_id))
            rows_by_entity[entity_key].append(row)
            entities_by_mention[row.normalized_term].add(entity_key)
        ranked_entities = sorted(
            rows_by_entity,
            key=lambda entity_key: _row_sort_key(
                max(
                    rows_by_entity[entity_key],
                    key=lambda row: _row_sort_key(row, normalized_query),
                ),
                normalized_query,
            ),
            reverse=True,
        )
        selected_entities = ranked_entities[: limits.max_matched_entities]
        entity_truncated = match_rows_truncated or len(ranked_entities) > len(selected_entities)

        all_term_rows: list[QueryLexiconEntry] = []
        if selected_entities:
            entity_filter = Q()
            for entity_type, entity_id in selected_entities:
                entity_filter |= Q(entity_type=entity_type, entity_id=entity_id)
            term_queryset = QueryLexiconEntry.objects.filter(
                entity_filter,
                generation_id=before.active_generation_id,
            )
            term_queryset = (
                term_queryset.filter(public_active=True)
                if scope == PUBLIC_ACTIVE
                else term_queryset.filter(admin_resolvable=True)
            )
            all_term_rows = list(
                term_queryset.order_by("entity_type", "entity_id", "normalized_term")
            )
            db_queries += 1
        terms_by_entity: dict[tuple[str, str], list[QueryLexiconEntry]] = defaultdict(list)
        for row in all_term_rows:
            terms_by_entity[(row.entity_type, str(row.entity_id))].append(row)

        after = QueryLexiconState.objects.only(
            "revision",
            "active_generation_id",
            "normalization_version",
            "source_registry_version",
        ).get(key="default")
        db_queries += 1
        if (
            before.revision != after.revision
            or before.active_generation_id != after.active_generation_id
            or before.normalization_version != after.normalization_version
            or before.source_registry_version != after.source_registry_version
        ):
            continue

        matched_entities = []
        stripped_query = normalize_term(_OUTER_QUOTE_RE.sub("", normalized_query))
        for entity_key in selected_entities:
            recognition = max(
                rows_by_entity[entity_key],
                key=lambda row: _row_sort_key(row, normalized_query),
            )
            entity_terms = terms_by_entity.get(entity_key, [])
            verified = {
                QueryLexiconEntry.TrustLevel.AUTHORITATIVE,
                QueryLexiconEntry.TrustLevel.VERIFIED,
            }
            canonical = [
                row
                for row in entity_terms
                if row.term_type == QueryLexiconEntry.TermType.CANONICAL
                and row.trust_level in verified
            ]
            translations = [
                row
                for row in entity_terms
                if row.term_type == QueryLexiconEntry.TermType.TRANSLATION
                and row.trust_level in verified
            ]
            aliases = [
                row
                for row in entity_terms
                if row.term_type
                in {
                    QueryLexiconEntry.TermType.ALIAS,
                    QueryLexiconEntry.TermType.ABBREVIATION,
                    QueryLexiconEntry.TermType.TRANSLITERATION,
                }
                and row.trust_level in verified
            ]
            historical = [
                row
                for row in entity_terms
                if row.term_type == QueryLexiconEntry.TermType.HISTORICAL
                and row.trust_level in verified
            ]
            search_variants = [
                row
                for row in entity_terms
                if row.term_type == QueryLexiconEntry.TermType.SEARCH_VARIANT
                or row.trust_level
                in {
                    QueryLexiconEntry.TrustLevel.LEGACY,
                    QueryLexiconEntry.TrustLevel.GENERATED,
                }
            ]
            # MAX_TERMS_PER_ENTITY is an entity-wide budget, rather than a
            # separate allowance for every provenance bucket. Canonical and
            # verified cross-language terms are selected first, while legacy
            # and generated variants can only use the remaining slots.
            selected_term_rows: list[QueryLexiconEntry] = []
            for group_rows in (
                canonical,
                translations,
                aliases,
                historical,
                search_variants,
            ):
                remaining = limits.max_terms_per_entity - len(selected_term_rows)
                if remaining <= 0:
                    break
                selected_term_rows.extend(
                    sorted(
                        group_rows,
                        key=lambda row: _term_sort_key(row, query_language),
                        reverse=True,
                    )[:remaining]
                )

            def selected_payload(group_rows: list[QueryLexiconEntry]) -> list[dict]:
                selected_ids = {row.pk for row in selected_term_rows}
                return [
                    _row_payload(row)
                    for row in sorted(
                        group_rows,
                        key=lambda row: _term_sort_key(row, query_language),
                        reverse=True,
                    )
                    if row.pk in selected_ids
                ]

            canonical_payload = selected_payload(canonical)
            same_mention_count = len(entities_by_mention[recognition.normalized_term])
            standalone = stripped_query == recognition.normalized_term
            high_ambiguity = recognition.normalized_term in AMBIGUOUS_STANDALONE_TERMS
            expansion_suppressed = bool(
                standalone
                and not _is_quoted(original_query)
                and (same_mention_count > 1 or high_ambiguity)
            )
            is_ambiguous = bool(same_mention_count > 1 or high_ambiguity)
            label = (
                canonical_payload[0]["term"]
                if canonical_payload
                else recognition.term
            )
            matched_entities.append(
                {
                    "canonical_entity": {
                        "entity_type": entity_key[0],
                        "entity_id": entity_key[1],
                        "canonical_label": label,
                    },
                    "matched_term": _row_payload(recognition),
                    "canonical_terms": canonical_payload,
                    "verified_translations": selected_payload(translations),
                    "verified_aliases": selected_payload(aliases),
                    "historical_terms": selected_payload(historical),
                    "search_variants": selected_payload(search_variants),
                    "ambiguity": {
                        "is_ambiguous": is_ambiguous,
                        "matching_entity_count": same_mention_count,
                        "high_ambiguity_standalone_term": high_ambiguity,
                        "expansion_suppressed": expansion_suppressed,
                        "reason": (
                            "ambiguous_term_without_context"
                            if expansion_suppressed
                            else ""
                        ),
                    },
                }
            )

        branches = _build_branches(
            original_query,
            normalized_query,
            matched_entities,
            query_language=query_language,
            max_branches=limits.max_expansion_branches,
            character_budget=limits.max_expansion_characters,
        )
        result = {
            "original_query": original_query,
            "normalized_original_query": normalized_query,
            "query_language": query_language,
            "scope": scope,
            "entity_type": entity_type,
            "entity_types": selected_types,
            "query_lexicon_revision": before.revision,
            "normalization_version": before.normalization_version,
            "source_registry_version": before.source_registry_version,
            "search_resolver_version": SEARCH_RESOLVER_VERSION,
            "matched_entities": matched_entities,
            "ambiguous": entity_truncated
            or any(row["ambiguity"]["is_ambiguous"] for row in matched_entities),
            "truncated": entity_truncated,
            "expansion_branches": branches,
            "query_profile": _query_profile(
                original_query,
                normalized_query,
                query_language,
                matched_entities,
                branches,
            ),
            "limits": limit_snapshot,
            "recognition_span_count": len(spans),
            "cache_hit": False,
            "resolver_db_query_count": db_queries,
            "resolver_timing_ms": round((time.monotonic() - started) * 1000, 3),
        }
        cache.set(
            key,
            deepcopy(result),
            timeout=max(
                1,
                min(
                    int(getattr(settings, "QUERY_LEXICON_SEARCH_CACHE_SECONDS", 300)),
                    3600,
                ),
            ),
        )
        return result
    raise QueryLexiconInvariantError("QueryLexicon 状态在搜索解析期间持续变化，请重试。")
