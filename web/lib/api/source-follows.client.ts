import { apiRequest } from "../api";
import { privateRequest } from "./research.client";

export type PublicSourceStatus = {
  path: string; canonical_path: string; status: "available" | "replaced" | "unavailable" | "page";
  title: string; authors: string[]; cover_url: string; source_type: string; version_label: string; location: string;
  updated_at: string | null; checked_at: string; can_subscribe: boolean; reader_url: string; notice: string;
  work_id: string | null; edition_id: string | null; asset_id: string | null;
  catalog_revision_id: string | null; document_revision_id: string | null;
};
export type SourceFollowEvent = { id: string; action: "subscribe" | "unsubscribe" | "mark_read" | "changed"; before_status: string; after_status: string; observed_at: string; revision: number };
export type SourceFollow = {
  id: string; owner_id: string; path: string; active: boolean; revision: number; created_at: string; updated_at: string;
  last_checked_at: string | null; check_error: string; unread_count: number; updates_paused: boolean; source: PublicSourceStatus; notice: string;
  history: { count: number; page: number; page_size: number; results: SourceFollowEvent[] };
};
export type SourceFollowsPage = { owner_id: string; count: number; page: number; page_size: number; results: SourceFollow[]; notice: string };
export type SourceCommand = { path: string; action: "subscribe" | "unsubscribe" | "mark_read"; request_id: string; expected_revision: number };
export const sourceFollowsPath = "/reading/source-follows/";
export const sourceStatusLabel: Record<PublicSourceStatus["status"], string> = { available: "当前可用", replaced: "已有新版本", unavailable: "暂不可用", page: "站内页面" };
export const sourceDate = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { dateStyle: "medium", timeStyle: "short" }) : "尚未记录";

export function loadPublicSource(path: string, signal: AbortSignal) {
  return apiRequest<PublicSourceStatus>(`/reading/source-status/?path=${encodeURIComponent(path)}`,
    { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) }, null, false);
}
export function commandSourceFollow(input: SourceCommand, ownerId: string, signal: AbortSignal) {
  return privateRequest<SourceFollow>(sourceFollowsPath, { method: "POST", headers: { "X-Reader-Owner": ownerId }, body: JSON.stringify(input), signal });
}
