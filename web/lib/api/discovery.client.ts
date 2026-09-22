import { apiRequest, getServerSessionCredential } from "../api";
import type { DiscoveryContext, DiscoveryFilters, DiscoverySearch } from "./discovery.types";

const endpoint = "/catalog/discovery-search/";
async function request<T>(path: string, options: RequestInit = {}, accessToken = ""): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  const headers = new Headers(options.headers);
  if (accessToken) headers.set("X-Discovery-Token", accessToken);
  try {
    return await apiRequest<T>(path, { ...options, headers, signal: controller.signal, cache: "no-store" }, getServerSessionCredential());
  } finally { clearTimeout(timeout); }
}
export function createDiscoverySearch(q: string, filters: DiscoveryFilters) {
  return request<DiscoverySearch>(endpoint, { method: "POST", body: JSON.stringify({ q, filters }) });
}
export function readDiscoverySearch(id: string, accessToken: string, options: { cursor?: string; limit?: number } = {}) {
  const params = new URLSearchParams();
  if (options.cursor) params.set("cursor", options.cursor);
  if (options.limit) params.set("limit", String(options.limit));
  return request<DiscoverySearch>(`${endpoint}${encodeURIComponent(id)}/?${params}`, {}, accessToken);
}
export function actOnDiscoverySearch(id: string, accessToken: string, action: "expand" | "cancel") {
  return request<DiscoverySearch>(`${endpoint}${encodeURIComponent(id)}/${action}/`, { method: "POST", body: "{}" }, accessToken);
}
export function readDiscoveryContext(id: string, accessToken: string, resultId: string) {
  return request<DiscoveryContext>(`${endpoint}${encodeURIComponent(id)}/context/?result_id=${encodeURIComponent(resultId)}`, {}, accessToken);
}
