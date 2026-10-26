import { apiRequest, getServerSessionCredential } from "../api";
import type { OutlineAsset } from "./curation-workspace.client";

export type MappingPage = { pdf_page: number; labels: string[]; page_type: "front" | "body" | "appendix" | "other" | "blank"; confirmed: boolean; note: string; source_note?: string; override_manual: boolean; source?: string; confidence?: number };
export type MappingSegment = { id: string; name: string; start: number; end: number; start_label: string; style: "arabic" | "roman_lower" | "roman_upper" | "custom" | "none" };
export type MappingMissing = { action?: "mark" | "blank"; id: string; label: string; after_pdf_page: number; note: string; confirmed: boolean };
export type MappingData = { pages: MappingPage[]; segments: MappingSegment[]; missing: MappingMissing[] };
export type MappingDiagnostics = { unconfirmed_pages: number[]; duplicate_labels: Array<{ label: string; pdf_pages: number[]; acknowledged: boolean }>; spreads: number[]; unconfirmed_missing: string[]; missing_present: string[] };
export type MappingRevision = { id: string; revision: number; origin: string; created_at: string; created_by_id: number | null; source_fingerprint: string; restored_from_id: string | null; applied_at: string | null; applied_asset_id: string | null; data?: MappingData; diagnostics?: MappingDiagnostics; publication: { event_id: string; status: string; revision_id: string; revision_status: string; error: string } | null };
export type MappingCopyJob = {id:string;status:string;progress:number;updated_at:string;error:string;mapping_revision_id:string;download_url:string};
export type MappingState = { jobs?: MappingCopyJob[]; asset: OutlineAsset & { publication_state: string; byte_size?: number }; asset_id: string; expected_revision: number; source_fingerprint: string; current: MappingData; latest: MappingRevision | null; history: MappingRevision[]; history_count: number; history_page: number; history_next_page: number | null; result?: MappingRevision; preceding_revision: { asset_id: string; revision_id: string; revision: number } | null };
export type MappingPreview = { revision_id: string; source_fingerprint: string; prepared_fingerprint: string; copy_asset_id: string | null; inserted_pages: Array<MappingMissing & { pdf_page: number }>; new_page_count: number; changes: Array<{ pdf_page: number; new_pdf_page: number; before: string[]; after: string[]; page_type_before: string; page_type_after: string; note: string; source_note_before?: string; source_note_after?: string; manual_before: boolean }>; changed_page_count: number; missing_before: MappingMissing[]; missing_after: MappingMissing[]; segments_before: MappingSegment[]; segments_after: MappingSegment[]; diagnostics: MappingDiagnostics; blockers: string[]; can_apply: boolean; mode: "publish" | "apply_draft" };
export type MappingCommand = { action: "save" | "analyze" | "segment" | "restore" | "publish" | "export"; request_id: string; expected_revision: number; source_fingerprint: string; data?: MappingData; segment?: MappingSegment; revision_id?: string; prepared_fingerprint?: string };
export const mappingPath = (assetId: string) => `/catalog/admin/assets/${encodeURIComponent(assetId)}/page-mapping/`;
function request<T>(path: string, options: RequestInit = {}) { return apiRequest<T>(path, { ...options, cache: "no-store", signal: options.signal || AbortSignal.timeout(60000) }, getServerSessionCredential()); }
export function mappingCommand(assetId: string, body: MappingCommand) { return request<MappingState>(mappingPath(assetId), { method: "POST", body: JSON.stringify(body) }); }
export function mappingPreview(assetId: string, body: { expected_revision: number; source_fingerprint: string; revision_id: string }) { return request<MappingPreview>(mappingPath(assetId), { method: "POST", body: JSON.stringify({ ...body, action: "prepare" }) }); }
export function readMappingRevision(assetId: string, revisionId: string) { return request<MappingRevision>(`${mappingPath(assetId)}?revision_id=${encodeURIComponent(revisionId)}`); }
export function readMappingHistory(assetId: string, page: number) { return request<MappingState>(`${mappingPath(assetId)}?history_page=${page}`); }

export function mappingEditable(state: MappingState) { return structuredClone(state.latest?.source_fingerprint === state.source_fingerprint && state.latest.data ? state.latest.data : state.current); }
export function mappingDuplicates(data: MappingData) {
  const labels = new Map<string, number[]>();
  data.pages.forEach(row => row.labels.forEach(label => { if (label) labels.set(label, [...(labels.get(label) || []), row.pdf_page]); }));
  return Array.from(labels, ([label, pages]) => ({ label, pages })).filter(row => row.pages.length > 1);
}
