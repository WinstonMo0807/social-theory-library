"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { knowledgeCall, type LibrarySource } from "./knowledge-workbench";
import s from "./knowledge-workbench.module.css";

type Compilation = { id: string; title: string; work_id: string; edition_id: string; enabled: boolean; execution_mode: "provider" | "agent";
  scope: { mode: string; start?: number; end?: number }; profile_key: string; target_page_ids: string[];
  status: string; stage?: number; changeset_id?: string; pending_refresh: boolean;
  coverage: { total_windows?: number; completed_windows?: number; read_characters?: number; total_characters?: number; analysis_complete?: boolean; missing_text_pages?: number[] };
  error?: { message?: string }; refresh_error?: { message?: string };
  windows?: { id: string; unit: string; status: string; elapsed_ms: number; usage: { model_calls?: number; agent_responses?: number } }[];
  synthesis?: { output: { summary: string; development: string[]; limitations: string[] } } | null };
type Product = { id: string; reader_url: string; chapter_path: string[]; ranges: { page_number: number }[]; executor_id: string;
  output: { summary: string; questions: string[]; methods?: string[]; limitations?: string[]; argument_role?: string;
    assertions: { text: string; claimant: string; expression: string; evidence: { page_number: number; exact: string; stance: string }[] }[] } };
const states: Record<string, string> = { waiting: "已排队", running: "正在编纂", waiting_agent: "等待代理续读", waiting_configuration: "待配置模型", waiting_resource: "等待执行资源", waiting_executor: "等待执行队列", waiting_remote: "等待计算节点", failed: "需要处理", succeeded: "范围完成，待审核", partial: "部分覆盖，待核对", empty: "范围完成，无新增建议", canceled: "已暂停" };
type TargetPage = { id: string; title: string; scope: string; kind: string };

export function KnowledgeCompilationPanel({ source, workId, pageId }: { source?: LibrarySource; workId?: string; pageId?: string }) {
  const [rows, setRows] = useState<Compilation[] | null>(null), [more, setMore] = useState(false), [offset, setOffset] = useState(0);
  const [error, setError] = useState(""), [busy, setBusy] = useState(false), [attempt, setAttempt] = useState(0), [editing, setEditing] = useState(false);
  const [mode, setMode] = useState<"provider" | "agent">("provider"), [range, setRange] = useState("whole"), [start, setStart] = useState(1), [end, setEnd] = useState(1);
  const [detail, setDetail] = useState<Compilation | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [targetIds, setTargetIds] = useState<string[]>([]), [targetQuery, setTargetQuery] = useState("");
  const [targetPages, setTargetPages] = useState<TargetPage[]>([]), [targetLabels, setTargetLabels] = useState<Record<string, string>>({});
  useEffect(() => {
    const controller = new AbortController(); setError("");
    const params = new URLSearchParams({ offset: String(offset) }); if (workId || source?.work_id) params.set("work_id", workId || source!.work_id);
    void knowledgeCall<{ compilations: Compilation[]; has_more: boolean }>(`/knowledge/compilations/?${params}`, undefined, controller.signal)
      .then(result => { setRows(source ? result.compilations.filter(row => row.edition_id === source.edition_id) : result.compilations); setMore(!source && result.has_more); }).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [workId, source?.work_id, source?.edition_id, offset, attempt]);
  useEffect(() => { setEditing(false); setDetail(null); setProduct(null); setEnd(source?.pages || 1); }, [source?.revision_id]);
  function toggleSettings() {
    if (!editing) {
      const current = rows?.find(row => row.edition_id === source?.edition_id);
      setMode(current?.execution_mode || "provider"); setRange(current?.scope.mode || "whole");
      setStart(current?.scope.start || 1); setEnd(current?.scope.end || source?.pages || 1);
      setTargetIds([...new Set([...(current?.target_page_ids || []), ...(pageId ? [pageId] : [])])]);
      void findTargets("");
    }
    setEditing(v => !v);
  }
  async function action(fn: () => Promise<void>) { if (busy) return; setBusy(true); setError(""); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "编纂操作未完成，请重试。"); } finally { setBusy(false); } }
  async function findTargets(query: string) { await action(async () => {
    const result = await knowledgeCall<{ pages: TargetPage[] }>(`/knowledge/workspace/?q=${encodeURIComponent(query)}`);
    setTargetPages(result.pages); setTargetLabels(old => ({ ...old, ...Object.fromEntries(result.pages.map(p => [p.id, p.title])) }));
  }); }
  async function control(row: Compilation, operation: string) { await action(async () => { await knowledgeCall(`/knowledge/compilations/${row.id}/`, { action: operation }); setAttempt(v => v + 1); setDetail(null); }); }
  async function enable() {
    if (!source) return;
    const current = rows?.find(row => row.edition_id === source.edition_id);
    await action(async () => {
      await knowledgeCall("/knowledge/compilations/", { document_revision_id: source.revision_id, execution_mode: mode,
        scope: range === "whole" ? { mode: "whole" } : { mode: "pages", start, end },
        profile_key: current?.profile_key || "", target_page_ids: targetIds });
      setEditing(false); setAttempt(v => v + 1);
    });
  }
  return <section className={s.compilation} aria-label="持续编纂">
    <div className={s.compilationHeading}><div><h2>持续编纂</h2><p>从已选原文形成有来源的修改，审核后再进入知识页。</p></div><div className={s.sectionBar}>
      <button disabled={busy || editing} onClick={() => { setDetail(null); setAttempt(v => v + 1); }}>刷新记录</button>
      {source && <button disabled={busy} onClick={toggleSettings}>{editing ? "收起设置" : "选择编纂范围"}</button>}</div></div>
    {error && <p role="alert" className={s.error}>{error}</p>}
    {editing && source && <form className={s.compilationForm} onSubmit={e => { e.preventDefault(); void enable(); }}>
      <div><strong>{source.title}</strong><p>{source.edition_label || "当前版本"}，正文修订 {source.revision_number}，共 {source.pages} 页</p></div>
      <label>读取范围<select value={range} onChange={e => setRange(e.target.value)}><option value="whole">整部文献</option><option value="pages">指定 PDF 页</option></select></label>
      {range === "pages" && <><label>起始页<input type="number" min={1} max={source.pages} value={start} onChange={e => setStart(Number(e.target.value))} /></label><label>结束页<input type="number" min={start} max={source.pages} value={end} onChange={e => setEnd(Number(e.target.value))} /></label></>}
      <label>执行方式<select value={mode} onChange={e => setMode(e.target.value as "provider" | "agent")}><option value="provider">配置中的模型</option><option value="agent">本次代理逐段编纂</option></select></label>
      <p>{mode === "agent" ? "保存后准备原文窗口，等待代理续读；不会启用或调用未配置的模型。" : "使用原模型管理中的知识编纂配置。未启用时保留范围并显示等待配置。"} 来源更新将接续此范围，已完成且仍有效的产物复用。</p>
      <fieldset className={s.compilationTargets}><legend>同时编纂的知识页</legend>
        <p>作品与相关身份页自动纳入。可另选主题、学科或专题页，建议将出现在所选页面的区块审核中。</p>
        <div className={s.sectionBar}><label>查找目标知识页<input value={targetQuery} onChange={e => setTargetQuery(e.target.value)} /></label><button type="button" disabled={busy} onClick={() => void findTargets(targetQuery)}>查找页面</button></div>
        {targetPages.map(p => <label key={p.id} className={s.compilationTarget}><input type="checkbox" checked={targetIds.includes(p.id)} disabled={!targetIds.includes(p.id) && targetIds.length >= 30} onChange={e => setTargetIds(ids => e.target.checked ? [...ids, p.id] : ids.filter(id => id !== p.id))} /><span>{p.title}{p.scope && <small>{p.scope}</small>}</span></label>)}
        {!!targetIds.length && <p>已选 {targetIds.length} 页：{targetIds.map(id => <span key={id}><Link target="_blank" rel="noreferrer" href={`/admin/knowledge?page=${id}`}>{targetLabels[id] || "查看已选页面"}</Link>{" "}<button type="button" onClick={() => setTargetIds(ids => ids.filter(key => key !== id))} aria-label={`移除${targetLabels[id] || "已选页面"}`}>移除</button>{" "}</span>)}</p>}
      </fieldset>
      <button className={s.primary} disabled={busy || range === "pages" && (!Number.isInteger(start) || !Number.isInteger(end) || end < start)} type="submit">保存并准备编纂</button>
    </form>}
    {rows === null ? !error && <p role="status">正在读取编纂记录…</p> : rows.length ? <ul className={s.compilationList}>{rows.map(row => <li key={row.id}>
      <div><Link href={`/admin/sources?work_id=${row.work_id}`}>{row.title}</Link><p>{row.scope.mode === "whole" ? "整部文献" : `PDF ${row.scope.start}–${row.scope.end} 页`}，{row.execution_mode === "agent" ? "代理编纂" : "配置中的模型"}</p></div>
      <div><strong>{!row.enabled ? "已暂停" : row.status === "waiting_agent" && (row.stage || 0) > 2 ? "原文已读，待代理编纂" : states[row.status] || row.status}</strong><p>{row.coverage.total_windows !== undefined ? `已完成 ${row.coverage.completed_windows || 0} / ${row.coverage.total_windows} 个原文窗口` : "等待建立读取清单"}</p>
        {!!row.coverage.missing_text_pages?.length && <p>范围内缺少正文 {row.coverage.missing_text_pages.length} 页</p>}
        {row.pending_refresh && <p>来源有变化，等待接续更新</p>}{row.refresh_error?.message && <p role="alert">{row.refresh_error.message}</p>}
        {row.error?.message && !["waiting_agent", "waiting_remote"].includes(row.status) && <p role="alert">{row.error.message}</p>}</div>
      <div className={s.compilationActions}><button disabled={busy} onClick={() => void action(async () => { setProduct(null); setDetail(await knowledgeCall<Compilation>(`/knowledge/compilations/${row.id}/`)); })}>查看读取记录</button>
        {row.changeset_id && <Link href={`/admin/knowledge/review?changeset=${row.changeset_id}`}>核验建议</Link>}
        <button disabled={busy} onClick={() => void control(row, !row.enabled || ["failed", "waiting_configuration", "waiting_resource", "waiting_executor"].includes(row.status) ? "resume" : "pause")}>{!row.enabled || ["failed", "waiting_configuration", "waiting_resource", "waiting_executor"].includes(row.status) ? "恢复编纂" : "暂停接续"}</button></div>
    </li>)}</ul> : <p className={s.searchNote}>尚未选择持续编纂的文献。可在原文工作区选定版本和读取范围。</p>}
    {(more || offset > 0) && <div className={s.sectionBar}><button disabled={!offset || busy} onClick={() => setOffset(v => Math.max(0, v - 30))}>上一页</button><button disabled={!more || busy} onClick={() => setOffset(v => v + 30)}>下一页</button></div>}
    {detail && <section className={s.compilationDetail}><div className={s.sectionBar}><h3>{detail.title}的读取记录</h3><button onClick={() => setDetail(null)}>收起</button></div>
      <p>实际读取 {detail.coverage.read_characters?.toLocaleString() || 0} / {detail.coverage.total_characters?.toLocaleString() || "待计算"} 个原文字符。{detail.coverage.analysis_complete ? "已覆盖所选范围，学术解释仍须审核。" : detail.coverage.total_windows && detail.coverage.completed_windows === detail.coverage.total_windows ? "原文窗口已读完，知识编纂仍在接续。" : "所选范围尚未全部完成。"}</p>
      {detail.synthesis && <><h4>已形成的论证梳理</h4><p>{detail.synthesis.output.summary}</p><ol>{detail.synthesis.output.development.map((value, i) => <li key={i}>{value}</li>)}</ol>{detail.synthesis.output.limitations.map((value, i) => <p key={i}>{value}</p>)}</>}
      <details><summary>窗口与执行记录</summary><ul>{detail.windows?.map(window => <li key={window.id}>{window.unit}：{window.status === "succeeded" || window.status === "empty" ? "已保存" : window.status === "waiting_agent" ? "等待代理" : window.status}，{window.usage.agent_responses ? "代理提交" : `${window.usage.model_calls || 0} 次模型调用`}
        {["succeeded", "empty"].includes(window.status) && <button disabled={busy} onClick={() => void action(async () => setProduct(await knowledgeCall<Product>(`/knowledge/compilation-products/${window.id}/`)))}>阅读产物</button>}</li>)}</ul></details>
      {product && <article className={s.compilationProduct} aria-live="polite"><h4>{product.chapter_path.join(" / ") || "所选原文"}</h4><p>PDF {[...new Set(product.ranges.map(row => row.page_number))].join("、")} 页 · {product.executor_id || "复用已验证产物"}</p>
        <p>{product.output.summary}</p>{product.output.argument_role && <p>{product.output.argument_role}</p>}
        {!!product.output.questions.length && <><h5>研究问题</h5><ul>{product.output.questions.map((text, i) => <li key={i}>{text}</li>)}</ul></>}
        {!!product.output.methods?.length && <><h5>材料与方法</h5><ul>{product.output.methods.map((text, i) => <li key={i}>{text}</li>)}</ul></>}
        {product.output.assertions.map((assertion, i) => <section key={i}><p><strong>{assertion.claimant || "归属待核对"}</strong> · {assertion.text}</p>{assertion.evidence.map((evidence, j) => <blockquote key={j}><p>{evidence.exact}</p><footer>{product.reader_url ? <Link target="_blank" rel="noreferrer" href={`${product.reader_url}&page=${evidence.page_number}`}>核对 PDF {evidence.page_number} 页</Link> : `PDF ${evidence.page_number} 页`} · {({ supports: "支持", opposes: "反对", qualifies: "限定", context: "语境" } as Record<string, string>)[evidence.stance] || evidence.stance}</footer></blockquote>)}</section>)}
        {product.output.limitations?.map((text, i) => <p key={i}>{text}</p>)}
      </article>}
    </section>}
  </section>;
}
