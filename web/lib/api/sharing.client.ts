import { apiRequest, getServerSessionCredential } from "../api";
import type { components } from "./generated/schema";

type Schema = components["schemas"];
export type GroupSummary = Schema["GroupSummary"];
export type GroupDirectory = Schema["GroupDirectory"];
export type GroupDetail = Schema["GroupDetail"];
export type GroupResult = Schema["GroupResult"];
export type GroupCommand = Schema["GroupCommandInputRequest"];
export type ShareSource = Schema["ShareSource"];
export type ShareSelection = Schema["ShareSelectionOutput"];
export type SharePreview = Schema["SharePreviewOutput"];
export type SharePreviewInput = Schema["SharePreviewInputRequest"];
export type ShareCreateInput = Schema["ShareCreateInputRequest"];
export type ShareReceipt = Schema["ShareReceipt"];
export type ShareDirectory = Schema["ShareDirectory"];
export type ShareDetail = Schema["ShareDetail"];
export type ShareContent = Schema["ShareContent"];
export type ShareBrief = Schema["ShareBrief"];
export type ShareNoticePage = Schema["ShareNoticePage"];
export type ShareNotifyResult = Schema["ShareNotifyResult"];
export type ShareSection = "questions" | "materials" | "notes";
export const sectionLabels: Record<ShareSection, string> = { questions: "研究问题", materials: "选材与引用", notes: "本人笔记" };
export const destinationLabels = { group: "小组成员", public: "公开摘要链接", proposal: "策划提案" };

export function sharingRequest<T>(owner: string, path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);
  headers.set("X-Reader-Owner", owner);
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return apiRequest<T>(path, { ...options, headers, signal, cache: "no-store" }, getServerSessionCredential(), false);
}

export function shareLink(id: string, token: string) {
  const url = new URL(`/shared/${id}`, window.location.origin);
  url.hash = new URLSearchParams({ key: token }).toString();
  return url.toString();
}

export function groupInviteLink(token: string) {
  const url = new URL("/account/groups", window.location.origin);
  url.hash = new URLSearchParams({ invite: token }).toString();
  return url.toString();
}

export function publicShare(id: string, key: string, signal: AbortSignal) {
  return apiRequest<ShareContent>(`/reading/share-links/${id}/`, { cache: "no-store", referrerPolicy: "no-referrer",
    headers: { "X-Share-Key": key }, signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) }, null, false);
}
