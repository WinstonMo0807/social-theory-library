"""Public knowledge page and admin-management contracts.

The registry is a read model over existing canonical, curated and computed
stores.  It does not own content and does not create a second mutation path.
It exists so public pages, Knowledge Studio and the dedicated Scholar, Theory
and Topic workspaces can describe the same management surface.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable

from catalog.models import (
    EditorialRevision,
    KnowledgeNode,
    KnowledgePublicationStatus,
    Person,
    RelationReviewStatus,
    ScholarProfile,
    Topic,
)


EDITORIAL = "editorial"
RELATION = "relation"
CURATED = "curated"
COMPUTED = "computed"
AI_OPTIONAL = "ai_optional"

REQUIRED = "required"
RECOMMENDED = "recommended"
OPTIONAL = "optional"


@dataclass(frozen=True)
class PublicModuleContract:
    module_id: str
    display_name: str
    public_component: str
    content_source_type: str
    data_source_type: str
    completeness_group: str
    serializer_fields: tuple[str, ...]
    requirement: str
    admin_editor_section: str
    preview_anchor: str
    projection_dependencies: tuple[str, ...] = ("public",)
    canonical_fields: tuple[str, ...] = ()
    relations: tuple[str, ...] = ()
    curated_fields: tuple[str, ...] = ()
    computed_fields: tuple[str, ...] = ()
    legacy_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class PublicPageContract:
    object_type: str
    page_id: str
    display_name: str
    route: str
    public_component: str
    serializer: str
    api: str
    modules: tuple[PublicModuleContract, ...]
    preview_support: bool
    admin_management_destination: str
    compatibility: bool = False


MODULE_GROUPS = {
    "scholar-identity": "Identity",
    "scholar-works": "Evidence",
    "scholar-representative-works": "Curation",
    "scholar-concepts": "Knowledge",
    "scholar-concept-map": "Knowledge",
    "scholar-network": "Knowledge",
    "scholar-theories": "Knowledge",
    "scholar-frequently-read": "Curation",
    "scholar-curated-claims": "Curation",
    "theory-identity": "Identity",
    "theory-disciplines": "Knowledge",
    "theory-topics": "Knowledge",
    "theory-scholars": "Knowledge",
    "theory-relations": "Knowledge",
    "theory-works": "Evidence",
    "theory-evidence": "Evidence",
    "theory-reading-paths": "Curation",
    "theory-curated-claims": "Curation",
    "topic-identity": "Identity",
    "topic-works": "Evidence",
    "topic-evidence": "Evidence",
    "topic-curated-works": "Curation",
    "topic-scholars": "Knowledge",
    "topic-theories": "Knowledge",
    "topic-concepts": "Knowledge",
    "topic-reading-paths": "Curation",
    "topic-curated-claims": "Curation",
}


def _module(
    module_id: str,
    display_name: str,
    component: str,
    source: str,
    fields: Iterable[str],
    requirement: str,
    section: str,
    *,
    group: str | None = None,
    canonical: Iterable[str] = (),
    relations: Iterable[str] = (),
    curated: Iterable[str] = (),
    computed: Iterable[str] = (),
    projections: Iterable[str] = ("public",),
    legacy: Iterable[str] = (),
) -> PublicModuleContract:
    return PublicModuleContract(
        module_id=module_id,
        display_name=display_name,
        public_component=component,
        content_source_type=source,
        data_source_type=source,
        completeness_group=group or MODULE_GROUPS.get(module_id, "Core Content"),
        serializer_fields=tuple(fields),
        requirement=requirement,
        admin_editor_section=section,
        preview_anchor=module_id,
        projection_dependencies=tuple(projections),
        canonical_fields=tuple(canonical),
        relations=tuple(relations),
        curated_fields=tuple(curated),
        computed_fields=tuple(computed),
        legacy_sources=tuple(legacy),
    )


# Module definitions deliberately use public serializer field names.  This lets
# the coverage test detect a page that cannot be rendered from its registered
# serializer instead of maintaining preview-only data.
SCHOLAR_MODULES = {
    "identity": _module(
        "scholar-identity", "身份与名称", "ScholarIdentity", EDITORIAL,
        ("person",), REQUIRED, "identity", canonical=("person",),
        projections=("public", "query_lexicon"),
    ),
    "position": _module(
        "scholar-position", "简介与学术位置", "ScholarOverview", EDITORIAL,
        ("short_description", "affiliations", "key_concerns"), RECOMMENDED,
        "overview", canonical=("short_description", "affiliations", "key_concerns"),
    ),
    "biography": _module(
        "scholar-biography", "完整传记", "ScholarBiography", EDITORIAL,
        ("person.biography",), RECOMMENDED, "biography", canonical=("person",),
    ),
    "timeline": _module(
        "scholar-timeline", "生平时间线", "ScholarTimeline", EDITORIAL,
        ("timeline",), OPTIONAL, "timeline", canonical=("timeline",),
        projections=("public", "timeline"),
    ),
    "quote": _module(
        "scholar-quote", "代表引文与出处", "ScholarQuote", EDITORIAL,
        ("featured_quote", "quote_source"), OPTIONAL, "overview",
        canonical=("featured_quote", "quote_source"),
    ),
    "works": _module(
        "scholar-works", "全部馆藏作品", "ScholarWorks", COMPUTED,
        ("works",), RECOMMENDED, "works", computed=("Contribution", "Edition", "Work"),
        projections=("public", "fulltext", "recommendation"),
    ),
    "representative_works": _module(
        "scholar-representative-works", "代表作品", "ScholarEssentialWorks", CURATED,
        ("curated.essential_works",), RECOMMENDED, "curation-works", curated=("curation.essential_work_ids",),
        projections=("public", "recommendation"),
    ),
    "concepts": _module(
        "scholar-concepts", "关键概念", "ScholarConcepts", CURATED,
        ("curated.key_concepts",), RECOMMENDED, "curation-concepts", curated=("curation.key_concepts",),
    ),
    "concept_map": _module(
        "scholar-concept-map", "概念图", "ScholarConceptMap", CURATED,
        ("curated.concept_map",), OPTIONAL, "curation-concept-map", curated=("curation.concept_map",),
        projections=("public", "knowledge_graph"),
    ),
    "network": _module(
        "scholar-network", "学术关系", "ScholarNetwork", CURATED,
        ("curated.network",), OPTIONAL, "relations", curated=("curation.network",),
        relations=("PersonNodeRelation",), projections=("public", "knowledge_graph"),
    ),
    "theories": _module(
        "scholar-theories", "理论传统", "ScholarTheories", RELATION,
        ("knowledge_nodes",), RECOMMENDED, "knowledge-relations",
        relations=("PersonNodeRelation", "WorkNodeRelation"),
        projections=("public", "knowledge_graph", "recommendation"),
    ),
    "frequent": _module(
        "scholar-frequently-read", "经常连着阅读", "ScholarFrequentlyRead", CURATED,
        ("curated.frequently_read_scholars",), OPTIONAL, "curation-related", curated=("curation.frequently_read_scholar_ids",),
        projections=("public", "recommendation"),
    ),
    "claims": _module(
        "scholar-curated-claims", "核心观点、批评与回应", "CuratedClaimGroups", AI_OPTIONAL,
        ("curated_claims",), OPTIONAL, "claims", curated=("CuratedClaim",),
        projections=("public", "claim_index"),
    ),
}

THEORY_MODULES = {
    "identity": _module(
        "theory-identity", "名称、外文名与别名", "KnowledgeNodeHero", EDITORIAL,
        ("canonical_name_zh", "canonical_name_en", "aliases"), REQUIRED, "identity",
        canonical=("canonical_name_zh", "canonical_name_en", "aliases"),
        projections=("public", "query_lexicon"),
    ),
    "definition": _module(
        "theory-definition", "定义与摘要", "KnowledgeNodeDefinition", EDITORIAL,
        ("definition", "summary"), REQUIRED, "definition", canonical=("definition", "summary"),
    ),
    "questions": _module(
        "theory-core-questions", "核心问题", "KnowledgeNodeQuestions", EDITORIAL,
        ("core_questions",), RECOMMENDED, "core-content", canonical=("core_questions",),
    ),
    "propositions": _module(
        "theory-propositions", "基本命题与理论边界", "KnowledgeNodePropositions", EDITORIAL,
        ("basic_propositions", "theoretical_boundary"), RECOMMENDED, "core-content",
        canonical=("basic_propositions", "theoretical_boundary"),
    ),
    "development": _module(
        "theory-development", "形成时期与发展脉络", "KnowledgeNodeDevelopment", EDITORIAL,
        ("start_year", "end_year", "period_label"), OPTIONAL, "development",
        canonical=("start_year", "end_year", "period_label"), projections=("public", "timeline"),
    ),
    "disciplines": _module(
        "theory-disciplines", "学科与子学科", "KnowledgeNodeDisciplines", RELATION,
        ("discipline_links", "subdiscipline_links"), RECOMMENDED, "knowledge-structure",
        relations=("KnowledgeNodeDiscipline", "KnowledgeNodeSubdiscipline"),
        projections=("public", "knowledge_graph"),
    ),
    "topics": _module(
        "theory-topics", "主题", "KnowledgeNodeTopics", RELATION,
        ("topic_links",), RECOMMENDED, "knowledge-structure", relations=("KnowledgeNodeTopic",),
        projections=("public", "knowledge_graph", "recommendation"),
    ),
    "scholars": _module(
        "theory-scholars", "代表学者", "KnowledgeNodeScholars", RELATION,
        ("representative_scholars",), RECOMMENDED, "scholars",
        relations=("PersonNodeRelation",), projections=("public", "knowledge_graph"),
    ),
    "relations": _module(
        "theory-relations", "理论关系", "KnowledgeNodeRelations", RELATION,
        ("direct_relations",), OPTIONAL, "relations", relations=("KnowledgeRelation",),
        projections=("public", "knowledge_graph"),
    ),
    "works": _module(
        "theory-works", "相关馆藏", "KnowledgeNodeWorks", COMPUTED,
        ("work_groups",), RECOMMENDED, "works", computed=("WorkNodeRelation",),
        projections=("public", "recommendation"),
    ),
    "evidence": _module(
        "theory-evidence", "馆藏证据", "KnowledgeNodeEvidence", COMPUTED,
        ("evidence",), OPTIONAL, "evidence", computed=("EvidenceSnippet", "EvidenceSpan"),
        projections=("public", "fulltext"),
    ),
    "reading_paths": _module(
        "theory-reading-paths", "阅读路径中的理论位置", "KnowledgeNodeReadingPaths", COMPUTED,
        ("reading_path_count",), OPTIONAL, "reading", computed=("ReadingPathItem",),
        projections=("public", "reading_path_support"),
    ),
    "claims": _module(
        "theory-curated-claims", "核心观点、批评与回应", "CuratedClaimGroups", AI_OPTIONAL,
        ("curated_claims",), OPTIONAL, "claims", curated=("CuratedClaim",),
        projections=("public", "claim_index"),
    ),
}

TOPIC_MODULES = {
    "identity": _module(
        "topic-identity", "名称与简介", "TopicHero", EDITORIAL,
        ("name", "description"), REQUIRED, "identity", canonical=("name", "description"),
        projections=("public", "query_lexicon"),
    ),
    "problem": _module(
        "topic-problem", "问题范围与核心问题", "TopicQuestions", EDITORIAL,
        ("problem_statement", "core_questions"), RECOMMENDED, "research-framework",
        canonical=("problem_statement", "core_questions"),
    ),
    "framework": _module(
        "topic-framework", "形成背景、研究维度与方法", "TopicFramework", EDITORIAL,
        ("formation_context", "research_dimensions", "methods"), RECOMMENDED,
        "research-framework", canonical=("formation_context", "research_dimensions", "methods"),
    ),
    "works": _module(
        "topic-works", "馆藏作品", "TopicWorks", COMPUTED,
        ("work_count",), RECOMMENDED, "works", computed=("WorkTopicRelation",),
        projections=("public", "recommendation"),
    ),
    "evidence": _module(
        "topic-evidence", "主题相关原文", "TopicEvidence", COMPUTED,
        ("passages",), OPTIONAL, "evidence", computed=("Passage", "EvidenceSpan"),
        projections=("public", "fulltext"),
    ),
    "curated_works": _module(
        "topic-curated-works", "奠基文献与推荐作品", "TopicCuratedWorks", CURATED,
        ("curated.foundational_works", "curated.recent_works"), OPTIONAL, "curation-works", curated=("curation.foundational_work_ids", "curation.recent_work_ids"),
        projections=("public", "recommendation"),
    ),
    "scholars": _module(
        "topic-scholars", "代表学者", "TopicScholars", RELATION,
        ("curated.related_scholars",), RECOMMENDED, "knowledge-relations",
        relations=("PersonTopicRelation",), curated=("curation.related_scholar_ids",),
        projections=("public", "knowledge_graph"),
    ),
    "theories": _module(
        "topic-theories", "理论传统", "TopicTheories", RELATION,
        ("knowledge_nodes", "linked_theories"), RECOMMENDED, "knowledge-relations",
        relations=("KnowledgeNodeTopic",), projections=("public", "knowledge_graph"),
        legacy=("TopicTheoryRelation -> TheorySchool",),
    ),
    "concepts": _module(
        "topic-concepts", "核心概念", "TopicConcepts", EDITORIAL,
        ("key_concepts", "knowledge_nodes"), RECOMMENDED, "knowledge-relations",
        canonical=("key_concepts",), relations=("KnowledgeNodeTopic",),
    ),
    "timeline": _module(
        "topic-timeline", "发展时间线", "TopicTimeline", EDITORIAL,
        ("timeline",), OPTIONAL, "development", canonical=("timeline",),
        projections=("public", "timeline"),
    ),
    "reading_paths": _module(
        "topic-reading-paths", "阅读路径", "TopicReadingPaths", CURATED,
        ("curated.reading_paths",), OPTIONAL, "reading", curated=("curation.reading_paths",),
        projections=("public", "reading_path_support"),
    ),
    "claims": _module(
        "topic-curated-claims", "观点、批评与回应", "CuratedClaimGroups", AI_OPTIONAL,
        ("curated_claims",), OPTIONAL, "claims", curated=("CuratedClaim",),
        projections=("public", "claim_index"),
    ),
}


def _page(
    object_type: str,
    page_id: str,
    display_name: str,
    route: str,
    component: str,
    modules: Iterable[PublicModuleContract],
    admin: str,
    *,
    serializer: str | None = None,
    api: str | None = None,
    compatibility: bool = False,
    preview_support: bool = True,
) -> PublicPageContract:
    serializers = {
        "scholar": ("ScholarProfileSerializer", "/api/catalog/scholars/{slug}/"),
        "theory": (
            "KnowledgeNodeDetailSerializer",
            "/api/catalog/theory-system/nodes/{slug}/",
        ),
        "topic": ("TopicSerializer", "/api/catalog/topics/{slug}/"),
    }
    default_serializer, default_api = serializers[object_type]
    return PublicPageContract(
        object_type=object_type,
        page_id=page_id,
        display_name=display_name,
        route=route,
        public_component=component,
        serializer=serializer or default_serializer,
        api=api or default_api,
        modules=tuple(modules),
        preview_support=preview_support,
        admin_management_destination=admin,
        compatibility=compatibility,
    )


PUBLIC_PAGE_CONTRACTS: tuple[PublicPageContract, ...] = (
    _page("scholar", "overview", "概览", "/scholars/{slug}", "ScholarPublicView", (SCHOLAR_MODULES["identity"], SCHOLAR_MODULES["position"], SCHOLAR_MODULES["quote"], SCHOLAR_MODULES["representative_works"], SCHOLAR_MODULES["claims"]), "/admin/scholars/{id}"),
    _page("scholar", "biography", "完整传记", "/scholars/{slug}/biography", "ScholarSectionPublicView", (SCHOLAR_MODULES["biography"],), "/admin/scholars/{id}?section=biography"),
    _page("scholar", "timeline", "生平时间线", "/scholars/{slug}/timeline", "ScholarSectionPublicView", (SCHOLAR_MODULES["timeline"],), "/admin/scholars/{id}?section=timeline"),
    _page("scholar", "works", "重要文献与全部作品", "/scholars/{slug}/works", "ScholarSectionPublicView", (SCHOLAR_MODULES["works"], SCHOLAR_MODULES["representative_works"]), "/admin/scholars/{id}?section=works"),
    _page("scholar", "concepts", "关键概念", "/scholars/{slug}/concepts", "ScholarSectionPublicView", (SCHOLAR_MODULES["concepts"],), "/admin/scholars/{id}?section=concepts"),
    _page("scholar", "concept-map", "概念图", "/scholars/{slug}/concept-map", "ScholarSectionPublicView", (SCHOLAR_MODULES["concept_map"],), "/admin/scholars/{id}?section=concept-map"),
    _page("scholar", "network", "学术关系", "/scholars/{slug}/network", "ScholarSectionPublicView", (SCHOLAR_MODULES["network"],), "/admin/scholars/{id}?section=network"),
    _page("scholar", "theories", "理论传统", "/scholars/{slug}/theories", "ScholarSectionPublicView", (SCHOLAR_MODULES["theories"],), "/admin/scholars/{id}?section=theories"),
    _page("scholar", "frequently-read", "经常连着阅读", "/scholars/{slug}/frequently-read", "ScholarSectionPublicView", (SCHOLAR_MODULES["frequent"],), "/admin/scholars/{id}?section=frequently-read"),
    _page("theory", "overview", "理论概览", "/theories/nodes/{slug}", "KnowledgeNodePublicView", (THEORY_MODULES["identity"], THEORY_MODULES["definition"], THEORY_MODULES["questions"], THEORY_MODULES["propositions"], THEORY_MODULES["development"], THEORY_MODULES["disciplines"], THEORY_MODULES["topics"], THEORY_MODULES["scholars"], THEORY_MODULES["relations"], THEORY_MODULES["works"], THEORY_MODULES["evidence"], THEORY_MODULES["reading_paths"], THEORY_MODULES["claims"]), "/admin/theories/{id}"),
    _page("theory", "graph", "理论图谱中的本理论", "/theories/graph?center={slug}", "TheoryGraph", (THEORY_MODULES["relations"], THEORY_MODULES["scholars"]), "/admin/theories/{id}?section=relations", serializer="LocalTheoryGraphSerializer", api="/api/catalog/theory-system/graph/?center={slug}"),
    _page("theory", "timeline", "时间线", "/theories/timeline?node={slug}", "TheoryTimeline", (THEORY_MODULES["development"],), "/admin/theories/{id}?section=timeline", serializer="TheoryTimelineEventSerializer", api="/api/catalog/theory-system/timeline/?node={slug}"),
    _page("theory", "discipline-entry", "学科中的理论入口", "/theories/disciplines/{discipline_slug}", "DisciplineTheoryView", (THEORY_MODULES["disciplines"],), "/admin/theories/{id}?section=disciplines", serializer="TheoryDisciplinePageSerializer", api="/api/catalog/theory-system/disciplines/{discipline_slug}/", preview_support=False),
    _page("theory", "scholar-entry", "学者中的理论入口", "/scholars/{scholar_slug}/theories", "ScholarSectionPublicView", (THEORY_MODULES["scholars"],), "/admin/theories/{id}?section=scholars", serializer="ScholarProfileSerializer", api="/api/catalog/scholars/{scholar_slug}/", preview_support=False),
    _page("theory", "topic-entry", "主题中的理论入口", "/topics/{topic_slug}/theory-schools", "TopicSectionPublicView", (THEORY_MODULES["topics"],), "/admin/theories/{id}?section=topics", serializer="TopicSerializer", api="/api/catalog/topics/{topic_slug}/", preview_support=False),
    _page("theory", "reading-path", "Reading Path", "/theories/reading-paths/{path_slug}", "ReadingPathPublicView", (THEORY_MODULES["reading_paths"],), "/admin/theories/{id}?section=reading", serializer="ReadingPathSerializer", api="/api/catalog/theory-system/reading-paths/{path_slug}/"),
    _page("topic", "overview", "概览", "/topics/{slug}", "TopicPublicView", (TOPIC_MODULES["identity"], TOPIC_MODULES["problem"], TOPIC_MODULES["framework"], TOPIC_MODULES["evidence"], TOPIC_MODULES["claims"]), "/admin/topics/{id}"),
    _page("topic", "works", "馆藏作品", "/topics/{slug}/works", "TopicSectionPublicView", (TOPIC_MODULES["works"], TOPIC_MODULES["curated_works"]), "/admin/topics/{id}?section=works"),
    _page("topic", "recent", "最新入库", "/topics/{slug}/recent", "TopicSectionPublicView", (TOPIC_MODULES["works"], TOPIC_MODULES["curated_works"]), "/admin/topics/{id}?section=works"),
    _page("topic", "scholars", "代表学者", "/topics/{slug}/scholars", "TopicSectionPublicView", (TOPIC_MODULES["scholars"],), "/admin/topics/{id}?section=scholars"),
    _page("topic", "theory-schools", "理论传统", "/topics/{slug}/theory-schools", "TopicSectionPublicView", (TOPIC_MODULES["theories"],), "/admin/topics/{id}?section=theories"),
    _page("topic", "timeline", "发展时间线", "/topics/{slug}/timeline", "TopicSectionPublicView", (TOPIC_MODULES["timeline"],), "/admin/topics/{id}?section=timeline"),
    _page("topic", "reading-paths", "阅读路径", "/topics/{slug}/reading-paths", "TopicSectionPublicView", (TOPIC_MODULES["reading_paths"],), "/admin/topics/{id}?section=reading-paths"),
    _page("topic", "concepts", "核心概念", "/topics/{slug}/concepts", "TopicSectionPublicView", (TOPIC_MODULES["concepts"],), "/admin/topics/{id}?section=concepts"),
)


LEGACY_PUBLIC_DEPENDENCIES = (
    {
        "public_route": "/theory-schools/{slug}/*",
        "module": "legacy theory pages",
        "legacy_source": "TheorySchool and WorkKnowledgeRelation",
        "canonical_equivalent": "KnowledgeNode(THEORY_TRADITION), WorkNodeRelation and KnowledgeRelation",
        "fallback_reason": "compatibility route remains public during identity backfill",
        "migration_readiness": "inventory_and_mapping_required",
    },
    {
        "public_route": "/topics/{slug}/theory-schools",
        "module": "topic theories legacy supplement",
        "legacy_source": "TopicTheoryRelation -> TheorySchool",
        "canonical_equivalent": "KnowledgeNodeTopic",
        "fallback_reason": "TopicSerializer still exposes linked_theories for compatibility",
        "migration_readiness": "mapping_available_per_relation",
    },
    {
        "public_route": "/scholars/{slug}/theories",
        "module": "curated related theories legacy supplement",
        "legacy_source": "ScholarProfile.curation.related_theory_ids -> TheorySchool",
        "canonical_equivalent": "PersonNodeRelation",
        "fallback_reason": "existing curation remains readable; new workspace writes normalized relations",
        "migration_readiness": "mapping_required",
    },
)


SOURCE_AUTHORITY_MATRIX = (
    {"identity": "theory", "canonical_source": "KnowledgeNode(THEORY_TRADITION)", "relation_sources": ("KnowledgeRelation", "WorkNodeRelation", "PersonNodeRelation", "KnowledgeNodeDiscipline", "KnowledgeNodeSubdiscipline", "KnowledgeNodeTopic")},
    {"identity": "concept", "canonical_source": "KnowledgeNode(CONCEPT)", "relation_sources": ("KnowledgeRelation", "WorkNodeRelation", "PersonNodeRelation")},
    {"identity": "debate", "canonical_source": "KnowledgeNode(DEBATE)", "relation_sources": ("KnowledgeRelation", "WorkNodeRelation", "PersonNodeRelation")},
    {"identity": "scholar", "canonical_source": "Person + ScholarProfile", "relation_sources": ("PersonNodeRelation", "PersonTopicRelation", "Contribution")},
    {"identity": "topic", "canonical_source": "Topic", "relation_sources": ("KnowledgeNodeTopic", "WorkTopicRelation", "PersonTopicRelation", "TopicDisciplineRelation", "TopicSubdisciplineRelation")},
)


# This inventory mirrors the checked-in App Router files.  Object routes must
# have a PublicPageContract.  Directory routes are managed by the matching
# directory workspace, while legacy routes remain explicit compatibility
# surfaces until their normalized backfill is complete.
AUDITED_OBJECT_PUBLIC_ROUTES = {
    "scholar": {
        "/scholars/{slug}",
        "/scholars/{slug}/biography",
        "/scholars/{slug}/timeline",
        "/scholars/{slug}/works",
        "/scholars/{slug}/concepts",
        "/scholars/{slug}/concept-map",
        "/scholars/{slug}/network",
        "/scholars/{slug}/theories",
        "/scholars/{slug}/frequently-read",
    },
    "theory": {
        "/theories/nodes/{slug}",
        "/theories/graph",
        "/theories/timeline",
        "/theories/disciplines/{discipline_slug}",
        "/scholars/{scholar_slug}/theories",
        "/topics/{topic_slug}/theory-schools",
        "/theories/reading-paths/{path_slug}",
    },
    "topic": {
        "/topics/{slug}",
        "/topics/{slug}/works",
        "/topics/{slug}/recent",
        "/topics/{slug}/scholars",
        "/topics/{slug}/theory-schools",
        "/topics/{slug}/timeline",
        "/topics/{slug}/reading-paths",
        "/topics/{slug}/concepts",
    },
}

AUDITED_DIRECTORY_PUBLIC_ROUTES = (
    {"route": "/scholars", "admin": "/admin/scholars", "object_type": "scholar"},
    {"route": "/topics", "admin": "/admin/topics", "object_type": "topic"},
    {"route": "/theories", "admin": "/admin/theories", "object_type": "theory"},
    {"route": "/theories/directory", "admin": "/admin/theories", "object_type": "theory"},
)

AUDITED_LEGACY_PUBLIC_ROUTES = (
    "/theory-schools",
    "/theory-schools/{slug}",
    "/theory-schools/{slug}/{section}",
    "/theory-schools/graph",
    "/theory-schools/timeline",
)


ADMIN_FIELD_USAGE = {
    "scholar": {
        "slug": ("scholar-identity", "Scholar route", "Search"),
        "short_description": ("scholar-position",),
        "affiliations": ("scholar-position",),
        "key_concerns": ("scholar-position", "Search"),
        "timeline": ("scholar-timeline",),
        "featured_quote": ("scholar-quote",),
        "quote_source": ("scholar-quote",),
        "curation": (
            "scholar-representative-works",
            "scholar-concepts",
            "scholar-concept-map",
            "scholar-network",
            "scholar-frequently-read",
        ),
        "editorial_status": ("Public visibility",),
        "person": ("scholar-identity", "Work contributor display", "QueryLexicon"),
    },
    "theory": {
        "canonical_name_zh": ("theory-identity", "Search", "QueryLexicon"),
        "canonical_name_en": ("theory-identity", "Search", "QueryLexicon"),
        "node_type": ("theory-identity", "Public route classification"),
        "slug": ("theory-identity", "Theory route", "Search"),
        "summary": ("theory-definition",),
        "definition": ("theory-definition",),
        "core_questions": ("theory-core-questions",),
        "basic_propositions": ("theory-propositions",),
        "theoretical_boundary": ("theory-propositions",),
        "start_year": ("theory-development", "Theory timeline"),
        "end_year": ("theory-development", "Theory timeline"),
        "period_label": ("theory-development", "Theory timeline"),
        "parent": ("Theory hierarchy", "Knowledge graph"),
        "primary_discipline": ("theory-disciplines", "Theory directory"),
        "sort_order": ("Theory directory order",),
        "status": ("Public visibility",),
        "aliases": ("theory-identity", "Search", "QueryLexicon"),
        "discipline_links": ("theory-disciplines",),
        "subdiscipline_links": ("theory-disciplines",),
        "topic_links": ("theory-topics",),
    },
    "topic": {
        "name": ("topic-identity", "Search", "QueryLexicon"),
        "slug": ("topic-identity", "Topic route", "Search"),
        "search_aliases": ("Search", "QueryLexicon"),
        "description": ("topic-identity",),
        "problem_statement": ("topic-problem",),
        "core_questions": ("topic-problem",),
        "research_dimensions": ("topic-framework",),
        "methods": ("topic-framework",),
        "formation_context": ("topic-framework",),
        "key_concepts": ("topic-concepts",),
        "timeline": ("topic-timeline",),
        "curation": ("topic-curated-works", "topic-reading-paths"),
        "editorial_status": ("Public visibility",),
        "discipline_relations": ("Topic directory", "Knowledge graph"),
        "theory_relations": ("topic-theories",),
        "subdiscipline_relations": ("Topic directory", "Knowledge graph"),
    },
}


def admin_field_usage(object_type: str) -> list[dict[str, Any]]:
    return [
        {
            "field": field,
            "classification": "public_consumer",
            "consumers": list(consumers),
        }
        for field, consumers in sorted(ADMIN_FIELD_USAGE.get(object_type, {}).items())
    ]


def page_contracts(object_type: str) -> tuple[PublicPageContract, ...]:
    return tuple(row for row in PUBLIC_PAGE_CONTRACTS if row.object_type == object_type)


def _value(data: dict[str, Any], field: str) -> Any:
    current: Any = data
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _present(value: Any) -> bool:
    if value is None or value == "":
        return False
    if isinstance(value, dict):
        return any(_present(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_present(item) for item in value)
    if isinstance(value, (int, float)):
        return value > 0
    return True


def _module_state(
    module: PublicModuleContract,
    data: dict[str, Any],
    *,
    changed_fields: set[str],
    candidate_available: bool,
    evidence_available: bool,
) -> dict[str, Any]:
    populated = [field for field in module.serializer_fields if _present(_value(data, field))]
    missing = [field for field in module.serializer_fields if field not in populated]
    computed_empty = module.content_source_type == COMPUTED and not populated
    ai_empty = module.content_source_type == AI_OPTIONAL and not populated
    changed = bool(changed_fields.intersection(module.canonical_fields or module.serializer_fields))
    if changed:
        status = "draft"
    elif populated and missing:
        status = "partial"
    elif populated:
        status = "complete"
    elif computed_empty:
        status = "empty_computed"
    elif ai_empty:
        status = "not_curated"
    else:
        status = "missing"
    return {
        **asdict(module),
        "populated_fields": populated,
        "missing_fields": missing,
        "available": bool(populated),
        "complete": not missing or computed_empty,
        "status": status,
        "has_draft": changed,
        "has_candidate": candidate_available and module.content_source_type in {CURATED, AI_OPTIONAL},
        "has_evidence": evidence_available and module.content_source_type in {CURATED, AI_OPTIONAL, COMPUTED},
        "counts_as_manual_missing": bool(missing) and not computed_empty and not ai_empty,
        "empty_reason": (
            "馆内目前没有关联内容" if computed_empty else
            "尚未策展；自动建议当前未启用" if ai_empty else
            "管理员尚未填写" if not populated else ""
        ),
    }


def _target_route_values(page: PublicPageContract, target) -> dict[str, str]:
    values = {
        "id": str(target.pk),
        "slug": getattr(target, "slug", ""),
        "discipline_slug": getattr(getattr(target, "primary_discipline", None), "slug", ""),
        "scholar_slug": "",
        "topic_slug": "",
        "path_slug": "",
    }
    if page.object_type == "theory":
        scholar_relation = target.person_relations.filter(
            status="published",
            person__authority_status=Person.AuthorityStatus.VERIFIED,
            person__scholar_profile__editorial_status=KnowledgePublicationStatus.PUBLISHED,
        ).select_related("person__scholar_profile").first()
        topic_relation = target.topic_links.filter(
            status="published",
            topic__editorial_status=KnowledgePublicationStatus.PUBLISHED,
        ).select_related("topic").first()
        reading_path_item = target.reading_path_items.filter(
            reading_path__status=KnowledgePublicationStatus.PUBLISHED,
        ).select_related("reading_path").first()
        values.update(
            {
                "scholar_slug": (
                    scholar_relation.person.scholar_profile.slug
                    if scholar_relation is not None
                    else ""
                ),
                "topic_slug": topic_relation.topic.slug if topic_relation is not None else "",
                "path_slug": (
                    reading_path_item.reading_path.slug
                    if reading_path_item is not None
                    else ""
                ),
            }
        )
    return values


def _format_route(template: str, values: dict[str, str]) -> str:
    try:
        return template.format(**values)
    except (KeyError, ValueError):
        return template


def _page_route(page: PublicPageContract, target) -> str:
    values = _target_route_values(page, target)
    route = _format_route(page.route, values)
    if page.object_type != "theory":
        return route
    fallback = f"/theories/nodes/{values['slug']}"
    if "{discipline_slug}" in page.route and not values["discipline_slug"]:
        return f"{fallback}?module=theory-disciplines"
    if "{scholar_slug}" in page.route and not values["scholar_slug"]:
        return f"{fallback}?module=theory-scholars"
    if "{topic_slug}" in page.route and not values["topic_slug"]:
        return f"{fallback}?module=theory-topics"
    if "{path_slug}" in page.route and not values["path_slug"]:
        return f"{fallback}?module=theory-reading-paths"
    return route


def _diff_value(published: Any, draft: Any) -> dict[str, Any]:
    if published == draft:
        return {"kind": "unchanged"}
    if isinstance(published, list) and isinstance(draft, list):
        published_keys = {repr(row): row for row in published}
        draft_keys = {repr(row): row for row in draft}
        return {
            "kind": "collection",
            "added": [draft_keys[key] for key in draft_keys.keys() - published_keys.keys()][:20],
            "removed": [published_keys[key] for key in published_keys.keys() - draft_keys.keys()][:20],
        }
    return {"kind": "changed", "published": published, "draft": draft}


def draft_published_diff(
    published: dict[str, Any] | None,
    draft: dict[str, Any] | None,
    changed_fields: Iterable[str],
) -> list[dict[str, Any]]:
    if not draft:
        return []
    published = published or {}
    rows = []
    for field in changed_fields:
        comparison = _diff_value(_value(published, field), _value(draft, field))
        if comparison["kind"] != "unchanged":
            rows.append({"field": field, **comparison})
    return rows


def _public_eligibility(object_type: str, target) -> dict[str, Any]:
    if object_type == "scholar":
        profile_published = target.editorial_status == KnowledgePublicationStatus.PUBLISHED
        person_verified = target.person.authority_status == Person.AuthorityStatus.VERIFIED
        return {
            "eligible": profile_published and person_verified,
            "profile_published": profile_published,
            "person_authority_status": target.person.authority_status,
            "reason": "" if profile_published and person_verified else (
                "person_authority_not_verified" if profile_published else "profile_not_published"
            ),
        }
    status = getattr(target, "status", getattr(target, "editorial_status", ""))
    return {"eligible": status == KnowledgePublicationStatus.PUBLISHED, "reason": "" if status == KnowledgePublicationStatus.PUBLISHED else "object_not_published"}


def _appearances(object_type: str, target) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if object_type == "scholar":
        work_count = target.person.contributions.filter(
            approved=True, edition__state="published"
        ).values("edition__work_id").distinct().count()
        theory_count = target.person.node_relations.filter(
            status="published", node__status="published"
        ).values("node_id").distinct().count()
        topic_count = target.person.topic_relations.filter(
            review_status=RelationReviewStatus.APPROVED,
            topic__editorial_status="published",
        ).values("topic_id").distinct().count()
        rows.extend((
            {"page_id": "overview", "label": "学者主要页面", "count": 1, "route": f"/scholars/{target.slug}"},
            {"page_id": "works", "label": "馆藏作品", "count": work_count, "route": f"/scholars/{target.slug}/works"},
            {"page_id": "theories", "label": "理论传统", "count": theory_count, "route": f"/scholars/{target.slug}/theories"},
            {"page_id": "topic-entry", "label": "主题页面", "count": topic_count, "route": f"/scholars/{target.slug}/network"},
        ))
    elif object_type == "theory":
        relation_count = target.outgoing_relations.filter(status="published").count() + target.incoming_relations.filter(status="published").count()
        rows.extend((
            {"page_id": "overview", "label": "理论主要页面", "count": 1, "route": f"/theories/nodes/{target.slug}"},
            {"page_id": "graph", "label": "知识图谱公开关系", "count": relation_count, "route": f"/theories/graph?center={target.slug}"},
            {"page_id": "scholar-entry", "label": "学者页面", "count": target.person_relations.filter(status="published", person__authority_status=Person.AuthorityStatus.VERIFIED, person__scholar_profile__editorial_status="published").values("person_id").distinct().count(), "route": f"/theories/nodes/{target.slug}?module=theory-scholars"},
            {"page_id": "topic-entry", "label": "主题页面", "count": target.topic_links.filter(status="published").values("topic_id").distinct().count(), "route": f"/theories/nodes/{target.slug}?module=theory-topics"},
            {"page_id": "works", "label": "相关馆藏", "count": target.work_relations.filter(status="published", work__editions__state="published").values("work_id").distinct().count(), "route": f"/theories/nodes/{target.slug}?module=theory-works"},
            {"page_id": "reading-path", "label": "Reading Path", "count": target.reading_path_items.filter(reading_path__status="published").values("reading_path_id").distinct().count(), "route": f"/theories/nodes/{target.slug}?module=theory-works"},
        ))
    elif object_type == "topic":
        rows.extend((
            {"page_id": "overview", "label": "主题主要页面", "count": 1, "route": f"/topics/{target.slug}"},
            {"page_id": "works", "label": "馆藏作品", "count": target.work_relations.filter(review_status=RelationReviewStatus.APPROVED, work__editions__state="published").values("work_id").distinct().count(), "route": f"/topics/{target.slug}/works"},
            {"page_id": "scholars", "label": "代表学者", "count": target.person_relations.filter(review_status=RelationReviewStatus.APPROVED, person__authority_status=Person.AuthorityStatus.VERIFIED, person__scholar_profile__editorial_status="published").values("person_id").distinct().count(), "route": f"/topics/{target.slug}/scholars"},
            {"page_id": "theory-schools", "label": "规范理论关系", "count": target.knowledge_node_links.filter(status="published", node__status="published").values("node_id").distinct().count(), "route": f"/topics/{target.slug}/theory-schools"},
            {"page_id": "timeline", "label": "时间线事件", "count": len(target.timeline or []), "route": f"/topics/{target.slug}/timeline"},
        ))
    return rows


def _legacy_state(object_type: str, target) -> list[dict[str, Any]]:
    rows = []
    if object_type == "topic" and target.theory_relations.filter(
        review_status=RelationReviewStatus.APPROVED,
        theory_school__editorial_status="published",
    ).exists():
        rows.append(LEGACY_PUBLIC_DEPENDENCIES[1])
    if object_type == "scholar" and (target.curation or {}).get("related_theory_ids"):
        rows.append(LEGACY_PUBLIC_DEPENDENCIES[2])
    return rows


def build_public_control(
    *,
    object_type: str,
    target,
    published_data: dict[str, Any] | None,
    draft_data: dict[str, Any] | None,
    revision: EditorialRevision | None,
    candidate_available: bool = False,
    evidence_available: bool = False,
) -> dict[str, Any]:
    contracts = page_contracts(object_type)
    if not contracts:
        return {}
    active = dict(draft_data or published_data or {})
    if object_type == "theory":
        active["reading_path_count"] = target.reading_path_items.filter(
            reading_path__status=KnowledgePublicationStatus.PUBLISHED,
        ).values("reading_path_id").distinct().count()
    changed_fields = set(revision.changed_fields or []) if revision else set()
    pages = []
    unique_modules: dict[str, dict[str, Any]] = {}
    for page in contracts:
        modules = [
            _module_state(
                module,
                active,
                changed_fields=changed_fields,
                candidate_available=candidate_available,
                evidence_available=evidence_available,
            )
            for module in page.modules
        ]
        for module in modules:
            unique_modules[module["module_id"]] = module
        statuses = {row["status"] for row in modules}
        required_missing = any(
            row["requirement"] == REQUIRED and row["status"] == "missing"
            for row in modules
        )
        recommended_missing = any(
            row["requirement"] == RECOMMENDED and row["status"] == "missing"
            for row in modules
        )
        page_status = (
            "draft"
            if "draft" in statuses
            else "missing"
            if required_missing
            else "partial"
            if recommended_missing or "partial" in statuses
            else "complete"
        )
        route_values = _target_route_values(page, target)
        route = _page_route(page, target)
        pages.append({
            "page_id": page.page_id,
            "display_name": page.display_name,
            "route": route,
            "public_component": page.public_component,
            "serializer": page.serializer,
            "api": _format_route(page.api, route_values),
            "status": page_status,
            "modules": modules,
            "preview": {
                "supported": page.preview_support,
                "published_route": route,
                "draft_route": f"/admin/preview/knowledge/{object_type}/{target.pk}?page={page.page_id}",
                "protected": True,
            },
            "admin_management_destination": page.admin_management_destination.format(id=target.pk),
        })
    scored = [row for row in unique_modules.values() if row["content_source_type"] != COMPUTED]
    satisfied = [row for row in scored if row["status"] in {"complete", "partial", "draft"}]
    required = [row for row in scored if row["requirement"] == REQUIRED]
    required_ready = [row for row in required if row["status"] not in {"missing"}]
    completeness_groups = []
    for group_name in ("Identity", "Core Content", "Knowledge", "Curation", "Evidence"):
        rows = [
            row for row in unique_modules.values()
            if row["completeness_group"] == group_name
        ]
        manual_rows = [row for row in rows if row["content_source_type"] != COMPUTED]
        ready_rows = [
            row for row in manual_rows
            if row["status"] in {"complete", "partial", "draft"}
        ]
        completeness_groups.append(
            {
                "group": group_name,
                "manual_ready": len(ready_rows),
                "manual_total": len(manual_rows),
                "computed_available": sum(
                    row["content_source_type"] == COMPUTED and row["available"]
                    for row in rows
                ),
                "computed_total": sum(
                    row["content_source_type"] == COMPUTED for row in rows
                ),
                "percent": (
                    round(len(ready_rows) * 100 / len(manual_rows))
                    if manual_rows
                    else 100
                ),
                "status": (
                    "complete"
                    if not manual_rows or len(ready_rows) == len(manual_rows)
                    else "partial"
                    if ready_rows
                    else "missing"
                ),
            }
        )
    return {
        "contract_version": "3.0.4",
        "object_type": object_type,
        "eligibility": _public_eligibility(object_type, target),
        "page_tree": pages,
        "modules": list(unique_modules.values()),
        "public_appearances": _appearances(object_type, target),
        "content_completeness": {
            "kind": "public_content_coverage",
            "overall_percent": round(len(satisfied) * 100 / len(scored)) if scored else 100,
            "required_ready": len(required_ready),
            "required_total": len(required),
            "computed_empty_is_manual_missing": False,
            "groups": completeness_groups,
        },
        "draft_published_diff": draft_published_diff(published_data, draft_data, changed_fields),
        "legacy_fallbacks": _legacy_state(object_type, target),
        "source_authority": [row for row in SOURCE_AUTHORITY_MATRIX if row["identity"] == object_type],
        "admin_field_usage": admin_field_usage(object_type),
        "ai_status": {
            "enabled": False,
            "workspace_message": "自动建议当前未启用",
            "publication_blocking": False,
        },
    }


def public_management_coverage() -> dict[str, Any]:
    from urllib.parse import urlsplit

    from django.urls import Resolver404, resolve

    from catalog.services.editorial_revision import TARGET_POLICIES

    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    contract_routes: dict[str, set[str]] = {key: set() for key in AUDITED_OBJECT_PUBLIC_ROUTES}
    seen_pages: set[tuple[str, str]] = set()
    relation_sources = {
        source
        for row in SOURCE_AUTHORITY_MATRIX
        for source in row["relation_sources"]
    }
    probe_values = {
        "slug": "public-control-probe",
        "discipline_slug": "public-control-discipline",
        "scholar_slug": "public-control-scholar",
        "topic_slug": "public-control-topic",
        "path_slug": "public-control-path",
    }
    for page in PUBLIC_PAGE_CONTRACTS:
        page_key = (page.object_type, page.page_id)
        if page_key in seen_pages:
            errors.append({"code": "DUPLICATE_PUBLIC_PAGE_CONTRACT", "object_type": page.object_type, "page_id": page.page_id})
        seen_pages.add(page_key)
        contract_routes.setdefault(page.object_type, set()).add(page.route.split("?", 1)[0])
        if not page.route or not page.admin_management_destination:
            errors.append({"code": "PUBLIC_PAGE_MANAGEMENT_GAP", "page_id": page.page_id})
        if page.preview_support and not page.public_component:
            errors.append({"code": "PREVIEW_COVERAGE_GAP", "page_id": page.page_id})
        if page.preview_support and not page.admin_management_destination:
            errors.append({"code": "PREVIEW_COVERAGE_GAP", "page_id": page.page_id})
        try:
            resolve(urlsplit(_format_route(page.api, probe_values)).path)
        except Resolver404:
            errors.append({"code": "PUBLIC_PAGE_API_UNRESOLVED", "page_id": page.page_id, "api": page.api})
        for module in page.modules:
            if not module.content_source_type or not module.admin_editor_section:
                errors.append({"code": "PUBLIC_MODULE_MANAGEMENT_GAP", "module_id": module.module_id})
            if not module.serializer_fields:
                errors.append({"code": "PUBLIC_MODULE_SOURCE_UNCLEAR", "module_id": module.module_id})
            source_contract = {
                EDITORIAL: module.canonical_fields,
                RELATION: module.relations,
                CURATED: module.curated_fields,
                COMPUTED: module.computed_fields,
                AI_OPTIONAL: module.curated_fields,
            }.get(module.content_source_type, ())
            if not source_contract:
                errors.append({"code": "PUBLIC_MODULE_SOURCE_UNCLEAR", "module_id": module.module_id})
            for relation in module.relations:
                if relation not in relation_sources:
                    errors.append({"code": "PUBLIC_RELATION_SOURCE_UNCLEAR", "module_id": module.module_id, "relation": relation})
            if module.legacy_sources:
                warnings.append({"code": "LEGACY_PUBLIC_FALLBACK_ACTIVE", "module_id": module.module_id, "sources": list(module.legacy_sources)})
    route_coverage: dict[str, dict[str, Any]] = {}
    for object_type, audited_routes in AUDITED_OBJECT_PUBLIC_ROUTES.items():
        missing_contracts = sorted(audited_routes - contract_routes.get(object_type, set()))
        unknown_contracts = sorted(contract_routes.get(object_type, set()) - audited_routes)
        for route in missing_contracts:
            errors.append({"code": "PUBLIC_PAGE_WITHOUT_CONTRACT", "object_type": object_type, "route": route})
        for route in unknown_contracts:
            warnings.append({"code": "PUBLIC_CONTRACT_ROUTE_NOT_IN_AUDIT", "object_type": object_type, "route": route})
        route_coverage[object_type] = {
            "audited": len(audited_routes),
            "covered": len(audited_routes) - len(missing_contracts),
            "percent": round((len(audited_routes) - len(missing_contracts)) * 100 / len(audited_routes)) if audited_routes else 100,
            "missing": missing_contracts,
        }

    target_types = {
        "scholar": EditorialRevision.TargetType.SCHOLAR_PROFILE,
        "theory": EditorialRevision.TargetType.KNOWLEDGE_NODE,
        "topic": EditorialRevision.TargetType.TOPIC,
    }
    field_coverage: dict[str, dict[str, Any]] = {}
    for object_type, target_type in target_types.items():
        editable = set(TARGET_POLICIES[target_type].editable_fields)
        classified = set(ADMIN_FIELD_USAGE.get(object_type, {}))
        missing_fields = sorted(editable - classified)
        stale_fields = sorted(classified - editable)
        for field in missing_fields:
            errors.append({"code": "ADMIN_FIELD_NO_PUBLIC_CONSUMER", "object_type": object_type, "field": field})
        for field in stale_fields:
            errors.append({"code": "ADMIN_FIELD_USAGE_STALE", "object_type": object_type, "field": field})
        field_coverage[object_type] = {
            "editable": len(editable),
            "classified": len(editable & classified),
            "percent": round(len(editable & classified) * 100 / len(editable)) if editable else 100,
            "missing": missing_fields,
        }

    for route in AUDITED_LEGACY_PUBLIC_ROUTES:
        warnings.append({"code": "LEGACY_PUBLIC_ROUTE_ACTIVE", "route": route, "retirement_condition": "normalized identity and relation backfill reaches full public coverage"})
    counts = {
        object_type: len(page_contracts(object_type))
        for object_type in ("scholar", "theory", "topic")
    }
    return {
        "status": "ok" if not errors else "error",
        "page_contract_count": len(PUBLIC_PAGE_CONTRACTS),
        "page_counts": counts,
        "errors": errors,
        "warnings": warnings,
        "route_coverage": route_coverage,
        "admin_field_coverage": field_coverage,
        "directory_routes": AUDITED_DIRECTORY_PUBLIC_ROUTES,
        "legacy_routes": AUDITED_LEGACY_PUBLIC_ROUTES,
        "source_authority_matrix": SOURCE_AUTHORITY_MATRIX,
        "legacy_public_dependency_matrix": LEGACY_PUBLIC_DEPENDENCIES,
    }
