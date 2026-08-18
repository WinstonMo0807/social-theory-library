from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
import re
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import DatabaseError
from django.db.models import Q

from catalog.models import (
    Asset,
    Discipline,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Person,
    PublicationState,
    ReadingPath,
    ScholarProfile,
    Subdiscipline,
    Topic,
    Work,
    WorkDisciplineRelation,
    WorkKnowledgeRelation,
    WorkNodeRelation,
    WorkSubdisciplineRelation,
)
from catalog.services.passage_language import passage_language_details
from catalog.services.query_lexicon.normalization import normalize_term
from catalog.services.query_lexicon.resolver import PUBLIC_ACTIVE
from catalog.services.query_lexicon.search import resolve_search_query

from .models import LibraryConversation, LibraryMessage
from .services import decrypt_private_text


LIBRARY_QUERY_VERSION = "library-query-v1"


class LibraryScopeError(ValueError):
    pass


class LibraryQueryType(StrEnum):
    EXACT_SCHOLAR = "exact_scholar"
    EXACT_THEORY = "exact_theory"
    CONCEPTUAL = "conceptual"
    MECHANISM = "mechanism"
    COMPARISON = "comparison"
    RELATION = "relation"
    HISTORICAL_TIMELINE = "historical_timeline"
    QUOTED_PHRASE = "quoted_phrase"
    MIXED_LANGUAGE = "mixed_language"
    GENERAL = "general"


class LibraryScopeContext(StrEnum):
    GLOBAL = "global"
    WORKS = "works"
    SCHOLARS = "scholars"
    DISCIPLINES = "disciplines"
    SUBDISCIPLINES = "subdisciplines"
    THEORIES = "theories"
    TOPICS = "topics"
    READING_PATHS = "reading_paths"


SCOPE_ALIASES = {
    "": LibraryScopeContext.GLOBAL,
    "global": LibraryScopeContext.GLOBAL,
    "whole_library": LibraryScopeContext.GLOBAL,
    "library": LibraryScopeContext.GLOBAL,
    "work": LibraryScopeContext.WORKS,
    "selected_work": LibraryScopeContext.WORKS,
    "selected_works": LibraryScopeContext.WORKS,
    "works": LibraryScopeContext.WORKS,
    "scholar": LibraryScopeContext.SCHOLARS,
    "scholars": LibraryScopeContext.SCHOLARS,
    "author": LibraryScopeContext.SCHOLARS,
    "authors": LibraryScopeContext.SCHOLARS,
    "discipline": LibraryScopeContext.DISCIPLINES,
    "disciplines": LibraryScopeContext.DISCIPLINES,
    "subdiscipline": LibraryScopeContext.SUBDISCIPLINES,
    "subdisciplines": LibraryScopeContext.SUBDISCIPLINES,
    "theory": LibraryScopeContext.THEORIES,
    "theories": LibraryScopeContext.THEORIES,
    "theory_school": LibraryScopeContext.THEORIES,
    "topic": LibraryScopeContext.TOPICS,
    "topics": LibraryScopeContext.TOPICS,
    "reading_path": LibraryScopeContext.READING_PATHS,
    "reading_paths": LibraryScopeContext.READING_PATHS,
}


@dataclass(frozen=True, slots=True)
class LibraryScope:
    context: str
    ids: tuple[str, ...] = ()
    asset_id: str = ""
    visibility: str = "public"

    def as_dict(self) -> dict:
        return {
            "context": self.context,
            "ids": list(self.ids),
            **({"asset_id": self.asset_id} if self.asset_id else {}),
            "visibility": self.visibility,
        }


@dataclass(frozen=True, slots=True)
class ResolvedLibraryScope:
    scope: LibraryScope
    semantic_filters: dict
    asset_id: str = ""
    labels: tuple[str, ...] = ()
    empty: bool = False


@dataclass(frozen=True, slots=True)
class LibraryQuery:
    original_query: str
    normalized_query: str
    resolved_query: str
    language: str
    query_type: str
    scope: LibraryScope
    entity_anchors: tuple[dict, ...]
    conversation_context: dict[str, Any]
    retrieval_limits: dict[str, int]
    retrieval_profile: str
    query_lexicon_revision: int | None
    implementation_version: str = LIBRARY_QUERY_VERSION

    def debug_dict(self) -> dict:
        return asdict(self)


def _uuid_values(values: object) -> tuple[str, ...]:
    if values in (None, ""):
        return ()
    if not isinstance(values, (list, tuple, set)):
        values = [values]
    output = []
    seen = set()
    for value in values:
        try:
            normalized = str(UUID(str(value)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise LibraryScopeError("Scope entity ID 必须是 UUID。") from exc
        if normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    if len(output) > 12:
        raise LibraryScopeError("单次 Ask scope 最多包含 12 个对象。")
    return tuple(output)


def normalize_library_scope(value: object, *, admin_visibility: bool = False) -> LibraryScope:
    if value in (None, ""):
        return LibraryScope(context=LibraryScopeContext.GLOBAL, visibility="admin" if admin_visibility else "public")
    if not isinstance(value, dict):
        raise LibraryScopeError("Library scope 必须是对象。")
    raw_context = str(value.get("context") or value.get("type") or "").strip().casefold()
    legacy_ids = None
    if not raw_context:
        for key, context in (
            ("work_ids", LibraryScopeContext.WORKS),
            ("work_id", LibraryScopeContext.WORKS),
            ("authors", LibraryScopeContext.SCHOLARS),
            ("author", LibraryScopeContext.SCHOLARS),
            ("theories", LibraryScopeContext.THEORIES),
            ("theory_school", LibraryScopeContext.THEORIES),
            ("topics", LibraryScopeContext.TOPICS),
            ("topic", LibraryScopeContext.TOPICS),
            ("reading_paths", LibraryScopeContext.READING_PATHS),
            ("reading_path", LibraryScopeContext.READING_PATHS),
        ):
            if value.get(key):
                raw_context = str(context)
                legacy_ids = value.get(key)
                break
    try:
        context = SCOPE_ALIASES[raw_context]
    except KeyError as exc:
        raise LibraryScopeError("不支持的 Library scope；不会回退 whole library。") from exc
    ids = _uuid_values(value.get("ids") if legacy_ids is None else legacy_ids)
    asset_id = ""
    if value.get("asset_id"):
        asset_id = _uuid_values([value["asset_id"]])[0]
        if context == LibraryScopeContext.GLOBAL:
            context = LibraryScopeContext.WORKS
    if context != LibraryScopeContext.GLOBAL and not ids and not asset_id:
        raise LibraryScopeError("Scoped Ask 必须选择至少一个对象。")
    return LibraryScope(
        context=str(context),
        ids=ids,
        asset_id=asset_id,
        visibility="admin" if admin_visibility else "public",
    )


def _published_work_ids(ids: tuple[str, ...]) -> set[str]:
    return {
        str(value)
        for value in Work.objects.filter(
            id__in=ids,
            editions__state=PublicationState.PUBLISHED,
            editions__is_primary=True,
        ).values_list("id", flat=True).distinct()
    }


def resolve_library_scope(scope: LibraryScope) -> ResolvedLibraryScope:
    filters: dict[str, list[str]] = {}
    labels: list[str] = []
    asset_id = scope.asset_id
    empty = False
    admin = scope.visibility == "admin"
    context = LibraryScopeContext(scope.context)
    ids = scope.ids
    if asset_id:
        asset = Asset.objects.select_related("edition__work").filter(
            pk=asset_id,
            edition__state=PublicationState.PUBLISHED,
            edition__is_primary=True,
            kind=Asset.Kind.NORMALIZED,
            status=Asset.Status.READY,
            is_current=True,
        ).first()
        if asset is None:
            raise LibraryScopeError("当前 Reader Asset 不可用于馆藏问答。")
        filters["work_ids"] = [str(asset.edition.work_id)]
        labels.append(asset.edition.work.title)
    elif context == LibraryScopeContext.GLOBAL:
        pass
    elif context == LibraryScopeContext.WORKS:
        work_ids = _published_work_ids(ids)
        if len(work_ids) != len(ids):
            raise LibraryScopeError("Scope 包含不可公开读取的 Work。")
        filters["work_ids"] = sorted(work_ids)
        labels.extend(Work.objects.filter(id__in=work_ids).values_list("title", flat=True))
    elif context == LibraryScopeContext.SCHOLARS:
        people = Person.objects.filter(id__in=ids)
        if not admin:
            people = people.filter(
                authority_status=Person.AuthorityStatus.VERIFIED,
                scholar_profile__editorial_status="published",
            )
        people_ids = {str(value) for value in people.values_list("id", flat=True)}
        if len(people_ids) != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 Scholar。")
        filters["authors"] = sorted(people_ids)
        labels.extend(people.values_list("preferred_name", flat=True))
    elif context == LibraryScopeContext.THEORIES:
        nodes = KnowledgeNode.objects.filter(id__in=ids)
        if not admin:
            nodes = nodes.filter(status="published")
        node_ids = {str(value) for value in nodes.values_list("id", flat=True)}
        if len(node_ids) != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 Theory。")
        work_ids = {
            str(value)
            for value in WorkNodeRelation.objects.filter(
                node_id__in=node_ids,
                status="published",
                work__editions__state=PublicationState.PUBLISHED,
            ).values_list("work_id", flat=True)
        }
        mapped_legacy = LegacyKnowledgeMapping.objects.filter(
            node_id__in=node_ids,
            migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
            legacy_model="TheorySchool",
        ).values_list("legacy_id", flat=True)
        work_ids.update(
            str(value)
            for value in WorkKnowledgeRelation.objects.filter(
                theory_school_id__in=mapped_legacy,
                approved=True,
                work__editions__state=PublicationState.PUBLISHED,
            ).values_list("work_id", flat=True)
        )
        filters["work_ids"] = sorted(work_ids)
        empty = not work_ids
        labels.extend(nodes.values_list("canonical_name_zh", flat=True))
    elif context == LibraryScopeContext.TOPICS:
        topics = Topic.objects.filter(id__in=ids)
        if not admin:
            topics = topics.filter(editorial_status="published")
        if topics.count() != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 Topic。")
        filters["topics"] = list(topics.values_list("slug", flat=True))
        labels.extend(topics.values_list("name", flat=True))
    elif context == LibraryScopeContext.DISCIPLINES:
        rows = Discipline.objects.filter(id__in=ids)
        if not admin:
            rows = rows.filter(editorial_status="published")
        if rows.count() != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 Discipline。")
        work_ids = WorkDisciplineRelation.objects.filter(
            discipline_id__in=ids,
            review_status="approved",
        ).values_list("work_id", flat=True)
        filters["work_ids"] = [str(value) for value in work_ids]
        empty = not filters["work_ids"]
        labels.extend(rows.values_list("name", flat=True))
    elif context == LibraryScopeContext.SUBDISCIPLINES:
        rows = Subdiscipline.objects.filter(id__in=ids)
        if not admin:
            rows = rows.filter(editorial_status="published")
        if rows.count() != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 Subdiscipline。")
        work_ids = WorkSubdisciplineRelation.objects.filter(
            subdiscipline_id__in=ids,
            review_status="approved",
        ).values_list("work_id", flat=True)
        filters["work_ids"] = [str(value) for value in work_ids]
        empty = not filters["work_ids"]
        labels.extend(rows.values_list("name", flat=True))
    elif context == LibraryScopeContext.READING_PATHS:
        paths = ReadingPath.objects.filter(id__in=ids)
        if not admin:
            paths = paths.filter(status="published")
        if paths.count() != len(ids):
            raise LibraryScopeError("Scope 包含不可公开解析的 ReadingPath。")
        work_ids = {str(value) for value in paths.values_list("items__work_id", flat=True) if value}
        node_ids = [value for value in paths.values_list("items__node_id", flat=True) if value]
        work_ids.update(
            str(value)
            for value in WorkNodeRelation.objects.filter(
                node_id__in=node_ids,
                status="published",
            ).values_list("work_id", flat=True)
        )
        filters["work_ids"] = sorted(work_ids)
        empty = not work_ids
        labels.extend(paths.values_list("title", flat=True))
    return ResolvedLibraryScope(
        scope=scope,
        semantic_filters=filters,
        asset_id=asset_id,
        labels=tuple(dict.fromkeys(str(value) for value in labels if value)),
        empty=empty,
    )


def _query_language(value: str) -> str:
    details = passage_language_details(value)
    if details["cjk_count"] and details["latin_count"]:
        return "mixed"
    return str(details["language"] or "unknown")


def _quoted(value: str) -> bool:
    stripped = value.strip()
    return any(
        stripped.startswith(left) and stripped.endswith(right)
        for left, right in (("\"", "\""), ("“", "”"), ("‘", "’"), ("《", "》"), ("「", "」"))
    )


def classify_library_query(
    query: str,
    *,
    language: str,
    entity_anchors: tuple[dict, ...],
) -> str:
    normalized = normalize_term(query)
    if _quoted(query) or re.search(r"(?:在哪里说|原句|原文|exact phrase|where does .* say)", query, re.I):
        return LibraryQueryType.QUOTED_PHRASE
    if re.search(r"(?:比较|区别|异同|相比|与.+(?:和|及).+|\bversus\b|\bvs\.?\b|compare|difference)", query, re.I):
        return LibraryQueryType.COMPARISON
    if re.search(r"(?:如何|为什么|机制|通过什么|how does|why does|mechanism)", query, re.I):
        return LibraryQueryType.MECHANISM
    if re.search(r"(?:关系|影响|批判|回应|继承|relation|influence|critic|respond)", query, re.I):
        return LibraryQueryType.RELATION
    if re.search(r"(?:历史|演变|时期|时间线|形成过程|history|historical|timeline|evolution)", query, re.I):
        return LibraryQueryType.HISTORICAL_TIMELINE
    if language == "mixed":
        return LibraryQueryType.MIXED_LANGUAGE
    exact = [
        row
        for row in entity_anchors
        if normalize_term(row.get("matched_term", {}).get("term")) == normalized
        or normalize_term(row.get("canonical_entity", {}).get("canonical_label")) == normalized
    ]
    if len(exact) == 1:
        entity_type = exact[0].get("canonical_entity", {}).get("entity_type")
        if entity_type == "person":
            return LibraryQueryType.EXACT_SCHOLAR
        if entity_type == "knowledge_node":
            return LibraryQueryType.EXACT_THEORY
    if re.search(r"(?:什么是|如何理解|概念|定义|meaning|concept|define)", query, re.I):
        return LibraryQueryType.CONCEPTUAL
    return LibraryQueryType.GENERAL


def _previous_user_question(conversation: LibraryConversation) -> str:
    row = conversation.messages.filter(
        role=LibraryMessage.Role.USER,
        status=LibraryMessage.Status.COMPLETED,
    ).order_by("-created_at").first()
    return decrypt_private_text(row.body_ciphertext)[:1000] if row else ""


def _followup_query(original: str, previous: str, has_entities: bool) -> str:
    if not previous or has_entities:
        return original
    if re.search(r"^(?:那|那么|这个|这种|他|她|其|它|that|what about|and )", original.strip(), re.I):
        return f"{previous}；追问：{original}"[:1600]
    return original


def build_library_query(
    *,
    conversation: LibraryConversation,
    question: str,
    retrieval_profile: str,
    scope: object | None = None,
    admin_visibility: bool = False,
) -> tuple[LibraryQuery, ResolvedLibraryScope, dict]:
    original = " ".join(str(question or "").split())
    if not original:
        raise ValueError("请输入问题。")
    max_question = int(getattr(settings, "LIBRARY_QA_MAX_QUESTION_CHARS", 4000))
    if len(original) > max_question:
        raise ValueError(f"问题不能超过 {max_question} 个字符。")
    normalized_scope = normalize_library_scope(
        conversation.scope if scope is None else scope,
        admin_visibility=admin_visibility,
    )
    resolved_scope = resolve_library_scope(normalized_scope)
    previous = _previous_user_question(conversation)
    first_resolution = {}
    try:
        first_resolution = resolve_search_query(original, scope=PUBLIC_ACTIVE)
    except (DatabaseError, RuntimeError, ValueError):
        first_resolution = {
            "normalized_original_query": normalize_term(original),
            "query_language": _query_language(original),
            "matched_entities": [],
            "query_lexicon_revision": None,
            "expansion_branches": [{"branch_type": "original", "query": original}],
        }
    resolved_query = _followup_query(
        original,
        previous,
        bool(first_resolution.get("matched_entities")),
    )
    resolution = first_resolution
    if resolved_query != original:
        try:
            resolution = resolve_search_query(resolved_query, scope=PUBLIC_ACTIVE)
        except (DatabaseError, RuntimeError, ValueError):
            resolution = first_resolution
    anchors = tuple(resolution.get("matched_entities") or [])
    language = str(resolution.get("query_language") or _query_language(original))
    query_type = classify_library_query(original, language=language, entity_anchors=anchors)
    limits = {
        "max_passages": max(1, min(int(getattr(settings, "LIBRARY_RAG_MAX_PASSAGES", 8)), 16)),
        "max_evidence_chars": max(1000, min(int(getattr(settings, "LIBRARY_RAG_MAX_EVIDENCE_CHARS", 9000)), 24000)),
        "per_work_cap": max(1, min(int(getattr(settings, "LIBRARY_RAG_PER_WORK_CAP", 2)), 6)),
        "comparison_per_anchor": max(1, min(int(getattr(settings, "LIBRARY_RAG_COMPARISON_PER_ANCHOR", 2)), 4)),
        "max_entity_branches": max(1, min(int(getattr(settings, "LIBRARY_RAG_MAX_ENTITY_BRANCHES", 3)), 4)),
    }
    query = LibraryQuery(
        original_query=original,
        normalized_query=str(resolution.get("normalized_original_query") or normalize_term(original)),
        resolved_query=resolved_query,
        language=language,
        query_type=str(query_type),
        scope=normalized_scope,
        entity_anchors=anchors,
        conversation_context={
            "previous_user_query_used": resolved_query != original,
            "previous_user_query_chars": len(previous) if resolved_query != original else 0,
        },
        retrieval_limits=limits,
        retrieval_profile=retrieval_profile,
        query_lexicon_revision=resolution.get("query_lexicon_revision"),
    )
    return query, resolved_scope, resolution
