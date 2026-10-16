import { apiRequest, apiStreamRequest, getServerSessionCredential } from "../api";
import type { Paginated } from "./pagination";
import type { DiscoveryFilters, DiscoveryPassage } from "./discovery.types";
import type { ReaderGeometryBox } from "../reader-coordinates";

export type EvidenceAnchor = {
  evidence_span_id?: string; asset_id?: string; document_revision_id?: string; pdf_page?: number; content_hash?: string;
};
export type EvidenceReference = EvidenceAnchor & { anchors?: EvidenceAnchor[] };
export type ResolvedEvidence = EvidenceAnchor & ReaderGeometryBox & {
  reference_id?: string; id?: string; source_status: string; text?: string; reader_url?: string | null;
  work_id?: string; edition_id?: string; title?: string; printed_label?: string;
  quote?: string; citation?: string; authors?: string[]; locator_precision?: string;
  bbox?: number[]; start_offset?: number; end_offset?: number;
  coordinate_space?: { width: number; height: number; text_source: string; requires_reader_transform: boolean };
  anchors?: ResolvedEvidence[];
};
export type QueryScope = { kind: "library" | "works" | "passages" | "filtered"; filters?: DiscoveryFilters; references?: EvidenceReference[]; allow_neighbors?: boolean };
export type ResearchCollection = "research-projects" | "research-turns" | "citation-audits" | "reading-plans" | "research-memories";
export type ResearchRecord<T = Record<string, unknown>> = {
  id: string; revision: number; data: T; created_at: string; updated_at: string;
  status?: string; state?: string; enhancement_status?: string; archived?: boolean; generation?: number;
  error_code?: string; poll_after_ms?: number | null; completed_units?: number; total_units?: number;
  project_id?: string | null; parent_id?: string | null; conversation_id?: string | null; discovery_session_id?: string | null;
};
export type ComparisonCell = { dimension: string; column_id?: string; author?: string; reference_ids?: string[]; note?: string; evidence_status?: "selected" | "partial" | "unavailable" | "missing" };
export type ProjectData = {
  title: string; question: string; notes?: string; scope: QueryScope; selections: ResolvedEvidence[];
  comparison?: { dimensions: string[]; cells: ComparisonCell[] }; layout?: Record<string, unknown>; last_turn_id?: string;
};
export type Statement = { proposition: string; subject?: string; predicate?: string; object?: string; polarity?: "positive" | "negative" | "mixed" | "uncertain"; modality?: string; qualifiers?: string[]; temporal_scope?: unknown; geographic_scope?: unknown; population_scope?: unknown };
export type AnalysisRelation = "support" | "different_conclusion" | "qualification" | "reframe" | "insufficient_evidence";
export type TurnData = { question: string; scope: QueryScope; mode: "search" | "counterargument"; result_refs?: ResolvedEvidence[]; selected_refs?: ResolvedEvidence[]; return_context?: Record<string, unknown>; analysis?: Array<{ id: string; reference: ResolvedEvidence; status: string; [key: string]: unknown }>; [key: string]: unknown };
export type MemoryData = { body: string; kind: "understanding" | "question" | "contradiction"; sources: ResolvedEvidence[]; [key: string]: unknown };
export type PlanPolicy = { time_budget?: string; budget_minutes?: number | null; session_minutes?: number; reading_level?: "beginner" | "intermediate" | "advanced"; reading_pace?: { cjk_chars_per_minute?: number; words_per_minute?: number; fallback_minutes_per_page?: number }; prefer_unread?: boolean; item_estimates?: Array<{ work_id: string; difficulty?: "beginner" | "intermediate" | "advanced"; minutes?: number }> };
export type PlanData = { goal: string; background?: string; items: Array<{ id: string; work_id: string; title?: string; status: "pending" | "reading" | "completed" | "skipped"; reference?: ResolvedEvidence; reader_url?: string | null; available?: boolean; [key: string]: unknown }>; [key: string]: unknown };
type Revision = { expected_revision: number };
type NewRequest = { request_id: string };

export const researchRecordPath = (collection: ResearchCollection, id?: string) => `/reading/${collection}/${id ? `${encodeURIComponent(id)}/` : ""}`;
export function privateRequest<T>(path: string, options: RequestInit = {}) {
  const timeout = AbortSignal.timeout(options.body instanceof FormData ? 5 * 60 * 1000 : 30000);
  const signal = options.signal ? AbortSignal.any([options.signal, timeout]) : timeout;
  return apiRequest<T>(path, { ...options, signal, cache: "no-store" }, getServerSessionCredential());
}
function write<T>(path: string, data: unknown, method = "POST") {
  return privateRequest<T>(path, { method, body: JSON.stringify(data) });
}
export function listResearchRecords<T>(collection: ResearchCollection, page = 1, signal?: AbortSignal) {
  return privateRequest<Paginated<ResearchRecord<T>>>(`${researchRecordPath(collection)}?page=${page}`, { signal });
}
export function readResearchRecord<T>(collection: ResearchCollection, id: string, signal?: AbortSignal) {
  return privateRequest<ResearchRecord<T>>(researchRecordPath(collection, id), { signal });
}
export function exportResearchRecord<T>(collection: ResearchCollection, id: string) {
  return privateRequest<ResearchRecord<T> & { schema_version: number; turns?: ResearchRecord<TurnData>[] }>(`${researchRecordPath(collection, id)}export/`);
}
export function deleteResearchRecord(collection: Exclude<ResearchCollection, "research-turns">, id: string, revision: number) {
  return write<void>(researchRecordPath(collection, id), { expected_revision: revision }, "DELETE");
}
export function createResearchProject(data: NewRequest & { title?: string; question?: string; conversation_id?: string; scope?: QueryScope }) {
  return write<ResearchRecord<ProjectData>>(researchRecordPath("research-projects"), data);
}
export type LocalResearchImport = NewRequest & {
  schema_version: 1; local_id: string; title?: string; question?: string; scope?: QueryScope; selections?: EvidenceReference[];
  notes?: string; layout?: Record<string, unknown>; comparison?: { dimensions: string[]; cells: ComparisonCell[] };
  turns?: Array<{ local_id: string; parent_local_id?: string; question: string; scope?: QueryScope; references?: EvidenceReference[]; selected_references?: EvidenceReference[]; notes?: string; created_at?: string; status?: string }>;
};
export function importLocalResearch(data: LocalResearchImport) {
  return write<ResearchRecord<ProjectData & { imported_turns: Record<string, string>; import_warnings: unknown[] }>>(`${researchRecordPath("research-projects")}import/`, data);
}
export function updateResearchProject(id: string, data: Revision & Partial<Pick<ProjectData, "title" | "question" | "notes" | "scope" | "layout">> & { archived?: boolean }) {
  return write<ResearchRecord<ProjectData>>(researchRecordPath("research-projects", id), data, "PATCH");
}
export function changeResearchSelection(id: string, data: Revision & { action: "add" | "remove" | "undo" | "reorder"; references?: EvidenceReference[]; reference_id?: string; order?: string[] }) {
  return write<ResearchRecord<ProjectData>>(`${researchRecordPath("research-projects", id)}selections/`, data);
}
export function saveResearchComparison(id: string, data: Revision & { dimensions: string[]; cells: ComparisonCell[] }) {
  return write<ResearchRecord<ProjectData>>(`${researchRecordPath("research-projects", id)}comparison/`, data);
}
export function listResearchTurns(projectId: string, page = 1, signal?: AbortSignal) {
  return privateRequest<Paginated<ResearchRecord<TurnData>>>(`${researchRecordPath("research-projects", projectId)}turns/?page=${page}`, { signal });
}
export function startResearchTurn(id: string, data: Revision & NewRequest & { question: string; parent_id?: string; scope?: QueryScope; mode?: "search" | "counterargument"; statement?: Statement; subclaims?: Array<Statement & { id: string }>; active_subclaim_id?: string | null; return_context?: Record<string, unknown> }) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-projects", id)}turns/`, data);
}
export function updateResearchSubclaims(id: string, data: Revision & { subclaims: Array<Statement & { id: string }> }) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-turns", id)}subclaims/`, data);
}
export function cancelResearchTurn(id: string) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-turns", id)}cancel/`, {});
}
export function retryResearchTurn(id: string, data: Revision & NewRequest) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-turns", id)}retry/`, data);
}
export function expandResearchTurn(id: string, data: Revision & NewRequest & { scope: QueryScope; question?: string }) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-turns", id)}expand/`, data);
}
export function decideResearchAnalysis(id: string, data: Revision & { id: string; relation: AnalysisRelation; note?: string }) {
  return write<ResearchRecord<TurnData>>(`${researchRecordPath("research-turns", id)}decision/`, data);
}
export function createResearchMemory(data: NewRequest & { body: string; kind?: MemoryData["kind"]; project_id?: string; turn_id?: string; annotation_id?: string; sources?: EvidenceReference[] }) {
  return write<ResearchRecord<MemoryData>>(researchRecordPath("research-memories"), data);
}
export function updateResearchMemory(id: string, data: Revision & { body?: string; sources?: EvidenceReference[]; state?: "proposed" | "confirmed" | "ignored" }) {
  return write<ResearchRecord<MemoryData>>(researchRecordPath("research-memories", id), data, "PATCH");
}
export function searchResearchMemories(data: { q: string; semantic?: boolean; allowed_ids?: string[] }) {
  return write<{ results: Array<ResearchRecord<MemoryData> & { match_reason: string }>; mode: "disabled" | "local_lexical" | "local_semantic_owner_candidates"; notice?: string; warning?: string; semantic_candidate_limit?: number | null; semantic_scope_count?: number; evaluated_count?: number; excluded_count?: number; scope_complete?: boolean }>(`${researchRecordPath("research-memories")}search/`, data);
}
export function createReadingPlan(data: NewRequest & PlanPolicy & { goal: string; background?: string; project_id?: string; turn_id?: string; reading_path_id?: string; references?: EvidenceReference[]; prerequisites?: Array<{ work_id: string; requires_work_id: string; reference: EvidenceReference }>; scope?: QueryScope }) {
  return write<ResearchRecord<PlanData>>(researchRecordPath("reading-plans"), data);
}
export function updateReadingPlan(id: string, data: Revision & PlanPolicy & { order?: string[]; item_id?: string; status?: PlanData["items"][number]["status"]; note?: string; reference?: EvidenceReference; adopt_suggestion?: boolean; optimize_order?: boolean }) {
  return write<ResearchRecord<PlanData>>(researchRecordPath("reading-plans", id), data, "PATCH");
}
export function commandReadingPlan(id: string, data: Revision & { action: "cancel" | "retry" | "enhance" }) {
  return write<ResearchRecord<PlanData>>(`${researchRecordPath("reading-plans", id)}command/`, data);
}
export function createCitationAudit(file: File, requestId: string, projectId?: string) {
  const body = new FormData(); body.set("file", file); body.set("request_id", requestId);
  if (projectId) body.set("project_id", projectId);
  return privateRequest<ResearchRecord>(researchRecordPath("citation-audits"), { method: "POST", body });
}
export function commandCitationAudit(id: string, data: Revision & { action: "cancel" | "match" | "link" | "decision" | "analyze" | "retry"; entry_id?: string; edition_id?: string; occurrence_id?: string; occurrence_ids?: string[]; entry_ids?: string[]; decision?: "accepted" | "ignored" | "corrected" | "needs_review"; note?: string; reference?: EvidenceReference }) {
  return write<ResearchRecord>(`${researchRecordPath("citation-audits", id)}command/`, data);
}
export function readCitationOCR(id: string, unit?: string, signal?: AbortSignal) {
  return privateRequest<{ progress: Record<string, unknown>; units?: Array<Record<string, unknown>>; unit?: Record<string, unknown> }>(`${researchRecordPath("citation-audits", id)}ocr/${unit ? `?unit_id=${encodeURIComponent(unit)}` : ""}`, { signal });
}
export async function downloadAuditOriginal(id: string) {
  const response = await apiStreamRequest(`${researchRecordPath("citation-audits", id)}original/`, { cache: "no-store", signal: AbortSignal.timeout(300000) }, getServerSessionCredential());
  if (!response.ok) throw new Error(`原稿下载失败（${response.status}），请核对登录状态后重试。`);
  return { blob: await response.blob(), disposition: response.headers.get("Content-Disposition") };
}
export function readResearchAccount(signal?: AbortSignal) {
  return privateRequest<{ counts: { research: number; memories: number; plans: number; audits: number }; preferences: boolean; deletion_notice: string }>("/reading/research-account/", { signal });
}
export function updateResearchPersonalization(enabled: boolean) {
  return write<{ research_personalization: boolean }>("/reading/research-account/", { research_personalization: enabled }, "PATCH");
}

/** Only immutable source identifiers cross from Discovery into a private project. */
export function passageReference(passage: DiscoveryPassage): EvidenceReference {
  return { ...(passage.evidence_span_id ? { evidence_span_id: passage.evidence_span_id } : {}), asset_id: passage.asset_id, document_revision_id: passage.document_revision_id, pdf_page: passage.pdf_page };
}
