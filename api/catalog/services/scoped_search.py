from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import ceil
from time import perf_counter

from django.db.models import Case, IntegerField, Prefetch, Q, QuerySet, Value, When

from catalog.models import (
    Discipline,
    Edition,
    KnowledgeNode,
    LegacyKnowledgeMapping,
    Person,
    QueryLexiconEntry,
    QueryLexiconState,
    ReadingPath,
    ScholarProfile,
    Subdiscipline,
    TheorySchool,
    Topic,
    Work,
)
from catalog.services.query_lexicon.normalization import normalize_term


IMPLEMENTATION_VERSION = "scoped-search-v1"
DEFAULT_LIMIT = 24
MAX_LIMIT = 50


class SearchContext(StrEnum):
    WORKS = "works"
    SCHOLARS = "scholars"
    DISCIPLINES = "disciplines"
    SUBDISCIPLINES = "subdisciplines"
    THEORIES = "theories"
    TOPICS = "topics"
    READING_PATHS = "reading_paths"
    GLOBAL = "global"


class SearchVisibility(StrEnum):
    PUBLIC = "public"
    ADMIN = "admin"


CONTEXT_LABELS = {
    SearchContext.WORKS: "馆藏",
    SearchContext.SCHOLARS: "学者",
    SearchContext.DISCIPLINES: "学科",
    SearchContext.SUBDISCIPLINES: "子学科",
    SearchContext.THEORIES: "理论",
    SearchContext.TOPICS: "主题",
    SearchContext.READING_PATHS: "阅读路径",
}

GLOBAL_CONTEXTS = tuple(CONTEXT_LABELS)
THEORY_NODE_TYPES = {
    KnowledgeNode.NodeType.THEORY_TRADITION,
    KnowledgeNode.NodeType.CONCEPT,
    KnowledgeNode.NodeType.DEBATE,
    KnowledgeNode.NodeType.RESEARCH_PROBLEM,
}


@dataclass(frozen=True)
class SearchRequest:
    query: str
    context: SearchContext
    page: int = 1
    limit: int = DEFAULT_LIMIT
    visibility: SearchVisibility = SearchVisibility.PUBLIC
    filters: dict | None = None

    @classmethod
    def from_values(
        cls,
        *,
        query: str,
        context: str,
        page=1,
        limit=DEFAULT_LIMIT,
        visibility: str = SearchVisibility.PUBLIC,
        filters: dict | None = None,
    ) -> "SearchRequest":
        try:
            parsed_context = SearchContext(str(context).strip())
        except ValueError as exc:
            raise ValueError("请选择有效的搜索范围。") from exc
        try:
            parsed_visibility = SearchVisibility(str(visibility).strip())
        except ValueError as exc:
            raise ValueError("请选择有效的可见范围。") from exc
        normalized_query = str(query or "").strip()
        if len(normalized_query) > 500:
            raise ValueError("实体搜索内容不能超过 500 个字符。")
        try:
            parsed_page = max(1, int(page))
        except (TypeError, ValueError):
            parsed_page = 1
        try:
            parsed_limit = min(MAX_LIMIT, max(1, int(limit)))
        except (TypeError, ValueError):
            parsed_limit = DEFAULT_LIMIT
        return cls(
            query=normalized_query,
            context=parsed_context,
            page=parsed_page,
            limit=parsed_limit,
            visibility=parsed_visibility,
            filters=filters or {},
        )


def public_work_queryset() -> QuerySet:
    published_editions = Edition.objects.filter(
        state="published",
        is_primary=True,
    ).prefetch_related("contributions__person", "assets")
    return (
        Work.objects.filter(editions__in=published_editions)
        .distinct()
        .prefetch_related(
            Prefetch("editions", queryset=published_editions),
            "knowledge_relations__theory_school",
            "knowledge_relations__topic",
        )
    )


def _lexicon_entity_ids(
    query: str,
    *,
    entity_type: str,
    visibility: SearchVisibility,
) -> set:
    normalized = normalize_term(query)
    if not normalized:
        return set()
    try:
        state = QueryLexiconState.objects.only("active_generation_id").get(key="default")
        rows = QueryLexiconEntry.objects.filter(
            generation_id=state.active_generation_id,
            entity_type=entity_type,
            normalized_term=normalized,
        )
        rows = (
            rows.filter(public_active=True)
            if visibility == SearchVisibility.PUBLIC
            else rows.filter(admin_resolvable=True)
        )
        return set(rows.values_list("entity_id", flat=True))
    except QueryLexiconState.DoesNotExist:
        # Compatibility for code-first development before QueryLexicon migrations
        # are applied. Search still uses canonical authority fields.
        return set()


def _lookup_q(fields: tuple[str, ...], lookup: str, value: str) -> Q:
    result = Q()
    for field in fields:
        result |= Q(**{f"{field}__{lookup}": value})
    return result


def _order_for_context(context: SearchContext) -> tuple[str, ...]:
    return {
        SearchContext.WORKS: ("title",),
        SearchContext.SCHOLARS: ("person__sort_name", "person__preferred_name"),
        SearchContext.DISCIPLINES: ("sort_order", "name"),
        SearchContext.SUBDISCIPLINES: ("discipline__sort_order", "name"),
        SearchContext.THEORIES: ("sort_order", "canonical_name_zh"),
        SearchContext.TOPICS: ("-curation_level", "name"),
        SearchContext.READING_PATHS: ("sort_order", "title"),
    }[context]


def _fields_for_context(context: SearchContext) -> tuple[tuple[str, ...], tuple[str, ...]]:
    canonical = {
        SearchContext.WORKS: ("title", "original_title", "uniform_title"),
        SearchContext.SCHOLARS: ("person__preferred_name", "person__original_name"),
        SearchContext.DISCIPLINES: ("name", "foreign_name"),
        SearchContext.SUBDISCIPLINES: ("name", "foreign_name"),
        SearchContext.THEORIES: ("canonical_name_zh", "canonical_name_en"),
        SearchContext.TOPICS: ("name",),
        SearchContext.READING_PATHS: ("title",),
    }[context]
    descriptive = {
        SearchContext.WORKS: (
            "subtitle",
            "abstract",
            "editions__contributions__person__preferred_name",
            "editions__contributions__person__original_name",
            "knowledge_relations__theory_school__name",
            "knowledge_relations__topic__name",
            "knowledge_relations__concept__name",
        ),
        SearchContext.SCHOLARS: ("short_description", "person__biography"),
        SearchContext.DISCIPLINES: ("description",),
        SearchContext.SUBDISCIPLINES: ("description", "research_object"),
        SearchContext.THEORIES: (
            "summary",
            "definition",
            "aliases__alias",
            "aliases__normalized_alias",
        ),
        SearchContext.TOPICS: ("description", "problem_statement"),
        SearchContext.READING_PATHS: ("introduction", "audience"),
    }[context]
    return canonical, descriptive


def _entity_type_for_context(context: SearchContext) -> str | None:
    return {
        SearchContext.SCHOLARS: QueryLexiconEntry.EntityType.PERSON,
        SearchContext.DISCIPLINES: QueryLexiconEntry.EntityType.DISCIPLINE,
        SearchContext.THEORIES: QueryLexiconEntry.EntityType.KNOWLEDGE_NODE,
        SearchContext.TOPICS: QueryLexiconEntry.EntityType.TOPIC,
    }.get(context)


def _filter_value(filters: dict, name: str) -> str:
    value = (filters or {}).get(name, "")
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    return str(value or "").strip()


class SearchService:
    """One orchestration layer over existing entity retrieval backends."""

    def __init__(self, *, request=None):
        self.request = request
        self._legacy_mapping_cache: dict[str, dict] = {}

    def canonical_mapping(self, legacy_model: str, legacy_id):
        if legacy_model not in self._legacy_mapping_cache:
            self._legacy_mapping_cache[legacy_model] = {
                row.legacy_id: row
                for row in LegacyKnowledgeMapping.objects.filter(
                    legacy_model=legacy_model,
                    migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
                ).select_related("node")
            }
        return self._legacy_mapping_cache[legacy_model].get(legacy_id)

    def base_queryset(
        self,
        context: SearchContext,
        *,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
    ) -> QuerySet:
        public = visibility == SearchVisibility.PUBLIC
        if context == SearchContext.WORKS:
            if public:
                return public_work_queryset()
            return Work.objects.all().prefetch_related("editions__contributions__person")
        if context == SearchContext.SCHOLARS:
            queryset = ScholarProfile.objects.select_related("person")
            if public:
                queryset = queryset.filter(
                    editorial_status="published",
                    person__authority_status=Person.AuthorityStatus.VERIFIED,
                )
            else:
                queryset = queryset.exclude(
                    person__authority_status__in=[
                        Person.AuthorityStatus.REJECTED,
                        Person.AuthorityStatus.ARCHIVED,
                        Person.AuthorityStatus.MERGED,
                    ]
                )
            return queryset
        if context == SearchContext.DISCIPLINES:
            queryset = Discipline.objects.all()
            return queryset.filter(editorial_status="published") if public else queryset
        if context == SearchContext.SUBDISCIPLINES:
            queryset = Subdiscipline.objects.select_related("discipline", "parent")
            return queryset.filter(editorial_status="published") if public else queryset
        if context == SearchContext.THEORIES:
            queryset = KnowledgeNode.objects.select_related("primary_discipline").prefetch_related(
                "aliases"
            ).filter(node_type__in=THEORY_NODE_TYPES)
            return queryset.filter(status="published") if public else queryset.exclude(status="archived")
        if context == SearchContext.TOPICS:
            queryset = Topic.objects.all()
            return queryset.filter(editorial_status="published") if public else queryset
        if context == SearchContext.READING_PATHS:
            queryset = ReadingPath.objects.select_related("primary_discipline").prefetch_related(
                "items__node", "items__work"
            )
            return queryset.filter(status="published") if public else queryset.exclude(status="archived")
        raise ValueError("Global context does not have one entity queryset.")

    def apply_query(
        self,
        queryset: QuerySet,
        context: SearchContext,
        query: str,
        *,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
    ) -> QuerySet:
        query = str(query or "").strip()
        if not query:
            return queryset.order_by(*_order_for_context(context))
        canonical, descriptive = _fields_for_context(context)
        exact_q = _lookup_q(canonical, "iexact", query)
        prefix_q = _lookup_q(canonical, "istartswith", query)
        contains_q = _lookup_q((*canonical, *descriptive), "icontains", query)
        alias_q = Q(pk__in=[])
        entity_type = _entity_type_for_context(context)
        if entity_type:
            ids = _lexicon_entity_ids(
                query,
                entity_type=entity_type,
                visibility=visibility,
            )
            if ids:
                alias_q = (
                    Q(person_id__in=ids)
                    if context == SearchContext.SCHOLARS
                    else Q(pk__in=ids)
                )
        return (
            queryset.filter(exact_q | prefix_q | contains_q | alias_q)
            .annotate(
                _search_rank=Case(
                    When(exact_q, then=Value(0)),
                    When(alias_q, then=Value(1)),
                    When(prefix_q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            )
            .distinct()
            .order_by("_search_rank", *_order_for_context(context))
        )

    def queryset(
        self,
        context: SearchContext,
        query: str = "",
        *,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
        base_queryset: QuerySet | None = None,
        filters: dict | None = None,
    ) -> QuerySet:
        queryset = base_queryset if base_queryset is not None else self.base_queryset(
            context,
            visibility=visibility,
        )
        queryset = self.apply_filters(queryset, context, filters or {})
        return self.apply_query(
            queryset,
            context,
            query,
            visibility=visibility,
        )

    def apply_filters(self, queryset: QuerySet, context: SearchContext, filters: dict) -> QuerySet:
        discipline = _filter_value(filters, "discipline")
        if context == SearchContext.WORKS:
            document_type = _filter_value(filters, "document_type")
            language = _filter_value(filters, "language")
            if document_type:
                queryset = queryset.filter(document_type=document_type)
            if language:
                queryset = queryset.filter(language=language)
        elif context == SearchContext.SUBDISCIPLINES and discipline:
            queryset = queryset.filter(discipline__slug=discipline)
        elif context == SearchContext.THEORIES:
            node_type = _filter_value(filters, "type") or _filter_value(filters, "node_type")
            if node_type:
                queryset = queryset.filter(node_type=node_type)
            if discipline:
                queryset = queryset.filter(
                    Q(primary_discipline__slug=discipline)
                    | Q(discipline_links__discipline__slug=discipline)
                ).distinct()
        elif context == SearchContext.TOPICS and discipline:
            queryset = queryset.filter(discipline_relations__discipline__slug=discipline).distinct()
        elif context == SearchContext.READING_PATHS and discipline:
            queryset = queryset.filter(primary_discipline__slug=discipline)
        return queryset

    def legacy_theory_queryset(
        self,
        query: str = "",
        *,
        visibility: SearchVisibility = SearchVisibility.PUBLIC,
        base_queryset: QuerySet | None = None,
        exclude_mapped: bool = False,
    ) -> QuerySet:
        queryset = base_queryset if base_queryset is not None else TheorySchool.objects.all()
        if visibility == SearchVisibility.PUBLIC:
            queryset = queryset.filter(editorial_status="published")
        if exclude_mapped:
            mapped_ids = LegacyKnowledgeMapping.objects.filter(
                legacy_model="TheorySchool",
                migration_status=LegacyKnowledgeMapping.MigrationStatus.MAPPED,
            ).values_list("legacy_id", flat=True)
            queryset = queryset.exclude(pk__in=mapped_ids)
        query = str(query or "").strip()
        if not query:
            return queryset.order_by("name")
        exact_q = Q(name__iexact=query)
        prefix_q = Q(name__istartswith=query)
        contains_q = (
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(search_aliases__icontains=query)
            | Q(key_themes__icontains=query)
        )
        return (
            queryset.filter(exact_q | prefix_q | contains_q)
            .annotate(
                _search_rank=Case(
                    When(exact_q, then=Value(0)),
                    When(prefix_q, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            )
            .distinct()
            .order_by("_search_rank", "name")
        )

    def legacy_global_work_queryset(self, query: str) -> QuerySet:
        """Compatibility matching for the existing Explore exact-search payload."""

        queryset = public_work_queryset()
        if not query:
            return queryset
        return queryset.filter(
            Q(title__icontains=query)
            | Q(subtitle__icontains=query)
            | Q(abstract__icontains=query)
            | Q(search_aliases__icontains=query)
            | Q(editions__contributions__person__preferred_name__icontains=query)
            | Q(editions__contributions__person__original_name__icontains=query)
            | Q(editions__contributions__person__aliases__icontains=query)
            | Q(knowledge_relations__theory_school__name__icontains=query)
            | Q(knowledge_relations__topic__name__icontains=query)
            | Q(knowledge_relations__concept__name__icontains=query)
        ).distinct()

    def legacy_global_scholar_queryset(self, query: str) -> QuerySet:
        queryset = self.base_queryset(SearchContext.SCHOLARS)
        if not query:
            return queryset
        return queryset.filter(
            Q(person__preferred_name__icontains=query)
            | Q(person__original_name__icontains=query)
            | Q(person__aliases__icontains=query)
            | Q(short_description__icontains=query)
            | Q(key_concerns__icontains=query)
        ).distinct()

    def legacy_global_topic_queryset(self, query: str) -> QuerySet:
        queryset = self.base_queryset(SearchContext.TOPICS)
        if not query:
            return queryset
        return queryset.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(search_aliases__icontains=query)
            | Q(key_concepts__icontains=query)
        ).distinct()

    def search(self, search_request: SearchRequest) -> dict:
        started = perf_counter()
        if search_request.context == SearchContext.GLOBAL:
            groups = []
            if search_request.query:
                for context in GLOBAL_CONTEXTS:
                    groups.append(self._group(context, search_request, global_mode=True))
            else:
                groups = [self._empty_group(context) for context in GLOBAL_CONTEXTS]
            total = sum(group["count"] for group in groups)
            pagination = {
                "page": 1,
                "limit": search_request.limit,
                "total": total,
                "total_pages": 1 if total else 0,
            }
        else:
            group = self._group(search_request.context, search_request, global_mode=False)
            groups = [group]
            total = group["count"]
            pagination = group["pagination"]
        return {
            "implementation_version": IMPLEMENTATION_VERSION,
            "context": search_request.context.value,
            "visibility": search_request.visibility.value,
            "query": search_request.query,
            "groups": groups,
            "total": total,
            "pagination": pagination,
            "latency_ms": round((perf_counter() - started) * 1000, 3),
        }

    def _empty_group(self, context: SearchContext) -> dict:
        return {
            "context": context.value,
            "label": CONTEXT_LABELS[context],
            "backend": "database",
            "count": 0,
            "results": [],
        }

    def _group(
        self,
        context: SearchContext,
        search_request: SearchRequest,
        *,
        global_mode: bool,
    ) -> dict:
        queryset = self.queryset(
            context,
            search_request.query,
            visibility=search_request.visibility,
            filters=search_request.filters,
        )
        if context == SearchContext.THEORIES:
            rows = list(queryset)
            legacy_rows = list(
                self.legacy_theory_queryset(
                    search_request.query,
                    visibility=search_request.visibility,
                    exclude_mapped=True,
                )
            )
            combined = [*rows, *legacy_rows]
            combined.sort(
                key=lambda row: (
                    int(getattr(row, "_search_rank", 4)),
                    str(
                        getattr(row, "canonical_name_zh", "")
                        or getattr(row, "name", "")
                    ).casefold(),
                )
            )
            total = len(combined)
            start = 0 if global_mode else (search_request.page - 1) * search_request.limit
            selected = combined[start : start + search_request.limit]
        else:
            total = queryset.count()
            start = 0 if global_mode else (search_request.page - 1) * search_request.limit
            selected = list(queryset[start : start + search_request.limit])
        results = [self._result(context, row, search_request.query) for row in selected]
        payload = {
            "context": context.value,
            "label": CONTEXT_LABELS[context],
            "backend": "database",
            "count": total,
            "results": results,
        }
        if not global_mode:
            payload["pagination"] = {
                "page": search_request.page,
                "limit": search_request.limit,
                "total": total,
                "total_pages": ceil(total / search_request.limit) if total else 0,
            }
        return payload

    def _result(self, context: SearchContext, row, query: str) -> dict:
        rank = int(getattr(row, "_search_rank", 4))
        match_type = {0: "exact", 1: "verified_alias", 2: "prefix", 3: "text"}.get(
            rank,
            "browse",
        )
        result = {
            "context": context.value,
            "entity_type": "",
            "id": str(row.pk),
            "title": "",
            "subtitle": "",
            "description": "",
            "url": "",
            "match": {
                "type": match_type,
                "query": query,
                "highlights": [query] if query else [],
            },
            "metadata": {},
        }
        if context == SearchContext.WORKS:
            edition = next(iter(row.editions.all()), None)
            contributors = [] if edition is None else [
                contribution.person.preferred_name
                for contribution in edition.contributions.all()
                if contribution.approved
            ]
            result.update(
                entity_type="work",
                title=row.title,
                subtitle="、".join(contributors[:3]) or row.original_title,
                description=row.abstract,
                url=f"/works/{edition.public_slug}" if edition else "",
                metadata={
                    "document_type": row.document_type,
                    "language": row.language,
                    "edition_id": str(edition.id) if edition else None,
                    "public_slug": edition.public_slug if edition else "",
                },
            )
        elif context == SearchContext.SCHOLARS:
            result.update(
                entity_type="person",
                id=str(row.person_id),
                title=row.person.preferred_name,
                subtitle=row.person.original_name,
                description=row.short_description or row.person.biography,
                url=f"/scholars/{row.slug}",
                metadata={
                    "profile_id": str(row.id),
                    "slug": row.slug,
                    "birth_year": row.person.birth_year,
                    "death_year": row.person.death_year,
                },
            )
        elif context == SearchContext.DISCIPLINES:
            result.update(
                entity_type="discipline",
                title=row.name,
                subtitle=row.foreign_name,
                description=row.description,
                url=f"/theories/disciplines/{row.slug}",
                metadata={"slug": row.slug},
            )
        elif context == SearchContext.SUBDISCIPLINES:
            mapping = self.canonical_mapping("Subdiscipline", row.id)
            result.update(
                entity_type="knowledge_node" if mapping else "subdiscipline",
                id=str(mapping.node_id if mapping else row.id),
                title=row.name,
                subtitle=row.foreign_name,
                description=row.description or row.research_object,
                url=f"/subdisciplines/{row.slug}",
                metadata={
                    "presentation_model": "Subdiscipline",
                    "presentation_id": str(row.id),
                    "slug": row.slug,
                    "discipline": row.discipline.name,
                },
            )
        elif context == SearchContext.THEORIES and isinstance(row, KnowledgeNode):
            result.update(
                entity_type="knowledge_node",
                title=row.canonical_name_zh,
                subtitle=row.canonical_name_en,
                description=row.summary or row.definition,
                url=f"/theories/nodes/{row.slug}",
                metadata={"slug": row.slug, "node_type": row.node_type},
            )
        elif context == SearchContext.THEORIES:
            result.update(
                entity_type="theory_school",
                title=row.name,
                description=row.description,
                url=f"/theory-schools/{row.slug}",
                metadata={"slug": row.slug, "presentation_model": "TheorySchool"},
            )
        elif context == SearchContext.TOPICS:
            result.update(
                entity_type="topic",
                title=row.name,
                description=row.description or row.problem_statement,
                url=f"/topics/{row.slug}",
                metadata={"slug": row.slug},
            )
        elif context == SearchContext.READING_PATHS:
            result.update(
                entity_type="reading_path",
                title=row.title,
                subtitle=row.audience,
                description=row.introduction,
                url=f"/theories/reading-paths/{row.slug}",
                metadata={
                    "slug": row.slug,
                    "difficulty": row.difficulty,
                    "estimated_reading": row.estimated_reading,
                },
            )
        return result
