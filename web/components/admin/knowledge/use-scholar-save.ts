"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";

type Pending = { id: string; path: string; body: string; headers: Record<string, string>; method: string };
type Receipt<K extends "scholar" | "topic" | "timeline"> = { actor_id: string; request_id: string; saved_version: string; exists: boolean; state:"applied"|"cancelled" } & Record<`${K}_id`,string|null>;
const key = (actor: string, kind: string) => `stl-${kind}-save:${actor}`;

export function useScholarSave<K extends "scholar" | "topic" | "timeline" = "scholar">(actor: string, kind: K = "scholar" as K) {
  const acting = useRef(false);
  const pending = useRef<Pending | null>(null), controller = useRef<AbortController | null>(null);
  const [recovery, setRecovery] = useState(""), [ready, setReady] = useState(false), [error, setError] = useState(""), [canRetry, setCanRetry] = useState(false);
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    queueMicrotask(() => { if (request.signal.aborted) return; try { setRecovery(sessionStorage.getItem(key(actor,kind)) || ""); setReady(true); } catch { setError("保存回执暂不可读，请先核对操作记录。"); } });
    return () => request.abort();
  }, [actor,kind]);
  async function save<T>(path: string, body: string, headers: Record<string, string>, method: string): Promise<T> {
    const request = controller.current; if (!actor || !ready || !request || request.signal.aborted) throw Error("正在核对编辑账户及原请求，请稍后。");
    if (!pending.current) {
      if (sessionStorage.getItem(key(actor,kind))) throw Error("存在未核对的保存，请先读取原请求回执。");
      pending.current = { id: crypto.randomUUID(), path, body, headers, method };
      sessionStorage.setItem(key(actor,kind), pending.current.id); setRecovery(pending.current.id); setCanRetry(true);
    }
    if (acting.current) throw Error("正在核对原保存，请稍后。");
    acting.current = true;
    const original = pending.current;
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(60000)]);
    try {
      const result = await withPrivateOwner(actor, () => apiRequest<T & { save_receipt: Receipt<K> }>(original.path, {
        method: original.method, body: original.body, headers: { ...original.headers, "X-Editor-Owner": actor, "Idempotency-Key": original.id }, signal,
      }, getServerSessionCredential(), false), signal);
      if (result.save_receipt?.actor_id !== actor || result.save_receipt.request_id !== original.id) throw Error("回执与原请求不匹配，请核对记录。");
      sessionStorage.removeItem(key(actor,kind)); pending.current = null; setRecovery(""); setCanRetry(false); setError(""); return result;
    } catch (reason) {
      if (reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && [400, 401, 403, 404, 409, 428].includes(reason.status)) {
        sessionStorage.removeItem(key(actor,kind)); pending.current = null; if (!request.signal.aborted) { setRecovery(""); setCanRetry(false); }
      }
      throw reason;
    } finally { acting.current = false; }
  }
  async function lookup(cancel = false) {
    const request = controller.current;
    if (!recovery || !request || request.signal.aborted || acting.current) return null;
    acting.current = true;
    const signal = AbortSignal.any([request.signal, AbortSignal.timeout(30000)]);
    try {
      const result = await withPrivateOwner(actor, () => apiRequest<Receipt<K>>(`/catalog/admin/${kind === "topic" ? "topics" : kind === "timeline" ? "theory-timeline" : "scholars"}/commands/${recovery}/`, {
        cache: "no-store", signal, headers: { "X-Editor-Owner": actor },...(cancel?{method:"POST",body:JSON.stringify({action:"cancel_pending"})}:{}),
      }, getServerSessionCredential(), false), signal);
      if (result.actor_id !== actor || result.request_id !== recovery) throw Error("原请求回执不匹配。");
      sessionStorage.removeItem(key(actor,kind)); pending.current = null; setRecovery(""); setCanRetry(false); setError(""); return result;
    } catch (reason) { if (!request.signal.aborted) setError(reason instanceof Error ? reason.message : "原请求暂不可读取。"); return null; } finally { acting.current = false; }
  }
  return { save, lookup, recovery, ready, error, canRetry };
}
