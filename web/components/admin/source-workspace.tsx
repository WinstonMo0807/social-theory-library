"use client";

import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowUpRight, PanelRightOpen, Search, X } from "lucide-react";
import { EvidencePanel, KnowledgeNavigation, knowledgeCall, type LibrarySource, type SourceLocator, type SourceSegment } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";
import { createRequestKey } from "@/lib/request-key";
import { AssertionFields, type AssertionFieldsValue } from "./assertion-fields";
import { KnowledgeAssertionContent } from "../public/knowledge-page-content";
import { ParagraphCorrection } from "./paragraph-correction";

type Node = { id: string; title: string; kind: string; parent_id: string | null };
type Context = { title: string; segments: SourceSegment[]; chapter_path: string[]; offset: number; next_offset: number | null; returned_characters: number; total_characters: number; references: { target_id: string; kind: string; label: string }[] };
type Hit = { id: string; title?: string; work_title?: string; excerpt: string; locator?: SourceLocator; node_id?: string; pdf_page?: number; page_start?: number; coverage?: string };
type Results = { status: string; results: Hit[]; warnings: { code: string; message: string }[]; elapsed_ms: number };
const ready: Record<string, string> = { ready: "可检索", partial: "部分就绪", pending: "待索引", unavailable: "服务待恢复" };
const runStates: Record<string, string> = { waiting_configuration: "待配置模型", waiting: "等待执行", running: "分析中", succeeded: "待审核", partial: "部分完成", empty: "完成 · 无建议", failed: "执行失败", canceled: "已取消" };

export function SourceWorkspace() {
  const query = useSearchParams(), router = useRouter(), revision = query.get("revision") || "", work = query.get("work_id") || "";
  const [rows, setRows] = useState<LibrarySource[]>([]), [filter, setFilter] = useState(""), [search, setSearch] = useState("");
  const [nodes, setNodes] = useState<Node[]>([]), [nodeId, setNodeId] = useState(""), [context, setContext] = useState<Context | null>(null), [offset, setOffset] = useState(0);
  const [view, setView] = useState<"text" | "search">("text"), [scope, setScope] = useState("node"), [q, setQ] = useState(""), [mode, setMode] = useState("keyword");
  const [results, setResults] = useState<Results | null>(null), [locator, setLocator] = useState<SourceLocator | null>(null), [page, setPage] = useState(1);
  const [selection, setSelection] = useState<SourceSegment[]>([]), [verified, setVerified] = useState<SourceLocator | null>(null), [evidenceOpen, setEvidenceOpen] = useState(false);
  const [error, setError] = useState(""), [contextError, setContextError] = useState(""), [busy, setBusy] = useState(false), [loaded, setLoaded] = useState(false), [attempt, setAttempt] = useState(0);
  const [parseStart,setParseStart] = useState(1), [parseEnd,setParseEnd] = useState(2), [parseNotice,setParseNotice] = useState("");
  const [assertionOpen,setAssertionOpen]=useState(false), [assertion,setAssertion]=useState<AssertionFieldsValue>({expression:"editorial_judgment",direction:"directed",participants:[],conditions:{}}), [stance,setStance]=useState("supports");
  const [draftRequest,setDraftRequest]=useState(() => createRequestKey());
  const source = rows.find(v => v.revision_id === revision);
  useEffect(() => { setRows([]); }, [search, revision, work]);
  useEffect(() => {
    const controller = new AbortController(); setError(""); setLoaded(false);
    const params = new URLSearchParams({ q: search }); if (revision) params.set("revision_id", revision); else if (work) params.set("work_id", work);
    void knowledgeCall<{ sources: LibrarySource[] }>(`/search/sources/?${params}`, undefined, controller.signal).then(r => { setRows(r.sources); setLoaded(true); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [search, revision, work, attempt]);
  useEffect(() => {
    setNodes([]); setContext(null); setNodeId(""); setOffset(0); setSelection([]); setVerified(null); setLocator(null); setResults(null); setPage(1);
  }, [revision]);
  useEffect(() => {
    if (!revision) return; const controller = new AbortController();
    void knowledgeCall<{ nodes: Node[] }>(`/knowledge/revisions/${revision}/structure/?preview=1`, undefined, controller.signal)
      .then(r => { setNodes(r.nodes); setNodeId(previous => r.nodes.some(n => n.id === previous) ? previous : r.nodes.find(n => n.kind !== "document")?.id || r.nodes[0]?.id || ""); })
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [revision, attempt]);
  useEffect(() => {
    setContext(null); setContextError(""); if (!nodeId) return; const controller = new AbortController();
    void knowledgeCall<Context>(`/knowledge/nodes/${nodeId}/context/?preview=1&scope=${scope}&offset=${offset}`, undefined, controller.signal)
      .then(r => { setContext(r); setPage(r.segments[0]?.page_number || 1); setLocator(old => old?.segments.some(segment => segment.node_id === nodeId) ? old : null); })
      .catch(e => { if (!controller.signal.aborted) setContextError(e.message); });
    return () => controller.abort();
  }, [nodeId, offset, scope]);
  async function action(fn: () => Promise<void>) { setBusy(true); setError(""); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "操作未完成，请重试。"); } finally { setBusy(false); } }
  function addSegment(segment: SourceSegment) {
    setVerified(null); setSelection(old => [...old.filter(v => !(v.page_number === segment.page_number && v.start === segment.start && v.end === segment.end)), segment].sort((a, b) => a.page_number - b.page_number || a.start - b.start));
  }
  async function searchText() { setResults(null); await action(async () => setResults(await knowledgeCall<Results>("/search/inspect/", { q, mode, revision_id: revision || undefined }))); }
  async function controlParse(operation: "retry" | "cancel") {
    if (!source?.structure_job) return;
    await action(async () => {
      await knowledgeCall("/ingestion/processing-center/", { action: operation, source: "processing_job", job_id: source.structure_job!.id });
      setParseNotice(operation === "retry" ? "已恢复该范围，原失败记录保留。" : "已取消该解析任务。");
      setAttempt(v => v + 1);
    });
  }
  async function useInPage() {
    if (!verified || !source) return;
    await action(async () => {
      const target = query.get("page") || (await knowledgeCall<{ id: string }>("/knowledge/workspace/", { work_id: source.work_id })).id;
      router.push(`/admin/knowledge?page=${target}&anchor=${verified.anchor_id}&revision=${revision}&work_id=${source.work_id}`);
    });
  }
  async function refreshStructure(value: SourceLocator | null) {
    await action(async () => {
      const result = await knowledgeCall<{ nodes: Node[] }>(`/knowledge/revisions/${revision}/structure/?preview=1`);
      setNodes(result.nodes); setNodeId(value?.segments[0]?.node_id || result.nodes.find(n => n.kind !== "document")?.id || "");
      setOffset(0); setScope("node"); setLocator(value); setSelection([]); setVerified(null);
      if (value) { setPage(value.segments[0]?.page_number || 1); setEvidenceOpen(true); }
    });
  }
  return <div className={s.workbench}>
    <header className={s.heading}><div><h1>{source?.title || "原文与检索"}</h1><p>{source ? `${source.edition_label || "当前版本"} · 正文修订 ${source.revision_number} · ${source.pages} 页` : "从文献版本出发，检查正文、检索与每一处引用。"}</p></div>
      {source && <Link className={s.buttonLink} href={source.catalog_url}>作品编目 <ArrowUpRight size={15} /></Link>}</header>
    <KnowledgeNavigation active="sources" workId={source?.work_id || work} revisionId={revision} />
    {parseNotice && <p role="status">{parseNotice}</p>}
    {error && <div className={s.error} role="alert">{error} <button onClick={() => setAttempt(v => v + 1)}>重新读取</button></div>}
    {!revision ? <>
      <form className={s.toolbar} onSubmit={e => { e.preventDefault(); setSearch(filter); }}><label>查找文献<input type="search" value={filter} onChange={e => setFilter(e.target.value)} placeholder="作品名称" /></label><button type="submit"><Search size={16} />查找</button><button type="button" onClick={() => setView(v => v === "search" ? "text" : "search")}>检验全库检索</button></form>
      <div className={s.tableWrap}><table className={s.table}><thead><tr><th>文献与来源</th><th>阅读</th><th>关键词</th><th>语义</th><th>策展</th><th>公开状态</th></tr></thead><tbody>{rows.map(row => <tr key={row.revision_id}>
        <td><Link href={`/admin/sources?revision=${row.revision_id}&work_id=${row.work_id}`}>{row.title}</Link><small>{row.edition_label || "馆藏版本"} · 修订 {row.revision_number} · {row.pages} 页</small></td>
        <td data-label="阅读">{row.readable ? "可阅读" : "待处理"}</td><td data-label="关键词" className={s.state} data-ready={row.keywords === "ready"}>{ready[row.keywords]}</td><td data-label="语义" className={s.state} data-ready={row.semantic === "ready"}>{ready[row.semantic]}</td>
        <td data-label="策展">{row.curation ? <Link href={`/admin/intelligence?run=${row.curation.id}&work_id=${row.work_id}`}>{runStates[row.curation.status] || row.curation.status}</Link> : "尚未分析"}</td><td data-label="公开状态">{row.published ? "已发布修订" : "内部修订"}</td>
      </tr>)}</tbody></table></div>{!loaded && !error && <p role="status" className={s.empty}>正在读取来源状态…</p>}{loaded && !rows.length && <p className={s.empty}>没有符合筛选的文献。</p>}
      {rows.length === 200 && <p className={s.muted}>当前显示前 200 个来源，请按作品名称缩小范围。</p>}
    </> : <div className={s.toolbar}><Link href="/admin/sources"><ArrowLeft size={15} />全部来源</Link><div className={s.segmented}><button aria-pressed={view === "text"} onClick={() => setView("text")}>正文结构</button><button aria-pressed={view === "search"} onClick={() => setView("search")}>检验检索</button></div>
      {source && <><span className={s.muted}>关键词 {ready[source.keywords]} · 语义 {ready[source.semantic]} · {source.published ? "已公开" : "内部修订"}</span><Link href={source.outline_url}>目录校准</Link>
        <button disabled={busy || !source.published || ["pending","running"].includes(source.index_job?.status || "")} onClick={() => void action(async () => { const result=await knowledgeCall<{job_id:string;status:string}>(`/knowledge/revisions/${revision}/reindex/`,{}); setParseNotice(result.status === "succeeded" ? "此结构的关键词索引已完成。" : "关键词更新已排队，上一有效索引继续可用。"); setAttempt(v=>v+1); })}>更新关键词索引</button>
        {source.index_job && <Link href={`/admin/processing?job=${source.index_job.id}`}>查看索引任务</Link>}</>}
      <button className={s.mobileOnly} onClick={() => setEvidenceOpen(true)}><PanelRightOpen size={16} />核对原文</button></div>}
    {(revision || view === "search") && <div className={s.workspace}>
      <aside className={s.rail}><h2>{view === "text" ? "正文目录" : "检索范围"}</h2>{view === "text" ? nodes.filter(n => ["document","part","chapter","section","preface","appendix","references"].includes(n.kind) && (n.title || n.kind === "document")).map(n => <button key={n.id} aria-current={nodeId === n.id} onClick={() => { setNodeId(n.id); setOffset(0); }}>{n.kind === "document" ? "全部正文" : n.title}</button>) : <p className={s.muted}>{source?.title || "全部已发布馆藏"}<br />与登录读者使用相同权限和检索服务。</p>}</aside>
      <main className={s.main}>
        {view === "search" ? <><h2>让结果回到原文</h2><form onSubmit={e => { e.preventDefault(); void searchText(); }}>
          <label>检索问题<input value={q} onChange={e => setQ(e.target.value)} minLength={2} maxLength={1200} required placeholder="输入一个问题、术语或原文短语" /></label>
          <div className={s.toolbar}><select aria-label="检索方式" value={mode} onChange={e => setMode(e.target.value)}><option value="keyword">仅关键词</option><option value="hybrid">混合检索</option></select><button className={s.primary} disabled={busy}><Search size={16} />检索</button></div></form>
          {busy && <p role="status">正在检索指定范围…</p>}{results && <><p className={s.muted}>{results.results.length} 条返回结果 · {results.elapsed_ms} ms</p>
            {results.warnings.map((v, i) => <p className={s.notice} key={`${v.code}-${i}`}>{v.message || v.code}</p>)}
            {results.status === "ready" && !results.results.length && <p className={s.empty}>此检索范围内没有匹配结果。可保留问题，切换检索方式后再试。</p>}
            {results.results.map((hit, i) => <button className={s.result} key={hit.id || i} onClick={() => { setLocator(hit.locator || null); setPage(hit.locator?.segments[0]?.page_number || hit.pdf_page || hit.page_start || 1); setEvidenceOpen(true); }}>
              <span>{hit.work_title || hit.title || source?.title} · {hit.locator ? hit.locator.segments.map(v => `PDF ${v.page_number}`).join("、") : "精确锚点待补齐"}</span><strong>{hit.excerpt}</strong><span>核对来源 →</span></button>)}</>}
        </> : <><h2>{context?.title || nodes.find(v => v.id === nodeId)?.title || "正文结构"}</h2>
          {source?.structure_coverage.structure_status === "needs_structure_review" && <details className={s.notice}><summary>部分目录尚未对应到正文</summary><p>以下标题尚未找到唯一原文位置，可进入目录校准核对。“全部正文”仍可读取完整修订。</p><ul>{(source.structure_coverage.unmapped_headings || []).map((gap, i) => <li key={i}>{gap.title || "未命名标题"} · PDF {gap.page || "未确定"}</li>)}</ul><Link href={source.outline_url}>打开目录校准</Link></details>}
          {!nodes.length && source && <><p>此修订尚未准备可引用的正文结构。已有正文和目录将用于建立映射。</p><button disabled={busy || ["pending","running"].includes(source?.sync_job?.status || "")} onClick={() => void action(async () => { await knowledgeCall(`/knowledge/revisions/${revision}/structure/`, {}); setAttempt(v => v + 1); })}>准备正文结构</button></>}
          {source?.sync_job && source.sync_job.status !== "succeeded" && <div className={s.notice} role="status"><p>{{pending:"目录与正文映射等待更新",running:"正在更新目录映射与检索来源",failed:"结构更新未完成",canceled:"此结构任务已停止"}[source.sync_job.status] || source.sync_job.status}{source.sync_job.error && ` · ${source.sync_job.error}`}</p><div className={s.toolbar}><button onClick={() => setAttempt(v=>v+1)}>刷新状态</button>{source.sync_job.status === "failed" && <button disabled={busy} onClick={() => void action(async()=>{await knowledgeCall(`/knowledge/revisions/${revision}/structure/`,{});setAttempt(v=>v+1);})}>恢复结构更新</button>}</div></div>}
          {source && <details className={s.notice}><summary>补充段落与脚注结构</summary><p>选择结构缺失或不准确的范围。计算节点只解析所选页，保留已有原文与人工目录；不能核对的片段会留待校准。</p>
            <form onSubmit={e => { e.preventDefault(); void action(async () => { const result = await knowledgeCall<{ job_id: string; status: string }>(`/knowledge/revisions/${revision}/structure/parse/`, { pages: [parseStart,parseEnd], request_id: createRequestKey() }); setParseNotice(`解析任务已保存，等待计算节点执行。`); setAttempt(v => v + 1); }); }}>
              <div className={s.toolbar}><label>PDF 起页<input type="number" min={1} max={source.pages} value={parseStart} onChange={e => setParseStart(Number(e.target.value))} required /></label><label>PDF 止页<input type="number" min={parseStart} max={Math.min(source.pages,parseStart+49)} value={parseEnd} onChange={e => setParseEnd(Number(e.target.value))} required /></label><button disabled={busy || ["pending","running"].includes(source.structure_job?.status || "")}>解析所选范围</button></div>
            </form>{source.structure_job && <div role="status"><p>最近范围 PDF {source.structure_job.pages.join("—")} · {{pending:"等待计算节点",running:"正在解析",succeeded:"结构已保存",failed:"解析失败",canceled:"已取消"}[source.structure_job.status] || source.structure_job.status}{source.structure_job.error && ` · ${source.structure_job.error}`}</p><div className={s.toolbar}><button disabled={busy} onClick={() => { setParseNotice(""); setAttempt(v => v + 1); }}>刷新结果</button>{["failed","canceled"].includes(source.structure_job.status) && <button disabled={busy} onClick={() => void controlParse("retry")}>恢复这一范围</button>}{["pending","running"].includes(source.structure_job.status) && <button disabled={busy} onClick={() => void controlParse("cancel")}>取消解析</button>}</div></div>}
            {!!source.structure_coverage.alignment_gaps?.length && <p>有 {source.structure_coverage.alignment_gaps.length} 个解析片段尚不能与原文唯一对应，相关原文已保留。</p>}
          </details>}
          {source && <ParagraphCorrection key={revision} revision={revision} pages={source.pages} onPage={number => { setPage(number); setLocator(null); setEvidenceOpen(true); }} onSaved={value => void refreshStructure(value)} />}
          {contextError && <p className={s.error} role="alert">{contextError}</p>}
          {nodeId && <div className={s.toolbar}><select aria-label="上下文范围" value={scope} onChange={e => { setScope(e.target.value); setOffset(0); }}><option value="node">所选正文节点</option><option value="section">所在小节</option><option value="chapter">所在章节</option></select><span className={s.muted}>{context ? `已展示 ${context.offset + 1}—${context.offset + context.returned_characters} / ${context.total_characters} 字符` : "正在读取…"}</span></div>}
          {context?.segments.map((part, i) => <article key={`${part.page_number}-${part.start}-${i}`}><p className={s.muted}>PDF {part.page_number}{part.printed_label ? ` · 书页 ${part.printed_label}` : ""}</p><div className={s.paragraph}>{part.exact}</div><div className={s.toolbar}><button onClick={() => { setPage(part.page_number); setLocator(null); setEvidenceOpen(true); }}>核对这一页</button><button onClick={() => addSegment(part)}>选用这段原文</button></div></article>)}
          {context?.next_offset != null && <button onClick={() => setOffset(context.next_offset!)}>继续阅读后续正文</button>}{offset > 0 && <button onClick={() => setOffset(0)}>返回章节开头</button>}
          {!!context?.references.length && <section><h3>相关注释</h3>{context.references.map((ref, i) => <button key={i} onClick={() => { setNodeId(ref.target_id); setOffset(0); setScope("node"); }}>{ref.label || "查看注释"}</button>)}</section>}
        </>}
        {!!selection.length && <section><h3>已选原文</h3>{selection.map((v, i) => <blockquote className={s.quote} key={i}><small>PDF {v.page_number} · {v.start}—{v.end}</small><p>{v.exact}</p><button aria-label={`移除第 ${i + 1} 段`} onClick={() => { setVerified(null); setSelection(old => old.filter((_, n) => n !== i)); }}><X size={15} />移除</button></blockquote>)}
          <div className={s.toolbar}><button disabled={busy} onClick={() => void action(async () => { const result = await knowledgeCall<SourceLocator>("/knowledge/anchors/verify/", { document_revision_id: revision, segments: selection }); setVerified(result); setLocator(result); setDraftRequest(createRequestKey()); })}>校验并固定引用</button>{verified && <button className={s.primary} disabled={busy} onClick={() => void useInPage()}>用于知识页</button>}{verified && <button disabled={busy} onClick={() => setAssertionOpen(true)}>编写学术陈述</button>}</div>{verified && <p role="status" className={s.muted}>已核对全部片段，并固定到当前正文修订。尚未写入知识页。</p>}
        </section>}
        {assertionOpen && verified && source && <section className={s.notice}><h3>从这段原文提出陈述</h3><AssertionFields value={assertion} disabled={busy} options={[]} onChange={v=>{setAssertion(v);setDraftRequest(createRequestKey());}} /><label>这段原文的作用<select value={stance} onChange={e=>{setStance(e.target.value);setDraftRequest(createRequestKey());}}><option value="supports">支持</option><option value="opposes">反对</option><option value="qualifies">限定</option><option value="context">提供语境</option></select></label><h4>页面呈现</h4><KnowledgeAssertionContent assertion={{id:"preview",text:assertion.text || "陈述正文将显示在这里",conditions:assertion.conditions,sources:[{work__title:source.title,attribution__label:null,expression:assertion.expression || "editorial_judgment"}],evidence:[{anchor_id:verified.anchor_id,stance,locator:verified}]}} /><div className={s.toolbar}><button className={s.primary} disabled={busy || !assertion.text?.trim()} onClick={() => void action(async()=>{const result=await knowledgeCall<{review_url:string}>(`/knowledge/revisions/${revision}/assertions/draft/`,{request_id:draftRequest,assertion:{...assertion,evidence:[{stance,segments:verified.segments}]}});router.push(result.review_url);})}>提交审核草稿</button><button disabled={busy} onClick={()=>setAssertionOpen(false)}>收起编辑</button></div></section>}
        {source && <details><summary>来源与索引诊断</summary><p className={s.muted}>关键词 {source.index_counts.keywords || 0} · 向量 {source.index_counts.vectors || 0} · 预期片段 {source.index_counts.expected || 0}</p>{source.index_error && <p role="alert">{source.index_error}</p>}<div className={s.toolbar}><Link href={source.ocr_url}>正文处理</Link><Link href={`/admin/processing${source.index_job ? `?job=${source.index_job.id}` : ""}`}>任务与恢复</Link></div></details>}
      </main>
      <EvidencePanel source={source} locator={locator} page={page} open={evidenceOpen} onClose={() => setEvidenceOpen(false)} onQuote={source && (!locator || locator.document_revision_id === revision) ? addSegment : undefined} />
    </div>}
  </div>;
}
