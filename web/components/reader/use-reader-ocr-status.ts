"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "@/lib/api";
import { pollBudgetExpired } from "@/lib/api/task-polling";
import { commandReaderOcr, readReaderOcrStatus, readerOcrReceiptMatches, sameReaderOcrCommandSource,
  type ReaderOcrAction, type ReaderOcrCommand, type ReaderOcrStatus } from "@/lib/api/reader-ocr.client";

type Options = { assetId: string; documentRevisionId?: string | null; ownerId?: number | null; canManage?: boolean; canViewManagement?: boolean };
type State = { identity: string; permissions: string; data: ReaderOcrStatus | null; error: string; pending: boolean; unknown: boolean; conflict: boolean; pollPaused: boolean; message: string };
const revoked = (error: unknown) => error instanceof ApiRequestError && [401, 403, 404, 410].includes(error.status);
const active = (data: ReaderOcrStatus) => Boolean(data.job && ["pending", "queued", "running", "pausing"].includes(data.job.status));
const initial = (identity: string, permissions: string): State => ({ identity, permissions, data: null, error: "", pending: false, unknown: false, conflict: false, pollPaused: false, message: "" });

export function useReaderOcrStatus({ assetId, documentRevisionId, ownerId, canManage = false, canViewManagement = false }: Options) {
  const [epoch, setEpoch] = useState(0), [attempt, setAttempt] = useState(0), [state, setState] = useState<State | null>(null);
  const identity = `${assetId}:${documentRevisionId ?? ""}:${ownerId ?? "public"}:${epoch}`;
  const permissions = `${canManage}:${canViewManagement}`, permissionsRef = useRef(permissions);
  const identityRef = useRef(identity), dataRef = useRef<ReaderOcrStatus | null>(null);
  const controller = useRef<AbortController | null>(null), pending = useRef(false), operation = useRef<ReaderOcrCommand | null>(null);
  const resetConflict = useRef(false), mutationGeneration = useRef(0);
  const current = state?.identity === identity ? { ...state, data: state.permissions === permissions ? state.data : null } : null;
  useLayoutEffect(() => {
    identityRef.current = identity; dataRef.current = null; pending.current = false; operation.current = null; resetConflict.current = false;
    controller.current?.abort();
  }, [identity]);
  useLayoutEffect(() => {
    if (permissionsRef.current === permissions) return;
    permissionsRef.current = permissions;
    controller.current?.abort(); mutationGeneration.current += 1; dataRef.current = null; pending.current = false;
    // Same account, new capabilities: hide management content, but never discard
    // a command whose response may have been lost while permissions changed.
    setState(previous => previous?.identity === identity ? { ...previous, permissions, data: null, pending: false,
      unknown: Boolean(operation.current), error: operation.current ? "当前账户权限已变化，原命令结果仍未确认。请在权限恢复后查回，或明确放弃本页核对。" : "" } : previous);
  }, [identity, permissions]);
  useEffect(() => subscribeToSessionChanges(() => {
    identityRef.current = ""; controller.current?.abort(); dataRef.current = null; operation.current = null;
    setState(null); setEpoch(value => value + 1);
  }), []);

  const apply = useCallback((data: ReaderOcrStatus, changes: Partial<State> = {}) => {
    if (identityRef.current !== identity) return;
    const changed = documentRevisionId !== undefined && (data.document_revision_id || null) !== (documentRevisionId || null);
    // Keep OCR recovery independent from the mounted PDF and its signed URL.
    dataRef.current = changed ? null : data;
    setState(previous => ({ ...(previous?.identity === identity ? previous : initial(identity, permissions)), ...changes,
      data, permissions,
      ...(changed ? { conflict: true, error: "当前正式原文修订已有变化。可在新标签页核对已处理内容；当前 PDF 保留，此面板暂停新的处理命令。" } : {}) }));
  }, [identity, documentRevisionId, permissions]);

  useEffect(() => {
    if (!assetId) return;
    const lifetime = new AbortController(), started = Date.now();
    controller.current = lifetime;
    let timer: ReturnType<typeof setTimeout> | undefined, loading = false, accessDenied = false;
    async function load(automatic = false) {
      if (lifetime.signal.aborted || identityRef.current !== identity || pending.current || loading || accessDenied) return;
      if (timer) clearTimeout(timer);
      if (automatic && pollBudgetExpired(started)) {
        setState(previous => previous?.identity === identity ? { ...previous, pollPaused: true } : previous);
        return;
      }
      if (automatic && document.visibilityState !== "visible") { timer = setTimeout(() => void load(true), 5000); return; }
      loading = true;
      const generation = mutationGeneration.current;
      try {
        const data = await readReaderOcrStatus(assetId, ownerId, lifetime.signal);
        if (lifetime.signal.aborted || identityRef.current !== identity || generation !== mutationGeneration.current) return;
        const acknowledge = resetConflict.current;
        resetConflict.current = false;
        apply(data, { error: "", pollPaused: false, ...(acknowledge ? { conflict: false, message: "" } : {}) });
        if (active(data)) timer = setTimeout(() => void load(true), 5000);
      } catch (error) {
        if (lifetime.signal.aborted || identityRef.current !== identity || generation !== mutationGeneration.current) return;
        accessDenied = revoked(error);
        if (accessDenied) dataRef.current = null;
        setState(previous => ({ ...(previous?.identity === identity ? previous : initial(identity, permissions)),
          ...(accessDenied ? { data: null, unknown: Boolean(operation.current) } : {}), error: error instanceof Error ? error.message : "处理状态暂不可读取，请重试。" }));
      } finally { loading = false; }
    }
    const refresh = () => { if (document.visibilityState === "visible") void load(true); };
    void load();
    window.addEventListener("focus", refresh); window.addEventListener("pageshow", refresh); document.addEventListener("visibilitychange", refresh);
    return () => { lifetime.abort(); if (timer) clearTimeout(timer); window.removeEventListener("focus", refresh); window.removeEventListener("pageshow", refresh); document.removeEventListener("visibilitychange", refresh); };
  }, [assetId, ownerId, identity, permissions, attempt, apply]);

  async function send(command: ReaderOcrCommand, recover: boolean) {
    const lifetime = controller.current;
    if (!ownerId || !canManage || pending.current || !lifetime || lifetime.signal.aborted) return;
    pending.current = true;
    const generation = ++mutationGeneration.current;
    setState(previous => previous?.identity === identity ? { ...previous, pending: true, error: "", message: "" } : previous);
    try {
      let result: ReaderOcrStatus | null = null;
      if (recover) {
        const found = await readReaderOcrStatus(assetId, ownerId, lifetime.signal, command.request_id);
        if (lifetime.signal.aborted || identityRef.current !== identity || generation !== mutationGeneration.current) return;
        if (readerOcrReceiptMatches(found, command)) result = found;
        else if (found.receipt !== null) throw new Error("处理回执尚不能对应本次命令，请保留原请求继续核对。");
        else if (!sameReaderOcrCommandSource(found, command)) {
          operation.current = null;
          apply(found, { pending: false, unknown: false, conflict: true, error: "任务或原文已变化，未重新发送旧命令。请读取并核对当前任务后继续。" });
          return;
        }
      }
      result ??= await commandReaderOcr(assetId, ownerId, command, lifetime.signal);
      if (lifetime.signal.aborted || identityRef.current !== identity || generation !== mutationGeneration.current) return;
      if (!readerOcrReceiptMatches(result, command)) throw new Error("尚未确认处理结果，请使用原请求查回。");
      operation.current = null;
      apply(result, { pending: false, unknown: false, conflict: false, error: "",
        message: command.action === "pause" ? "暂停请求已确认，请以下方实际任务状态为准。已保存页面保留。" : "继续处理请求已确认，请以下方实际任务状态为准。" });
      setAttempt(value => value + 1);
    } catch (error) {
      if (lifetime.signal.aborted || identityRef.current !== identity || generation !== mutationGeneration.current) return;
      // A denied receipt lookup cannot establish whether the earlier POST was applied.
      const clear = revoked(error), unknown = recover && clear || !clear && (!(error instanceof ApiRequestError) || [0, 408, 429].includes(error.status) || error.status >= 500);
      if (!unknown) operation.current = null;
      if (clear) dataRef.current = null;
      setState(previous => ({ ...(previous?.identity === identity ? previous : initial(identity, permissions)), pending: false, unknown,
        conflict: error instanceof ApiRequestError && error.status === 409, ...(clear ? { data: null } : {}),
        error: error instanceof Error ? error.message : "本次处理结果尚未确认，请查回原请求。" }));
    } finally { if (identityRef.current === identity && generation === mutationGeneration.current) pending.current = false; }
  }
  function command(action: ReaderOcrAction) {
    const data = dataRef.current;
    if (!data?.job || !ownerId || !canManage || pending.current || operation.current || current?.conflict
      || !(action === "pause" ? data.can_pause : data.can_resume)) return;
    operation.current = { action, request_id: crypto.randomUUID(), job_id: data.job.id, job_version: data.job.job_version,
      source_sha256: data.source_sha256, document_revision_id: data.document_revision_id };
    void send(operation.current, false);
  }
  return { ...(current || initial(identity, permissions)), loading: Boolean(assetId) && !current, command,
    refresh: () => { if (!pending.current) { resetConflict.current = true; setAttempt(value => value + 1); } },
    recover: () => { if (operation.current) void send(operation.current, true); },
    abandon: () => {
      if (pending.current || !operation.current) return;
      operation.current = null;
      setState(previous => previous?.identity === identity ? { ...previous, unknown: false, conflict: true, error: "",
        message: "已放弃本页核对。原命令是否执行仍未确认，未取消后台处理，也未发送新命令。" } : previous);
    } };
}
