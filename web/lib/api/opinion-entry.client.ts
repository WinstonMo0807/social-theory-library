import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";
import type { DiscoveryFilters } from "./discovery.types";
import type { ScopedSearchEnvelope } from "./search.types";
import type { CatalogSearchPayload } from "./catalog-search.client";

export type OpinionScope = "all" | "topic" | "scholar" | "work";
export type ScopeOption = { id: string; title: string; subtitle: string };
export type ScopePage = { results: ScopeOption[]; page: number; total_pages: number; total: number };
export type SearchRecordsPage = { owner_id: string; recording_enabled: boolean; count: number; page: number; page_size: number;
  results: Array<{ id: string; query: string; filters: DiscoveryFilters; created_at: string }>; notice: string };
export const scopeKeys = {
  work: ["work", "work_id", "work_ids"], scholar: ["author", "authors", "scholar"], topic: ["topic", "topics", "topic_ids"],
};
export const scopeFilterKeys = Object.values(scopeKeys).flat();
export const opinionFilterKeys = [...scopeFilterKeys, "document_type", "document_types", "source_type", "source_types", "theory", "theory_node_ids", "theories", "concept", "concepts", "language", "languages", "year", "years", "year_min", "year_max", "access", "availability"];

export function opinionResultHref(query: string, filters: DiscoveryFilters) {
  const params = new URLSearchParams({ q: query });
  for (const [key, value] of Object.entries(filters)) if (opinionFilterKeys.includes(key)) {
    for (const part of Array.isArray(value) ? value : [value]) if (part) params.append(key, String(part));
  }
  return `/explore/evidence?${params}`;
}

export async function loadSearchRecords(path: string, signal: AbortSignal): Promise<SearchRecordsPage> {
  const ownerId = new URL(path, "https://private.invalid").searchParams.get("owner_id");
  if (!ownerId) throw new ApiRequestError("请先核对当前登录账户。", 403);
  const data = await apiRequest<SearchRecordsPage>(path, { cache: "no-store", headers: { "X-Reader-Owner": ownerId }, signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) }, getServerSessionCredential(), false);
  if (data.owner_id !== ownerId) throw new ApiRequestError("登录账户已变化，请重新读取当前账户的资料。", 403);
  return data;
}

/** Reuse public catalog identities; no mock options or private/admin visibility. */
export async function loadOpinionScope(kind: Exclude<OpinionScope, "all">, query: string, page: number, signal: AbortSignal): Promise<ScopePage> {
  const params = new URLSearchParams({ q: query, page: String(page), page_size: "12" });
  const options = { cache: "no-store" as const, signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]) };
  if (kind === "work") {
    params.set("context", "global"); params.set("scope", "catalog");
    const data = await apiRequest<CatalogSearchPayload>(`/catalog/search/?${params}`, options, null, false);
    return { results: data.works.map(row => ({ id: row.id, title: row.title, subtitle: row.edition?.version_label || "" })),
      page: data.pagination.page, total_pages: data.pagination.total_pages, total: data.pagination.total };
  }
  const context = kind === "topic" ? "topics" : "scholars";
  params.set("context", context); params.set("envelope", "1");
  const data = await apiRequest<ScopedSearchEnvelope>(`/catalog/search/?${params}`, options, null, false);
  const rows = data.groups.flatMap(group => group.results);
  // Scholar result IDs are Person IDs; profile IDs/slugs cannot constrain authors.
  if (data.visibility !== "public" || data.context !== context || rows.some(row => row.context !== context || row.entity_type !== (kind === "topic" ? "topic" : "person"))) {
    throw new Error("检索范围暂时无法核对，请重新读取公开选项。");
  }
  return { results: rows.map(row => ({ id: row.id, title: row.title, subtitle: row.subtitle })),
    page: data.pagination.page, total_pages: data.pagination.total_pages, total: data.pagination.total };
}
