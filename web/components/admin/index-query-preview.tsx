"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { Search } from "lucide-react";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import type { DiscoverySearch } from "@/lib/api/discovery.types";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useCatalogCommand } from "./workflow/use-intake-command";
import styles from "./index-maintenance.module.css";

type Receipt = components["schemas"]["IndexQueryReceipt"];
type Command = Omit<components["schemas"]["IndexQueryCommandRequest"], "request_id">;
const endpoint = "/catalog/admin/index-maintenance/query/";
const states: Record<string, string> = { queued: "等待检索", running: "正在检索", partial: "部分结果", completed: "检索完成", canceled: "已取消", failed: "检索未完成" };
const localHref = (value: string) => value.startsWith("/") && !value.startsWith("//") && !/[\\\u0000-\u001f\u007f]/.test(value) ? value : "";

export function IndexQueryPreview({ owner, workId, editionId }: { owner: string; workId: string; editionId: string }) {
  const [query, setQuery] = useState(""), [session, setSession] = useState(""), [limit, setLimit] = useState(3), [tab, setTab] = useState("passages"), [notice, setNotice] = useState("");
  // One unresolved query per account survives closing the selected material.
  const command = useCatalogCommand<Command, Receipt>(owner, endpoint, `stl-index-query:${owner}`);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<DiscoverySearch>(path, { signal, cache: "no-store", headers: { "X-Editor-Owner": owner } }, getServerSessionCredential(), false), [owner]);
  const resource = usePersistentWorkspace<DiscoverySearch>(session ? `/catalog/discovery-search/${session}/?limit=${limit}` : "", owner, result => result.task_progress.terminal ? null : Math.max(1500, Math.min(result.poll_after_ms || 3000, 10000)), load);
  const data = resource.data;
  const passageRows = (tab === "deep" ? data?.deep_passages : data?.passages)?.slice(0, limit) || [];
  const counts = { passages: data?.counts?.passages ?? data?.passages.length ?? 0, entities: data?.counts?.entities ?? data?.entities.length ?? 0, curation: data?.counts?.curation ?? data?.curation.length ?? 0, deep: data?.deep_passages?.length ?? 0 };
  const active = Boolean(data && !data.task_progress.terminal);
  const originalWork = Array.isArray(data?.filters?.work_ids) ? data.filters.work_ids[0] : data?.filters?.work_ids || workId;
  const locked = Boolean(session && !data && !resource.error) || !command.ready || command.busy || Boolean(command.recovery) || resource.pending;
  function accept(receipt: Receipt | null) {
    if (!receipt) return;
    if (receipt.state === "cancelled") { setNotice("未执行的原查询请求已停止。"); return; }
    if (receipt.session_id) { setSession(receipt.session_id); setLimit(3); setNotice(""); }
  }
  async function act(action: "cancel" | "retry") {
    if (!data) return;
    const body = action === "retry" ? { expected_generation: data.task_progress.generation } : {};
    try {
      await resource.mutate(JSON.stringify([data.id, action, body]), () => apiRequest<DiscoverySearch>(`/catalog/discovery-search/${data.id}/${action}/`, { method: "POST", signal: AbortSignal.timeout(25000), cache: "no-store", headers: { "X-Editor-Owner": owner }, body: JSON.stringify(body) }, getServerSessionCredential(), false));
      setNotice("");
    } catch { setNotice("操作结果待核实，请重新读取本次检索；不会另起一轮查询。"); }
  }
  return <section className={styles.queryLinks} aria-label="作品检索预览"><h3>检索词与命中预览</h3>
    <p className={styles.note}>正文限定这部作品的公开版本；知识与策展按同一查询检索全库公开内容。查询记录遵循账户的搜索记录设置。</p>
    <form className={styles.search} onSubmit={event => { event.preventDefault(); if (!locked && !active && query.trim().length >= 2) void command.send({ q: query.trim(), work_id: workId }).then(accept); }}><Search size={15}/><input aria-label="查询作品原文" minLength={2} maxLength={1200} value={query} disabled={locked || active} onChange={event => setQuery(event.target.value)} placeholder="输入词句或原文线索…"/><button type="submit" className={styles.primary} disabled={locked || active || query.trim().length < 2}>检索</button></form>
    {command.error || resource.error ? <p role="alert" className={styles.notice}>{command.error || resource.error}</p> : null}{notice ? <p role="status" className={styles.notice}>{notice}</p> : null}
    {command.recovery ? <div className={styles.notice}><p>查询是否建立尚待确认，请先查回原记录。</p><div className={styles.actions}><button type="button" disabled={command.busy} onClick={() => void command.lookup().then(accept)}>查回原查询</button>{command.canRetry ? <button type="button" disabled={command.busy} onClick={() => void command.send().then(accept)}>重送原请求</button> : null}<button type="button" disabled={command.busy} onClick={() => void command.lookup(true).then(accept)}>停止待定请求</button></div></div> : null}
    {session ? <div className={styles.actions}><button type="button" disabled={resource.pending} onClick={resource.reload}>读取查询进度</button>{active ? <button type="button" disabled={locked} onClick={() => void act("cancel")}>停止后续检索</button> : data?.task_progress.retryable ? <button type="button" disabled={locked} onClick={() => void act("retry")}>继续原查询</button> : null}</div> : null}
    {session && !data && !resource.error ? <p role="status">正在读取这次检索…</p> : null}
    {data ? <>{originalWork !== workId ? <p className={styles.notice}>这里查回的是此前作品的原查询。结果按各自的作品与版本显示；本次查询结束后可输入新查询检索当前选中作品。</p> : null}<p role="status" className={styles.note}>“{data.query}” · {states[data.status] || "状态待核实"}{data.task_progress.total > 0 ? ` · ${data.task_progress.completed} / ${data.task_progress.total} ${data.task_progress.unit}` : ""}</p>{data.notice ? <p className={styles.notice}>{data.notice}</p> : null}{data.warnings.map((warning, index) => <p className={styles.notice} key={index}>{typeof warning === "string" ? warning : warning.message}</p>)}
    <nav className={styles.queryTabs} aria-label="查询结果类型">{[["passages", "正文匹配"], ["deep", "深度结果"], ["entities", "知识条目"], ["curation", "策展内容"]].map(([id, label]) => <button key={id} type="button" aria-pressed={tab === id} onClick={() => setTab(id)}>{label}（{counts[id as keyof typeof counts]}）</button>)}</nav>
    <div className={styles.queryResults}>{(tab === "passages" || tab === "deep") ? <>{tab === "deep" ? <p className={styles.note}>{data.deep_stage?.notice || data.task_progress.deep.notice || "按既定方案读取本次已返回的深度结果，未返回时保留为空。"}</p> : null}{passageRows.map(item => <article key={item.id}><header><strong>{item.work.title}</strong><span>{item.edition_id === editionId ? "当前所选版本" : item.bibliography?.version_label || "作品的其他版本"}</span></header><blockquote>{item.excerpt}</blockquote><p>{item.printed_page ? `印刷页 ${item.printed_page} · ` : ""}PDF 第 {item.pdf_page} 页{item.section_title ? ` · ${item.section_title}` : ""}</p><div className={styles.matchBasis}>{item.match_basis.map((basis, index) => <span key={index}>{basis}</span>)}</div>{!item.match_basis.length ? <p className={styles.note}>本项未返回额外命中说明。</p> : null}{localHref(item.reader_url) ? <Link href={localHref(item.reader_url)}>对照原文 →</Link> : null}</article>)}{!passageRows.length ? <p className={styles.empty}>{active ? "正在获取原文结果。" : "本次尚未返回正文命中；请结合索引覆盖和来源状态核对，不代表馆藏中没有相关文字。"}</p> : null}</> : tab === "entities" ? <>{data.entities.map(item => <article key={item.id}><strong>{item.title}</strong><p>{item.excerpt}</p><div className={styles.matchBasis}>{item.match_basis.map((basis, index) => <span key={index}>{basis}</span>)}</div>{localHref(item.url) ? <Link href={localHref(item.url)}>查看来源 →</Link> : null}</article>)}{!data.entities.length ? <p className={styles.empty}>本次尚无知识条目结果。</p> : null}</> : <>{data.curation.map(item => <article key={item.id}><strong>{item.source_title}</strong><p>{item.recommendation_excerpt}</p><div className={styles.matchBasis}>{item.match_basis.map((basis, index) => <span key={index}>{basis}</span>)}</div>{localHref(item.url) ? <Link href={localHref(item.url)}>查看策展来源 →</Link> : null}</article>)}{!data.curation.length ? <p className={styles.empty}>本次尚无策展结果。</p> : null}</>}</div>
    {(data.next_cursor || (data.deep_passages?.length || 0) > limit) && limit < 50 ? <button type="button" disabled={locked || resource.loading} onClick={() => setLimit(value => Math.min(50, value + 10))}>显示更多已取得结果</button> : null}<p className={styles.note}>此处最多显示前 50 条已取得原文。<Link href={`/explore/evidence?${new URLSearchParams({q:data.query,work_ids:originalWork})}`}>在完整检索页进一步查询</Link></p><details className={styles.queryIdentity}><summary>本次检索来源与版本</summary><dl className={styles.facts}><div><dt>索引版本</dt><dd>{data.retrieval_identity.index_uid || "尚未取得"}</dd></div><div><dt>检索流程</dt><dd>{data.retrieval_identity.pipeline_version || "未记录"}</dd></div><div><dt>原文与术语</dt><dd>展示实际匹配依据，不据此自动建立学术关系。</dd></div></dl></details></> : null}
  </section>;
}
