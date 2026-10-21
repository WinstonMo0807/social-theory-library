import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "./private-owner";
import type { GraphViewState } from "./graph.types";

export type GraphViewData = { title: string; view: GraphViewState };
export type GraphViewRecord = { id: string; revision: number; created_at: string; updated_at: string; data: GraphViewData };
export type GraphViewReceipt = { request_id: string; applied_revision: number; deleted: boolean };
export type GraphViewResponse = { owner_id: string; record: GraphViewRecord | null; receipt: GraphViewReceipt | null };
export type GraphViewPage = { owner_id: string; count: number; next: string | null; previous: string | null; results: GraphViewRecord[] };
export type GraphViewCommand = { method: "POST" | "PATCH" | "DELETE"; request_id: string; id?: string; expected_revision?: number; data?: GraphViewData };

async function request<T extends { owner_id: string }>(path: string, owner: string, signal: AbortSignal, options: RequestInit = {}, onDispatch?: () => void) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  const combined = AbortSignal.any([signal, session.signal, AbortSignal.timeout(30000)]);
  try {
    return await withPrivateOwner(owner, async () => {
      combined.throwIfAborted();
      onDispatch?.();
      const result = await apiRequest<T>(`/reading/graph-views/${path}`, { ...options, cache: "no-store", headers: { "X-Reader-Owner": owner },
        signal: combined }, getServerSessionCredential(), false);
      combined.throwIfAborted();
      if (String(result.owner_id) !== owner) throw new PrivateOwnerVerificationError("图谱视图与当前账户不一致，请重新读取。", 403);
      return result;
    }, combined);
  } finally { unsubscribe(); }
}
export const loadGraphViews = (owner: string, signal: AbortSignal, page = 1) => request<GraphViewPage>(`?page=${page}`, owner, signal);
export const loadGraphView = (id: string, owner: string, signal: AbortSignal) => request<GraphViewResponse>(`${encodeURIComponent(id)}/`, owner, signal);
export const findGraphViewReceipt = (id: string, owner: string, signal: AbortSignal) => request<GraphViewResponse>(`by-request/?${new URLSearchParams({ request_id: id })}`, owner, signal);
export function writeGraphView(command: GraphViewCommand, owner: string, signal: AbortSignal, onDispatch?: () => void) {
  const path = command.id ? `${encodeURIComponent(command.id)}/` : "";
  const query = command.method === "DELETE" ? `?${new URLSearchParams({ request_id: command.request_id, expected_revision: String(command.expected_revision) })}` : "";
  return request<GraphViewResponse>(path + query, owner, signal, { method: command.method,
    body: command.method === "DELETE" ? undefined : JSON.stringify({ request_id: command.request_id, ...(command.expected_revision !== undefined ? { expected_revision: command.expected_revision } : {}), data: command.data }) }, onDispatch);
}
