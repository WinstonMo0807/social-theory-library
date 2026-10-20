"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiRequestError, classifyClientError, getServerSessionCredential, isUnauthenticatedError, subscribeToSessionChanges } from "@/lib/api";
import { readAllPages } from "@/lib/api/read-all-pages";
import { readResearchRecord, type ProjectData, type ResearchRecord, type TurnData } from "@/lib/api/research.client";
import { isTaskRunning, pollBudgetExpired, taskPollDelay } from "@/lib/api/task-polling";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";

/** Private reads and mutations share one invalidation boundary, including logout. */
export function useResearchProject(id: string, includeTurns = false) {
  const { state: session, retry: retrySession } = useSessionBootstrap();
  const [record, setRecord] = useState<ResearchRecord<ProjectData> | null>(null);
  const [turns, setTurns] = useState<ResearchRecord<TurnData>[]>([]);
  const [owner, setOwner] = useState<number>();
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [pollPaused, setPollPaused] = useState(false);
  const epoch = useRef(0);
  const busy = useRef(false);
  const pollStarted = useRef(0);
  const request = useRef({ fingerprint: "", id: "" });
  const snapshotIdentity = useRef("");
  const lastReadAt = useRef(0);
  const ownerId = session.user?.id;

  const load = useCallback(async (signal?: AbortSignal) => {
    const credential = getServerSessionCredential();
    if (!credential || ownerId === undefined) throw new Error("请重新登录后读取研究资料。");
    const [project, rows] = await Promise.all([
      readResearchRecord<ProjectData>("research-projects", id, signal),
      includeTurns ? readAllPages<ResearchRecord<TurnData>>(`/reading/research-projects/${encodeURIComponent(id)}/turns/`, credential, signal, String(ownerId)) : Promise.resolve([]),
    ]);
    return { project, rows };
  }, [id, includeTurns, ownerId]);
  const accept = useCallback(({ project, rows }: Awaited<ReturnType<typeof load>>) => {
    snapshotIdentity.current = `${ownerId}:${project.id}`;
    lastReadAt.current = Date.now();
    setRecord(project); setTurns(rows); setOwner(ownerId); setError("");
  }, [ownerId]);
  const handleError = useCallback((reason: unknown, action = false) => {
    const category = classifyClientError(reason);
    if (reason instanceof ApiRequestError && [404, 410].includes(reason.status)) {
      snapshotIdentity.current = ""; epoch.current += 1;
      setRecord(null); setTurns([]); setOwner(undefined);
      setError("这份研究或操作目标已经移除，请重新读取最新状态。");
      return;
    }
    if (isUnauthenticatedError(reason) || category === "auth_403") {
      snapshotIdentity.current = "";
      epoch.current += 1; setRecord(null); setTurns([]); setOwner(undefined);
      setError("当前登录状态无法访问这份私人研究，请重新验证登录。");
      retrySession();
      return;
    }
    const message = reason instanceof Error ? reason.message : "研究资料暂时无法读取，请重试。";
    if (action) setActionError(message); else setError(message);
  }, [retrySession]);

  useEffect(() => subscribeToSessionChanges(() => {
    snapshotIdentity.current = "";
    epoch.current += 1; request.current = { fingerprint: "", id: "" };
    setRecord(null); setTurns([]); setOwner(undefined); setNotice(""); setActionError("");
  }), []);
  useEffect(() => {
    if (session.status === "unauthenticated") {
      window.location.replace(`/login?next=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    if (session.status !== "authenticated") return;
    const controller = new AbortController();
    const generation = ++epoch.current;
    pollStarted.current = Date.now();
    load(controller.signal).then((snapshot) => {
      if (!controller.signal.aborted && epoch.current === generation) accept(snapshot);
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted && epoch.current === generation) handleError(reason, snapshotIdentity.current === `${ownerId}:${id}`);
    });
    return () => { controller.abort(); epoch.current += 1; };
  }, [id, attempt, session.status, ownerId, load, accept, handleError]);

  useEffect(() => {
    const revalidate = () => {
      if (document.visibilityState !== "visible" || busy.current || session.status !== "authenticated"
        || snapshotIdentity.current !== `${ownerId}:${id}` || Date.now() - lastReadAt.current < 30_000) return;
      lastReadAt.current = Date.now();
      setAttempt((value) => value + 1);
    };
    window.addEventListener("focus", revalidate);
    window.addEventListener("pageshow", revalidate);
    document.addEventListener("visibilitychange", revalidate);
    return () => {
      window.removeEventListener("focus", revalidate);
      window.removeEventListener("pageshow", revalidate);
      document.removeEventListener("visibilitychange", revalidate);
    };
  }, [session.status, ownerId, id]);

  useEffect(() => {
    if (session.status !== "authenticated" || owner !== ownerId || pending || pollPaused) return;
    const delays = turns.filter((turn) => isTaskRunning(turn.status)).map(taskPollDelay).filter((delay): delay is number => delay !== null);
    if (!delays.length) return;
    const delay = Math.min(...delays);
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (controller.signal.aborted) return;
      if (pollBudgetExpired(pollStarted.current)) {
        setPollPaused(true); setNotice("自动更新已暂停。已读取的材料仍保留，可点击刷新继续读取进度。"); return;
      }
      if (document.visibilityState !== "visible" || busy.current) { timer = setTimeout(poll, delay); return; }
      const generation = epoch.current;
      try {
        const snapshot = await load(controller.signal);
        if (!controller.signal.aborted && epoch.current === generation) accept(snapshot);
      } catch (reason) {
        if (!controller.signal.aborted && epoch.current === generation) {
          setPollPaused(true); handleError(reason, true);
        }
      }
    };
    timer = setTimeout(poll, delay);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [turns, pending, pollPaused, session.status, owner, ownerId, load, accept, handleError]);

  function refresh() {
    setError(""); setActionError(""); setPollPaused(false); pollStarted.current = Date.now();
    if (session.status !== "authenticated") retrySession(); else setAttempt((value) => value + 1);
  }
  function requestId(fingerprint: string) {
    if (request.current.fingerprint !== fingerprint) request.current = { fingerprint, id: crypto.randomUUID() };
    return request.current.id;
  }
  async function run(operation: () => Promise<unknown>, success: string) {
    if (busy.current || session.status !== "authenticated" || owner !== ownerId || record?.id !== id) return false;
    busy.current = true; setPending(true); setNotice(""); setActionError("");
    const generation = ++epoch.current;
    let saved = false;
    try {
      await operation();
      saved = true;
      if (epoch.current !== generation) return false;
      const snapshot = await load();
      if (epoch.current !== generation) return false;
      accept(snapshot); setNotice(success); setPollPaused(false); pollStarted.current = Date.now();
      request.current = { fingerprint: "", id: "" };
      return true;
    } catch (reason) {
      if (epoch.current !== generation) return false;
      handleError(reason, true);
      if (saved) {
        request.current = { fingerprint: "", id: "" };
        setNotice(`${success} 最新状态暂未读回，请刷新。`);
      }
      return saved;
    } finally { busy.current = false; setPending(false); }
  }
  const accessible = session.status === "authenticated" && owner === ownerId && record?.id === id;
  return { record: accessible ? record : null, turns: accessible ? turns : [], session, pending, error, notice, actionError, refresh, run, requestId, pollPaused };
}
