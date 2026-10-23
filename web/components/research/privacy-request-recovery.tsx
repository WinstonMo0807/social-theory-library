"use client";

import { useEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { PrivateOwnerVerificationError, withPrivateOwner } from "@/lib/api/private-owner";
import { preparePrivacyOperation, recoverPrivacyRequest, type ExportCategory, type PrivacyTarget } from "@/lib/api/privacy.client";
import { createRequestKey } from "@/lib/request-key";
import { useUnsavedForm } from "@/lib/use-unsaved-form";
import { ConfirmDialog } from "@/components/confirm-dialog";

type Input = Parameters<typeof preparePrivacyOperation>[2];
type Intent = { requestId: string; input: Input };
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function readIntent(raw: string): Intent {
  const value = JSON.parse(raw);
  // Accept the original reader-center record without changing its request or targets.
  const input = value?.input ?? { kind: value?.kind, targets: value?.targets };
  if (!uuid.test(value?.requestId || "") || !["export", "erase"].includes(input?.kind)) throw new Error("原请求恢复记录无法读取。请保留此标签页，并从资料任务核对已创建的任务。");
  const targets = input.targets as PrivacyTarget[] | undefined, categories = input.categories as ExportCategory[] | undefined;
  if (Boolean(targets) === Boolean(categories) || (targets && (!Array.isArray(targets) || !targets.length || targets.length > 500 || targets.some(row => !row || typeof row.category !== "string" || !uuid.test(row.id) || typeof row.revision !== "string"))) || (categories && (input.kind !== "export" || !Array.isArray(categories) || !categories.length || categories.length > 8 || categories.some(row => typeof row !== "string")))) throw new Error("原请求选择记录无法读取，请保留记录并核对资料任务。");
  return { requestId: value.requestId, input };
}

/** Both private entry points use the same server receipt; storage contains only IDs and versions. */
export function usePrivacyPreparation(ownerId: string, storageKey: string) {
  const [intent, setIntent] = useState<Intent | null>(null);
  const [ready, setReady] = useState(false);
  const [broken, setBroken] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const request = useRef<AbortController | null>(null), sending = useRef(false);
  useEffect(() => {
    const controller = new AbortController(); request.current = controller;
    const unsubscribe = subscribeToSessionChanges(() => controller.abort());
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      try {
        const raw = sessionStorage.getItem(storageKey);
        if (raw) { setIntent(readIntent(raw)); setMessage("上次请求尚未取得明确回执。请查回原请求，或使用原选择重试。"); }
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "无法读取原请求，请保留记录。"); }
      finally { setReady(true); }
    });
    return () => { controller.abort(); unsubscribe(); };
  }, [storageKey]);
  useUnsavedForm(busy || Boolean(intent), false);
  function clear() { sessionStorage.removeItem(storageKey); setIntent(null); }
  async function act(input?: Input, recovery?: "read" | "stop"): Promise<string | null> {
    const controller = request.current;
    if (!ready || broken || sending.current || !controller || controller.signal.aborted) return null;
    // A new selection must never replace an unresolved request.
    if (input && intent) { setMessage("请先查回或停止原请求，再提交新的选择。"); return null; }
    const command = intent ?? (input ? { requestId: createRequestKey(), input } : null);
    if (!command) return null;
    sending.current = true; setBusy(true); setMessage("");
    let saved = false;
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(command)); setIntent(command); saved = true;
      const id = await withPrivateOwner(ownerId, async () => {
        if (!recovery) return (await preparePrivacyOperation(ownerId, command.requestId, command.input, controller.signal)).id;
        const receipt = await recoverPrivacyRequest(ownerId, command.requestId, recovery === "stop", controller.signal);
        if (receipt.state === "applied" && receipt.kind !== command.input.kind) throw new PrivateOwnerVerificationError("原请求类型不匹配，请保留编号并核对资料任务。", 409);
        return receipt.operation_id;
      }, controller.signal);
      if (controller.signal.aborted) return null;
      clear();
      setMessage(id ? "已找到原任务，可在任务详情继续查看。" : "尚未创建的原请求已停止，迟到的同一请求不会创建任务。已有任务没有被取消。");
      return id;
    } catch (reason) {
      if (controller.signal.aborted) return null;
      // A failed owner check can happen after an accepted POST. Never discard that receipt.
      if (!recovery && saved && !(reason instanceof PrivateOwnerVerificationError) && reason instanceof ApiRequestError && [400, 422].includes(reason.status)) {
        try { clear(); } catch { setMessage("无法清除本机恢复记录，请保留并查回原请求。"); return null; }
      }
      setMessage(reason instanceof Error ? reason.message : "尚未收到明确回执，请查回或重试原请求。");
      return null;
    } finally { sending.current = false; if (!controller.signal.aborted) setBusy(false); }
  }
  return { ready, busy, message, pending: Boolean(intent), locked: !ready || busy || Boolean(intent) || broken,
    prepare: (input?: Input) => act(input), recover: (stop = false) => act(undefined, stop ? "stop" : "read") };
}

export function PrivacyRequestRecovery({ preparation, onOpen, className }: { preparation: ReturnType<typeof usePrivacyPreparation>; onOpen: (id: string) => void; className?: string }) {
  const [stopping, setStopping] = useState(false);
  const { message, pending, busy } = preparation;
  async function recover(stop = false, retry = false) {
    const id = await (retry ? preparation.prepare() : preparation.recover(stop));
    setStopping(false);
    if (id) onOpen(id);
  }
  return <>
    {message || pending ? <div className={className} role="status"><p>{message || "正在处理原请求…"}</p>{pending ? <><button type="button" disabled={busy} onClick={() => void recover()}>查回原请求</button><button type="button" disabled={busy} onClick={() => void recover(false, true)}>重试原请求</button><button type="button" disabled={busy} onClick={() => setStopping(true)}>停止尚未创建的请求</button></> : null}</div> : null}
    <ConfirmDialog open={stopping} title="停止尚未创建的请求？" description="系统会先核对原编号。已经创建的任务将打开原详情，不会重复创建或自动取消；尚未创建的请求会被停止，迟到的同一请求也不会生效。" confirmLabel={busy ? "正在核对…" : "核对并停止"} pending={busy} onCancel={() => setStopping(false)} onConfirm={() => recover(true)} />
  </>;
}
