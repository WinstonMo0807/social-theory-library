"use client";

import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import type { PublicReadingPath } from "@/lib/api/reading-paths.types";

export type PathPreviewState = { data: PublicReadingPath | null; error: string; loading: boolean; retry: () => void };

/** The response belongs to the exact form body and owner, never a prior selection. */
export function useReadingPathPreview(owner: string, body: string, refreshKey: string): PathPreviewState {
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify([owner, body, refreshKey, attempt]);
  const [result, setResult] = useState<{ key: string; data?: PublicReadingPath; error?: string } | null>(null);
  useEffect(() => {
    if (!owner) return;
    const controller = new AbortController();
    const unsubscribe = subscribeToSessionChanges(() => { controller.abort(); setResult(null); });
    const timer = window.setTimeout(() => {
      const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(30000)]);
      void withPrivateOwner(owner, () => apiRequest<PublicReadingPath>("/catalog/admin/theory-system/reading-paths/preview/", {
        method: "POST", body, signal, cache: "no-store", headers: { "X-Editor-Owner": owner },
      }, getServerSessionCredential(), false), signal).then(data => {
        if (!controller.signal.aborted) setResult({ key, data });
      }).catch(reason => {
        if (!controller.signal.aborted) setResult({ key, error: reason instanceof Error ? reason.message : "材料预览暂不可读取，当前输入仍保留。" });
      });
    }, 450);
    return () => { window.clearTimeout(timer); controller.abort(); unsubscribe(); };
  }, [owner, body, key]);
  const current = result?.key === key ? result : null;
  return { data: current?.data || null, error: current?.error || "", loading: Boolean(owner && !current), retry: () => setAttempt(value => value + 1) };
}
