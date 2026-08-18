export const searchContexts = [
  "works",
  "scholars",
  "disciplines",
  "subdisciplines",
  "theories",
  "topics",
  "reading_paths",
  "global",
] as const;

export type SearchContext = typeof searchContexts[number];

export function isSearchContext(value: unknown): value is SearchContext {
  return typeof value === "string" && searchContexts.includes(value as SearchContext);
}

export function scopedSearchHref(
  path: string,
  context: SearchContext,
  values: Record<string, string | number | null | undefined> = {},
) {
  const params = new URLSearchParams({ context });
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim()) {
      params.set(key, String(value));
    }
  });
  return `${path}?${params.toString()}`;
}

export function searchPage(value: string | string[] | undefined) {
  const raw = Array.isArray(value) ? value[0] : value;
  const page = Number(raw || 1);
  return Number.isFinite(page) ? Math.max(1, Math.floor(page)) : 1;
}
