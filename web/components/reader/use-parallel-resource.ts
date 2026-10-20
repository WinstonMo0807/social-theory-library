"use client";

import { useEffect, useEffectEvent, useState } from "react";
import { parallelRequest } from "@/lib/api/parallel-reader.client";

/** A changed file, revision or owner never renders a previous resource's text. */
export function useParallelResource<T>(path: string, ownerId?: number) {
  const key = `${ownerId ?? "public"}:${path}`;
  const [state, setState] = useState<{ key: string; data: T | null; error: string } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [stopped, setStopped] = useState("");
  const requestKey = `${key}:${attempt}`;
  const revalidate = useEffectEvent(() => {
    if (path && stopped !== requestKey && document.visibilityState === "visible") setAttempt(value => value + 1);
  });
  useEffect(() => {
    const refresh = () => revalidate();
    window.addEventListener("focus", refresh);
    window.addEventListener("pageshow", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      window.removeEventListener("focus", refresh);
      window.removeEventListener("pageshow", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, []);
  useEffect(() => {
    if (!path || stopped === requestKey) return;
    const request = new AbortController();
    void parallelRequest<T>(path, { signal: request.signal }, ownerId)
      .then(data => { if (!request.signal.aborted) setState({ key: requestKey, data, error: "" }); })
      .catch(reason => { if (!request.signal.aborted) setState({ key: requestKey, data: null, error: reason instanceof Error ? reason.message : "读取失败，请重试。" }); });
    return () => request.abort();
  }, [path, ownerId, requestKey, stopped]);
  const current = state?.key === requestKey ? state : null;
  return {
    data: current?.data ?? null, error: current?.error ?? "",
    loading: Boolean(path) && !current && stopped !== requestKey,
    stopped: stopped === requestKey,
    reload: () => setAttempt(value => value + 1),
    stop: () => setStopped(requestKey),
  };
}
