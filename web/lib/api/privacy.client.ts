import { privateRequest } from "./research.client";

export type RetentionKey = "reading_history" | "search_history" | "personal_notes" | "followed_topics" | "source_follows";
export type ExportCategory = "research" | "notes" | "plans" | "audits" | "source_follows";
export type EraseCategory = "reading_history" | "search_history" | "personal_notes" | "reading_plans" | "followed_topics" | "source_follows";
export type PrivacyLeaf = "reading_history" | "search_history" | "annotations" | "memories" | "plans" | "followed_topics" | "source_follows";
export type PrivacyTarget = { category: PrivacyLeaf; id: string; revision: string };
export type PrivacyItem = PrivacyTarget & { title: string; updated_at: string; impact: string; source: { title?: string; authors?: string[]; edition?: string; cover_url?: string | null; pdf_page?: number; printed_label?: string } };
export type PrivacyItems = { owner_id: string; count: number; page: number; page_size: number; results: PrivacyItem[] };
export type PrivacyOperation = {
  id: string; owner_id: string; revision: number; kind: "export" | "erase";
  status: "preview" | "queued" | "running" | "completed" | "partial" | "failed" | "canceled";
  created_at: string; updated_at: string; finished_at: string | null; total: number; completed: number; failed: number; remaining: number;
  categories: string[]; results: Array<{ id: string; category: string; status: "completed" | "failed"; error_code: string; bytes?: number }>;
  preview: Array<PrivacyTarget & { title?: string; current?: boolean; impact: { message: string; scope_count: number; memories: Array<{ id: string; revision: number }> } }>;
  error_code: string; download_available: boolean; notice: string;
};
export type PrivacySummary = { owner_id: string; revision: number; retention: Record<RetentionKey, boolean>; automatic_memory_use: false;
  confirmed_notes: number; authorized_contexts: number; export_counts: Record<ExportCategory, number>; erase_counts: Record<EraseCategory, number>;
  operations: PrivacyOperation[]; preference_history: Array<{ at: string; retention: Partial<Record<RetentionKey, boolean>> }>;
  max_operation_items: number; export_formats: string[]; notice: string };
export type PrivacyOperations = { count: number; next: string | null; previous: string | null; results: PrivacyOperation[] };
export const privacyPath = "/reading/privacy/";
export const operationPath = (id?: string) => `${privacyPath}operations/${id ? `${encodeURIComponent(id)}/` : ""}`;
export const privacyActive = (status: string) => status === "queued" || status === "running";

export function savePrivacyPreferences(expectedRevision: number, retention: Record<RetentionKey, boolean>) {
  return privateRequest<PrivacySummary>(privacyPath, { method: "PATCH", body: JSON.stringify({ expected_revision: expectedRevision, retention }) });
}
export function preparePrivacyOperation(requestId: string, input: { kind: "export"; categories: ExportCategory[] } | { kind: "erase"; targets: PrivacyTarget[] }) {
  return privateRequest<PrivacyOperation>(operationPath(), { method: "POST", body: JSON.stringify({ request_id: requestId, ...input }) });
}
export function commandPrivacyOperation(id: string, expectedRevision: number, action: "confirm" | "cancel" | "retry") {
  return privateRequest<PrivacyOperation>(`${operationPath(id)}command/`, { method: "POST", body: JSON.stringify({ expected_revision: expectedRevision, action }) });
}
