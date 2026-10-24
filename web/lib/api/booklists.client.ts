import { apiRequest, apiStreamRequest, getServerSessionCredential } from "../api";
import type { ApiWork } from "./public-catalog";
import { withPrivateOwner } from "./private-owner";
import type { EvidenceReference } from "./research.client";
import type { components } from "./generated/schema";
import type { NotebookRecord } from "./notebook.client";

export type BooklistSummary = { id: string; title: string; description: string; goal: string; tags: string[]; topic_ids: string[]; version: string; created_at: string; updated_at: string; item_count: number };
export type BooklistItem = { id: string; work_id: string; order: number; work: ApiWork | null; created_at: string; removed_at: string | null; expires_at: string | null; progress_ratio: number | null; reader_url: string | null };
export type BooklistWorkspace = { owner_id: string; list: BooklistSummary; items: BooklistItem[]; count: number; page: number; total_pages: number; active_count: number; trash_count: number };
export type BooklistDirectory = { owner_id: string; count: number; page: number; total_pages: number; results: BooklistSummary[] };
export type BooklistRelatedSection = "plans" | "notes" | "topics" | "scholars";
export type BooklistPublicLink = { id: string; title: string; href: string | null; selected: boolean; description: string; source_count: number; portrait_url: string | null; portrait_media: components["schemas"]["PublicCoverMedia"] | null };
export type BooklistRelated = { owner_id: string; list_id: string; version: string; section: BooklistRelatedSection; page: number; count: number; total_pages: number; notice: string;
  plans: { id: string; title: string; status: string; href: string; updated_at: string }[]; notes: NotebookRecord[]; topics: BooklistPublicLink[]; scholars: BooklistPublicLink[] };
export type BooklistCommand = { list_id: string; request_id: string; expected_version: string; action: "create" | "edit" | "add" | "remove" | "restore" | "purge" | "move" | "delete" | "topic_add" | "topic_remove"; title?: string; description?: string; goal?: string; tags?: string[]; work_id?: string; topic_id?: string; item_id?: string; item_ids?: string[]; direction?: -1 | 1 };
export type BooklistResult = { owner_id: string; id: string; exists: boolean; receipt: { request_id: string } };
export type CitationBooklistInput = { request_id: string; expected_version: string; edition_id: string; reference?: EvidenceReference; save_excerpt: boolean; note: string };
export type CitationBooklistResult = { owner_id: string; list_id: string; request_id: string; exists: boolean; undone: boolean; note_ids: string[]; undo_token: string | null };

export function booklistRequest<T>(owner: string, path: string, options: RequestInit = {}) {
  const signal = AbortSignal.any([AbortSignal.timeout(30000), ...(options.signal ? [options.signal] : [])]);
  return apiRequest<T>(path, { ...options, signal, cache: "no-store", headers: { ...options.headers, "X-Reader-Owner": owner } }, getServerSessionCredential(), false);
}

export async function downloadBooklist(owner: string, id: string, data: { expected_version: string; format: string; include_notes: boolean; include_progress: boolean; include_covers?:boolean; item_ids?: string[] }, signal: AbortSignal) {
  const blob = await withPrivateOwner(owner, async () => {
    const response = await apiStreamRequest(`/reading/lists/${id}/export/`, { method: "POST", headers: { "X-Reader-Owner": owner }, body: JSON.stringify(data), cache: "no-store", signal }, getServerSessionCredential(), false);
    if (!response.ok) {
      const text = await response.text();
      let detail = "书单导出未完成，请重新读取后重试。";
      try { const value = JSON.parse(text); if (typeof value.detail === "string") detail = value.detail; } catch { /* No raw server response is inserted into the page. */ }
      throw new Error(detail);
    }
    const expected={pdf:"application/pdf",csv:"text/csv",bibtex:"application/x-bibtex",ris:"application/x-research-info-systems"}[data.format];
    if(!expected||!response.headers.get("Content-Type")?.toLowerCase().includes(expected))throw new Error("下载响应不是所选文件格式，请重新核对后导出。");
    const file=await response.blob();
    if(!file.size||file.size>32*1024*1024)throw new Error("下载文件为空或超过32 MiB，请减少选择后重试。");
    if(data.format==="pdf"&&await file.slice(0,5).text()!=="%PDF-")throw new Error("PDF内容未能确认，请重新导出。");
    return file;
  }, signal);
  signal.throwIfAborted();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url; anchor.download = `booklist-${id}.${data.format === "bibtex" ? "bib" : data.format}`;
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
