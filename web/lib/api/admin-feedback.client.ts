import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";

export const feedbackCategories = { content: "内容错误", function: "功能问题", usage: "使用咨询", suggestion: "改进建议", other: "其他", citation: "引用问题", accessibility: "无障碍" } as const;
export const feedbackStatuses = { submitted: "待处理", reviewing: "处理中", resolved: "已处理" } as const;
export type FeedbackStatus = keyof typeof feedbackStatuses;
export type AdminFeedbackSummary = {
  id: string; category: keyof typeof feedbackCategories; status: FeedbackStatus; excerpt: string;
  created_at: string; updated_at: string; revision: number; follow_up: boolean;
};
export type FeedbackHandling = { status: FeedbackStatus; note: string; follow_up: boolean };
export type FeedbackHistory = { count: number; page: number; page_size: number; results: {
  id: string; created_at: string; actor: string; before: FeedbackHandling & { revision: number }; after: FeedbackHandling & { revision: number };
}[] };
export type AdminFeedbackDetail = AdminFeedbackSummary & {
  body: string; contact: string; path: string; consent_at: string | null; consent_version: string; note: string;
  handled_by: string; can_follow_up: boolean; history: FeedbackHistory;
  source: { status: "available" | "replaced" | "unavailable" | "page"; canonical_path: string; title: string; authors: string[];
    cover_url: string; source_type: string; version_label: string; location: string; updated_at: string | null;
    checked_at: string; reader_url: string; notice: string };
};
export type AdminFeedbackList = {
  count: number; page: number; page_size: number; counts: { total: number } & Record<FeedbackStatus, number>; results: AdminFeedbackSummary[];
};
export type FeedbackHandlingInput = FeedbackHandling & { request_id: string; expected_revision: number };
export const adminFeedbackPath = (id?: string) => `/catalog/admin/public-feedback/${id ? `${encodeURIComponent(id)}/` : ""}`;
export async function updateFeedback(id: string, data: FeedbackHandlingInput, signal?: AbortSignal) {
  const controller = new AbortController(), unsubscribe = subscribeToSessionChanges(() => controller.abort());
  try {
    return await apiRequest<{ request_id: string; accepted_revision: number; record: AdminFeedbackDetail }>(adminFeedbackPath(id), {
      method: "PATCH", cache: "no-store", body: JSON.stringify(data),
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30000), ...(signal ? [signal] : [])]),
    }, getServerSessionCredential(), false);
  } catch (reason) {
    // Preserve the mutation nonce when an intermediary cannot confirm receipt.
    if (reason instanceof ApiRequestError && [408, 429].includes(reason.status)) throw new ApiRequestError(reason.message);
    throw reason;
  } finally { unsubscribe(); }
}
export function feedbackDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间待核对" : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}
