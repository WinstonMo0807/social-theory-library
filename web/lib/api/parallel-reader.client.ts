import { apiRequest, getServerSessionCredential } from "../api";
import type { EvidenceReference, ResolvedEvidence } from "./research.client";

export type ParallelVersion = {
  work_id: string; edition_id: string; asset_id: string | null; document_revision_id: string | null;
  title: string; original_title: string; authors: string[]; language: string;
  publication_year: number | null; version_label: string; cover_url: string | null; total_pages: number;
  relation: string; current: boolean; state: "available" | "metadata_only"; notice: string;
};
export type ParallelVersions = { source_asset_id: string; versions: ParallelVersion[]; truncated: boolean };
export type ParallelSegment = { id: string; label: string; order: number; reference: ResolvedEvidence; printed_label: string; text: string; text_truncated?: boolean };
export type ParallelSegments = {
  asset_id: string; edition_id: string; document_revision_id: string | null; page: number; total_pages: number;
  previous_page: number | null; next_page: number | null; state: "ready" | "unstructured" | "empty" | "text_unavailable";
  notice: string; segments: ParallelSegment[]; offset: number; has_more: boolean; next_offset: number | null;
};
export type ParallelCandidates = {
  state: "ready" | "partial" | "empty" | "unavailable"; notice: string;
  candidates: Array<{ reference: ResolvedEvidence; label: string; text: string; text_truncated?: boolean; status: "pending" }>;
  warnings: unknown[]; allows_no_correspondence: boolean;
};
export type ParallelAlignment = {
  id: string; left: ResolvedEvidence | null; right: ResolvedEvidence | null;
  status: "confirmed" | "no_match" | "addition"; note: string;
};
export type ParallelTerm = {
  id: string; original: string; translation: string; note: string;
  left?: ResolvedEvidence | null; right?: ResolvedEvidence | null;
};
export type ParallelData = {
  left_asset_id: string; right_asset_id: string; left_document_revision_id: string; right_document_revision_id: string;
  positions: { left_page: number; right_page: number; left_segment_id?: string | null; right_segment_id?: string | null };
  sync_scroll: boolean; alignments: ParallelAlignment[]; terms: ParallelTerm[];
};
export type ParallelRecord = {
  id: string; revision: number; request_id: string; data: ParallelData; created_at: string; updated_at: string;
  source_available?: boolean; notice?: string;
};

export function parallelRequest<T>(path: string, options: RequestInit = {}, ownerId?: number) {
  const signal = options.signal ? AbortSignal.any([options.signal, AbortSignal.timeout(30000)]) : AbortSignal.timeout(30000);
  return apiRequest<T>(path, {
    ...options, signal, cache: "no-store",
    headers: { ...options.headers, ...(ownerId ? { "X-Reader-Owner": String(ownerId) } : {}) },
  }, getServerSessionCredential(), ownerId === undefined);
}
export const referenceKey = (ref: EvidenceReference | null | undefined) => ref
  ? `${ref.asset_id || ""}:${ref.document_revision_id || ""}:${ref.content_hash || ""}:${ref.evidence_span_id || ref.pdf_page || ""}:${ref.selection_start ?? ""}:${ref.selection_end ?? ""}` : "";
export function sameParallelSegment(a: ResolvedEvidence | null | undefined, b: ResolvedEvidence | null | undefined) {
  if (!a || !b || a.asset_id !== b.asset_id || a.document_revision_id !== b.document_revision_id || a.content_hash !== b.content_hash) return false;
  if (a.evidence_span_id || b.evidence_span_id) return Boolean(a.evidence_span_id && a.evidence_span_id === b.evidence_span_id);
  if (a.pdf_page !== b.pdf_page) return false;
  if (a.selection_start !== undefined && a.selection_end !== undefined && b.selection_start !== undefined && b.selection_end !== undefined) {
    return a.selection_start < b.selection_end && b.selection_start < a.selection_end;
  }
  return referenceKey(a) === referenceKey(b);
}
export function compactParallelReference(ref: ResolvedEvidence | null | undefined): EvidenceReference | null {
  return ref ? {
    asset_id: ref.asset_id, document_revision_id: ref.document_revision_id, evidence_span_id: ref.evidence_span_id,
    pdf_page: ref.pdf_page, content_hash: ref.content_hash, selection_start: ref.selection_start, selection_end: ref.selection_end,
  } : null;
}
