export type DiscoveryStatus = "queued" | "running" | "partial" | "completed" | "failed" | "canceled";
export type DiscoveryDeepStatus = "baseline_ready" | "deep_queued" | "deep_running" | "completed" | "partial" | "unavailable" | "pending" | "queued" | "running" | "degraded" | "disabled" | "skipped" | "failed";
export type DiscoveryFilters = Record<string, string | string[]>;
export type DiscoveryPassage = {
  id: string; excerpt: string; work: { id: string; title: string; slug?: string }; authors: string[];
  asset_id: string; document_revision_id: string; evidence_span_id?: string; passage_id?: string; pdf_page: number; printed_page?: string;
  reader_url: string; context_reference?: string; source_kind: string; locator_precision: string; match_basis: string[];
  deep_rank?: number; deep_score?: number | null; deep_context?: { policy?: string; provider?: string; available?: boolean; before?: string; after?: string; blocks?: Array<Record<string, unknown>> };
};
export type DiscoveryEntity = {
  id: string; kind: string; title: string; url: string; excerpt?: string; portrait_url?: string; match_basis: string[];
};
export type DiscoveryCuration = {
  id: string; source_title: string; title?: string; recommendation_excerpt: string; url: string;
  source_kind?: string; match_basis: string[]; linked_work_ids?: string[];
};
export type DiscoveryCoverage = {
  message?: string; readable?: number; text_ready?: number; keyword_ready?: number; vector_ready?: number;
  knowledge_ready?: number; waiting?: number; failed?: number;
  eligible_editions?: number; indexed_editions?: number; vector_editions?: number; pending_editions?: number;
  published_editions?: number; bibliographic_editions?: number; text_pending_editions?: number;
  index_pending_editions?: number; vector_pending_editions?: number;
  passage_count?: number; partial?: boolean; generation?: string | null;
};
export type DiscoveryDeepProgress = {
  status: DiscoveryDeepStatus; stage: string; completed: number; total: number; terminal: boolean;
  model: string; index_uid: string; index_generation: string; embedding_artifact: string;
  embedding_dimensions?: number | null; reranker_artifact: string; context_artifact: string; notice: string;
  started_at?: string | null; updated_at?: string | null; finished_at?: string | null;
};
export type DiscoveryTaskProgress = {
  id: string; generation: number; status: DiscoveryStatus; terminal: boolean; stage: string;
  completed: number; total: number; unit: string; retryable: boolean;
  started_at?: string | null; updated_at: string; finished_at?: string | null;
  deep: DiscoveryDeepProgress;
};
export type DiscoveryRetrievalIdentity = {
  index_generation: string; index_uid: string; embedding_artifact: string;
  embedding_dimensions?: number | null; reranker_artifact: string; pipeline_version: string;
};
export type DiscoverySearch = {
  id: string; access_token?: string; query: string; status: DiscoveryStatus; status_message?: string;
  mode: "standard" | "expanded"; expansion_count: number; passages: DiscoveryPassage[];
  entities: DiscoveryEntity[]; curation: DiscoveryCuration[]; next_cursor: string | null; can_expand: boolean;
  count?: number; warnings: Array<string | { code: string; message: string; channel?: string }>; coverage_summary: DiscoveryCoverage; completed_channels: string[];
  corpus_version?: string; knowledge_version?: string; pipeline_version?: string; source_changed?: boolean;
  notice?: string; poll_after_ms?: number | null; can_retry?: boolean; task_progress: DiscoveryTaskProgress;
  retrieval_identity: DiscoveryRetrievalIdentity;
  deep_passages?: DiscoveryPassage[]; deep_stage?: DiscoveryDeepProgress;
  channels?: Record<string, { status?: string; [key: string]: unknown }>;
  counts?: Record<string, number>;
  generation?: number; original_query?: string; filters?: DiscoveryFilters;
};
export type DiscoveryContext = {
  result_id: string; excerpt: string; before: string; after: string; reader_url: string; locator_precision: string;
  blocks: Array<{ text: string; pdf_page: number; role: string }>; notice?: string;
};
