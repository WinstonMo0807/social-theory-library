import { apiRequest, apiStreamRequest, getServerSessionCredential } from "../api";
import { withPrivateOwner } from "./private-owner";
import type { ResolvedEvidence } from "./research.client";
import type { PrivacyTarget } from "./privacy.client";

export type NotebookRecord = PrivacyTarget & {
  category: "annotations" | "bookmarks"; owner_id: string; key: string; kind: "note" | "highlight" | "underline" | "bookmark";
  asset_id: string; page_id: string; pdf_page: number; body: string; tags: string[]; label: string; saved_quote: string;
  work: { id: string; title: string; authors: string[]; year: number | null; href: string | null; cover_url: string | null };
  source: ResolvedEvidence; notice: string; created_at: string; updated_at: string;
};
export type NotebookPage<T = NotebookRecord> = { owner_id: string; count: number; page: number; total_pages: number; results: T[] };
export type NotebookChoice = { id: string; title: string; count?: number; revision?: number };
export const notebookPath = "/reading/notebook/";
export const notebookRecordPath = (row: Pick<NotebookRecord, "category" | "id">) => `${notebookPath}${row.category}/${row.id}/`;
export function notebookRequest<T extends { owner_id: string }>(owner: string, path: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers); headers.set("X-Reader-Owner", owner);
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return apiRequest<T>(path, { ...options, headers, signal, cache: "no-store" }, getServerSessionCredential(), false).then(result => {
    if (result.owner_id !== owner) throw Error("登录账户已变化，请重新读取本人资料。");
    return result;
  });
}

export type NotebookExportInput = { targets: PrivacyTarget[]; format: "pdf" | "markdown" | "bibtex" | "ris"; include_notes: boolean; include_quotes: boolean };
export async function downloadNotebook(owner: string, data: NotebookExportInput, signal: AbortSignal) {
  const blob = await withPrivateOwner(owner, async () => {
    const response = await apiStreamRequest(`${notebookPath}export/`, { method: "POST", headers: { "X-Reader-Owner": owner }, body: JSON.stringify(data), cache: "no-store", signal }, getServerSessionCredential(), false);
    if (!response.ok) {
      let message = "导出未完成，请重新读取记录后选择。";
      try { const body = await response.json(); if (typeof body.detail === "string") message = body.detail; } catch { /* Do not render raw server responses. */ }
      throw Error(message);
    }
    return response.blob();
  }, signal);
  signal.throwIfAborted();
  const url = URL.createObjectURL(blob), anchor = document.createElement("a");
  anchor.href = url; anchor.download = `stl-reading-records.${data.format === "markdown" ? "md" : data.format === "bibtex" ? "bib" : data.format}`;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
