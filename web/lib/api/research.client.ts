import { apiRequest, apiStreamRequest, getServerSessionCredential } from "../api";
import type { Paginated } from "./pagination";
import type { DiscoveryFilters, DiscoveryPassage } from "./discovery.types";
import type { ReaderGeometryBox } from "../reader-coordinates";
import { subscribeToSessionChanges } from "../api";
import { withPrivateOwner } from "./private-owner";

export type EvidenceAnchor = {
  evidence_span_id?: string; asset_id?: string; document_revision_id?: string; pdf_page?: number; content_hash?: string;
  selection_start?: number; selection_end?: number;
};
export type EvidenceReference = EvidenceAnchor & { anchors?: EvidenceAnchor[] };
export type ResolvedEvidence = EvidenceAnchor & ReaderGeometryBox & {
  reference_id?: string; id?: string; source_status: string; text?: string; reader_url?: string | null;
  work_id?: string; edition_id?: string; title?: string; printed_label?: string;
  printed_labels?: string[]; printed_label_precision?: "spread" | "page" | "unknown";
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
  finished_at?: string | null;
};
export type ComparisonCell = { dimension: string; column_id?: string; author?: string; reference_ids?: string[]; note?: string; evidence_status?: "selected" | "partial" | "unavailable" | "missing" };
export type ProjectData = {
  title: string; question: string; notes?: string; scope: QueryScope; selections: ResolvedEvidence[];
  selection_notes?: Record<string, string>;
  comparison?: { dimensions: string[]; cells: ComparisonCell[] }; layout?: Record<string, unknown>; last_turn_id?: string;
};
export type Statement = { proposition: string; subject?: string; predicate?: string; object?: string; polarity?: "positive" | "negative" | "mixed" | "uncertain"; modality?: string; qualifiers?: string[]; temporal_scope?: unknown; geographic_scope?: unknown; population_scope?: unknown };
export type AnalysisRelation = "support" | "different_conclusion" | "qualification" | "reframe" | "insufficient_evidence";
export type TurnData = { question: string; scope: QueryScope; mode: "search" | "counterargument"; result_refs?: ResolvedEvidence[]; selected_refs?: ResolvedEvidence[]; return_context?: Record<string, unknown>; analysis?: Array<{ id: string; reference: ResolvedEvidence; status: string; [key: string]: unknown }>; memory_reminders?: Array<{ id: string; revision: number; body: string; kind: string; notice?: string }>; memory_reminders_status?: string; [key: string]: unknown };
export type MemoryData = { body: string; kind: "understanding" | "question" | "contradiction"; sources: ResolvedEvidence[]; [key: string]: unknown };
export type PlanLevel = "beginner" | "intermediate" | "advanced";
export type PlanPolicy = {
  time_budget?: string; budget_minutes?: number | null; session_minutes?: number; reading_level?: PlanLevel;
  weekly_minutes?: number; duration_weeks?: number; language_preference?: string;
  use_confirmed_memories?: boolean; confirmed_memory_ids?: string[];
  reading_pace?: { cjk_chars_per_minute?: number; words_per_minute?: number; fallback_minutes_per_page?: number };
  prefer_unread?: boolean; item_estimates?: Array<{ work_id: string; difficulty?: PlanLevel; minutes?: number }>;
};
export type PlanItem = {
  id: string; work_id: string; title?: string; status: "pending" | "reading" | "completed" | "skipped";
  reference?: ResolvedEvidence | null; reader_url?: string | null; available?: boolean; cover_url?: string | null;
  authors?: string[]; publication_year?: number | null; stage?: string; reason?: string; learning_goal?: string;
  note?: string; estimated_minutes?: number | null; reading_scope?: string;
  difficulty?: { level: PlanLevel | null; basis?: string; notice?: string };
  budget_assignment?: { included: boolean; reason: string; planned_minutes: number | null };
  planning_estimate?: { method?: string; total_pages?: number; sampled_pages?: number[]; limits?: string };
  prior_reading?: { recorded?: boolean; progress_ratio?: number | null };
  model_suggestion?: { stage: string; reason: string; learning_goal: string };
  suggestion_adopted_at?: string; [key: string]: unknown;
};
export type PlanData = {
  goal: string; background?: string; time_budget?: string; items: PlanItem[]; notice?: string;
  generation_status?: string; enhancement_status?: string; error_code?: string;
  use_confirmed_memories?: boolean; confirmed_memory_ids?: string[];
  planning_inputs?: PlanPolicy;
  planning_policy?: PlanPolicy & { budget_period?: string; notice?: string; pace?: PlanPolicy["reading_pace"]; personalization_enabled?: boolean };
  schedule?: { budget_minutes: number | null; planned_minutes: number; unknown_duration_count: number;
    deferred_item_ids: string[]; sessions: Array<{ index: number; minutes: number; items: Array<{ item_id: string; planned_minutes: number }> }>;
    unscheduled_minutes?: number; notice?: string };
  prerequisites?: Array<{ work_id: string; requires_work_id: string; reference: ResolvedEvidence }>;
  origin?: { reading_path_id?: string; turn_id?: string; type?: string; source_revision?: { token: string }; path_slug?: string }; [key: string]: unknown;
};
type Revision = { expected_revision: number };
type NewRequest = { request_id: string };

export type AuditCheck = "citation_identification" | "bibliography_identity" | "version_page" | "scan_ocr";
export type AuditCapabilities = {
  max_upload_bytes: number; max_pdf_pages: number;
  checks: Array<{ id: AuditCheck | "deep_analysis"; label: string; available: boolean; required?: boolean; requires?: AuditCheck[]; description: string }>;
  scopes: Array<{ id: string; label: string; available: boolean; description: string }>;
  default_checks?: AuditCheck[]; max_active_jobs_per_owner?: number;
  ocr?: { available: boolean; reason: string; service_verified: boolean };
  analysis?: { available: boolean; reason: string; service_verified: boolean };
  [key: string]: unknown;
};
export type AuditLocation = { part?: string; paragraph?: number | null; note_id?: string | number | null; pdf_page?: number | null; start?: number; end?: number; xml_node?: string; end_paragraph?: number };
export type AuditTextUnit = { id: string; index: number; text: string; location: AuditLocation; matchable?: boolean; coverage_status?: "parsed_text" | "unread_content" };
export type AuditTextPage = { audit_id?: string; source_id?: string; manuscript_revision?: number; generation?: number; status?: string; revision: number; count: number; page: number; next_page: number | null; units: AuditTextUnit[]; notice?: string };
export type PrivateCitationSourceData = { purpose: "private_source"; filename: string; filetype: "pdf" | "docx"; title?: string; citation?: string; parsed?: boolean; source_generation?: number; segment_count?: number; matchable_segment_count?: number; stage?: string; file_size_bytes?: number; manuscript_stats?: AuditData["manuscript_stats"]; warnings?: AuditData["warnings"] };
export type PrivateCitationCandidate = { source_id: string; kind?: "private_source"; source_generation?: number; title?: string; filename?: string; citation?: string; source_status?: string };
export type PrivateCitationReference = { source_id: string; source_generation: number; unit_id: string; content_hash?: string; quote?: string; location?: AuditLocation; source_status: string; title?: string; filename?: string; citation?: string; original_url?: string | null };
export type AuditCandidate = {
  edition_id: string; work_id?: string; title: string; year?: number | null; version_label?: string; citation?: string;
  basis?: string; similarity?: number | null; review_fields?: string[]; source_status?: string;
  cover_url?: string | null; authors?: string[];
  identity_signals?: Record<string, { status: string; [key: string]: unknown }>;
};
export type AuditEntry = { id: string; label?: string; raw: string; doi?: string; location?: AuditLocation;
  identity_status: string; candidates: AuditCandidate[]; selected_edition_id?: string | null;
  selected_source_status?: string;
  private_candidates?: PrivateCitationCandidate[]; selected_private_source_id?: string | null; selected_private_source_status?: string;
  history?: Array<{ at: string; selected_edition_id?: string | null; identity_status?: string }> };
export type AuditDecision = { value: "accepted" | "ignored" | "corrected" | "needs_review"; note: string; at: string; corrected_text?: string };
export type AuditFinding = { kind: string; status: string; source_status?: string; message?: string; edition_id?: string; references?: ResolvedEvidence[];
  private_references?: PrivateCitationReference[];
  claimed_printed_label?: string | null; page_status?: string };
export type AuditOccurrence = {
  id: string; raw: string; quote?: string; context: string; note_text?: string; location: AuditLocation; entry_ids: string[];
  findings: AuditFinding[]; decision?: AuditDecision | null; decision_history?: AuditDecision[];
  checked_at?: string; checked_generation?: number;
  support_analysis?: { status: string; reference: ResolvedEvidence; suggestions: Array<{ relation?: string; reason?: string; [key: string]: unknown }> };
  history?: Array<{ generation: number; checked_at: string; findings: AuditFinding[]; decision?: AuditDecision | null }>;
};
export type AuditVersionSummary = {
  id: string; revision: number; manuscript_revision: number; filename: string; status: string;
  created_at: string; finished_at: string | null; parent_audit_id: string | null;
};
export type AuditVersions = { current_id: string; versions: AuditVersionSummary[]; notice: string; truncated?: boolean };
export type AuditVersionComparison = {
  status: "pending" | "completed"; base_audit_id: string; notice?: string;
  total_occurrences?: number; changed_occurrences?: number; reused_occurrences?: number; added_occurrences?: number;
  removed_occurrences?: number; ambiguous_occurrences?: number; changed_bibliography_entries?: number; rechecked_occurrences?: number;
};
export type AuditData = {
  filename: string; filetype: "pdf" | "docx"; manuscript_revision?: number; stage?: string; parsed?: boolean;
  bibliography: AuditEntry[]; occurrences: AuditOccurrence[]; checks?: AuditCheck[]; scope?: string;
  private_source_ids?: string[]; private_sources?: PrivateCitationCandidate[];
  warnings?: Array<{ code: string; message: string }>; report_notice?: string; location_notice?: string;
  file_size_bytes?: number;
  manuscript_stats?: { file_size_bytes?: number; paragraph_count?: number; char_count?: number; pdf_page_count?: number | null; embedded_image_count?: number; occurrence_count?: number; bibliography_count?: number };
  ocr_progress?: { processed?: number; total?: number; completed?: number; failed?: number; no_text?: number };
  ocr_units?: Record<string, { status: string; pdf_page?: number; error?: string; [key: string]: unknown }>;
  parse_history?: Array<{ occurrences?: AuditOccurrence[]; bibliography?: AuditEntry[]; [key: string]: unknown }>;
  version_lineage?: { parent_audit_id: string; parent_revision: number; ancestor_ids: string[]; check_changed_only: boolean };
  version_comparison?: AuditVersionComparison;
};

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
export function exportResearchRecord<T>(collection: ResearchCollection, id: string, ownerId?: string) {
  return privateRequest<ResearchRecord<T> & { schema_version: number; turns?: ResearchRecord<TurnData>[] }>(`${researchRecordPath(collection, id)}export/`, ownerId ? { headers: { "X-Reader-Owner": ownerId } } : {});
}
export function deleteResearchRecord(collection: Exclude<ResearchCollection, "research-turns">, id: string, revision: number) {
  return write<void>(researchRecordPath(collection, id), { expected_revision: revision }, "DELETE");
}
export function createResearchProject(data: NewRequest & { expected_owner_id?: number; title?: string; question?: string; conversation_id?: string; scope?: QueryScope }) {
  return apiRequest<ResearchRecord<ProjectData>>(researchRecordPath("research-projects"), { method: "POST", body: JSON.stringify(data),
    signal: AbortSignal.timeout(30000), cache: "no-store" }, getServerSessionCredential(), false);
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
export function changeResearchSelection(id: string, data: Revision & { expected_owner_id?: number; request_id?: string; note?: string; notes?: Record<string, string>; action: "add" | "remove" | "undo" | "reorder"; references?: EvidenceReference[]; reference_id?: string; order?: string[] }) {
  return apiRequest<ResearchRecord<ProjectData>>(`${researchRecordPath("research-projects", id)}selections/`, { method: "POST", body: JSON.stringify(data),
    signal: AbortSignal.timeout(30000), cache: "no-store" }, getServerSessionCredential(), false);
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
export async function updateReadingPlan(id: string, data: Revision & PlanPolicy & { request_id?: string; item_minutes?: number | null; goal?: string; background?: string; order?: string[]; item_id?: string; status?: PlanItem["status"]; note?: string; reference?: EvidenceReference; adopt_suggestion?: boolean; optimize_order?: boolean; preview?: boolean; remove_related_prerequisites?: boolean }, ownerId: string, signal?: AbortSignal, onDispatch?: () => void) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  const combined = AbortSignal.any([session.signal, AbortSignal.timeout(30000), ...(signal ? [signal] : [])]);
  try {
    return await withPrivateOwner(ownerId, () => {
      combined.throwIfAborted(); onDispatch?.();
      return apiRequest<ResearchRecord<PlanData>>(researchRecordPath("reading-plans", id), { method: "PATCH", body: JSON.stringify(data), cache: "no-store", signal: combined, headers: { "X-Reader-Owner": ownerId } }, getServerSessionCredential(), false);
    }, combined);
  } finally { unsubscribe(); }
}
export function commandReadingPlan(id: string, data: Revision & { action: "cancel" | "retry" | "enhance" }) {
  return write<ResearchRecord<PlanData>>(`${researchRecordPath("reading-plans", id)}command/`, data);
}
export function readAuditCapabilities(signal?: AbortSignal) {
  return privateRequest<AuditCapabilities>(`${researchRecordPath("citation-audits")}capabilities/`, { signal });
}
export function createCitationAudit(file: File, requestId: string, projectId?: string, options?: { checks: AuditCheck[]; scope: string; private_source_ids?: string[] }) {
  const body = new FormData(); body.set("file", file); body.set("request_id", requestId);
  if (projectId) body.set("project_id", projectId);
  if (options) { for (const check of options.checks) body.append("checks", check); body.set("scope", options.scope); }
  for (const id of options?.private_source_ids || []) body.append("private_source_ids", id);
  return privateRequest<ResearchRecord<AuditData>>(researchRecordPath("citation-audits"), { method: "POST", body });
}
export function commandCitationAudit(id: string, data: Revision & { action: "cancel" | "match" | "match_private" | "sources" | "link" | "decision" | "analyze" | "retry"; entry_id?: string; edition_id?: string; source_id?: string; private_source_ids?: string[]; occurrence_id?: string; occurrence_ids?: string[]; entry_ids?: string[]; decision?: "accepted" | "ignored" | "corrected" | "needs_review"; note?: string; corrected_text?: string; reference?: EvidenceReference }) {
  return write<ResearchRecord<AuditData>>(`${researchRecordPath("citation-audits", id)}command/`, data);
}
export function createCitationAuditVersion(id: string, file: File, data: Revision & { request_id: string; check_changed_only: boolean }) {
  const body = new FormData(); body.set("file", file); body.set("request_id", data.request_id);
  body.set("expected_revision", String(data.expected_revision)); body.set("check_changed_only", String(data.check_changed_only));
  return privateRequest<ResearchRecord<AuditData>>(`${researchRecordPath("citation-audits", id)}versions/`, { method: "POST", body });
}
export function readCitationOCR(id: string, unit?: string, signal?: AbortSignal) {
  return privateRequest<{ progress: Record<string, unknown>; units?: Array<Record<string, unknown>>; unit?: Record<string, unknown> }>(`${researchRecordPath("citation-audits", id)}ocr/${unit ? `?unit_id=${encodeURIComponent(unit)}` : ""}`, { signal });
}
export async function downloadAuditOriginal(id: string) {
  const response = await apiStreamRequest(`${researchRecordPath("citation-audits", id)}original/`, { cache: "no-store", signal: AbortSignal.timeout(300000) }, getServerSessionCredential());
  if (!response.ok) throw new Error(`原稿下载失败（${response.status}），请核对登录状态后重试。`);
  return { blob: await response.blob(), disposition: response.headers.get("Content-Disposition") };
}
export const privateCitationSourcePath = (id?: string) => `/reading/citation-sources/${id ? `${encodeURIComponent(id)}/` : ""}`;
export function createPrivateCitationSource(file: File, data: NewRequest & { title?: string; citation?: string; scan_ocr: boolean }) {
  const body = new FormData(); body.set("file", file); body.set("request_id", data.request_id); body.set("scan_ocr", String(data.scan_ocr));
  if (data.title) body.set("title", data.title); if (data.citation) body.set("citation", data.citation);
  return privateRequest<ResearchRecord<PrivateCitationSourceData>>(privateCitationSourcePath(), { method: "POST", body });
}
export function commandPrivateCitationSource(id: string, data: Revision & { action: "cancel" | "retry" }) {
  return write<ResearchRecord<PrivateCitationSourceData>>(`${privateCitationSourcePath(id)}command/`, data);
}
export function deletePrivateCitationSource(id: string, revision: number) {
  return write<void>(privateCitationSourcePath(id), { expected_revision: revision }, "DELETE");
}
export async function downloadPrivateCitationSource(id: string) {
  const response = await apiStreamRequest(`${privateCitationSourcePath(id)}original/`, { cache: "no-store", signal: AbortSignal.timeout(300000) }, getServerSessionCredential());
  if (!response.ok) throw new Error(`私人来源读取失败（${response.status}），请核对登录与来源状态。`);
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
