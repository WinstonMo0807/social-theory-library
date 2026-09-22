export type DiscoveryStatus = "queued" | "running" | "partial" | "completed" | "failed" | "canceled";
export type DiscoveryFilters = Record<string, string | string[]>;
export type DiscoveryPassage = {
  id: string; excerpt: string; work: { id: string; title: string; slug?: string }; authors: string[];
  asset_id: string; document_revision_id: string; pdf_page: number; printed_page?: string;
  reader_url: string; context_reference?: string; source_kind: string; locator_precision: string; match_basis: string[];
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
  passage_count?: number; partial?: boolean; generation?: string | null;
};
export type DiscoverySearch = {
  id: string; access_token?: string; query: string; status: DiscoveryStatus; status_message?: string;
  mode: "standard" | "expanded"; expansion_count: number; passages: DiscoveryPassage[];
  entities: DiscoveryEntity[]; curation: DiscoveryCuration[]; next_cursor: string | null; can_expand: boolean;
  count?: number; warnings: Array<string | { code: string; message: string; channel?: string }>; coverage_summary: DiscoveryCoverage; completed_channels: string[];
  corpus_version?: string; knowledge_version?: string; pipeline_version?: string; source_changed?: boolean;
  notice?: string; poll_after_ms?: number | null;
};
export type DiscoveryContext = {
  result_id: string; excerpt: string; before: string; after: string; reader_url: string; locator_precision: string;
  blocks: Array<{ text: string; pdf_page: number; role: string }>; notice?: string;
};
