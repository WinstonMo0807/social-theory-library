"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { createRequestKey } from "@/lib/request-key";
import { knowledgeCall } from "./knowledge-workbench";
import { KnowledgeAssertionContent, type KnowledgeAssertion } from "../public/knowledge-page-content";
import s from "./knowledge-workbench.module.css";

type Row = KnowledgeAssertion & { status: string; base_hash: string; page_id: string | null; predicate: string; predicate_label: string };
export function AcademicRelations({ legacyType, legacyId, blocked = false }: { legacyType?: string; legacyId?: string; blocked?: boolean }) {
  const [scope, setScope] = useState<{ id: string; entity_id?: string; work_id?: string; title: string } | null>(null);
  const [data, setData] = useState<{ assertions: Row[]; count: number; pending_changesets: { id: string; origin: string }[] } | null>(null);
  const [query, setQuery] = useState(""), [search, setSearch] = useState(""), [state, setState] = useState("");
  const [offset, setOffset] = useState(0), [attempt, setAttempt] = useState(0), [selected, setSelected] = useState("");
  const [reason, setReason] = useState(""), [error, setError] = useState(""), [busy, setBusy] = useState(false), [reviewUrl, setReviewUrl] = useState("");
  const key = useRef<{ signature: string; id: string } | null>(null);
  useEffect(() => {
    if (!legacyType || !legacyId) return;
    const c = new AbortController();
    void knowledgeCall<NonNullable<typeof scope>>("/knowledge/relations/", { legacy_type: legacyType, legacy_id: legacyId }, c.signal).then(setScope).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [legacyType, legacyId, attempt]);
  useEffect(() => {
    if (legacyId && !scope) return;
    const c = new AbortController(); setData(null); setError("");
    const p = new URLSearchParams({ q: search, state, offset: String(offset) });
    if (scope?.entity_id) p.set("entity_id", scope.entity_id);
    if (scope?.work_id) p.set("work_id", scope.work_id);
    void knowledgeCall<{ assertions: Row[]; count: number; pending_changesets: { id: string; origin: string }[] }>(`/knowledge/relations/?${p}`, undefined, c.signal).then(setData).catch(e => { if (!c.signal.aborted) setError(e.message); });
    return () => c.abort();
  }, [scope, legacyId, search, state, offset, attempt]);
  async function withdraw(row: Row) {
    setBusy(true); setError("");
    try {
      const body = { base_hash: row.base_hash, reason };
      const signature = JSON.stringify([row.id, body]);
      if (key.current?.signature !== signature) key.current = { signature, id: createRequestKey() };
      const result = await knowledgeCall<{ review_url: string }>(`/knowledge/assertions/${row.id}/withdrawal/`, { ...body, request_id: key.current.id });
      setReviewUrl(result.review_url);
    } catch (e) { setError(e instanceof Error ? e.message : "撤回草稿未保存，请重试。"); } finally { setBusy(false); }
  }
  return <section className={s.workbench} aria-label="学术陈述与关系">
    <header className={s.sectionBar}><div><h2>{scope?.title ? `${scope.title} · 学术陈述` : "学术陈述与关系"}</h2><p className={s.muted}>按来源保留不同用法、批评与解释。</p></div><Link className={s.buttonLink} aria-disabled={blocked} onClick={e => { if (blocked) e.preventDefault(); }} href={scope ? `/admin/knowledge?page=${scope.id}&new_assertion=1` : "/admin/knowledge"}>编纂新陈述 →</Link></header>
    <form className={s.toolbar} onSubmit={e => { e.preventDefault(); setSearch(query); setOffset(0); }}><label>陈述与出处<input type="search" value={query} onChange={e => setQuery(e.target.value)} /></label><label>状态<select value={state} onChange={e => { setState(e.target.value); setOffset(0); }}><option value="">当前记录</option><option value="published">已发布</option><option value="draft">草稿</option><option value="withdrawn">已撤回</option><option value="superseded">历史修订</option></select></label><button>查找</button></form>
    {error && <p className={s.error} role="alert">{error} <button onClick={() => setAttempt(v => v + 1)}>重试</button></p>}
    {reviewUrl && <p className={s.notice} role="status">撤回已形成审核草稿，公开内容尚未改变。<Link href={reviewUrl}>核对撤回范围 →</Link></p>}
    {!data && !error && <p role="status">正在读取陈述和原始出处…</p>}
    {!!data?.pending_changesets.length && <details><summary>待审核草稿 · {data.pending_changesets.length}</summary>{data.pending_changesets.map(v => <p key={v.id}><Link href={`/admin/knowledge/review?changeset=${v.id}`}>{v.origin === "legacy_candidate" ? "历史候选迁入" : "知识编纂草稿"} →</Link></p>)}</details>}
    {data?.assertions.map(row => <article className={s.relationEntry} key={row.id}><aside className={s.relationMeta}><span>{{ published: "已发布", draft: "草稿", superseded: "历史修订", withdrawn: "已撤回" }[row.status] || row.status}</span><strong>{row.predicate_label || row.predicate || "学术陈述"}</strong>{row.page_id && <Link href={`/admin/knowledge?page=${row.page_id}&assertion=${row.id}`}>查看与修订</Link>}</aside><div className={s.relationBody}><KnowledgeAssertionContent assertion={row} />
      {row.page_id && ["published", "draft", "confirmed"].includes(row.status) && <><button disabled={blocked || busy} onClick={() => { setSelected(selected === row.id ? "" : row.id); setReviewUrl(""); setReason(""); }}>提出撤回</button>{selected === row.id && <div className={s.toolbar}><label>撤回原因<textarea value={reason} onChange={e => setReason(e.target.value)} disabled={busy || !!reviewUrl} /></label><button disabled={busy || !!reviewUrl || !reason.trim()} onClick={() => void withdraw(row)}>提交撤回审核</button></div>}</>}
    </div></article>)}
    {data && !data.count && <p className={s.empty}>此范围暂无陈述。选择知识页后，可补充明确身份和文献出处。</p>}
    {!!data?.count && <div className={s.toolbar}><button disabled={!offset} onClick={() => setOffset(v => Math.max(0, v - 30))}>上一页</button><span>{offset + 1}—{Math.min(offset + 30, data.count)} / {data.count}</span><button disabled={offset + 30 >= data.count} onClick={() => setOffset(v => v + 30)}>下一页</button></div>}
  </section>;
}
