"use client";

import { createRequestKey } from "../../../lib/request-key";
import { useEffect, useRef, useState } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import type { PlacementCommand, PlacementState, PlacementPage } from "@/lib/api/curation-workspace.client";

type Receipt = { actor_id: string; request_id: string; page_id: string; page_type: string; revision_id: string | null; state: "applied" | "cancelled"; exists: boolean };
export function usePlacementCommand(owner: string, nodeId: string, pageType: PlacementPage = "node") {
  const path = `/catalog/admin/content-placements/${pageType}/${nodeId}/`, key = `stl-placement-command:${owner}:${pageType}:${nodeId}`;
  const [ready, setReady] = useState(false), [recovery, setRecovery] = useState(""), [busy, setBusy] = useState(false), [error, setError] = useState(""), [canRetry, setCanRetry] = useState(false);
  const original = useRef<PlacementCommand | null>(null), lifetime = useRef<AbortController | null>(null), sending = useRef(false);
  const uncertain = useRef(false);
  useEffect(() => { const controller = new AbortController(); lifetime.current = controller; queueMicrotask(() => { if (controller.signal.aborted) return; try { setRecovery(sessionStorage.getItem(key) || ""); setReady(true); } catch { setError("浏览器暂不能读取原操作记录，请保留当前页面。"); } }); return () => controller.abort(); }, [key]);
  async function send(body?: Omit<PlacementCommand, "request_id"> & { confirmed_only?: boolean }) {
    if (!ready || !owner || sending.current || lifetime.current?.signal.aborted) return null;
    sending.current = true; setBusy(true); setError("");
    try {
      if (!original.current) {
        if (!body || sessionStorage.getItem(key)) throw Error("请先查询原请求，不能用新内容覆盖未知结果。");
        original.current = { ...body, request_id: createRequestKey() };
        uncertain.current = false;
        sessionStorage.setItem(key, original.current.request_id); setRecovery(original.current.request_id); setCanRetry(true);
      }
      const signal = AbortSignal.any([lifetime.current!.signal, AbortSignal.timeout(60000)]);
      const result = await withPrivateOwner(owner, () => apiRequest<PlacementState>(path, { method: "POST", body: JSON.stringify(original.current), signal, headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), signal);
      if (result.page_id !== nodeId || result.page_type !== pageType || !result.applied_revision_id) throw Error("编排操作结果与当前对象不一致，请核对记录。");
      sessionStorage.removeItem(key); original.current = null; uncertain.current = false; setRecovery(""); setCanRetry(false); return result;
    } catch (reason) {
      // A rejection of a retry cannot prove a timed-out original was not saved.
      if (!uncertain.current && reason instanceof ApiRequestError && !(reason instanceof PrivateOwnerVerificationError) && [400,401,403,404,409,422,428].includes(reason.status)) { sessionStorage.removeItem(key); original.current = null; if (!lifetime.current?.signal.aborted) { setRecovery(""); setCanRetry(false); } }
      else uncertain.current = true;
      if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "未收到操作结果，请查询原请求。");
      return null;
    } finally { sending.current = false; if (!lifetime.current?.signal.aborted) setBusy(false); }
  }
  async function lookup(cancel = false) {
    if (!recovery || sending.current || lifetime.current?.signal.aborted) return null;
    sending.current = true; setBusy(true); setError("");
    try {
      const signal = AbortSignal.any([lifetime.current!.signal, AbortSignal.timeout(30000)]);
      const result = await withPrivateOwner(owner, () => apiRequest<Receipt>(`${path}commands/${recovery}/`, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner }, ...(cancel ? { method:"POST",body:JSON.stringify({action:"cancel_pending"}) } : {}) }, getServerSessionCredential(), false), signal);
      if (result.actor_id !== owner || result.page_id !== nodeId || result.page_type !== pageType || result.request_id !== recovery || !["applied", "cancelled"].includes(result.state)) throw Error("原请求结果不匹配。");
      sessionStorage.removeItem(key); original.current = null; uncertain.current = false; setRecovery(""); setCanRetry(false); return result;
    } catch (reason) { if (!lifetime.current?.signal.aborted) setError(reason instanceof Error ? reason.message : "原请求暂不可读取。"); return null; }
    finally { sending.current = false; if (!lifetime.current?.signal.aborted) setBusy(false); }
  }
  return { send, lookup, ready, recovery, busy, error, canRetry };
}
