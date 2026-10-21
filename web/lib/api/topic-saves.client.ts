import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import { withPrivateOwner } from "./private-owner";

export type SavedTopic = { id: string; topic: string; name: string; slug: string; description: string; created_at: string; version: string };
export type TopicSaveCommand = { topic: string; saved: boolean; expected_version: string; request_id: string };
export type TopicSaveState = { owner_id: string; topic_id: string; saved: boolean; version: string; can_save: boolean; record: SavedTopic | null;
  receipt: { request_id: string; applied_saved: boolean } | null };

async function request(path: string, owner: string, signal: AbortSignal, options: RequestInit = {}, onDispatch?: () => void) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  const combined = AbortSignal.any([signal, session.signal, AbortSignal.timeout(30000)]);
  try {
    return await withPrivateOwner(owner, async () => {
      combined.throwIfAborted(); onDispatch?.();
      const result = await apiRequest<TopicSaveState>(path, { ...options, cache: "no-store", signal: combined,
        headers: { "X-Reader-Owner": owner } }, getServerSessionCredential(), false);
      if (result.owner_id !== owner) throw new Error("主题收藏与当前账户不一致，原操作仍待核对。");
      return result;
    }, combined);
  } finally { unsubscribe(); }
}

export function loadTopicSave(topic: string, owner: string, signal: AbortSignal, requestId?: string) {
  return request(`/reading/saved-topics/state/?${new URLSearchParams({ topic, ...(requestId ? { request_id: requestId } : {}) })}`, owner, signal);
}

export function commandTopicSave(input: TopicSaveCommand, owner: string, signal: AbortSignal, onDispatch?: () => void) {
  return request("/reading/saved-topics/command/", owner, signal, { method: "POST", body: JSON.stringify(input) }, onDispatch);
}
