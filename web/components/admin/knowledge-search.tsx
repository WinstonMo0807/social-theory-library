"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowLeft, Search } from "lucide-react";
import { EvidencePanel, KnowledgeNavigation, knowledgeCall, type SourceLocator } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";

const kinds: Record<string, string> = { original_text: "原文", bibliography: "作品", knowledge_object: "实体", knowledge_page: "知识页", curated_content: "人工策展" };
type Hit = { id: string; source_type: string; title?: string; excerpt?: string; text?: string; url?: string; reader_url?: string; page_id?: string; locator?: SourceLocator; coverage: string };
type Group = { status: string; results: Hit[]; detail?: string; has_more?: boolean; warnings: { code: string; message: string }[] };
type Results = { query: string; groups: Record<string, Group>; elapsed_ms: number; status: string };

export function KnowledgeSearch() {
  const [query, setQuery] = useState(""), [kind, setKind] = useState("knowledge_page"), [data, setData] = useState<Results | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [selected, setSelected] = useState<Hit | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  async function search() {
    request.current?.abort(); const c = new AbortController(); request.current = c;
    setBusy(true); setError(""); setData(null); setSelected(null);
    try { const result = await knowledgeCall<Results>("/search/query/", { q: query, source_types: kind ? [kind] : Object.keys(kinds), mode: "keyword" }, c.signal); if (!c.signal.aborted) setData(result); }
    catch (e) { if (!c.signal.aborted) setError(e instanceof Error ? e.message : "检索请求失败，请重试。"); }
    finally { if (!c.signal.aborted) setBusy(false); }
  }
  return <div className={s.workbench}>
    <header className={s.heading}><div><h1>检索已发布知识</h1><p>从原文、作品与编纂成果之间回查来源。</p></div><Link href="/admin/knowledge" className={s.buttonLink}><ArrowLeft size={15} />知识编纂</Link></header>
    <KnowledgeNavigation active="pages" />
    <form className={`${s.toolbar} ${s.searchForm}`} onSubmit={e => { e.preventDefault(); void search(); }}>
      <label>检索内容<input type="search" value={query} onChange={e => setQuery(e.target.value)} minLength={2} maxLength={1200} required placeholder="输入概念、问题或文献题名" /></label>
      <label>资料类型<select value={kind} onChange={e => setKind(e.target.value)}><option value="">全部资料</option>{Object.entries(kinds).map(([key, title]) => <option key={key} value={key}>{title}</option>)}</select></label>
      <button className={s.primary} disabled={busy}><Search size={16} />{busy ? "正在检索…" : "检索"}</button>
    </form>
    {error && <p className={s.error} role="alert">{error} <button disabled={busy} onClick={() => void search()}>重试</button></p>}
    {data && <div className={s.searchLayout}>
      <main>{Object.entries(data.groups).map(([type, group]) => <section key={type} className={s.searchGroup} aria-label={kinds[type]}>
        <header className={s.sectionBar}><h2>{kinds[type]}</h2>{group.status === "ready" && <span>{group.results.length} 项{group.has_more ? " · 可缩小查询范围" : ""}</span>}</header>
        {type === "knowledge_page" && !!group.results.length && <p className={s.searchNote}>以下为已发布的编纂正文；原文引用请打开页面内的证据。</p>}
        {group.status === "failed" ? <p role="alert" className={s.error}>{group.detail} <button onClick={() => void search()}>重试</button></p> : group.status === "waiting_index" ? <p role="status">索引尚未完整就绪，可在原文与检索工作区查看状态。</p> : !group.results.length ? <p className={s.empty}>此类资料中没有匹配内容。可调整检索词或资料类型。</p> : null}
        {group.warnings.map(w => <p key={w.code} role="status" className={s.searchNote}>{w.message}</p>)}
        {group.results.map(hit => <article key={hit.id} className={s.searchHit}>
          <h3>{hit.url || hit.reader_url ? <Link href={hit.url || hit.reader_url || ""}>{hit.title || "原文片段"}</Link> : hit.title || "原文片段"}</h3>
          {type === "original_text" ? <blockquote>{hit.excerpt || hit.text}</blockquote> : <p>{hit.excerpt || hit.text}</p>}
          <div className={s.toolbar}>{hit.locator && <button onClick={() => setSelected(hit)}>核对原文</button>}{hit.page_id && ["knowledge_page", "knowledge_object"].includes(type) && <Link href={`/admin/knowledge?page=${hit.page_id}`}>打开编纂工作区</Link>}{hit.reader_url && <Link href={hit.reader_url}>阅读对应版本</Link>}{type === "original_text" && !hit.locator && <span className={s.searchNote}>旧来源定位，精确锚点待核验</span>}</div>
        </article>)}
      </section>)}</main>
      {selected?.locator && <EvidencePanel locator={selected.locator} open onClose={() => setSelected(null)} />}
    </div>}
  </div>;
}
