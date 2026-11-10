"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AcademicRelations } from "../academic-relations";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { createRequestKey } from "@/lib/request-key";
import { useAdminSession } from "@/lib/admin-session";
import { RelationSourceQuote } from "@/components/public/relation-source-quote";
import type { Paginated } from "@/lib/api/pagination";
import type { ScholarRelation } from "@/lib/api/scholar-relations.types";
import type { RelationSourceRequest } from "./relation-source-picker";

export type ScholarRelationGuard = { dirty: boolean; pending: boolean; composing: boolean };
type Props = RelationSourceRequest & { scholarId: string; initialRelationId?: string; embedded?: boolean; detailOnly?: boolean; onGuardChange?: (value: ScholarRelationGuard) => void; onSaved?: () => void };

/** Old URLs retain their history. All editing uses the shared knowledge workspace. */
export function ScholarRelationsEditor({ scholarId, initialRelationId, onGuardChange, onSaved }: Props) {
  const user = useAdminSession(), [history, setHistory] = useState<Paginated<ScholarRelation> | null>(null);
  const [page, setPage] = useState(1), [error, setError] = useState(""), [review, setReview] = useState("");
  const [busy, setBusy] = useState(false), [attempt, setAttempt] = useState(0);
  const requests = useRef(new Map<string, string>());
  useEffect(() => { onGuardChange?.({ dirty: false, pending: busy, composing: false }); }, [busy, onGuardChange]);
  useEffect(() => {
    if (!user) return;
    const c = new AbortController();
    void apiRequest<Paginated<ScholarRelation>>(`/catalog/admin/scholar-relations/?scholar=${scholarId}&page=${page}`, { signal: c.signal, cache: "no-store", headers: { "X-Editor-Owner": String(user.id) } }, getServerSessionCredential())
      .then(setHistory).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [user?.id, scholarId, page, attempt]);
  async function propose(row: ScholarRelation) {
    if (!user) return;
    setBusy(true); setError("");
    try {
      const requestId = requests.current.get(row.id) || createRequestKey(); requests.current.set(row.id, requestId);
      const result = await apiRequest<{ review_url: string }>(`/catalog/admin/scholar-relations/${row.id}/`, {
        method: "PUT", headers: { "X-Editor-Owner": String(user.id), "Idempotency-Key": requestId }, body: JSON.stringify({})
      }, getServerSessionCredential());
      setReview(result.review_url); onSaved?.();
    } catch (e) { setError(e instanceof Error ? e.message : "历史草稿送审失败，请重试。"); } finally { setBusy(false); }
  }
  return <>
    <AcademicRelations legacyType="scholar" legacyId={scholarId} blocked={busy} />
    {review && <p role="status">历史草稿已进入统一审核，原记录保留。<Link href={review}>继续审核 →</Link></p>}
    {error && <p role="alert">{error} <button onClick={() => setAttempt(v => v + 1)}>重新读取</button></p>}
    {!!history?.count && <details open={!!initialRelationId}><summary>旧关系与编辑历史 · {history.count}</summary>
      {history.results.map(row => <article key={row.id}><h3>{row.source_name} → {row.target_name}</h3><p>{row.summary}</p><p>{row.source}</p><RelationSourceQuote material={row.source_material} />
        {row.status !== "published" && <button disabled={busy} onClick={() => void propose(row)}>将此历史草稿送入审核</button>}
        {row.has_unpublished_changes && row.status === "published" && <p>此旧记录另有未发布修订，内容保留在本条历史中。请在上方对应陈述中修订，核对当前基准后送审。</p>}
      </article>)}
      <button disabled={page === 1} onClick={() => setPage(v => v - 1)}>上一页</button><span>第 {page} 页</span><button disabled={!history.next} onClick={() => setPage(v => v + 1)}>下一页</button>
    </details>}
  </>;
}
