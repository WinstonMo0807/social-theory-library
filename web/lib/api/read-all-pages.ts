import { apiRequest } from "../api";
import type { Paginated } from "./pagination";

/** Follow only the query of the same collection. Never send credentials to a next URL. */
export function nextCollectionPath(firstPath: string, next: string): string {
  const first = new URL(firstPath, "https://library.invalid");
  const target = new URL(next, first);
  if (![first.pathname, `/api${first.pathname}`].includes(target.pathname)) {
    throw new Error("分页返回了不同的资料入口，请刷新后重试。");
  }
  for (const name of new Set(first.searchParams.keys())) {
    if (!["page", "p", "cursor"].includes(name) && JSON.stringify(first.searchParams.getAll(name)) !== JSON.stringify(target.searchParams.getAll(name))) {
      throw new Error("分页改变了当前资料范围，请刷新后重试。");
    }
  }
  return `${first.pathname}${target.search}`;
}

export async function readAllPages<T>(path: string, credential: string, signal: AbortSignal | undefined, expectedOwner: string): Promise<T[]> {
  if (!expectedOwner) throw new Error("请先确认登录账户，再读取私人资料。");
  const rows: T[] = [];
  const seen = new Set<string>();
  let current = path;
  while (current) {
    if (signal?.aborted) throw new DOMException("请求已取消。", "AbortError");
    if (seen.has(current) || seen.size >= 1000) throw new Error("资料分页未能完整读取，请稍后重试或导出资料。");
    seen.add(current);
    const deadline = AbortSignal.timeout(30000);
    const pageSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
    const payload = await apiRequest<Paginated<T> | T[]>(current, {
      signal: pageSignal, cache: "no-store",
      headers: { "X-Reader-Owner": expectedOwner },
    }, credential, false);
    if (Array.isArray(payload)) return [...rows, ...payload];
    rows.push(...payload.results);
    current = payload.next ? nextCollectionPath(path, payload.next) : "";
  }
  return rows;
}
