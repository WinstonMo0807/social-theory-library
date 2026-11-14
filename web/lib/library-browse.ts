export const libraryKinds = [["", "全部文献"], ["book", "图书"], ["journal_article", "期刊论文"], ["journal_issue", "整期期刊"], ["thesis", "学位论文"], ["report", "研究报告"], ["chapter", "论文集章节"], ["other", "其他资料"]] as const;
export function libraryParams(input: string | URLSearchParams) {
  const source = new URLSearchParams(input), result = new URLSearchParams();
  const q = source.get("q")?.trim().slice(0, 180);
  if (q) result.set("q", q);
  const kind = source.get("kind");
  if (kind && libraryKinds.some(([value]) => value === kind)) result.set("kind", kind);
  const sort = source.get("sort");
  if (sort === "title") result.set("sort", sort);
  if (source.get("view") === "list") result.set("view", "list");
  const page = source.get("page") || "1";
  if (/^[1-9]\d{0,5}$/.test(page) && page !== "1") result.set("page", page);
  return result;
}
export function libraryHref(input: string | URLSearchParams, changes: Record<string, string | null> = {}) {
  const result = new URLSearchParams(input);
  for (const [key, value] of Object.entries(changes)) { result.delete(key); if (value) result.set(key, value); }
  const safe = libraryParams(result);
  return `/library${safe.size ? `?${safe}` : ""}`;
}
export function libraryApiQuery(input: string | URLSearchParams) {
  const params = libraryParams(input), api = new URLSearchParams();
  if (params.has("q")) api.set("q", params.get("q")!);
  if (params.has("kind")) api.set("document_type", params.get("kind")!);
  if (params.has("page")) api.set("page", params.get("page")!);
  // Ordering by a one-to-many edition field repeats works before pagination.
  // A library shelf represents works; use their own collection date.
  api.set("ordering", params.get("sort") === "title" ? "title" : "-created_at,title");
  return api;
}
