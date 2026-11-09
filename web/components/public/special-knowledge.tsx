"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { usePublicSession } from "../public-session-provider";
import { KnowledgePageContent, type KnowledgePageData } from "./knowledge-page-content";
import styles from "./special-knowledge.module.css";

export function SpecialKnowledge({ slug }: { slug: string }) {
  const { state } = usePublicSession();
  const [page, setPage] = useState<KnowledgePageData | null>(null), [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const c = new AbortController(); setError(""); setPage(null);
    void apiRequest<KnowledgePageData>(`/knowledge/special/${encodeURIComponent(slug)}/`, { signal: c.signal, cache: "no-store" }, getServerSessionCredential())
      .then(setPage).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [slug, state.status, attempt]);
  return <article className={styles.page} data-ui-scope="editorial-v2">
    <nav aria-label="当前位置"><Link href="/home">书库</Link><span aria-hidden="true"> / </span><span>专题知识</span></nav>
    {error ? <div className={styles.message} role="alert"><h1>此专题暂时无法读取</h1><p>{error}</p><button onClick={() => setAttempt(v => v + 1)}>重新读取</button></div>
      : !page ? <p className={styles.message} role="status">正在读取已发布专题…</p> : <>
        <header className={styles.header}><p className={styles.label}>跨著作编纂</p><h1>{page.title}</h1><p className={styles.scope}>{page.scope}</p></header>
        <div className={styles.body}><KnowledgePageContent page={page} /></div>
      </>}
  </article>;
}
