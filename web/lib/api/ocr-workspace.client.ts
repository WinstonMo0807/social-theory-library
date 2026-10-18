import { apiRequest, getServerSessionCredential } from "../api";
import type { OutlineAsset } from "./curation-workspace.client";

export type OCROptions = { languages: string[]; layout: boolean; quality_threshold: number; detect_spreads: boolean; detect_garbled: boolean; skip_reviewed: boolean };
export type OCRCorrection = { id: string; revision: number; pdf_page: number; text: string; original_text: string; note: string; confirmed: boolean; review_only: boolean; source_fingerprint: string; created_at: string; applied_at: string | null; applied_asset_id: string | null; publication: { id: string; status: string; revision_status: string } | null };
export type OCRPage = { pdf_page: number; printed_label: string; text_source: string; confidence: number; is_text_manual: boolean; char_count: number; status: string; reason: string; source_fingerprint: string };
export type OCRJob = { id: string; status: string; phase_label: string; completed_pages: number | null; total_pages: number | null; percent: number | null; updated_at: string; error: string; warnings: string[]; can_pause: boolean; can_resume: boolean; resume_reason: string; can_cancel: boolean; result_asset_id: string; source_asset_id: string; public_result: string; stale: boolean; active_pages: number[]; task_options?: OCROptions | null; protected_page_indexes?: number[]; reviewed_page_indexes?: number[] };
export type OCRWorkspace = { asset: OutlineAsset; source_version: string; expected_revision: number; pages: OCRPage[]; count: number; list_page: number; next_page: number | null; counts: Record<string, number>; parsed_page_count: number; missing_page_count: number; detail: { pdf_page: number; text: string; original_text: string; parsed: boolean; manual: boolean; manual_revision_id: string | null; manual_revision: OCRCorrection | null; latest: OCRCorrection | null; source_fingerprint: string; history: OCRCorrection[]; history_count: number; history_page: number; history_next_page: number | null }; jobs: OCRJob[]; active_job_id: string; paused: boolean; can_run: boolean; denied_reason: string; provider_label: string; checked_at: string; settings: { languages: string; layout: string; manual_text: string; service_verified: boolean }; result?: OCRCorrection };
export type OCRPreview = { revision_id: string; pdf_page: number; before: string; after: string; blockers: string[]; can_apply: boolean; mode: "publish" | "apply_draft"; notice: string; prepared_fingerprint: string };
export type OCRCommand = { action: "save" | "apply" | "start" | "pause" | "resume" | "cancel" | "review"; request_id: string; pdf_page?: number; expected_revision?: number; source_fingerprint?: string; text?: string; note?: string; confirmed?: boolean; revision_id?: string; prepared_fingerprint?: string; page_indexes?: number[]; source_version?: string; job_id?: string; job_version?: string; task_options?: OCROptions; pages?: Array<{ pdf_page: number; source_fingerprint: string }> };
export const ocrWorkspacePath = (id: string) => `/ingestion/ocr-workspace/${encodeURIComponent(id)}/`;
function request<T>(path: string, options: RequestInit = {}) { return apiRequest<T>(path, { ...options, cache: "no-store", signal: options.signal || AbortSignal.timeout(60000) }, getServerSessionCredential(), false); }
export function changeOCR(id: string, data: OCRCommand) { return request<OCRWorkspace>(ocrWorkspacePath(id), { method: "POST", body: JSON.stringify(data) }); }
export function previewOCRCorrection(id: string, data: { pdf_page: number; expected_revision: number; source_fingerprint: string; revision_id: string }) { return request<OCRPreview>(ocrWorkspacePath(id), { method: "POST", body: JSON.stringify({ ...data, action: "prepare" }) }); }

/** Bounded paragraph comparison, using exact text; no guessed character boxes. */
export function correctionDiff(before: string, after: string) {
  const oldLines = before.split("\n"), newLines = after.split("\n");
  let start = 0, end = 0;
  while (start < oldLines.length && start < newLines.length && oldLines[start] === newLines[start]) start += 1;
  while (end < oldLines.length - start && end < newLines.length - start && oldLines[oldLines.length - end - 1] === newLines[newLines.length - end - 1]) end += 1;
  return { prefix: oldLines.slice(0, start).join("\n"), removed: oldLines.slice(start, oldLines.length-end).join("\n"), added: newLines.slice(start, newLines.length-end).join("\n"), suffix: end ? oldLines.slice(-end).join("\n") : "", changed: before !== after };
}
