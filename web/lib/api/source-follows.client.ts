import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import { withPrivateOwner } from "./private-owner";

export type PublicSourceStatus = {
  path: string; canonical_path: string; status: "available" | "replaced" | "unavailable" | "page";
  title: string; authors: string[]; cover_url: string; source_type: string; version_label: string; location: string;
  updated_at: string | null; checked_at: string; can_subscribe: boolean; reader_url: string; notice: string;
  work_id: string | null; edition_id: string | null; asset_id: string | null;
  catalog_revision_id: string | null; document_revision_id: string | null;
  scholar_profile_id?: string | null; person_id?: string | null; public_revision?: string; href?: string; scope_notice?: string;
};
export type SourceFollowEvent = { id: string; action: "subscribe" | "unsubscribe" | "mark_read" | "changed" | "delete"; before_status: string; after_status: string; observed_at: string; revision: number };
export type SourceFollow = {
  id: string; owner_id: string; path: string; active: boolean; revision: number; created_at: string; updated_at: string;
  last_checked_at: string | null; check_error: string; unread_count: number; updates_paused: boolean; source: PublicSourceStatus; notice: string;
  history: { count: number; page: number; page_size: number; results: SourceFollowEvent[] };
  scholar_profile_id?: string | null;
};
export type SourceFollowsPage = { owner_id: string; count: number; page: number; page_size: number; results: SourceFollow[]; notice: string };
export type SourceCommand = { path: string; scholar_profile_id?: string; action: "subscribe" | "unsubscribe" | "mark_read"; request_id: string; expected_revision: number };
export type SourceCommandResult = { owner_id: string; record: SourceFollow | null; receipt: { request_id: string; applied_revision: number; deleted: boolean } };
export const sourceFollowsPath = "/reading/source-follows/";
export const sourceStatusLabel: Record<PublicSourceStatus["status"], string> = { available: "当前可用", replaced: "已有新版本", unavailable: "暂不可用", page: "站内页面" };
export const sourceDate = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "尚未记录";

export function loadPublicSource(path: string, signal: AbortSignal, scholarProfileId?: string) {
  const query = new URLSearchParams({ path, ...(scholarProfileId ? { scholar_profile_id: scholarProfileId } : {}) });
  return apiRequest<PublicSourceStatus>(`/reading/source-status/?${query}`,
    { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) }, null, false);
}
async function ownerRequest<T>(path: string, owner: string, signal: AbortSignal, options: RequestInit = {}, onDispatch?: () => void) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  const combined = AbortSignal.any([signal, session.signal, AbortSignal.timeout(30000)]);
  try {
    return await withPrivateOwner(owner, async () => {
      combined.throwIfAborted(); onDispatch?.();
      const result = await apiRequest<T & { owner_id: string }>(path, { ...options, cache: "no-store", signal: combined,
        headers: { ...options.headers, "X-Reader-Owner": owner } }, getServerSessionCredential(), false);
      if (result.owner_id !== owner) throw new Error("来源记录与当前账户不一致，已保留原操作供核对。");
      return result;
    }, combined);
  } finally { unsubscribe(); }
}
export function commandSourceFollow(input: SourceCommand, ownerId: string, signal: AbortSignal, onDispatch?: () => void) {
  return ownerRequest<SourceCommandResult>(sourceFollowsPath, ownerId, signal, { method: "POST", body: JSON.stringify(input) }, onDispatch);
}
export function findSourceFollowReceipt(requestId: string, ownerId: string, signal: AbortSignal) {
  return ownerRequest<SourceCommandResult>(`${sourceFollowsPath}by-request/?request_id=${encodeURIComponent(requestId)}`, ownerId, signal);
}
export function loadSourceFollows(ownerId: string, signal: AbortSignal, params: Record<string, string> = {}) {
  return ownerRequest<SourceFollowsPage>(`${sourceFollowsPath}?${new URLSearchParams(params)}`, ownerId, signal);
}
