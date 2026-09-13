// Existing public presentation contracts. Only schema-backed imports are generated.
import type { SearchContext } from "../search-context";
import type { ApiScholar } from "./people.types";
import type { ApiWork } from "./public-catalog";

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

export type SearchPayload = {
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
