import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";
import type { DiscoveryContext, DiscoveryCoverage, DiscoveryFilters, DiscoveryPassage, DiscoverySearch, DiscoverySort } from "./discovery.types";

export function canKeepDiscoveryContext(item: DiscoveryPassage, next: DiscoverySearch) {
  return !next.source_changed && next.passages.some(row => row.id === item.id && row.asset_id === item.asset_id &&
    row.document_revision_id === item.document_revision_id && row.excerpt === item.excerpt);
}

export function discoveryCoverageRows(coverage: DiscoveryCoverage | undefined) {
  const labels = { published_editions: "当前范围已发布文献", bibliographic_editions: "纯书目记录", text_pending_editions: "正文尚未就绪", eligible_editions: "全文已具备资格", indexed_editions: "关键词已就绪", vector_editions: "向量已就绪", index_pending_editions: "等待关键词索引", vector_pending_editions: "等待向量索引", ...(coverage?.index_pending_editions === undefined ? { pending_editions: "等待索引更新" } : {}), passage_count: "索引段落" } as const;
  return Object.entries({ ...labels, verification_pending_editions: "等待索引状态核验" }).flatMap(([key, label]) => {
    const value = coverage?.[key as keyof DiscoveryCoverage];
    return typeof value === "number" && Number.isFinite(value) ? [{ key, label, value }] : [];
  });
}

const endpoint = "/catalog/discovery-search/";
export function canRetryDiscoveryRead(reason: unknown, failedReads: number) {
  return failedReads < 3 && reason instanceof ApiRequestError &&
    (reason.status === 0 || reason.status === 408 || reason.status === 429 || reason.status >= 500);
}
async function request<T>(path: string, options: RequestInit = {}, accessToken = ""): Promise<T> {
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("X-Discovery-Token", accessToken);
  const readOnly = !options.method || options.method === "GET";
  return apiRequest<T>(path, { ...options, headers, signal: AbortSignal.timeout(readOnly ? 45000 : 25000), cache: "no-store" }, getServerSessionCredential(), readOnly);
}
export function createDiscoverySearch(q: string, filters: DiscoveryFilters) {
  return request<DiscoverySearch>(endpoint, { method: "POST", body: JSON.stringify({ q, filters }) });
}
export function readDiscoverySearch(id: string, accessToken: string, options: { cursor?: string; limit?: number; sort?: DiscoverySort } = {}) {
  const params = new URLSearchParams();
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.limit) params.set("limit", String(options.limit));
  if (options.sort) params.set("sort", options.sort);
  return request<DiscoverySearch>(`${endpoint}${encodeURIComponent(id)}/?${params}`, {}, accessToken);
}
export function actOnDiscoverySearch(id: string, accessToken: string, action: "expand" | "cancel" | "retry", expectedGeneration?: number) {
  if (action === "retry" && (!Number.isInteger(expectedGeneration) || (expectedGeneration ?? 0) < 1)) {
    return Promise.reject(new Error("检索轮次不可用，请刷新结果后重试。"));
  }
  return request<DiscoverySearch>(`${endpoint}${encodeURIComponent(id)}/${action}/`, {
    method: "POST", body: JSON.stringify(action === "retry" ? { expected_generation: expectedGeneration } : {}),
  }, accessToken);
}
export function readDiscoveryContext(id: string, accessToken: string, resultId: string) {
  return request<DiscoveryContext>(`${endpoint}${encodeURIComponent(id)}/context/?result_id=${encodeURIComponent(resultId)}`, {}, accessToken);
}

export function removeDiscoveryDocument(id: string, accessToken: string, editionId: string, expectedGeneration: number) {
  return request<DiscoverySearch>(`${endpoint}${encodeURIComponent(id)}/remove-document/`, {
    method: "POST", body: JSON.stringify({ edition_id: editionId, expected_generation: expectedGeneration }),
  }, accessToken);
}
