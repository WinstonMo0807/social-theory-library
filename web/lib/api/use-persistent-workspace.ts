"use client";

import { createRequestKey } from "../request-key";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiRequestError, subscribeToSessionChanges } from "../api";
import { privateRequest, researchRecordPath, type ResearchCollection, type ResearchRecord } from "./research.client";
import { outlinePath, placementsPath, editorialAssistancePath, type PlacementPage, type PlacementState, type OutlineState, type EditorialAssistance } from "./curation-workspace.client";
import { isTaskRunning, pollBudgetExpired, taskPollDelay } from "./task-polling";
import { PrivateOwnerVerificationError, withPrivateOwner } from "./private-owner";

type LoadState<T> = { key: string; data: T | null; error: string; conflict: boolean; pending: boolean; pollPaused?: boolean };

/** Private/admin data stays in memory, scoped to the authenticated owner and exact object. */
export function usePersistentWorkspace<T>(path: string, ownerId: string | null, pollAfter?: (data: T) => number | null | undefined,
  loadResource?: (path: string, signal: AbortSignal) => Promise<T>) {
  const key = ownerId && path ? `${ownerId}:${path}` : "";
  const [state, setState] = useState<LoadState<T> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [sessionEpoch, setSessionEpoch] = useState(0);
  const identity = `${key}:${sessionEpoch}`;
  const activeIdentity = useRef(identity);
  const current = state?.key === identity && key ? state : null;
  const dataRef = useRef<T | null>(null);
  const pendingRef = useRef(false);
  const revision = useRef(0);
  const operation = useRef<{ fingerprint: string; requestId: string } | null>(null);
  const currentPoll = useRef(pollAfter);
  useEffect(() => { currentPoll.current = pollAfter; }, [pollAfter]);
  useLayoutEffect(() => { activeIdentity.current = identity; dataRef.current = current?.data ?? null; }, [identity, current?.data]);
  useLayoutEffect(() => { pendingRef.current = false; operation.current = null; revision.current += 1; }, [identity]);
  useEffect(() => subscribeToSessionChanges(() => {
    activeIdentity.current = "";
    revision.current += 1; dataRef.current = null; operation.current = null; pendingRef.current = false;
    setState(null); setSessionEpoch(value => value + 1);
  }), []);

  const reload = useCallback(() => setAttempt(value => value + 1), []);
  useEffect(() => {
    if (!key) return;
    const request = new AbortController();
    const startedAt = Date.now();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let loading = false;
    const load = async (automatic = false) => {
      if (request.signal.aborted || pendingRef.current || loading) return;
      if (automatic && pollBudgetExpired(startedAt)) {
        setState(previous => previous?.key === identity ? { ...previous, pollPaused: true, error: "自动刷新已暂停，后台任务可能仍在继续。请重新读取进度，不会重新提交任务。" } : previous);
        return;
      }
      if (automatic && document.visibilityState !== "visible") {
        timer = setTimeout(() => void load(true), 5000);
        return;
      }
      loading = true;
      const expected = revision.current;
      try {
        const data = await withPrivateOwner(ownerId!, () => loadResource ? loadResource(path, request.signal) : privateRequest<T>(path, { signal: request.signal }), request.signal);
        if (request.signal.aborted || revision.current !== expected || activeIdentity.current !== identity) return;
        dataRef.current = data;
        setState({ key: identity, data, error: "", conflict: false, pending: false });
        const delay = currentPoll.current?.(data);
        if (delay && Number.isFinite(delay) && delay > 0) timer = setTimeout(() => void load(true), Math.max(1000, Math.min(delay, 30000)));
      } catch (reason) {
        if (request.signal.aborted || revision.current !== expected) return;
        // A failed permission check immediately clears retained private content.
        const revoked = reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status);
        setState(previous => ({ key: identity, data: revoked ? null : previous?.key === identity ? previous.data : null,
          error: reason instanceof Error ? reason.message : "读取失败，请重试。", conflict: false, pending: false }));
        if (revoked) dataRef.current = null;
      } finally { loading = false; }
    };
    const revalidate = () => { if (document.visibilityState === "visible") { if (timer) clearTimeout(timer); void load(); } };
    void load();
    window.addEventListener("focus", revalidate);
    window.addEventListener("pageshow", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => { request.abort(); if (timer) clearTimeout(timer); window.removeEventListener("focus", revalidate); window.removeEventListener("pageshow", revalidate); document.removeEventListener("visibilitychange", revalidate); };
  }, [key, path, identity, attempt, ownerId, loadResource]);

  /** Caller-owned form input is never overwritten. A 409 retains it and fetches the competing revision. */
  const mutate = useCallback(async (fingerprint: string, action: (data: T, requestId: string) => Promise<T>) => {
    if (!key || !dataRef.current || pendingRef.current) return null;
    pendingRef.current = true;
    revision.current += 1;
    const expectedIdentity = identity;
    const requestId = operation.current?.fingerprint === fingerprint ? operation.current.requestId : createRequestKey();
    operation.current = { fingerprint, requestId };
    setState(previous => previous?.key === identity ? { ...previous, pending: true, error: "", conflict: false } : previous);
    try {
      const data = await withPrivateOwner(ownerId!, () => {
        if (activeIdentity.current !== expectedIdentity || !dataRef.current) throw new DOMException("Session changed", "AbortError");
        return action(dataRef.current, requestId);
      });
      if (activeIdentity.current !== expectedIdentity) return null;
      operation.current = null; dataRef.current = data;
      setState({ key: identity, data, error: "", conflict: false, pending: false });
      setAttempt(value => value + 1);
      return data;
    } catch (reason) {
      if (activeIdentity.current !== expectedIdentity) return null;
      const conflict = reason instanceof ApiRequestError && reason.status === 409;
      const revoked = reason instanceof PrivateOwnerVerificationError || reason instanceof ApiRequestError && [401, 403, 404, 410].includes(reason.status);
      if (reason instanceof ApiRequestError && reason.status >= 400 && reason.status < 500) operation.current = null;
      let data = revoked ? null : dataRef.current;
      if (conflict) {
        try { data = await withPrivateOwner(ownerId!, () => loadResource ? loadResource(path, AbortSignal.timeout(30000)) : privateRequest<T>(path)); } catch (refreshError) {
          if (refreshError instanceof PrivateOwnerVerificationError || refreshError instanceof ApiRequestError && [401, 403, 404, 410].includes(refreshError.status)) data = null;
        }
        if (activeIdentity.current !== expectedIdentity) return null;
      }
      dataRef.current = data;
      setState({ key: identity, data, pending: false, conflict, error: reason instanceof Error ? reason.message : "保存失败，输入仍保留。" });
      throw reason;
    } finally { if (activeIdentity.current === expectedIdentity) pendingRef.current = false; }
  }, [key, identity, path, ownerId, loadResource]);

  return { data: current?.data ?? null, loading: Boolean(key) && !current, error: current?.error ?? "", pending: current?.pending ?? false, conflict: current?.conflict ?? false, pollPaused: current?.pollPaused ?? false, reload, mutate };
}

export function useResearchRecord<T>(collection: ResearchCollection, id: string | null, ownerId: string | null) {
  const load = useCallback((path: string, signal: AbortSignal) => privateRequest<ResearchRecord<T>>(path,
    { signal, ...(collection === "reading-plans" && ownerId ? { headers: { "X-Reader-Owner": ownerId } } : {}) }), [collection, ownerId]);
  return usePersistentWorkspace<ResearchRecord<T>>(id ? researchRecordPath(collection, id) : "", ownerId, taskPollDelay, load);
}
export function useContentPlacements(type: PlacementPage, id: string | null, ownerId: string | null) {
  return usePersistentWorkspace<PlacementState>(id ? placementsPath(type, id) : "", ownerId);
}
export function useDocumentOutline(assetId: string | null, ownerId: string | null) {
  return usePersistentWorkspace<OutlineState>(assetId ? outlinePath(assetId) : "", ownerId,
    data => data.jobs.some(job => isTaskRunning(job.status)) ? 2000 : null);
}
export function useEditorialAssistance(issueId: string, jobId: string | null, ownerId: string | null) {
  return usePersistentWorkspace<EditorialAssistance>(jobId ? editorialAssistancePath(issueId, jobId) : "", ownerId, taskPollDelay);
}
