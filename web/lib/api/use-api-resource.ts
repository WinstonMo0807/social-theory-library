"use client";

import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../api";

/** Request-local state. Old results are never rendered under a new URL/key. */
export function useApiResource<T>(url: string, credential: string | null, contextKey = "") {
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([url, credential, attempt, contextKey]);
  const [result, setResult] = useState<{ key: string; data: T | null; error: string } | null>(null);
  useEffect(() => {
    if (!url || !credential) return;
    const request = new AbortController();
    void apiRequest<T>(url, { signal: request.signal }, credential).then(
      (data) => { if (!request.signal.aborted) setResult({ key, data, error: "" }); },
      (error) => {
        if (!request.signal.aborted) setResult({ key, data: null, error: error instanceof Error ? error.message : "读取失败，请重试。" });
      },
    );
    return () => request.abort();
  }, [url, credential, key]);
  const current = result?.key === key ? result : null;
  const retry = useCallback(() => setAttempt((value) => value + 1), []);
  return { data: current?.data ?? null, error: current?.error ?? "", loading: current === null, retry };
}
