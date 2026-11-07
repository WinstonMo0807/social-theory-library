"use client";

import Link from "next/link";
import { ArrowRight, BookOpen } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import type { components } from "@/lib/api/generated/schema";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import styles from "./research-session-list.module.css";
import { LoadingState } from "@/components/ui/loading-state";

type Directory = components["schemas"]["ResearchDirectoryOutput"];
type Project = components["schemas"]["ProjectSummary"];
const path = "/reading/research-projects/directory/";
const date = (value: string) => new Date(value).toLocaleDateString("zh-CN");

export function ResearchSessionList() {
  const { state, retry } = useSessionBootstrap();
  const [epoch, setEpoch] = useState(0);
  useEffect(() => subscribeToSessionChanges(() => setEpoch(value => value + 1)), []);
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace("/login?next=%2Faccount%2Fresearch"); }, [state.status]);
  if (state.status !== "authenticated" || !state.user) return <main className={styles.page}><h1>研究会话</h1><div className={styles.state}>{state.status === "temporary_error" || state.status === "forbidden" ? <><p role="alert">{state.message}</p><button onClick={retry}>重新核对登录</button></> : <LoadingState>正在读取你的研究会话…</LoadingState>}</div></main>;
  return <DirectoryView key={`${state.user.id}:${epoch}`} owner={String(state.user.id)} />;
}

function DirectoryView({ owner }: { owner: string }) {
  const [page, setPage] = useState(1), [scope, setScope] = useState("active"), [expanded, setExpanded] = useState(false);
  const load = useCallback(async (url: string, signal: AbortSignal) => {
    const value = await apiRequest<Directory>(url, { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), headers: { "X-Reader-Owner": owner } }, getServerSessionCredential(), false);
    if (value.owner_id !== owner) throw Error("账户已变化，请重新读取本人的研究会话。");
    return value;
  }, [owner]);
  const resource = usePersistentWorkspace<Directory>(`${path}?page=${page}&scope=${scope}`, owner,
    data => data.results.some(row => row.status === "running" || row.status === "queued") ? 5000 : null, load);
  const refresh = resource.reload, lastFocus = useRef(0);
  useEffect(() => {
    const update = () => { if (document.visibilityState === "visible" && Date.now() - lastFocus.current > 30000) { lastFocus.current = Date.now(); refresh(); } };
    window.addEventListener("focus", update); window.addEventListener("pageshow", update); document.addEventListener("visibilitychange", update);
    return () => { window.removeEventListener("focus", update); window.removeEventListener("pageshow", update); document.removeEventListener("visibilitychange", update); };
  }, [refresh]);
  const data = resource.error ? null : resource.data, first = data?.results[0];
  return <main className={styles.page}><div className={styles.main}><nav className={styles.crumb} aria-label="面包屑"><Link href="/home">首页</Link><span>/</span><Link href="/account">读者中心</Link></nav><header className={styles.heading}><h1>研究会话</h1><p>只显示你自己的阅读和研究内容。</p></header><section className={styles.panel} data-expanded={expanded || !first} aria-label="最近研究"><div className={styles.readerNav}><h2>读者中心</h2><nav aria-label="读者中心">{[["/account","概览"],["/account?section=history","继续阅读"],["/account/notes","笔记与批注"],["/account/research","研究会话"],["/account/plans","阅读计划"],["/account/citation-audits","引文校验"]].map(([href,label])=><Link key={href} href={href} aria-current={label==="研究会话"?"page":undefined}>{label}</Link>)}</nav></div>
    {resource.error ? <div className={styles.state} role="alert"><h2>研究会话暂时不可用</h2><p>{resource.error}</p><button onClick={() => { setPage(1); refresh(); }}>重新读取</button></div> : !data ? <LoadingState>正在读取你的研究会话…</LoadingState> : <>
      {first ? <div className={styles.mobile}><dl><dt>最近阅读</dt><dd>{data.recent_reading ? <Link href={data.recent_reading.reader_url}>{data.recent_reading.title}</Link> : "暂无可继续阅读的记录"}</dd>{data.recent_reading ? <><dt>进度</dt><dd>第 {data.recent_reading.current_page} 页{data.recent_reading.page_count ? ` / ${data.recent_reading.page_count} 页` : ""}</dd></> : null}<dt>最近研究</dt><dd>{first.title}</dd><dt>状态</dt><dd>{first.status_label}</dd><dt>下一步</dt><dd><Link href={`/account/research/${first.id}`}>查看研究 →</Link></dd></dl><Link className={styles.open} href={`/account/research/${first.id}`}>打开</Link><button onClick={() => { if (expanded) { setPage(1); setScope("active"); } setExpanded(value => !value); }}>{expanded ? "返回最近研究" : `查看研究列表（${data.count}）`}</button></div> : null}
      <header className={styles.sectionTitle}><h2>{scope === "archived" ? "归档研究" : "最近研究"}</h2><Link href="/explore/opinions">开始新的研究 <ArrowRight size={14} /></Link></header><div className={styles.controls}><span>{data.count} 个会话</span><label>范围 <select value={scope} onChange={event => { setScope(event.target.value); setPage(1); setExpanded(true); }}><option value="active">当前研究</option><option value="archived">已归档</option><option value="all">全部研究</option></select></label><button onClick={refresh}>刷新</button></div>
      {data.results.length ? <div className={styles.cards}>{data.results.map(row => <ProjectCard key={row.id} row={row} />)}</div> : <div className={styles.state}><BookOpen size={28} /><h2>{scope === "archived" ? "还没有归档研究" : "还没有研究会话"}</h2><p>研究会话来自你实际保存的问题和材料。</p><Link href="/explore/opinions">从一个研究问题开始 →</Link></div>}
      <nav className={styles.pager} aria-label="研究分页"><span>第 {page} / {data.total_pages} 页</span><button disabled={page <= 1} onClick={() => setPage(value => value - 1)}>上一页</button><button disabled={page >= data.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav>
    </>}
  </section></div></main>;
}

function ProjectCard({ row }: { row: Project }) {
  return <article className={styles.card}><div><h3>{row.title}</h3>{row.question && row.question !== row.title ? <p>{row.question}</p> : null}<time dateTime={row.activity_at}>{date(row.activity_at)}</time></div><span className={styles.status} data-status={row.status}>{row.status_label}</span><Link href={`/account/research/${row.id}`}>查看 <ArrowRight size={14} /><span className="sr-only">{row.title}</span></Link></article>;
}
