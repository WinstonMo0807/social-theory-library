"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, BookOpen, Check, ChevronDown, ChevronLeft, ChevronRight, CircleAlert, Clock3, FileText, Info, Layers, Search, UserRound, X } from "lucide-react";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { loadOpinionScope, loadSearchRecords, opinionResultHref, scopeFilterKeys, scopeKeys, type OpinionScope, type ScopeOption, type ScopePage, type SearchRecordsPage } from "@/lib/api/opinion-entry.client";
import type { DiscoveryFilters } from "@/lib/api/discovery.types";
import { Dialog } from "./ui/dialog";
import styles from "./opinion-search-entry.module.css";

const scopes = [
  { key: "all", title: "全部文献", detail: "在本馆所有收录文献中检索", icon: BookOpen },
  { key: "topic", title: "特定主题", detail: "限定在指定主题的相关文献", icon: FileText },
  { key: "scholar", title: "特定学者", detail: "限定在指定学者的文献", icon: UserRound },
  { key: "work", title: "特定文献", detail: "仅在指定的文献或书目中检索", icon: Layers },
] as const;
const exampleQuestions = ["算法如何影响社会分层？", "平台经济是否创造了新的劳动形式？", "技术进步会带来更大的社会公平吗？"];
const initialScope = (filters: DiscoveryFilters): OpinionScope => (["work", "scholar", "topic"] as const).find(kind => scopeKeys[kind].some(key => filters[key]?.length)) || "all";

export function OpinionSearchEntry({ initialFilters = {} }: { initialFilters?: DiscoveryFilters }) {
  const router = useRouter(), field = useRef<HTMLTextAreaElement>(null);
  const [query, setQuery] = useState(""), [scope, setScope] = useState<OpinionScope>(() => initialScope(initialFilters));
  const [selected, setSelected] = useState<ScopeOption[]>([]), [picker, setPicker] = useState(false);
  const [inherited, setInherited] = useState<DiscoveryFilters>(() => Object.fromEntries(Object.entries(initialFilters).filter(([key]) => scopeFilterKeys.includes(key))));
  const [draftScope, setDraftScope] = useState<OpinionScope>("all"), [draftSelected, setDraftSelected] = useState<ScopeOption[]>([]);
  const [message, setMessage] = useState(""), [pending, setPending] = useState(false);
  const inheritedGroups = scopes.filter(item => item.key !== "all" && scopeKeys[item.key].some(key => inherited[key]?.length));
  const hasInheritedScope = inheritedGroups.some(item => item.key === scope);
  const ready = query.trim().length >= 2 && query.length <= 500 && (scope === "all" || selected.length > 0 || hasInheritedScope);
  const title = scopes.find(row => row.key === scope)!.title;
  const extras = Object.fromEntries(Object.entries(initialFilters).filter(([key]) => !scopeFilterKeys.includes(key)));
  const currentScopes: DiscoveryFilters = { ...inherited };
  if (scope !== "all" && selected.length) currentScopes[scope === "work" ? "work_id" : scope] = selected.map(row => row.id);
  function openPicker(next = scope) { setDraftScope(next); setDraftSelected(next === scope ? selected : []); setPicker(true); }
  function chooseScope(next: OpinionScope) {
    if (next === "all") { setScope(next); setSelected([]); setInherited({}); setMessage(""); }
    else openPicker(next);
  }
  function confirmScope() {
    if (draftScope !== "all" && !draftSelected.length) return;
    setInherited(draftScope === "all" ? {} : Object.fromEntries(Object.entries(currentScopes).filter(([key]) => !scopeKeys[draftScope].includes(key))));
    setScope(draftScope); setSelected(draftScope === "all" ? [] : draftSelected); setPicker(false); setMessage("");
  }
  function submit(event: FormEvent) {
    event.preventDefault(); if (pending) return;
    if (!ready) { setMessage(query.trim().length < 2 ? "请输入至少两个字符的问题。" : "请先选择有效检索范围以继续搜索。"); return; }
    const filters: DiscoveryFilters = { ...extras, ...currentScopes };
    setPending(true); setMessage("");
    try { router.push(opinionResultHref(query.trim(), filters)); }
    catch { setPending(false); setMessage("暂时无法进入检索结果。问题与范围已保留，请重试。"); }
  }
  return <div className={styles.page}>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/">首页</Link><ChevronRight size={12} /><Link href="/explore">探索</Link><ChevronRight size={12} /><span>观点检索</span></nav>
    <header className={styles.header}><h1>观点检索：问题起点</h1><p>用你自己的话提出问题，发现来自经典文献的思想、论证与不同视角。</p></header>
    <form className={styles.queryForm} onSubmit={submit} action="/explore/evidence">
      <div className={styles.queryBox}><label className="sr-only" htmlFor="opinion-question">你的研究问题</label><textarea ref={field} id="opinion-question" name="q" value={query} onChange={event => { setQuery(event.target.value); setMessage(""); }} maxLength={500} rows={1} placeholder="请输入你的问题…" aria-describedby="opinion-count" />
        {query ? <button type="button" className={styles.clear} aria-label="清除问题" onClick={() => { setQuery(""); field.current?.focus(); }}><X size={15} /></button> : null}<span className={styles.counter} id="opinion-count" aria-live="polite">{query.length}/500</span></div>
      <button type="submit" className={styles.searchButton} disabled={!ready || pending}><Search size={22} />{pending ? "正在进入检索…" : "检索原文"}</button>
    </form>
    {message ? <p className={styles.alert} role="alert"><CircleAlert size={18} />{message}</p> : null}
    {scope !== "all" && selected.length === 0 && !hasInheritedScope ? <p className={styles.alert} role="status"><CircleAlert size={18} />请先选择当前公开的{title.replace("特定", "")}，核对范围后再检索。</p> : null}
    <section className={styles.scopeSection} aria-labelledby="opinion-scope-title"><h2 id="opinion-scope-title">选择检索范围 <Info size={16} aria-label="范围用于原文检索；知识与策展按问题提供线索" /></h2>
      <div className={styles.scopeCards} role="radiogroup" aria-label="检索范围">{scopes.map((item, index) => <button type="button" role="radio" aria-checked={scope === item.key} tabIndex={scope === item.key ? 0 : -1} key={item.key} onClick={() => chooseScope(item.key)} onKeyDown={event => {
        const delta = ["ArrowRight", "ArrowDown"].includes(event.key) ? 1 : ["ArrowLeft", "ArrowUp"].includes(event.key) ? -1 : 0;
        if (!delta) return;
        event.preventDefault(); const next = (index + delta + scopes.length) % scopes.length;
        event.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus(); chooseScope(scopes[next].key);
      }} className={scope === item.key ? styles.selected : ""}><span className={styles.radio} /><item.icon size={27} /><span><strong>{item.title}</strong><small>{item.detail}</small></span></button>)}</div>
      <button type="button" className={styles.mobileScope} onClick={() => openPicker()}><span>{title}{selected.length ? ` · ${selected.length} 项` : ""}</span><ChevronDown size={16} /></button>
      {selected.length ? <div className={styles.chips}>{selected.map(row => <button key={row.id} type="button" onClick={() => setSelected(current => current.filter(item => item.id !== row.id))} aria-label={`移除范围：${row.title}`}>{row.title}<X size={13} /></button>)}<button type="button" onClick={() => openPicker()}>修改范围</button></div> : null}
      {inheritedGroups.length ? <div className={styles.inherited}><p>保留入口指定的范围，检索时按当前公开资料核对。修改一种范围会保留其他限制。</p><div className={styles.chips}>{inheritedGroups.map(item => <button type="button" key={item.key} onClick={() => openPicker(item.key)}>已限定{item.title.replace("特定", "")} · 修改</button>)}</div></div> : null}
      {Object.keys(extras).length ? <p className={styles.quiet}>本次还保留了入口附带的 {Object.keys(extras).length} 组筛选条件，结果页可继续调整。</p> : null}
    </section>
    <section className={styles.examples} aria-labelledby="opinion-examples-title"><header><h2 id="opinion-examples-title">试试这些问题</h2><p>你可以直接使用以下示例，或修改后检索。</p></header><div>{exampleQuestions.map(example => <button type="button" key={example} onClick={() => { setQuery(example); setMessage(""); field.current?.focus(); }}><Search size={17} /><span>{example}</span><ArrowRight size={17} /></button>)}</div></section>
    <RecentResearch />
    <Dialog open={picker} onRequestClose={() => setPicker(false)} className={styles.scopeDialog} aria-labelledby="scope-dialog-title"><header><h2 id="scope-dialog-title">选择检索范围</h2><button type="button" aria-label="关闭范围选择" onClick={() => setPicker(false)}><X size={20} /></button></header>
      <div className={styles.dialogScopes}>{scopes.map(item => <label key={item.key}><item.icon size={22} /><span><strong>{item.title}</strong><small>{item.detail}</small></span><input type="radio" name="scope-choice" value={item.key} checked={draftScope === item.key} onChange={() => { setDraftScope(item.key); setDraftSelected(item.key === scope ? selected : []); }} /></label>)}</div>
      {draftScope !== "all" ? <ScopePicker key={draftScope} kind={draftScope} selected={draftSelected} onChange={setDraftSelected} /> : null}
      <footer><button type="button" onClick={() => setPicker(false)}>取消</button><button type="button" disabled={draftScope !== "all" && !draftSelected.length} onClick={confirmScope}><Check size={16} />确认范围{draftSelected.length && draftScope !== "all" ? `（${draftSelected.length}）` : ""}</button></footer>
    </Dialog>
  </div>;
}

function ScopePicker({ kind, selected, onChange }: { kind: Exclude<OpinionScope, "all">; selected: ScopeOption[]; onChange: (rows: ScopeOption[]) => void }) {
  const [input, setInput] = useState(""), [query, setQuery] = useState(""), [page, setPage] = useState(1), [attempt, setAttempt] = useState(0);
  const [snapshot, setSnapshot] = useState<{ key: string; data?: ScopePage; error?: string } | null>(null);
  const key = `${kind}:${query}:${page}:${attempt}`, current = snapshot?.key === key ? snapshot : null;
  useEffect(() => {
    const request = new AbortController();
    void loadOpinionScope(kind, query, page, request.signal).then(data => { if (!request.signal.aborted) setSnapshot({ key, data }); })
      .catch(error => { if (!request.signal.aborted) setSnapshot({ key, error: error instanceof Error ? error.message : "当前无法读取公开选项。" }); });
    return () => request.abort();
  }, [kind, query, page, key]);
  return <section className={styles.picker} aria-label="选择公开条目"><form onSubmit={event => { event.preventDefault(); setQuery(input.trim()); setPage(1); setAttempt(value => value + 1); }}><label className="sr-only" htmlFor="scope-search">查找公开条目</label><input id="scope-search" value={input} onChange={event => setInput(event.target.value)} maxLength={160} placeholder={`查找${scopes.find(row => row.key === kind)!.title.replace("特定", "")}`} /><button type="submit"><Search size={16} />查找</button></form>
    <p className={styles.quiet}>已选 {selected.length} 项，最多30项。仅显示当前公开资料。</p>
    {!current ? <p role="status">正在读取公开选项…</p> : current.error ? <p role="alert">{current.error}<button onClick={() => setAttempt(value => value + 1)}>重新读取</button></p> : !current.data?.results.length ? <p>当前没有符合条件的公开条目。可以调整关键词，或返回全部文献。</p> : <div className={styles.options}>{current.data.results.map(row => <label key={row.id}><input type="checkbox" checked={selected.some(item => item.id === row.id)} disabled={selected.length >= 30 && !selected.some(item => item.id === row.id)} onChange={event => onChange(event.target.checked ? [...selected, row] : selected.filter(item => item.id !== row.id))} /><span><strong>{row.title}</strong>{row.subtitle ? <small>{row.subtitle}</small> : null}</span></label>)}</div>}
    {current?.data && current.data.total_pages > 1 ? <nav className={styles.pagination} aria-label="范围选项分页"><button type="button" disabled={page === 1} onClick={() => setPage(value => value - 1)}>上一页</button><span>{page} / {current.data.total_pages}</span><button type="button" disabled={page === current.data.total_pages} onClick={() => setPage(value => value + 1)}>下一页</button></nav> : null}
  </section>;
}

function RecentResearch() {
  const { state: session, retry } = useSessionBootstrap();
  const owner = session.status === "authenticated" && session.user ? String(session.user.id) : null;
  const history = usePersistentWorkspace<SearchRecordsPage>(`/reading/search-records/?page_size=3&owner_id=${encodeURIComponent(owner || "")}`, owner, undefined, loadSearchRecords);
  const [expanded, setExpanded] = useState(false);
  return <section className={styles.history} aria-labelledby="recent-research-title"><header><h2 id="recent-research-title"><Clock3 size={22} />我最近的研究</h2><p>仅在主动开启保存后，记录到本人账户。</p>{history.data?.count ? <button type="button" onClick={() => setExpanded(true)}>查看全部<ArrowRight size={15} /></button> : null}</header>
    {session.status === "unauthenticated" ? <div className={styles.guest}><Info size={19} /><div><strong>登录后可保存检索记录</strong><p>你正在以访客身份使用。本次检索不会保留到个人历史记录中。</p><Link href="/login?next=%2Faccount%2Fsettings%2Fprivacy">登录并管理保存设置</Link></div></div> : !owner ? <p role="status">{session.message || "正在核对登录状态…"}{session.status !== "loading" ? <button type="button" onClick={retry}>重新验证</button> : null}</p> : <>
      {history.loading ? <p role="status">正在读取本人记录…</p> : null}{history.error ? <p role="alert">{history.error}<button type="button" onClick={history.reload}>重新读取</button></p> : null}
      {history.data ? <>{!history.data.recording_enabled ? <p className={styles.privacyNotice}>搜索记录保存当前关闭。<Link href="/account/settings/privacy">管理隐私设置</Link></p> : null}<HistoryRows rows={history.data.results} />{!history.data.results.length ? <p className={styles.empty}>暂无已保存的研究检索。</p> : null}</> : null}
    </>}
    {expanded && owner && history.data ? <SearchHistory key={owner} ownerId={owner} onClose={() => setExpanded(false)} /> : null}
  </section>;
}

function HistoryRows({ rows }: { rows: SearchRecordsPage["results"] }) {
  return <ol className={styles.historyRows}>{rows.map(row => <li key={row.id}><Link href={opinionResultHref(row.query, row.filters)}><Clock3 size={16} /><span>{row.query}</span><time dateTime={row.created_at}>{new Date(row.created_at).toLocaleDateString("zh-CN")}</time><ChevronRight size={15} /></Link></li>)}</ol>;
}

function SearchHistory({ ownerId, onClose }: { ownerId: string; onClose: () => void }) {
  const [page, setPage] = useState(1);
  const history = usePersistentWorkspace<SearchRecordsPage>(`/reading/search-records/?page_size=20&page=${page}&owner_id=${encodeURIComponent(ownerId)}`, ownerId, undefined, loadSearchRecords);
  return <Dialog open onRequestClose={onClose} className={styles.historyDialog} aria-labelledby="search-history-title"><header><h2 id="search-history-title">我的研究检索记录</h2><button aria-label="关闭检索历史" onClick={onClose}><X size={20} /></button></header>
    <p className={styles.quiet}>点击记录会按当前公开内容重新检索，不恢复过期结果。</p>
    {history.error ? <p role="alert">{history.error}<button onClick={history.reload}>重新读取</button></p> : null}{history.loading ? <p role="status">正在读取…</p> : null}
    {history.data ? <><HistoryRows rows={history.data.results} /><nav className={styles.pagination} aria-label="研究检索记录分页"><button disabled={page === 1} onClick={() => setPage(value => value - 1)}><ChevronLeft size={14} />上一页</button><span>第 {page} 页</span><button disabled={page * history.data.page_size >= history.data.count} onClick={() => setPage(value => value + 1)}>下一页<ChevronRight size={14} /></button></nav></> : null}
    <footer><Link href="/account/settings/privacy">管理保存与删除</Link><button onClick={onClose}>关闭</button></footer>
  </Dialog>;
}
