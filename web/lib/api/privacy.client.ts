import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";
import { PrivateOwnerVerificationError } from "./private-owner";

export type RetentionKey = "reading_history" | "search_history" | "personal_notes" | "followed_topics" | "source_follows" | "saved_knowledge";
export type ExportCategory = "collaboration" | "article_comments" | "research" | "notes" | "plans" | "audits" | "source_follows" | "saved_knowledge";
export type EraseCategory = "collaboration" | "article_comments" | "reading_history" | "search_history" | "personal_notes" | "reading_plans" | "followed_topics" | "source_follows" | "saved_knowledge";
export type PrivacyLeaf = "reader_groups" | "group_memberships" | "group_invitations" | "reader_shares" | "share_notices" | "article_comments" | "reading_history" | "search_history" | "annotations" | "bookmarks" | "memories" | "parallel_alignments" | "plans" | "followed_topics" | "source_follows" | "saved_knowledge" | "graph_views" | "reading_lists" | "saved_items" | "research" | "audits" | "citation_sources";
export type PrivacyTarget = { category: PrivacyLeaf; id: string; revision: string };
export type PrivacyItem = PrivacyTarget & { title: string; updated_at: string; impact: string; source: { path?: string; title?: string; authors?: string[]; edition?: string; cover_url?: string | null; pdf_page?: number; printed_label?: string } };
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

async function privacyOwnerRequest<T extends { owner_id: string }>(ownerId: string, path: string, options: RequestInit) {
  if (!ownerId) throw new ApiRequestError("登录账户暂时无法确认，请重新验证。", 403);
  const headers = new Headers(options.headers);
  headers.set("X-Reader-Owner", ownerId);
  const timeout = AbortSignal.timeout(30000);
  const result = await apiRequest<T>(path, { ...options, headers, cache: "no-store",
    signal: options.signal ? AbortSignal.any([options.signal, timeout]) : timeout,
  }, getServerSessionCredential(), false);
  if (result.owner_id !== ownerId) throw new PrivateOwnerVerificationError("登录账户已变化，请重新读取当前账户的资料。", 403);
  return result;
}
export function savePrivacyPreferences(ownerId: string, expectedRevision: number, retention: Record<RetentionKey, boolean>, signal?: AbortSignal) {
  return privacyOwnerRequest<PrivacySummary>(ownerId, privacyPath, { method: "PATCH", signal, body: JSON.stringify({ expected_revision: expectedRevision, retention }) });
}
export function preparePrivacyOperation(ownerId: string, requestId: string, input: { kind: "export"; categories: ExportCategory[] } | { kind: "export" | "erase"; targets: PrivacyTarget[] }, signal?: AbortSignal) {
  return privacyOwnerRequest<PrivacyOperation>(ownerId, operationPath(), { method: "POST", signal, body: JSON.stringify({ request_id: requestId, ...input }) });
}
export type PrivacyRequestReceipt = { owner_id: string; request_id: string; state: "applied" | "cancelled"; operation_id: string | null; kind: string };
export async function recoverPrivacyRequest(ownerId: string, requestId: string, stop = false, signal?: AbortSignal) {
  const result = await privacyOwnerRequest<PrivacyRequestReceipt>(ownerId, `${privacyPath}requests/${encodeURIComponent(requestId)}/`,
    { method: stop ? "POST" : "GET", signal, ...(stop ? { body: JSON.stringify({ action: "cancel_pending" }) } : {}) });
  if (result.request_id !== requestId || !["applied", "cancelled"].includes(result.state) || (result.state === "applied" && !result.operation_id)) {
    throw new PrivateOwnerVerificationError("原请求回执不匹配，请保留编号并重新核对。", 409);
  }
  return result;
}
export function commandPrivacyOperation(ownerId: string, id: string, expectedRevision: number, action: "confirm" | "cancel" | "retry", signal?: AbortSignal) {
  return privacyOwnerRequest<PrivacyOperation>(ownerId, `${operationPath(id)}command/`, { method: "POST", signal, body: JSON.stringify({ expected_revision: expectedRevision, action }) });
}
export function downloadPrivacyOperation(ownerId: string, id: string, signal?: AbortSignal) {
  return privacyOwnerRequest<{ owner_id: string; operation_id: string; records: unknown[]; unavailable_since_preparation: unknown[] }>(
    ownerId, `${operationPath(id)}download/`, { method: "GET", signal });
}
