"use client";

import { useEffect, useState } from "react";
import { FileText } from "lucide-react";
import { normalizePublicResourceUrl } from "@/lib/api";
import { loadPublicSource, sourceStatusLabel, type PublicSourceStatus } from "@/lib/api/source-follows.client";
import styles from "./source-status.module.css";

export function usePublicSource(path: string) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ path: string; source: PublicSourceStatus | null; error: string } | null>(null);
  useEffect(() => {
    if (!path) return;
    const request = new AbortController();
    void loadPublicSource(path, request.signal).then(source => {
      if (!request.signal.aborted) setState({ path, source, error: "" });
    }).catch(reason => {
      if (!request.signal.aborted) setState({ path, source: null, error: reason instanceof Error ? reason.message : "来源状态暂时无法读取。" });
    });
    return () => request.abort();
  }, [path, attempt]);
  const current = state?.path === path ? state : null;
  return { source: current?.source ?? null, error: current?.error ?? "", loading: Boolean(path) && !current,
    reload: () => { setState(null); setAttempt(value => value + 1); } };
}

/** Metadata always comes from the anonymous-public resolver, never the referring page. */
export function FeedbackSourceCard({ path }: { path: string }) {
  const state = usePublicSource(path);
  return <div className={styles.related} aria-live="polite">
    {state.source?.cover_url ? <img src={normalizePublicResourceUrl(state.source.cover_url)} alt="" width={42} height={60} /> : <FileText size={30} aria-hidden="true" />}
    <div><strong>{state.source?.title || (state.loading ? "正在读取相关页面…" : "相关页面尚未核对")}</strong>
      {state.source ? <span>{[state.source.authors.join("、"), state.source.version_label, state.source.location, sourceStatusLabel[state.source.status]].filter(Boolean).join(" · ")}</span> : null}
      {state.error ? <span role="alert">{state.error}<button type="button" onClick={state.reload}>重新读取</button></span> : null}
      <small>{path}</small>
    </div>
  </div>;
}
