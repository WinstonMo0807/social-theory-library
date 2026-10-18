import { apiRequest, getServerSessionCredential } from "../api";
import type { Paginated } from "./pagination";
import type { OutlineNode } from "./document-outline";

const segment = encodeURIComponent;
function request<T>(path: string, options: RequestInit = {}) {
  const deadline = AbortSignal.timeout(30000);
  const signal = options.signal ? AbortSignal.any([options.signal, deadline]) : deadline;
  return apiRequest<T>(path, { ...options, signal, cache: "no-store" }, getServerSessionCredential());
}
function command<T>(path: string, body: unknown) { return request<T>(path, { method: "POST", body: JSON.stringify(body) }); }

export type OutlineRevision = { id: string; revision: number; asset_id: string; document_revision_id: string; origin: string; is_active: boolean; reviewed: boolean; diagnostics: Array<Record<string, unknown>>; created_at: string; node_count: number; nodes?: OutlineNode[] };
export type OutlineState = { asset_id: string; expected_revision: number; active: OutlineRevision | null; latest: OutlineRevision | null; history: OutlineRevision[]; history_page: number; history_count: number; history_next_page: number | null; jobs: Array<{ id: string; status: string; progress: number; error: string; updated_at: string; result_revision_id?: string }> };
export type OutlineEditNode = { id?: string; parent_id?: string | null; title: string; pdf_page: number | null; printed_label?: string; pdf_position?: number[]; normalized_position?: number[]; contents_page?: number | null };
export const outlinePath = (assetId: string) => `/catalog/admin/assets/${segment(assetId)}/outline/`;
export function readOutlineState(assetId: string, historyPage = 1, signal?: AbortSignal) { return request<OutlineState>(`${outlinePath(assetId)}?history_page=${historyPage}`, { signal }); }
export function readOutlineRevision(assetId: string, revisionId: string, signal?: AbortSignal) { return request<OutlineRevision>(`${outlinePath(assetId)}?revision_id=${segment(revisionId)}`, { signal }); }
export function editOutline(assetId: string, body: { request_id: string; expected_revision: number; nodes: OutlineEditNode[] }) { return command<OutlineState>(outlinePath(assetId), { ...body, action: "edit" }); }
export function adoptOutline(assetId: string, body: { request_id: string; expected_revision: number; revision_id: string; action: "adopt" | "restore" }) { return command<OutlineState>(outlinePath(assetId), body); }
export function rebuildOutline(assetId: string, requestId: string) { return command<{ job_id: string; status: string }>(outlinePath(assetId), { action: "rebuild", request_id: requestId }); }
export function actOnOutlineJob(id: string, action: "cancel" | "retry") { return command<{ job_id: string; status: string }>(`/catalog/admin/outline-jobs/${segment(id)}/`, { action }); }
export function listOutlineRebuilds(filter: "missing" | "stale" | "needs_review" | "all", after = "", signal?: AbortSignal) {
  return request<{ items: Array<{ asset_id: string; edition_id: string; title: string; page_count: number }>; next_cursor: string | null }>(`/catalog/admin/outline-rebuilds/?${new URLSearchParams({ filter, ...(after ? { after } : {}) })}`, { signal });
}
export function rebuildOutlineBatch(assetIds: string[], requestId: string) { return command<{ results: Array<{ asset_id: string; job_id?: string; status?: string; error?: string }> }>("/catalog/admin/outline-rebuilds/", { asset_ids: assetIds, request_id: requestId }); }

export type PlacementPage = "scholar" | "node" | "topic" | "discipline" | "subdiscipline" | "reading_path" | "issue" | "site" | "timeline_event";
export type PlacementTarget = { type: "work" | "edition" | "node" | "span"; id: string; edition_id?: string; document_revision_id?: string };
export type PlacementSource = { type: PlacementTarget["type"]; id: string; title: string; public_eligible: boolean; reader_url?: string; edit_url?: string; work_id?: string; edition_id?: string; document_revision_id?: string | null; asset_id?: string; text?: string; [key: string]: unknown };
export type Placement = { id?: string; area?: string; group?: string; position?: number; target: PlacementTarget; reason?: string; local_text?: string; reading_target?: { asset_id: string; document_revision_id: string; pdf_page: number } | null; concept_usage?: Record<string, unknown> | null };
export type PlacementState = { schema_version: number; page_type: PlacementPage; page_id: string; revision_id: string | null; configured: boolean; items: Array<Placement & { id: string; source: PlacementSource | null }>; withdrawn: boolean; expected_revision?: string; is_current_revision?: boolean; published_revision_id?: string | null; has_unpublished_changes?: boolean; source_problems?: Array<Record<string, unknown>>; publication_blockers?: Array<Record<string, unknown>>; state?: string; can_publish?: boolean; impact?: string; title?: string; replayed?: boolean; applied_revision_id?: string };
export type PlacementCommand = { action: "save" | "add" | "move" | "update" | "remove" | "undo" | "restore" | "publish" | "withdraw"; request_id: string; expected_revision: string; items?: Placement[]; item?: Placement; item_id?: string; position?: number; area?: string; group?: string; patch?: Partial<Placement>; revision_id?: string };
export const placementsPath = (type: PlacementPage, id: string) => `/catalog/admin/content-placements/${segment(type)}/${segment(id)}/`;
export function readPlacements(type: PlacementPage, id: string, revision?: string, signal?: AbortSignal) { return request<PlacementState>(`${placementsPath(type, id)}${revision ? `?revision=${segment(revision)}` : ""}`, { signal }); }
export function changePlacements(type: PlacementPage, id: string, body: PlacementCommand) { return command<PlacementState>(placementsPath(type, id), body); }
export function listPlacementSources(type: PlacementTarget["type"], q: string, page = 1, signal?: AbortSignal) { return request<Paginated<{ target: PlacementTarget; source: PlacementSource }>>(`/catalog/admin/content-placements/sources/?${new URLSearchParams({ type, q, page: String(page) })}`, { signal }); }
export function readPlacementHistory(type: PlacementPage, id: string, page = 1, signal?: AbortSignal) { return request<Paginated<{ id: string; revision: number; base_revision: number; status: string; created_at: string; published_at: string | null; item_count: number; withdrawn: boolean }>>(`${placementsPath(type, id)}history/?page=${page}`, { signal }); }

export type EditorialAssistance = { id: string; issue_id: string; operation: "outline" | "guide" | "comparison"; status: string; stage: string; progress: number; error_code: string; error_message: string; source_available: boolean; draft_changed: boolean; can_adopt: boolean; edit_version: string; sources: Array<Record<string, unknown>>; suggestions: Array<{ id: string; kind: "heading" | "paragraph"; text: string; source_keys: string[]; gap: string }>; adopted_ids: string[]; model: Record<string, unknown> | null; poll_after_ms: number | null };
export const editorialAssistancePath = (issueId: string, jobId?: string) => `/catalog/admin/recommendation-issues/${segment(issueId)}/assistant/${jobId ? `${segment(jobId)}/` : ""}`;
export function listEditorialAssistance(issueId: string, page = 1, signal?: AbortSignal) { return request<{ count: number; page: number; total_pages: number; results: EditorialAssistance[] }>(`${editorialAssistancePath(issueId)}?page=${page}`, { signal }); }
export function readEditorialAssistance(issueId: string, jobId: string, signal?: AbortSignal) { return request<EditorialAssistance>(editorialAssistancePath(issueId, jobId), { signal }); }
export function startEditorialAssistance(issueId: string, body: { request_id: string; edit_version: string; operation: EditorialAssistance["operation"]; question: string; references: Record<string, unknown>[] }) { return command<EditorialAssistance>(editorialAssistancePath(issueId), body); }
export function actOnEditorialAssistance(issueId: string, jobId: string, body: { action: "retry" | "cancel" | "adopt"; request_id?: string; edit_version?: string; suggestion_ids?: string[] }) { return command<EditorialAssistance>(editorialAssistancePath(issueId, jobId), body); }
