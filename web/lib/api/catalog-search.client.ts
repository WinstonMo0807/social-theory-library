import { apiRequest } from "@/lib/api";
import type { ApiWork, PublicEdition } from "./public-catalog";
import type { SearchPayload } from "./search.types";

export type CatalogSearchWork = ApiWork & {
  editions: Array<PublicEdition & { language?: string; availability?: string }>;
  matched_edition_ids: string[];
};
export type CatalogSearchPayload = Omit<SearchPayload, "works" | "facets"> & {
  works: CatalogSearchWork[];
  facets: SearchPayload["facets"] & { year_histogram: Array<{ year: number; count: number }> };
};
export const catalogFilters = ["match", "document_type", "author", "language", "year", "year_min", "year_max", "theory", "topic", "concept", "access"] as const;
export const defaultCatalogMatches = ["title", "author", "keyword", "abstract"];
const catalogKeys = new Set<string>(["q", "sort", "view", "page", ...catalogFilters]);

/** Preserve only public catalog controls; never carry account or arbitrary URL state. */
export function catalogParams(input: string | URLSearchParams) {
  const result = new URLSearchParams();
  for (const [name, value] of new URLSearchParams(input)) {
    if (catalogKeys.has(name) && value.trim()) result.append(name, value.trim());
  }
  return result;
}

export function catalogHref(input: string | URLSearchParams, changes: Record<string, string | null> = {}) {
  const result = catalogParams(input);
  for (const [key, value] of Object.entries(changes)) {
    result.delete(key);
    if (value !== null && value !== "") result.set(key, value);
  }
  return `/explore/original${result.size ? `?${result}` : ""}`;
}

export function clearCatalogFilters(input: string | URLSearchParams) {
  const result = catalogParams(input);
  catalogFilters.forEach(key => result.delete(key));
  result.delete("page");
  return catalogHref(result);
}

export function readCatalogSearch(input: string, signal: AbortSignal) {
  const params = catalogParams(input);
  params.delete("view");
  params.set("context", "global");
  params.set("scope", "catalog");
  params.set("page_size", "24");
  return apiRequest<CatalogSearchPayload>(`/catalog/search/?${params}`, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), cache: "no-store",
  });
}
