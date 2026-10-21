import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "../api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "./private-owner";
import type { PathFollowCommand, PathFollowResponse, PathUpgradePreview } from "./reading-paths.types";

async function request<T extends { owner_id: string }>(path: string, owner: string, signal: AbortSignal, options: RequestInit = {}, onDispatch?: () => void) {
  const session = new AbortController(), unsubscribe = subscribeToSessionChanges(() => session.abort());
  const combined = AbortSignal.any([signal, session.signal, AbortSignal.timeout(30000)]);
  try {
    return await withPrivateOwner(owner, async () => {
      combined.throwIfAborted(); onDispatch?.();
      const result = await apiRequest<T>(`/reading/path-follows/${path}`, { ...options, cache: "no-store", headers: { "X-Reader-Owner": owner }, signal: combined }, getServerSessionCredential(), false);
      combined.throwIfAborted();
      if (String(result.owner_id) !== owner) throw new PrivateOwnerVerificationError("阅读路径与当前账户不一致，请重新读取。", 403);
      return result;
    }, combined);
  } finally { unsubscribe(); }
}
export const loadPathFollow = (id: string, owner: string, signal: AbortSignal) => request<PathFollowResponse>(`by-path/?${new URLSearchParams({ path_id: id })}`, owner, signal);
export const loadPathPlan = (id: string, owner: string, signal: AbortSignal) => request<PathFollowResponse>(`${encodeURIComponent(id)}/`, owner, signal);
export const findPathFollowReceipt = (id: string, owner: string, signal: AbortSignal) => request<PathFollowResponse>(`by-request/?${new URLSearchParams({ request_id: id })}`, owner, signal);
export const previewPathUpgrade = (id: string, revision: string, owner: string, signal: AbortSignal) => request<PathUpgradePreview>(`${encodeURIComponent(id)}/upgrade-preview/?${new URLSearchParams({ target_revision: revision })}`, owner, signal);
export function writePathFollow(command: PathFollowCommand, owner: string, signal: AbortSignal, onDispatch?: () => void) {
  if (command.action === "create") return request<PathFollowResponse>("", owner, signal, { method: "POST", body: JSON.stringify({ request_id: command.request_id, path_id: command.path_id, expected_source_revision: command.expected_source_revision, ...(command.bookmarked !== undefined ? { bookmarked: command.bookmarked } : {}) }) }, onDispatch);
  const { id, action, ...data } = command;
  if (action === "delete") return request<PathFollowResponse>(`${encodeURIComponent(id)}/?${new URLSearchParams({ request_id: command.request_id, expected_revision: String(command.expected_revision) })}`, owner, signal, { method: "DELETE" }, onDispatch);
  const special = action === "copy-plan" || action === "upgrade";
  return request<PathFollowResponse>(`${encodeURIComponent(id)}/${special ? `${action}/` : ""}`, owner, signal, { method: special ? "POST" : "PATCH", body: JSON.stringify({ ...data, ...(special ? {} : { action }) }) }, onDispatch);
}
