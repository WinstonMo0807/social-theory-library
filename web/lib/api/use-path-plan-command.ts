"use client";

import { createRequestKey } from "../request-key";
import { useEffect, useRef, useState, type RefObject } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "../api";
import { PrivateOwnerVerificationError } from "./private-owner";
import { findPathFollowReceipt } from "./reading-paths.client";
import { updateReadingPlan } from "./research.client";

export type PendingPathPlanCommand = { owner: string; id: string; payload: Parameters<typeof updateReadingPlan>[1] & { request_id: string }; dispatched: boolean };

/** The parent retains this one command in memory while the same owner verifies their session again. */
export function usePathPlanCommand(owner: string, id: string, pendingRef: RefObject<PendingPathPlanCommand | null>, reload: () => void, onPending: (value: boolean) => void) {
  const [hasPending, setHasPending] = useState(true);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const active = useRef(false), request = useRef<AbortController | null>(null);
  useEffect(() => {
    active.current = true;
    if (pendingRef.current?.owner !== owner) pendingRef.current = null;
    const retained = Boolean(pendingRef.current?.id === id);
    setHasPending(retained); onPending(retained);
    const off = subscribeToSessionChanges(() => { active.current = false; request.current?.abort(); });
    return () => { active.current = false; request.current?.abort(); off(); };
  }, [owner, id, pendingRef, onPending]);

  async function submit(payload?: Parameters<typeof updateReadingPlan>[1]) {
    if (!active.current || request.current) return false;
    let current = pendingRef.current?.owner === owner && pendingRef.current.id === id ? pendingRef.current : null;
    if (payload && current) return false;
    if (!current) {
      if (!payload) return false;
      current = { owner, id, payload: { ...payload, request_id: createRequestKey() }, dispatched: false };
      pendingRef.current = current;
    }
    const operation = current, controller = new AbortController();
    request.current = controller; setRunning(true); setError(""); setHasPending(true); onPending(true);
    const clear = () => { if (pendingRef.current === operation) { pendingRef.current = null; onPending(false); if (active.current) setHasPending(false); } };
    try {
      let confirmed = false;
      if (operation.dispatched) {
        try {
          const result = await findPathFollowReceipt(operation.payload.request_id, owner, controller.signal);
          if (result.receipt?.request_id !== operation.payload.request_id || result.receipt.deleted !== (result.record === null) || result.record && result.record.id !== id) throw new Error("保存回执与当前计划不一致，已保留待核对操作。");
          if (result.receipt.deleted) { clear(); throw new ApiRequestError("此计划已删除，旧保存请求不会重新创建它。", 410); }
          confirmed = true;
        } catch (reason) {
          if (!(reason instanceof ApiRequestError) || reason instanceof PrivateOwnerVerificationError || reason.status !== 404) throw reason;
        }
      }
      if (!confirmed) await updateReadingPlan(id, operation.payload, owner, controller.signal, () => { operation.dispatched = true; });
      controller.signal.throwIfAborted();
      if (!active.current) return false;
      clear(); reload(); return true;
    } catch (reason) {
      // A server rejection is definitive; an interrupted response or owner check is not.
      if (!(reason instanceof PrivateOwnerVerificationError) && reason instanceof ApiRequestError && [400, 401, 403, 404, 409, 410, 422].includes(reason.status)) clear();
      if (active.current) setError(reason instanceof Error ? reason.message : "保存结果暂时无法确认，请先核对结果。");
      return false;
    } finally {
      request.current = null;
      if (active.current) setRunning(false);
    }
  }
  return { pending: hasPending, running, error, submit };
}
