import { ApiRequestError, apiRequest, getServerSessionCredential } from "../api";

export type KnowledgeSaveState = {
  owner_id: string; node_id: string; record_id: string | null; saved: boolean; version: string;
  node: { id: string; title: string; slug: string; node_type: string } | null;
  receipt: { request_id: string; applied_saved: boolean } | null;
};
export type KnowledgeSaveCommand = { saved: boolean; request_id: string; expected_version: string };
export type KnowledgeCitation = { node_id: string; title: string; url: string; text: string; notice: string;
  published_at: string | null; updated_at: string; accessed_on: string };

export async function knowledgeSaveRequest(nodeId: string, ownerId: string, signal: AbortSignal,
  command?: KnowledgeSaveCommand, requestId?: string) {
  const query = requestId ? `?${new URLSearchParams({ request_id: requestId })}` : "";
  const result = await apiRequest<KnowledgeSaveState>(`/reading/saved-knowledge/${encodeURIComponent(nodeId)}/${query}`, {
    method: command ? "POST" : "GET", cache: "no-store", headers: { "X-Reader-Owner": ownerId },
    body: command ? JSON.stringify(command) : undefined,
    signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
  }, getServerSessionCredential(), false);
  if (result.owner_id !== ownerId || result.node_id !== nodeId) throw new ApiRequestError("收藏状态与当前账户或条目不一致，请重新核对。", 403);
  return result;
}

export function loadKnowledgeCitation(slug: string, signal: AbortSignal) {
  return apiRequest<KnowledgeCitation>(`/catalog/theory-system/nodes/${encodeURIComponent(slug)}/citation/`, {
    cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]),
  }, undefined, false);
}
