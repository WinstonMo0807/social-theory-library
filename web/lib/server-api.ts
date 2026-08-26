import {
  scholars as demoScholars,
  theorySchools as demoTheorySchools,
  topic as demoTopic,
  works as demoWorks,
  type Scholar,
  type TheorySchool,
  type Work,
  type CuratedWorkClaim,
} from "./data";
import { defaultSiteConfig, type SiteConfig } from "./site-config";
import type { SearchContext } from "./search-context";
import { WEB_APP_VERSION } from "./version";
import { adaptApiScholar, adaptApiScholarDetail, adaptApiTopic, adaptApiWork } from "./public-data-adapters";

const SERVER_API =
  process.env.INTERNAL_API_URL?.replace(/\/$/, "") ??
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://localhost:8000/api";

const INTERNAL_API_TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

const allowDemoFallback = (
  process.env.NODE_ENV !== "production"
  && process.env.ALLOW_DEMO_FALLBACK !== "false"
);

type ApiPerson = {
  preferred_name: string;
  original_name: string;
  aliases: string[];
  portrait?: string;
  birth_year?: number | null;
  death_year?: number | null;
  biography?: string;
  scholar_slug?: string | null;
};

export type PublicCuratedClaim = Omit<CuratedWorkClaim, "kind"> & {
  kind: "core_viewpoint" | "major_criticism" | "major_response" | "debate_position";
  position: "direct" | "support" | "oppose" | "qualify";
};

export type PublicCuratedClaimGroups = Record<
  "core_viewpoint" | "major_criticism" | "major_response",
  PublicCuratedClaim[]
>;

export type PublicKnowledgeNodeLink = {
  id: string;
  node_type: "theory_tradition" | "concept" | "debate" | "research_problem" | "subdiscipline";
  name: string;
  foreign_name: string;
  slug: string;
  summary: string;
  relation_label: string;
  is_representative?: boolean;
  relation_source?: "person_relation" | "published_work_relation";
};

export type ApiWork = {
  id: string;
  document_type: "book" | "journal_article" | "thesis" | "report";
  title: string;
  subtitle: string;
  abstract: string;
  language: string;
  cover: string;
  recommendation_image: string;
  edition: {
    id: string;
    public_slug: string;
    publication_year: number | null;
    publisher: string;
    journal_title: string;
    contributors: { role: string; person: ApiPerson }[];
    readable_asset: { id: string; page_count: number } | null;
  } | null;
  theories: { name: string; slug: string }[];
  topics: { name: string; slug: string }[];
  disciplines: { name: string; slug: string; is_primary: boolean }[];
  subdisciplines: { name: string; slug: string; is_primary: boolean }[];
  theory_associations?: {
    id: string;
    node: { id: string; name: string; foreign_name: string; slug: string; type: string };
    role: string;
    role_label: string;
    strength: string;
    evidence: {
      id: string;
      page_number: number;
      page_end: number | null;
      printed_page_label: string;
      quote: string;
      reader_href: string;
    }[];
  }[];
  curated_claims?: {
    core_viewpoint: import("./data").CuratedWorkClaim[];
    major_criticism: import("./data").CuratedWorkClaim[];
    major_response: import("./data").CuratedWorkClaim[];
  };
  outline?: { index: number; printed_label: string; chapter_title: string }[];
};

export type ApiScholar = {
  slug: string;
  person: ApiPerson & { id: string };
  short_description: string;
  affiliations: string[];
  key_concerns: string[];
  timeline: [string, string][];
  featured_quote: string;
  quote_source?: string;
  works: ApiWork[];
  knowledge_nodes?: PublicKnowledgeNodeLink[];
  curated_claims?: PublicCuratedClaimGroups;
  curated?: {
    essential_works: ApiWork[];
    key_concepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    concept_map: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
    network: {
      scholar: { id: string; name: string; slug: string };
      relation: string;
      source: string;
    }[];
    frequently_read_scholars: { id: string; name: string; slug: string }[];
    related_theories: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      symbol?: string;
    }[];
  };
};

export type ApiTheorySchool = {
  id: string;
  slug: string;
  name: string;
  description: string;
  symbol: string;
  foreign_name: string;
  entity_level: "tradition" | "school" | "branch";
  formation_period: string;
  core_questions: string[];
  key_themes: string[];
  hero_image: string;
  disciplines: { id: string; name: string; slug: string; role: string }[];
  subdisciplines: { id: string; name: string; slug: string; role: string }[];
  hierarchy: {
    parents: { id: string; name: string; slug: string }[];
    branches: { id: string; name: string; slug: string }[];
  };
  relations: {
    id: string;
    direction: string;
    relation_type: string;
    strength: string;
    theory: { id: string; name: string; slug: string };
    evidence_page?: number | null;
    evidence_text?: string;
  }[];
  timeline: TheoryTimelineEvent[];
  work_count: number;
  scholar_count: number;
  works?: ApiWork[];
  scholars?: ApiScholar[];
  curated?: {
    hero_caption: string;
    foundational_works: ApiWork[];
    curated_reading_works: ApiWork[];
    key_scholars: { id: string; name: string; slug: string }[];
    neighbors: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      relation?: string;
      source?: string;
    }[];
    core_concepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptual_map: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
  };
};

export type ApiTopic = {
  id: string;
  slug: string;
  name: string;
  description: string;
  problem_statement: string;
  core_questions: string[];
  research_dimensions: string[];
  methods: string[];
  formation_context: string;
  hero_image: string;
  disciplines: { id: string; name: string; slug: string; is_primary: boolean }[];
  subdisciplines: { id: string; name: string; slug: string; relation_label: string }[];
  linked_theories: { id: string; name: string; slug: string; relation_label: string }[];
  knowledge_nodes?: PublicKnowledgeNodeLink[];
  key_concepts: string[];
  timeline: [string, string, string][];
  work_count: number;
  works?: ApiWork[];
  scholars?: ApiScholar[];
  theories?: ApiTheorySchool[];
  passages?: {
    id: string;
    asset_id: string;
    title: string;
    page_index: number;
    printed_label: string;
    snippet: string;
  }[];
  curated_claims?: PublicCuratedClaimGroups;
  curated?: {
    hero_caption: string;
    foundational_works: ApiWork[];
    recent_works: ApiWork[];
    related_scholars: { id: string; name: string; slug: string }[];
    linked_theories: { id: string; name: string; slug: string }[];
    reading_paths: {
      title: string;
      description: string;
      level: string;
      works: ApiWork[];
    }[];
    featured_passage_id: string;
    featured_passage_reason?: string;
    featured_passage_evidence?: Record<string, unknown>;
  };
};

export type Discipline = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  introduction: string;
  hero_image: string;
  sort_order: number;
  theory_count: number;
  subdiscipline_count: number;
  topic_count: number;
  work_count: number;
  scholar_count: number;
};

export type Subdiscipline = {
  id: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  hero_image: string;
  discipline: Discipline;
  parent: { id: string; name: string; slug: string } | null;
  research_object: string;
  core_questions: string[];
  formation_period: string;
  research_directions: string[];
  methods: string[];
  representative_issues: string[];
  theories: { id: string; name: string; slug: string; role: string }[];
  topics: { id: string; name: string; slug: string; relation_label: string }[];
  works: ApiWork[];
  scholars: { id: string; name: string; slug: string }[];
};

export type TheoryTimelineEvent = {
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  orientation: string;
  image: string;
  theory: { id: string; name: string; slug: string } | null;
  discipline: { id: string; name: string; slug: string } | null;
  subdiscipline: { id: string; name: string; slug: string } | null;
  scholar: { id: string; name: string; slug: string } | null;
  work: { id: string; title: string } | null;
  evidence_page?: number | null;
  evidence_printed_label?: string;
  evidence_text?: string;
};

export type TheoryGraph = {
  nodes: {
    id: string;
    slug: string;
    name: string;
    foreign_name: string;
    entity_level: string;
    symbol: string;
    curation_level: number;
  }[];
  edges: {
    id: string;
    source: string;
    target: string;
    relation_type: string;
    strength: string;
    evidence_page?: number | null;
    evidence_text?: string;
  }[];
};

export type AboutPageBlock = {
  id: string;
  key: string;
  block_type: "intro" | "stat" | "feature" | "process" | "principle" | "notice" | "action" | "footer";
  title: string;
  body: string;
  icon: string;
  action_label: string;
  action_href: string;
  sort_order: number;
  visible: boolean;
  configuration: Record<string, unknown>;
};

export type RecommendationItem = {
  id: string;
  position: number;
  reason: string;
  image_override: string;
  target_type: "work" | "theory_school" | "topic" | "scholar";
  target: ApiWork | {
    id: string;
    name: string;
    slug: string;
    description: string;
    symbol?: string;
    hero_image?: string;
  };
};

export type RecommendationPlacement = {
  id: string;
  placement: string;
  title: string;
  item_count: number;
  rotation_days: number;
  enabled: boolean;
  last_generated_at: string | null;
  next_refresh_at: string | null;
  current: {
    id: string;
    starts_at: string;
    expires_at: string;
    source: "automatic" | "manual";
    items: RecommendationItem[];
  } | null;
};

export type RecommendationBundle = {
  shared_for_all_readers: boolean;
  rotation_days: number;
  placements: Record<string, RecommendationPlacement>;
};

type Paginated<T> = {
  count: number;
  results: T[];
  next?: string | null;
  previous?: string | null;
};

export type DirectoryPage<T> = {
  count: number;
  results: T[];
  page: number;
  pageSize: number;
  totalPages: number;
};

function directoryPage<T>(payload: Paginated<T>, page: number, pageSize = 24): DirectoryPage<T> {
  return {
    count: payload.count,
    results: payload.results,
    page,
    pageSize,
    totalPages: payload.count ? Math.ceil(payload.count / pageSize) : 0,
  };
}

export type TheoryDisciplineCompact = {
  id: string;
  code: string;
  name: string;
  foreign_name: string;
  slug: string;
  description: string;
  hero_image: string;
};

export type TheoryPersonLink = {
  id: string;
  name: string;
  original_name: string;
  birth_year: number | null;
  death_year: number | null;
  portrait_url: string;
  scholar_slug: string;
  relation_label: string;
  is_representative: boolean;
  sort_order: number;
};

export type TheoryWorkCompact = {
  id: string;
  slug: string;
  title: string;
  subtitle: string;
  document_type: string;
  language: string;
  author: string;
  year: number | null;
  publisher: string;
  cover_url: string;
  asset_id: string | null;
  reader_href: string | null;
  detail_href: string | null;
};

export type KnowledgeNodeListItem = {
  id: string;
  node_type: "theory_tradition" | "subdiscipline" | "concept" | "debate" | "research_problem";
  canonical_name_zh: string;
  canonical_name_en: string;
  slug: string;
  summary: string;
  core_questions: string[];
  start_year: number | null;
  end_year: number | null;
  period_label: string;
  primary_discipline: TheoryDisciplineCompact | null;
  related_disciplines: TheoryDisciplineCompact[];
  status: string;
  sort_order: number;
  aliases_count: number;
  work_count: number;
  relation_count: number;
  representative_scholars: TheoryPersonLink[];
  cover_url: string;
  updated_at: string;
};

export type TheoryEvidence = {
  id: string;
  work: string;
  work_title: string;
  file: string;
  node: string | null;
  node_name: string;
  relation_role: string;
  page_number: number;
  page_end: number | null;
  printed_page_label: string;
  quote: string;
  bounding_box: Record<string, unknown>;
  extraction_method: string;
  ocr_confidence: number | null;
  semantic_confidence: number | null;
  review_status: string;
  reader_href: string;
};

export type TheoryWorkRelation = {
  id: string;
  work: string;
  work_data: TheoryWorkCompact | null;
  node: string;
  node_name: string;
  node_slug: string;
  role: string;
  role_label: string;
  is_primary: boolean;
  strength: string;
  confidence: number;
  status: string;
  source: string;
  evidence: TheoryEvidence[];
};

export type NormalizedKnowledgeRelation = {
  id: string;
  source_node: string;
  source_name: string;
  source_slug: string;
  target_node: string;
  target_name: string;
  target_slug: string;
  relation_type: string;
  relation_label: string;
  direction: string;
  description: string;
  evidence_source: string;
  confidence: number;
  status: string;
};

export type KnowledgeNodeDetail = KnowledgeNodeListItem & {
  aliases: { id: string; alias: string; language: string; alias_type: string; normalized_alias: string }[];
  discipline_links: {
    id: string;
    discipline: TheoryDisciplineCompact;
    relation_type: string;
    discipline_specific_summary: string;
    sort_order: number;
    status: string;
  }[];
  subdiscipline_links: Array<{
    id: string;
    subdiscipline: {
      id: string;
      name: string;
      foreign_name: string;
      slug: string;
      discipline_id: string;
    };
    is_primary: boolean;
    relation_role: string;
    source: string;
    confidence: number;
    sort_order: number;
    status: string;
  }>;
  topic_links: Array<{
    id: string;
    topic: { id: string; name: string; slug: string };
    relation_label: string;
    source: string;
    confidence: number;
    sort_order: number;
    status: string;
  }>;
  definition: string;
  basic_propositions: string[];
  theoretical_boundary: string;
  direct_relations: NormalizedKnowledgeRelation[];
  work_groups: Record<string, TheoryWorkRelation[]>;
  evidence: TheoryEvidence[];
  curated_claims: Record<
    "core_viewpoint" | "major_criticism" | "major_response" | "debate_position",
    Array<{
      id: string;
      kind: string;
      kind_label: string;
      title: string;
      proposition: string;
      editorial_note: string;
      qualifiers: unknown[];
      position: "direct" | "support" | "oppose" | "qualify";
      evidence: Array<{
        id: string;
        text: string;
        source: { work_title: string; authors: string[] };
        locator: { page: number; printed_page_label: string };
        reader_url: string;
        claim_role: string;
        claim_role_label: string;
      }>;
    }>
  >;
  published_at: string | null;
};

export type NormalizedTimelineEvent = {
  id: string;
  title: string;
  description: string;
  event_type: string;
  start_year: number | null;
  end_year: number | null;
  date_label: string;
  source: string;
  evidence_page: number | null;
  evidence_printed_label: string;
  evidence_text: string;
  relations: { relation_type: string; type: string; id: string; name: string; slug?: string }[];
  reader_href: string | null;
};

export type NormalizedReadingPathItem = {
  id: string;
  stage_name: string;
  stage_description: string;
  node: string | null;
  node_data: KnowledgeNodeListItem | null;
  work: string | null;
  work_data: TheoryWorkCompact | null;
  recommendation_reason: string;
  prerequisite?: string;
  reading_order: number;
  is_required: boolean;
  editorial_note: string;
};

export type NormalizedReadingPath = {
  id: string;
  title: string;
  slug: string;
  introduction: string;
  learning_goal?: string;
  primary_discipline: string | null;
  primary_discipline_data: TheoryDisciplineCompact | null;
  audience: string;
  difficulty: string;
  estimated_reading: string;
  cover_url: string;
  status: string;
  sort_order: number;
  items: NormalizedReadingPathItem[];
  published_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TheorySystemOverview = {
  disciplines: (TheoryDisciplineCompact & {
    counts: Partial<Record<"theory_traditions" | "subdisciplines" | "works", number>>;
  })[];
  browse: Partial<Record<"theory_traditions" | "subdisciplines" | "debates", number>>;
  reading_paths: NormalizedReadingPath[];
  recent: {
    nodes: KnowledgeNodeListItem[];
    timeline_events: NormalizedTimelineEvent[];
    work_relations: TheoryWorkRelation[];
  };
};

export type TheoryDisciplinePage = {
  discipline: TheoryDisciplineCompact;
  counts: Partial<Record<"theory_traditions" | "subdisciplines" | "debates" | "scholars" | "works", number>>;
  active_type: string;
  nodes: KnowledgeNodeListItem[];
  lineage: NormalizedTimelineEvent[];
  reading_paths: NormalizedReadingPath[];
};

const fallbackTheoryDisciplines: Record<string, TheoryDisciplineCompact> = {
  sociology: {
    id: "fallback-sociology",
    code: "SOC",
    name: "社会学",
    foreign_name: "Sociology",
    slug: "sociology",
    description: "研究社会关系、制度、结构及其变迁。",
    hero_image: "",
  },
  anthropology: {
    id: "fallback-anthropology",
    code: "ANTH",
    name: "人类学",
    foreign_name: "Anthropology",
    slug: "anthropology",
    description: "从文化、实践与比较视角理解人类生活。",
    hero_image: "",
  },
  ethnology: {
    id: "fallback-ethnology",
    code: "ETH",
    name: "民族学",
    foreign_name: "Ethnology",
    slug: "ethnology",
    description: "研究族群、民族关系及其历史与现实变化。",
    hero_image: "",
  },
};

export type LocalTheoryGraph = {
  center: string | null;
  nodes: Array<{
    id: string;
    kind: "knowledge_node" | "scholar" | "work";
    node_type?: string;
    name: string;
    foreign_name?: string;
    slug?: string;
    summary?: string;
    period_label?: string;
    is_center?: boolean;
    work?: TheoryWorkCompact | null;
  }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    relation_type: string;
    relation_label: string;
    direction: string;
    description?: string;
  }>;
  depth: number;
  limit: number;
  truncated: boolean;
};

export type ScopedSearchResult = {
  context: Exclude<SearchContext, "global">;
  entity_type: string;
  id: string;
  title: string;
  subtitle: string;
  description: string;
  url: string;
  match: {
    type: "exact" | "verified_alias" | "prefix" | "text" | "browse";
    query: string;
    highlights: string[];
  };
  metadata: Record<string, unknown>;
};

export type ScopedSearchEnvelope = {
  implementation_version: string;
  context: SearchContext;
  visibility: "public" | "admin";
  query: string;
  groups: Array<{
    context: Exclude<SearchContext, "global">;
    label: string;
    backend: string;
    count: number;
    results: ScopedSearchResult[];
    pagination?: { page: number; limit: number; total: number; total_pages: number };
  }>;
  total: number;
  pagination: { page: number; limit: number; total: number; total_pages: number };
  latency_ms: number;
};

type SearchPayload = {
  counts: {
    works: number;
    books: number;
    articles: number;
    theses: number;
    reports: number;
    scholars: number;
    topics: number;
    theories: number;
    passages: number;
  };
  works: ApiWork[];
  scholars: ApiScholar[];
  topics: { id: string; name: string; slug: string; description: string; work_count: number }[];
  theories: { id: string; name: string; slug: string; description: string; work_count: number }[];
  passages: {
    id: string;
    asset_id: string;
    title: string;
    edition_slug: string;
    page_index: number;
    printed_label: string;
    snippet: string;
    bbox: number[];
    query: string;
  }[];
  facets: {
    document_types: SearchFacetOption[];
    authors: SearchFacetOption[];
    years: SearchFacetOption[];
    languages: SearchFacetOption[];
    access: SearchFacetOption[];
    theories: SearchFacetOption[];
    topics: SearchFacetOption[];
    concepts: SearchFacetOption[];
  };
  pagination: {
    page: number;
    page_size: number;
    total: number;
    total_pages: number;
  };
};

export type SearchFacetOption = {
  value: string;
  label: string;
  count: number;
};

export type SearchFilters = {
  scope?: string;
  documentType?: string[];
  theory?: string[];
  topic?: string[];
  concept?: string[];
  author?: string[];
  scholar?: string[];
  year?: string[];
  yearMin?: number;
  yearMax?: number;
  language?: string[];
  relation?: string[];
  sourceType?: string[];
  access?: string[];
  sort?: string;
  page?: number;
  pageSize?: number;
  rewrite?: string;
  rewriteDisabled?: boolean;
  workId?: string;
  maxPerWork?: number;
};

export type SemanticSearchResult = {
  id: string;
  asset_id: string;
  edition_id: string;
  edition_slug: string;
  work_id: string;
  title: string;
  cover_url: string;
  authors: string[];
  document_type: "book" | "journal_article" | "thesis" | "report";
  language: string;
  publication_year: number | null;
  page_index: number;
  page_start: number;
  page_end: number;
  printed_label: string;
  chapter_title: string;
  section_title: string;
  snippet: string;
  context_before: string;
  context_after: string;
  bbox: number[];
  locators: { page_index?: number; printed_label?: string; bbox?: number[] }[];
  relevance: string;
  response_type?: "direct_response" | "partial_response" | "semantic_related" | "background_context" | string;
  response_label?: string;
  reasons: string[];
  concepts: string[];
  reader_url: string;
  debug?: {
    keyword_rank: number | null;
    vector_rank: number | null;
    rrf_score: number;
    reranker_score: number;
    final_rank: number;
  };
};

export type SemanticSearchPayload = {
  query: string;
  engine: "hybrid" | "keyword_fallback" | "unavailable" | string;
  strategy?: "legacy" | "keyword" | "vector" | "hybrid" | "hybrid_rerank";
  sort?: "relevance" | "newest" | "year";
  fallback_used: boolean;
  service_unavailable?: boolean;
  fallback_reason?: string;
  query_rewrite_fallback?: boolean;
  reranker_fallback?: boolean;
  notice: string;
  count: number;
  work_count: number;
  understanding: {
    type: string;
    terms: string[];
    related_concepts: { name: string; kind: string; slug: string }[];
    rewrites: string[];
    rewrite_source: string;
  };
  query_rewrite_enabled: boolean;
  query_rewrite_active?: boolean;
  active_rewrite?: string;
  facets: SearchPayload["facets"];
  timing_ms?: number | null;
  search_version?: string;
  search_profile?: string;
  stage_timings_ms?: Record<string, number | null>;
  candidate_counts?: Record<string, number>;
  results: SemanticSearchResult[];
};

export type ViewpointStance =
  | "direct"
  | "support"
  | "oppose"
  | "qualify"
  | "critique"
  | "extend"
  | "reframe";

export type ViewpointSearchResult = {
  id: string;
  source_kind: "semantic_chunk" | "derived_claim" | string;
  claim_id: string | null;
  proposition: string;
  stance: ViewpointStance;
  stance_label: string;
  stance_confidence: number;
  stance_reasons: string[];
  score: number;
  authors: string[];
  work: { id: string; title: string; slug: string };
  source_type: "book" | "journal" | "other" | string;
  language: string;
  publication_year: number | null;
  page: number;
  printed_page_label: string;
  evidence: {
    id: string;
    kind: "collection_text";
    source: {
      work_id: string;
      work_title: string;
      edition_id: string;
      asset_id: string;
      authors: string[];
      document_revision_id: string;
      document_revision: number;
    };
    text: string;
    locator: {
      page: number;
      page_id: string;
      printed_page_label: string;
      start_offset: number;
      end_offset: number;
      bbox: unknown;
      section: string;
    };
    quality: { score: number; stale: boolean; stale_reason: string };
    provenance: Record<string, unknown>;
    reader_url: string;
    pdf_url: string;
  };
  reader_url: string;
  pdf_url: string;
  attribution: string;
  claim_type: string;
  quality_score: number;
  importance_score?: number;
  qualifiers?: unknown[];
  ranking_source: "semantic_v2_baseline" | "claim_index_shadow" | string;
};

export type ViewpointFacetOption = {
  id: string;
  slug: string;
  label: string;
  count: number;
};

export type ViewpointFacets = {
  relations: ViewpointFacetOption[];
  source_types: ViewpointFacetOption[];
  languages: ViewpointFacetOption[];
  scholars: ViewpointFacetOption[];
  theories: ViewpointFacetOption[];
  topics: ViewpointFacetOption[];
  works: ViewpointFacetOption[];
  publication_year: { min: number | null; max: number | null };
};

export type ViewpointSearchPayload = {
  query: string;
  query_claim: {
    proposition: string;
    subject: string;
    predicate: string;
    object: string;
    polarity: string;
    qualifiers: string[];
    claim_type: string;
  };
  default_mode: "baseline" | "claim";
  results: ViewpointSearchResult[];
  groups: Record<ViewpointStance, ViewpointSearchResult[]>;
  facets: ViewpointFacets;
  count: number;
  work_count: number;
  stance_counts: Record<ViewpointStance, number>;
  engine: string;
  search_version: string;
  fallback_used: boolean;
  fallback_reason: string;
  notice: string;
  service_unavailable?: boolean;
  metadata: {
    benchmark_gate_passed: boolean;
    default_ranking: string;
    claim_ranking_status: "shadow" | "promoted" | string;
    evidence_span_validation_required: boolean;
    cosine_similarity_used_for_stance: boolean;
  };
};

export class ServerApiError extends Error {
  readonly status: number;
  readonly path: string;

  constructor(status: number, path: string) {
    super(`API ${status}: ${path}`);
    this.name = "ServerApiError";
    this.status = status;
    this.path = path;
  }
}

async function serverRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${SERVER_API}${path}`, {
    cache: "no-store",
    headers: {
      accept: "application/json",
      // Public deployments keep Django's HTTPS redirect enabled. Server-side
      // requests still travel over the private Docker network, so mark the
      // original scheme explicitly and avoid redirects to https://api:8000.
      "x-forwarded-proto": "https",
      ...(INTERNAL_API_TOKEN ? { "x-internal-api-token": INTERNAL_API_TOKEN } : {}),
    },
  });
  if (!response.ok) {
    throw new ServerApiError(response.status, path);
  }
  return response.json() as Promise<T>;
}

export async function loadSiteConfig(): Promise<SiteConfig> {
  try {
    return await serverRequest<SiteConfig>("/catalog/site-config/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return defaultSiteConfig;
  }
}

export type SiteStats = {
  documents: number;
  scholars: number;
  knowledge_objects: number;
  last_updated: string | null;
  last_updated_label: string;
  version: string;
};

export async function loadSiteStats(): Promise<SiteStats> {
  try {
    return await serverRequest<SiteStats>("/catalog/site-stats/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      documents: 0,
      scholars: 0,
      knowledge_objects: 0,
      last_updated: null,
      last_updated_label: "尚未发布",
      version: WEB_APP_VERSION,
    };
  }
}

export async function loadDisciplines(): Promise<Discipline[]> {
  try {
    const payload = await serverRequest<Paginated<Discipline>>("/catalog/disciplines/");
    return payload.results;
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return [];
  }
}

export async function loadSubdisciplinePage(
  discipline = "",
  query = "",
  page = 1,
): Promise<DirectoryPage<Subdiscipline>> {
  try {
    const parameters = new URLSearchParams({ page: String(page) });
    if (discipline) parameters.set("discipline", discipline);
    if (query.trim()) parameters.set("q", query.trim());
    const payload = await serverRequest<Paginated<Subdiscipline>>(`/catalog/subdisciplines/?${parameters.toString()}`);
    return directoryPage(payload, page);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: 0, results: [] }, page);
  }
}

export async function loadSubdisciplines(discipline = "", query = ""): Promise<Subdiscipline[]> {
  return (await loadSubdisciplinePage(discipline, query)).results;
}

export async function loadSubdiscipline(slug: string): Promise<(Omit<Subdiscipline, "works"> & { works: Work[] }) | null> {
  try {
    const payload = await serverRequest<Subdiscipline>(
      `/catalog/subdisciplines/${encodeURIComponent(slug)}/`,
    );
    return { ...payload, works: payload.works.map(adaptWork) };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return null;
  }
}

export async function loadKnowledgeMatrix(): Promise<{
  disciplines: Discipline[];
  entry_modes: { key: string; title: string; description: string; href: string }[];
  counts: { disciplines: number; theories: number; subdisciplines: number; topics: number };
}> {
  try {
    return await serverRequest<{
      disciplines: Discipline[];
      entry_modes: { key: string; title: string; description: string; href: string }[];
      counts: { disciplines: number; theories: number; subdisciplines: number; topics: number };
    }>("/catalog/knowledge-matrix/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      disciplines: [],
      entry_modes: [],
      counts: { disciplines: 0, theories: 0, subdisciplines: 0, topics: 0 },
    };
  }
}

export async function loadTheorySystemOverview(): Promise<TheorySystemOverview | null> {
  try {
    return await serverRequest<TheorySystemOverview>("/catalog/theory-system/overview/");
  } catch {
    return null;
  }
}

export async function loadScopedSearch(
  context: SearchContext,
  query = "",
  options: { page?: number; limit?: number } = {},
): Promise<ScopedSearchEnvelope> {
  const parameters = new URLSearchParams({ context, envelope: "1" });
  if (query.trim()) parameters.set("q", query.trim());
  if (options.page) parameters.set("page", String(options.page));
  if (options.limit) parameters.set("limit", String(options.limit));
  try {
    return await serverRequest<ScopedSearchEnvelope>(`/catalog/search/?${parameters.toString()}`);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      implementation_version: "scoped-search-demo-fallback",
      context,
      visibility: "public",
      query,
      groups: [],
      total: 0,
      pagination: { page: options.page || 1, limit: options.limit || 24, total: 0, total_pages: 0 },
      latency_ms: 0,
    };
  }
}

export async function loadTheorySystemNodes(filters: {
  type?: string;
  discipline?: string;
  q?: string;
} = {}): Promise<KnowledgeNodeListItem[]> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<KnowledgeNodeListItem>>(
      `/catalog/theory-system/nodes/${suffix}`,
    );
    return payload.results;
  } catch {
    return [];
  }
}

export async function loadKnowledgeNode(slug: string): Promise<KnowledgeNodeDetail | null> {
  try {
    return await serverRequest<KnowledgeNodeDetail>(
      `/catalog/theory-system/nodes/${encodeURIComponent(slug)}/`,
    );
  } catch {
    return null;
  }
}

export async function loadTheoryDisciplinePage(
  slug: string,
  nodeType = "theory_tradition",
): Promise<TheoryDisciplinePage | null> {
  try {
    return await serverRequest<TheoryDisciplinePage>(
      `/catalog/theory-system/disciplines/${encodeURIComponent(slug)}/?type=${encodeURIComponent(nodeType)}`,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const discipline = fallbackTheoryDisciplines[slug];
    if (!discipline) return null;
    return {
      discipline,
      counts: {},
      active_type: nodeType,
      nodes: [],
      lineage: [],
      reading_paths: [],
    };
  }
}

export async function loadNormalizedTheoryTimeline(filters: {
  discipline?: string;
  node?: string;
  event_type?: string;
  has_collection?: string;
  q?: string;
} = {}): Promise<NormalizedTimelineEvent[]> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<NormalizedTimelineEvent>>(
      `/catalog/theory-system/timeline/${suffix}`,
    );
    return payload.results;
  } catch {
    return [];
  }
}

export async function loadNormalizedTheoryTimelinePage(filters: {
  discipline?: string;
  node?: string;
  event_type?: string;
  has_collection?: string;
  q?: string;
  page?: string;
} = {}): Promise<Paginated<NormalizedTimelineEvent>> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return await serverRequest<Paginated<NormalizedTimelineEvent>>(
      `/catalog/theory-system/timeline/${suffix}`,
    );
  } catch {
    return { count: 0, next: null, previous: null, results: [] };
  }
}

export async function loadLocalTheoryGraph(filters: {
  center?: string;
  discipline?: string;
  node_type?: string;
  relation_type?: string;
  start_year?: number;
  end_year?: number;
  has_collection?: string;
  depth?: number;
  limit?: number;
} = {}): Promise<LocalTheoryGraph> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") parameters.set(key, String(value));
  });
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return await serverRequest<LocalTheoryGraph>(`/catalog/theory-system/graph/${suffix}`);
  } catch {
    return { center: null, nodes: [], edges: [], depth: 1, limit: 20, truncated: false };
  }
}

export async function loadNormalizedReadingPaths(discipline = ""): Promise<NormalizedReadingPath[]> {
  try {
    const suffix = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    const payload = await serverRequest<Paginated<NormalizedReadingPath>>(
      `/catalog/theory-system/reading-paths/${suffix}`,
    );
    return payload.results;
  } catch {
    return [];
  }
}

export async function loadNormalizedReadingPath(slug: string): Promise<NormalizedReadingPath | null> {
  try {
    return await serverRequest<NormalizedReadingPath>(
      `/catalog/theory-system/reading-paths/${encodeURIComponent(slug)}/`,
    );
  } catch {
    return null;
  }
}

export async function loadTheoryTimeline(discipline = ""): Promise<TheoryTimelineEvent[]> {
  try {
    const query = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    const payload = await serverRequest<Paginated<TheoryTimelineEvent>>(`/catalog/theory-timeline/${query}`);
    return payload.results;
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return [];
  }
}

export async function loadTheoryGraph(discipline = ""): Promise<TheoryGraph> {
  try {
    const query = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    return await serverRequest<TheoryGraph>(`/catalog/theory-graph/${query}`);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { nodes: [], edges: [] };
  }
}

export async function loadRecommendations(): Promise<RecommendationBundle> {
  try {
    return await serverRequest<RecommendationBundle>("/catalog/recommendations/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { shared_for_all_readers: true, rotation_days: 3, placements: {} };
  }
}

export async function loadAboutBlocks(): Promise<{ configured: boolean; blocks: AboutPageBlock[] }> {
  try {
    const payload = await serverRequest<Paginated<AboutPageBlock> & { configured?: boolean }>("/catalog/about-blocks/");
    return { configured: payload.configured ?? payload.results.length > 0, blocks: payload.results };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { configured: false, blocks: [] };
  }
}

export function recommendationWorks(bundle: RecommendationBundle, placement: string): Work[] {
  return (bundle.placements[placement]?.current?.items ?? [])
    .filter((item) => item.target_type === "work")
    .map((item, index) => adaptWork(item.target as ApiWork, index));
}

export function recommendationSlugs(
  bundle: RecommendationBundle,
  placement: string,
  targetType: "theory_school" | "topic" | "scholar",
): string[] {
  const seen = new Set<string>();
  return (bundle.placements[placement]?.current?.items ?? []).flatMap((item) => {
    if (item.target_type !== targetType || !("slug" in item.target)) return [];
    const slug = String(item.target.slug || "").trim();
    if (!slug || seen.has(slug)) return [];
    seen.add(slug);
    return [slug];
  });
}

export async function loadRecommendedScholars(
  bundle: RecommendationBundle,
  limit = 4,
): Promise<Scholar[]> {
  const itemBySlug = new Map(
    (bundle.placements.home_scholars?.current?.items ?? []).flatMap((item) => (
      item.target_type === "scholar" && "slug" in item.target
        ? [[String(item.target.slug), item] as const]
        : []
    )),
  );
  const items = recommendationSlugs(bundle, "home_scholars", "scholar")
    .slice(0, Math.max(0, limit))
    .flatMap((slug) => itemBySlug.has(slug) ? [itemBySlug.get(slug)!] : []);
  const loaded = await Promise.all(items.map(async (item) => {
    const target = item.target as {
      slug: string;
    };
    try {
      const detail = await loadScholar(target.slug);
      if (detail) return detail.scholar;
    } catch {
      // A missing public detail must not become a visible recommendation with a broken link.
    }
    return null;
  }));
  const seen = new Set<string>();
  return loaded.filter((scholar): scholar is Scholar => {
    if (!scholar) return false;
    if (!scholar.slug || seen.has(scholar.slug)) return false;
    seen.add(scholar.slug);
    return true;
  });
}

export const adaptWork = adaptApiWork;
const adaptScholar = adaptApiScholar;

export async function loadWorks(): Promise<Work[]> {
  try {
    const payload = await serverRequest<Paginated<ApiWork>>("/catalog/works/?ordering=-editions__first_published_at");
    return payload.results.map(adaptWork);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return demoWorks;
  }
}

export async function loadHotSearches(): Promise<string[]> {
  try {
    const payload = await serverRequest<{
      results: { query: string; search_count: number; unique_sessions: number }[];
    }>("/catalog/hot-searches/?days=30&limit=10");
    return payload.results.map((item) => item.query);
  } catch {
    return [];
  }
}

export async function loadCatalogOverview(): Promise<{
  works: number;
  scholars: number;
  theories: number;
}> {
  try {
    const [worksPayload, scholarsPayload, theoriesPayload] = await Promise.all([
      serverRequest<Paginated<ApiWork>>("/catalog/works/"),
      serverRequest<Paginated<ApiScholar>>("/catalog/scholars/"),
      serverRequest<Paginated<{ slug: string }>>("/catalog/theory-schools/"),
    ]);
    return {
      works: worksPayload.count,
      scholars: scholarsPayload.count,
      theories: theoriesPayload.count,
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      works: demoWorks.length,
      scholars: demoScholars.length,
      theories: demoTheorySchools.length,
    };
  }
}

export async function loadWork(slug: string): Promise<Work | null> {
  try {
    return adaptWork(await serverRequest<ApiWork>(`/catalog/works/${encodeURIComponent(slug)}/`));
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    if (!allowDemoFallback) throw error;
    return demoWorks.find((item) => item.slug === slug) ?? null;
  }
}

export async function loadScholarPage(query = "", page = 1): Promise<DirectoryPage<Scholar>> {
  try {
    const parameters = new URLSearchParams({ page: String(page) });
    if (query) parameters.set("q", query);
    const payload = await serverRequest<Paginated<ApiScholar>>(`/catalog/scholars/?${parameters.toString()}`);
    return directoryPage(
      { ...payload, results: payload.results.map(adaptScholar) },
      page,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: demoScholars.length, results: demoScholars }, page);
  }
}

export async function loadScholars(query = ""): Promise<Scholar[]> {
  return (await loadScholarPage(query)).results;
}

export type TheoryDirectoryFilters = {
  theme?: string;
  discipline?: string;
  hasWorks?: boolean;
  hasScholars?: boolean;
  sort?: "name" | "works";
};

export async function loadTheorySchools(
  query = "",
  filters: TheoryDirectoryFilters = {},
): Promise<TheorySchool[]> {
  return (await loadTheorySchoolPage(query, filters)).results;
}

export async function loadTheorySchoolPage(
  query = "",
  filters: TheoryDirectoryFilters = {},
  page = 1,
): Promise<DirectoryPage<TheorySchool>> {
  try {
    const parameters = new URLSearchParams();
    parameters.set("page", String(page));
    if (query) parameters.set("q", query);
    if (filters.theme) parameters.set("theme", filters.theme);
    if (filters.discipline) parameters.set("discipline", filters.discipline);
    if (filters.hasWorks) parameters.set("has_works", "true");
    if (filters.hasScholars) parameters.set("has_scholars", "true");
    if (filters.sort && filters.sort !== "name") parameters.set("sort", filters.sort);
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<ApiTheorySchool>>(`/catalog/theory-schools/${suffix}`);
    const results = payload.results.map((school, index) => ({
      slug: school.slug,
      name: school.name,
      description: school.description || "馆藏关联理论流派",
      books: school.work_count,
      scholars: school.scholar_count,
      symbol: school.symbol || school.name.slice(0, 2) || String(index + 1),
    }));
    return directoryPage({ ...payload, results }, page);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return directoryPage({ count: demoTheorySchools.length, results: demoTheorySchools }, page);
  }
}

export async function loadTheoryEntity(slug: string): Promise<ApiTheorySchool | null> {
  try {
    return await serverRequest<ApiTheorySchool>(
      `/catalog/theory-schools/${encodeURIComponent(slug)}/`,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return null;
  }
}

export async function loadTheorySchool(slug: string): Promise<{
  school: TheorySchool;
  works: Work[];
  scholars: Scholar[];
  keyThemes: string[];
  curated: {
    heroCaption: string;
    foundationalWorks: Work[];
    curatedReadingWorks: Work[];
    keyScholars: { id: string; name: string; slug: string }[];
    neighbors: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      relation?: string;
      source?: string;
    }[];
    coreConcepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptualMap: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
  };
} | null> {
  try {
    const payload = await serverRequest<ApiTheorySchool>(
      `/catalog/theory-schools/${encodeURIComponent(slug)}/`,
    );
    return {
      school: {
        slug: payload.slug,
        name: payload.name,
        description: payload.description,
        books: payload.work_count,
        scholars: payload.scholars?.length ?? 0,
        symbol: payload.symbol || payload.name.slice(0, 2),
      },
      works: (payload.works ?? []).map(adaptWork),
      scholars: (payload.scholars ?? []).map(adaptScholar),
      keyThemes: payload.key_themes ?? [],
      curated: {
        heroCaption: payload.curated?.hero_caption ?? "",
        foundationalWorks: (payload.curated?.foundational_works ?? []).map(adaptWork),
        curatedReadingWorks: (payload.curated?.curated_reading_works ?? []).map(adaptWork),
        keyScholars: payload.curated?.key_scholars ?? [],
        neighbors: payload.curated?.neighbors ?? [],
        coreConcepts: payload.curated?.core_concepts ?? [],
        conceptualMap: payload.curated?.conceptual_map ?? [],
      },
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const school = demoTheorySchools.find((item) => item.slug === slug);
    return school
      ? {
          school,
          works: demoWorks.filter((work) => work.school.includes(school.name.slice(0, 2))),
          scholars: demoScholars.filter((scholar) => scholar.school === school.name),
          keyThemes: [],
          curated: {
            heroCaption: "",
            foundationalWorks: [],
            curatedReadingWorks: [],
            keyScholars: [],
            neighbors: [],
            coreConcepts: [],
            conceptualMap: [],
          },
        }
      : null;
  }
}

export type LibraryTopic = {
  id: string;
  slug: string;
  name: string;
  description: string;
  problemStatement: string;
  coreQuestions: string[];
  researchDimensions: string[];
  methods: string[];
  formationContext: string;
  heroImage: string;
  disciplines: { id: string; name: string; slug: string; is_primary: boolean }[];
  subdisciplines: { id: string; name: string; slug: string; relation_label: string }[];
  linkedTheories: { id: string; name: string; slug: string; relation_label: string }[];
  knowledgeNodes: PublicKnowledgeNodeLink[];
  concepts: string[];
  timeline: [string, string, string][];
  works: Work[];
  scholars: Scholar[];
  theories: TheorySchool[];
  passages: {
    id: string;
    assetId: string;
    title: string;
    pageIndex: number;
    printedLabel: string;
    snippet: string;
  }[];
  workCount: number;
  curatedClaims: PublicCuratedClaimGroups;
  curated: {
    heroCaption: string;
    foundationalWorks: Work[];
    recentWorks: Work[];
    relatedScholars: { id: string; name: string; slug: string }[];
    linkedTheories: { id: string; name: string; slug: string }[];
    readingPaths: {
      title: string;
      description: string;
      level: string;
      works: Work[];
    }[];
    featuredPassageId: string;
    featuredPassageReason: string;
    featuredPassageEvidence: Record<string, unknown>;
  };
};

const adaptTopic = adaptApiTopic;

export async function loadTopics(
  query = "",
  filters: { discipline?: string; subdiscipline?: string; theory?: string; sort?: "name" | "works" } = {},
): Promise<LibraryTopic[]> {
  return (await loadTopicPage(query, filters)).results;
}

export async function loadTopicPage(
  query = "",
  filters: { discipline?: string; subdiscipline?: string; theory?: string; sort?: "name" | "works" } = {},
  page = 1,
): Promise<DirectoryPage<LibraryTopic>> {
  try {
    const parameters = new URLSearchParams();
    parameters.set("page", String(page));
    if (query) parameters.set("q", query);
    if (filters.discipline) parameters.set("discipline", filters.discipline);
    if (filters.subdiscipline) parameters.set("subdiscipline", filters.subdiscipline);
    if (filters.theory) parameters.set("theory", filters.theory);
    if (filters.sort) parameters.set("sort", filters.sort);
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<ApiTopic>>(`/catalog/topics/${suffix}`);
    return directoryPage(
      { ...payload, results: payload.results.map(adaptTopic) },
      page,
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const results = [{
      ...demoTopic,
      id: demoTopic.slug,
      problemStatement: demoTopic.description,
      coreQuestions: [],
      researchDimensions: [],
      methods: [],
      formationContext: "",
      heroImage: "",
      disciplines: [],
      subdisciplines: [],
      linkedTheories: [],
      knowledgeNodes: [],
      works: demoWorks.slice(0, 3),
      scholars: demoScholars.slice(0, 4),
      theories: demoTheorySchools.slice(0, 5),
      passages: [],
      workCount: demoWorks.length,
      curated: {
        heroCaption: "",
        foundationalWorks: [],
        recentWorks: [],
        relatedScholars: [],
        linkedTheories: [],
        readingPaths: [],
        featuredPassageId: "",
        featuredPassageReason: "",
        featuredPassageEvidence: {},
      },
      curatedClaims: {
        core_viewpoint: [],
        major_criticism: [],
        major_response: [],
      },
    }];
    return directoryPage({ count: results.length, results }, page);
  }
}

export async function loadTopic(slug: string): Promise<LibraryTopic | null> {
  try {
    return adaptTopic(
      await serverRequest<ApiTopic>(`/catalog/topics/${encodeURIComponent(slug)}/`),
    );
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return slug === demoTopic.slug
      ? {
          ...demoTopic,
          id: demoTopic.slug,
          problemStatement: demoTopic.description,
          coreQuestions: [],
          researchDimensions: [],
          methods: [],
          formationContext: "",
          heroImage: "",
          disciplines: [],
          subdisciplines: [],
          linkedTheories: [],
          knowledgeNodes: [],
          works: demoWorks.slice(0, 6),
          scholars: demoScholars.slice(0, 4),
          theories: demoTheorySchools.slice(0, 5),
          passages: [],
          workCount: demoWorks.length,
          curated: {
            heroCaption: "",
            foundationalWorks: [],
            recentWorks: [],
            relatedScholars: [],
            linkedTheories: [],
            readingPaths: [],
            featuredPassageId: "",
            featuredPassageReason: "",
            featuredPassageEvidence: {},
          },
          curatedClaims: {
            core_viewpoint: [],
            major_criticism: [],
            major_response: [],
          },
        }
      : null;
  }
}

export async function loadScholar(slug: string): Promise<{
  scholar: Scholar;
  shortDescription: string;
  works: Work[];
  affiliations: string[];
  timeline: [string, string][];
  featuredQuote: string;
  quoteSource: string;
  curatedClaims: PublicCuratedClaimGroups;
  knowledgeNodes: PublicKnowledgeNodeLink[];
  curated: {
    essentialWorks: Work[];
    keyConcepts: Array<{
      name?: string;
      description?: string;
      source?: string;
    } | string>;
    conceptMap: Array<{
      source?: string;
      target?: string;
      relation?: string;
      description?: string;
      label?: string;
    } | string>;
    network: {
      scholar: { id: string; name: string; slug: string };
      relation: string;
      source: string;
    }[];
    frequentlyReadScholars: { id: string; name: string; slug: string }[];
    relatedTheories: {
      id: string;
      name: string;
      slug: string;
      description?: string;
      symbol?: string;
    }[];
  };
} | null> {
  try {
    const payload = await serverRequest<ApiScholar>(
      `/catalog/scholars/${encodeURIComponent(slug)}/`,
    );
    return adaptApiScholarDetail(payload);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const scholar = demoScholars.find((item) => item.slug === slug);
    return scholar
      ? {
          scholar,
          shortDescription: scholar.biography,
          works: demoWorks.filter((work) => work.author.includes(scholar.name.split("·").at(-1) ?? scholar.name)),
          affiliations: [],
          timeline: [],
          featuredQuote: "",
          quoteSource: "",
          curatedClaims: {
            core_viewpoint: [],
            major_criticism: [],
            major_response: [],
          },
          knowledgeNodes: [],
          curated: {
            essentialWorks: [],
            keyConcepts: [],
            conceptMap: [],
            network: [],
            frequentlyReadScholars: [],
            relatedTheories: [],
          },
        }
      : null;
  }
}

export async function loadSearch(query: string, filters: SearchFilters = {}) {
  try {
    const parameters = new URLSearchParams({ context: "global" });
    if (query) parameters.set("q", query);
    if (filters.scope) parameters.set("scope", filters.scope);
    if (filters.sort) parameters.set("sort", filters.sort);
    if (filters.page) parameters.set("page", String(filters.page));
    if (filters.pageSize) parameters.set("page_size", String(filters.pageSize));
    [
      ["document_type", filters.documentType],
      ["theory", filters.theory],
      ["topic", filters.topic],
      ["concept", filters.concept],
      ["author", filters.author],
      ["year", filters.year],
      ["language", filters.language],
      ["access", filters.access],
    ].forEach(([name, values]) => {
      (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
    });
    const payload = await serverRequest<SearchPayload>(
      `/catalog/search/?${parameters.toString()}`,
    );
    return {
      source: "api" as const,
      counts: payload.counts,
      works: payload.works.map(adaptWork),
      scholars: payload.scholars.map(adaptScholar),
      topics: payload.topics,
      theories: payload.theories,
      passages: payload.passages,
      facets: payload.facets,
      pagination: payload.pagination,
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    const folded = query.toLocaleLowerCase("zh-CN");
    const filteredWorks = demoWorks.filter((work) =>
      [work.title, work.author, work.school, work.summary]
        .join(" ")
        .toLocaleLowerCase("zh-CN")
        .includes(folded),
    );
    return {
      source: "demo" as const,
      counts: {
        works: filteredWorks.length,
        books: filteredWorks.filter((work) => work.kind === "图书").length,
        articles: filteredWorks.filter((work) => work.kind === "期刊论文").length,
        theses: filteredWorks.filter((work) => work.kind === "学位论文").length,
        reports: filteredWorks.filter((work) => work.kind === "研究报告").length,
        scholars: demoScholars.length,
        topics: 0,
        theories: 0,
        passages: 1,
      },
      works: filteredWorks.length ? filteredWorks : demoWorks.slice(0, 3),
      scholars: demoScholars,
      topics: [],
      theories: [],
      passages: [],
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      pagination: {
        page: 1,
        page_size: 24,
        total: filteredWorks.length,
        total_pages: 1,
      },
    };
  }
}

export async function loadSemanticSearch(
  query: string,
  filters: SearchFilters = {},
): Promise<SemanticSearchPayload> {
  if (query.trim().length < 2) {
    return {
      query,
      engine: "keyword_fallback",
      fallback_used: false,
      notice: "输入一个词、一句话或一段文字，系统会查找观点相近的公开全文。",
      count: 0,
      work_count: 0,
      understanding: {
        type: "等待输入",
        terms: [],
        related_concepts: [],
        rewrites: [],
        rewrite_source: "",
      },
      query_rewrite_enabled: false,
      query_rewrite_active: false,
      active_rewrite: "",
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      results: [],
    };
  }
  const parameters = new URLSearchParams({ q: query.trim() });
  [
    ["document_type", filters.documentType],
    ["language", filters.language],
    ["author", filters.author],
    ["year", filters.year],
    ["theory", filters.theory],
    ["topic", filters.topic],
    ["concept", filters.concept],
    ["access", filters.access],
  ].forEach(([name, values]) => {
    (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
  });
  if (filters.pageSize) parameters.set("limit", String(filters.pageSize));
  if (filters.workId) parameters.set("work_id", filters.workId);
  if (filters.maxPerWork !== undefined) parameters.set("max_per_work", String(filters.maxPerWork));
  if (filters.sort) parameters.set("sort", filters.sort);
  if (filters.rewrite) parameters.set("rewrite", filters.rewrite);
  if (filters.rewriteDisabled) parameters.set("rewrite_disabled", "1");
  try {
    return await serverRequest<SemanticSearchPayload>(
      `/catalog/semantic-search/?${parameters.toString()}`,
    );
  } catch {
    return {
      query,
      engine: "unavailable",
      fallback_used: false,
      service_unavailable: true,
      fallback_reason: "api_unavailable",
      notice: "观点检索服务暂时无法连接，因此无法验证关键词或语义检索是否已经执行。原文检索、在线阅读和下载仍可继续使用。",
      count: 0,
      work_count: 0,
      understanding: {
        type: "服务暂不可用",
        terms: [],
        related_concepts: [],
        rewrites: [query],
        rewrite_source: "原始查询",
      },
      query_rewrite_enabled: false,
      query_rewrite_active: false,
      active_rewrite: "",
      facets: {
        document_types: [],
        authors: [],
        years: [],
        languages: [],
        access: [],
        theories: [],
        topics: [],
        concepts: [],
      },
      results: [],
    };
  }
}

function emptyViewpointGroups(): Record<ViewpointStance, ViewpointSearchResult[]> {
  return {
    direct: [],
    support: [],
    oppose: [],
    qualify: [],
    critique: [],
    extend: [],
    reframe: [],
  };
}

function emptyViewpointCounts(): Record<ViewpointStance, number> {
  return {
    direct: 0,
    support: 0,
    oppose: 0,
    qualify: 0,
    critique: 0,
    extend: 0,
    reframe: 0,
  };
}

function unavailableViewpointSearch(
  query: string,
  notice: string,
  serviceUnavailable = false,
): ViewpointSearchPayload {
  const groups = emptyViewpointGroups();
  return {
    query,
    query_claim: {
      proposition: query,
      subject: "",
      predicate: "",
      object: "",
      polarity: "uncertain",
      qualifiers: [],
      claim_type: "assertion",
    },
    default_mode: "baseline",
    results: [],
    groups,
    facets: {
      relations: [],
      source_types: [],
      languages: [],
      scholars: [],
      theories: [],
      topics: [],
      works: [],
      publication_year: { min: null, max: null },
    },
    count: 0,
    work_count: 0,
    stance_counts: emptyViewpointCounts(),
    engine: serviceUnavailable ? "unavailable" : "v2",
    search_version: "v2",
    fallback_used: false,
    fallback_reason: serviceUnavailable ? "api_unavailable" : "",
    notice,
    service_unavailable: serviceUnavailable,
    metadata: {
      benchmark_gate_passed: false,
      default_ranking: "semantic_v2_baseline",
      claim_ranking_status: "shadow",
      evidence_span_validation_required: true,
      cosine_similarity_used_for_stance: false,
    },
  };
}

export async function loadViewpointSearch(
  query: string,
  filters: SearchFilters = {},
): Promise<ViewpointSearchPayload> {
  if (query.trim().length < 2) {
    return unavailableViewpointSearch(
      query,
      "输入一个完整的社会科学命题，系统会按直接、支持、相斥、限定和批评整理馆藏原文。",
    );
  }
  const parameters = new URLSearchParams({ q: query.trim() });
  [
    ["document_type", filters.documentType],
    ["language", filters.language],
    ["author", filters.author],
    ["scholar", filters.scholar],
    ["relation", filters.relation],
    ["source_type", filters.sourceType],
    ["year", filters.year],
    ["theory", filters.theory],
    ["topic", filters.topic],
    ["concept", filters.concept],
    ["access", filters.access],
  ].forEach(([name, values]) => {
    (values as string[] | undefined)?.forEach((value) => parameters.append(name as string, value));
  });
  if (filters.yearMin !== undefined) parameters.set("year_min", String(filters.yearMin));
  if (filters.yearMax !== undefined) parameters.set("year_max", String(filters.yearMax));
  if (filters.pageSize) parameters.set("limit", String(filters.pageSize));
  if (filters.workId) parameters.set("work_id", filters.workId);
  if (filters.maxPerWork !== undefined) parameters.set("max_per_work", String(filters.maxPerWork));
  if (filters.sort) parameters.set("sort", filters.sort);
  try {
    return await serverRequest<ViewpointSearchPayload>(
      `/catalog/viewpoint-search/?${parameters.toString()}`,
    );
  } catch {
    return unavailableViewpointSearch(
      query,
      "观点检索暂时无法连接，系统没有生成替代结果。原文检索和在线阅读仍可继续使用。",
      true,
    );
  }
}

export type ReaderOutlineItem = {
  index: number;
  printed_label: string;
  chapter_title: string;
};

export type ReaderManifest = {
  work: Work;
  outline: ReaderOutlineItem[];
  scholars: { name: string; slug: string; years: string }[];
  theories: { name: string; slug: string }[];
  topics: { name: string; slug: string }[];
};

export async function loadReaderManifest(assetId: string): Promise<ReaderManifest | null> {
  try {
    const payload = await serverRequest<{
      asset_id: string;
      edition_id: string;
      page_count: number;
      work: ApiWork;
      outline: ReaderOutlineItem[];
      related_scholars: { name: string; slug: string; years: string }[];
      related_theories: { name: string; slug: string }[];
      related_topics: { name: string; slug: string }[];
    }>(`/catalog/assets/${encodeURIComponent(assetId)}/manifest/`);
    return {
      work: {
        ...adaptWork(payload.work),
        id: payload.asset_id,
        editionId: payload.edition_id,
        pages: payload.page_count,
      },
      outline: payload.outline,
      scholars: payload.related_scholars,
      theories: payload.related_theories,
      topics: payload.related_topics,
    };
  } catch {
    if (!allowDemoFallback) return null;
    const fallback = demoWorks.find((item) => item.id === assetId) ?? demoWorks[0];
    return fallback ? {
      work: { ...fallback, id: assetId },
      outline: [],
      scholars: [],
      theories: [],
      topics: [],
    } : null;
  }
}
