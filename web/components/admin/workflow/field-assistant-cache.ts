"use client";

import { apiRequest, subscribeToSessionChanges } from "@/lib/api";

type Pending = { controller: AbortController; promise: Promise<unknown>; users: number };
const completed = new Map<string, { expires: number; value: unknown }>();
const pending = new Map<string, Pending>();
let listening = false;

export function assistantCacheKey(editionId: string, field: string, query = "", context = "") {
  return `edition:${editionId}:${JSON.stringify([field, query, context])}`;
}

export function invalidateAssistantCache(editionId?: string) {
  const matches = (key: string) => !editionId || key.startsWith(`edition:${editionId}:`);
  for (const key of completed.keys()) if (matches(key)) completed.delete(key);
  for (const [key, request] of pending) if (matches(key)) { pending.delete(key); request.controller.abort(); }
}

// Private, memory-only, short-lived results. Never persisted into catalog data.
// Prefetch and the visible field share requests; cancel the transport only when
// no remaining consumer needs it. Session changes discard all private results.
export async function cachedAssistantRequest<T>(key: string, path: string, options: RequestInit, token: string | null, signal?: AbortSignal): Promise<T> {
  if (!listening && typeof window !== "undefined") {
    listening = true;
    subscribeToSessionChanges(() => invalidateAssistantCache());
  }
  if (signal?.aborted) throw new DOMException("Request cancelled", "AbortError");
  const saved = completed.get(key);
  if (saved && saved.expires > Date.now()) return saved.value as T;
  completed.delete(key);
  let request = pending.get(key);
  if (!request || request.controller.signal.aborted) {
    const controller = new AbortController();
    const next: Pending = { controller, users: 0, promise: Promise.resolve() };
    next.promise = apiRequest<T>(path, { ...options, signal: controller.signal }, token).then((value) => {
      if (!controller.signal.aborted) {
        completed.set(key, { expires: Date.now() + 60_000, value });
        while (completed.size > 64) completed.delete(completed.keys().next().value!);
      }
      return value;
    }).finally(() => { if (pending.get(key) === next) pending.delete(key); });
    pending.set(key, next);
    request = next;
  }
  const current = request;
  current.users += 1;
  return new Promise<T>((resolve, reject) => {
    let finished = false;
    const release = () => {
      finished = true;
      signal?.removeEventListener("abort", cancel);
      current.users -= 1;
      if (!current.users && pending.get(key) === current) current.controller.abort();
    };
    const cancel = () => {
      if (finished) return;
      release();
      reject(new DOMException("Request cancelled", "AbortError"));
    };
    signal?.addEventListener("abort", cancel, { once: true });
    current.promise.then((value) => { if (!finished) { release(); resolve(value as T); } }, (error) => { if (!finished) { release(); reject(error); } });
  });
}

export function lookupFieldSuggestions<T>({ editionId, fieldName, query = "", contextKey = "", token, signal, refresh = false }: {
  editionId: string; fieldName: string; query?: string; contextKey?: string; token: string | null; signal?: AbortSignal; refresh?: boolean;
}) {
  if (refresh) {
    // Only a direct user action schedules external research. Prefetch and
    // initial cached rendering never request it; the server deduplicates runs.
    invalidateAssistantCache(editionId);
    return apiRequest<T>("/catalog/admin/field-assistant/lookup/", {
      method: "POST", signal, body: JSON.stringify({ object_type: "edition", object_id: editionId, field_name: fieldName, query, refresh: true, allow_external: true }),
    }, token);
  }
  return cachedAssistantRequest<T>(assistantCacheKey(editionId, fieldName, query, contextKey), "/catalog/admin/field-assistant/lookup/", {
    method: "POST", body: JSON.stringify({ object_type: "edition", object_id: editionId, field_name: fieldName, query }),
  }, token, signal);
}
