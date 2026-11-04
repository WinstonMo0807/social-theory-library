"use client";

import { writeClipboardText } from "@/lib/clipboard";
import { createRequestKey } from "../../lib/request-key";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDown, ArrowUp, BookOpen, Download, List, LockKeyhole, MoreHorizontal, Plus, RotateCcw, Search, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode, type RefObject } from "react";
import { ApiRequestError, apiRequest, getServerSessionCredential, subscribeToSessionChanges } from "@/lib/api";
import { withPrivateOwner } from "@/lib/api/private-owner";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { booklistRequest, downloadBooklist, type BooklistCommand, type BooklistDirectory, type BooklistResult, type BooklistSummary, type BooklistWorkspace } from "@/lib/api/booklists.client";
import type { ApiWork } from "@/lib/api/public-catalog";
import { useSessionBootstrap } from "@/lib/use-session-bootstrap";
import { adaptApiWork } from "@/lib/public-data-adapters";
import { BookCover } from "@/components/ui";
import { Dialog } from "@/components/ui/dialog";
import { BooklistTopicPicker } from "./booklist-topic-picker";
import { BooklistPlanForm } from "./booklist-plan-form";
import { BooklistLinkedPanel, BooklistPublicSidebar } from "./booklist-related";
import { ResearchCenterNav } from "./research-center-nav";
import { ReaderMobileNav } from "./reader-mobile-nav";
import styles from "./reader-booklists.module.css";

const stamp = (value: string) => new Date(value).toLocaleDateString("zh-CN");
type Recovery = Pick<BooklistCommand, "list_id" | "request_id">;

export function ReaderBooklists({ id }: { id?: string }) {
  const { state, retry } = useSessionBootstrap();
  const next = `/account/collections${id ? `/${id}` : ""}`;
  useEffect(() => {
    if (!id && /^#list-[\da-f-]{36}$/i.test(window.location.hash)) window.location.replace(`/account/collections/${window.location.hash.slice(6)}`);
  }, [id]);
  useEffect(() => { if (state.status === "unauthenticated") window.location.replace(`/login?next=${encodeURIComponent(next)}`); }, [state.status, next]);
  if (state.status === "temporary_error" || state.status === "forbidden") return <Frame><div className={styles.empty} role="alert"><h1>书单暂时无法读取</h1><p>{state.message}</p><button onClick={retry}>重新核对登录</button></div></Frame>;
  if (state.status !== "authenticated" || !state.user) return <Frame><p role="status">正在核对登录状态…</p></Frame>;
  return <BooklistsWorkspace key={`${state.user.id}:${id || "index"}`} owner={String(state.user.id)} name={state.user.display_name || "读者"} id={id} />;
}

function Frame({ children }: { children: ReactNode }) { return <main className={styles.page}>{children}</main>; }

function BooklistsWorkspace({ owner, name, id }: { owner: string; name: string; id?: string }) {
  const router = useRouter();
  const search = useSearchParams();
  const [view, setView] = useState<"works" | "plans" | "notes" | "related">(() => {
    const tab = search?.get("tab"); return tab === "plans" || tab === "notes" || tab === "related" ? tab : "works";
  });
  function show(value: "works" | "plans" | "notes" | "related") {
    setView(value); setSelected([]); setTrash(false); setPage(1);
    if (value !== "works") setTable(false);
    const url = new URL(window.location.href); url.searchParams.set("tab", value); window.history.replaceState(null, "", url);
  }
  const [table, setTable] = useState(view === "works");
  const [page, setPage] = useState(1), [q, setQ] = useState(""), [kind, setKind] = useState(""), [order, setOrder] = useState("manual"), [trash, setTrash] = useState(false);
  const [selected, setSelected] = useState<string[]>([]), [modal, setModal] = useState<"edit" | "create" | "add" | "export" | "delete" | "remove" | "purge" | "plan" | "topics" | null>(null);
  const [message, setMessage] = useState(""), [busy, setBusy] = useState(false), [recovery, setRecovery] = useState<Recovery | null>(null), [broken, setBroken] = useState(false);
  const [canRetry, setCanRetry] = useState(false);
  const [editing, setEditing] = useState<BooklistSummary | undefined>();
  const [planSource, setPlanSource] = useState<{ row: BooklistSummary; selected: string[] } | null>(null);
  const pending = useRef<BooklistCommand | null>(null), sending = useRef(false), controller = useRef<AbortController | null>(null);
  const storageKey = `stl-booklist-request:${owner}`;
  const query = new URLSearchParams({ page: String(page), q, kind, order, trash: String(trash) }).toString();
  const load = useCallback((path: string, signal: AbortSignal) => booklistRequest<BooklistWorkspace | BooklistDirectory>(owner, path, { signal }), [owner]);
  const resource = usePersistentWorkspace<BooklistWorkspace | BooklistDirectory>(id ? `/reading/lists/${id}/workspace/?${query}` : `/reading/lists/directory/?${query}`, owner, undefined, load);
  const data = resource.error ? null : resource.data;
  const detail = data && "list" in data ? data : null;
  const directory = data && "results" in data ? data : null;
  const blocked = busy || Boolean(recovery) || broken;
  useEffect(() => {
    const request = new AbortController(); controller.current = request;
    const off = subscribeToSessionChanges(() => request.abort());
    queueMicrotask(() => {
      if (request.signal.aborted) return;
      try {
        const raw = sessionStorage.getItem(storageKey);
        if (!raw) return;
        const value = JSON.parse(raw) as Recovery;
        if (!value || !/^[\da-f-]{36}$/i.test(value.list_id) || !/^[\da-f-]{36}$/i.test(value.request_id)) throw Error("原请求记录无法读取，请先核对服务端书单。 ");
        setRecovery(value); setMessage("上次操作尚未取得明确操作结果，请先核对原结果。");
      } catch (reason) { setBroken(true); setMessage(reason instanceof Error ? reason.message : "恢复信息不可用。"); }
    });
    return () => { request.abort(); off(); };
  }, [storageKey]);
  useEffect(() => {
    if (!recovery) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn);
  }, [recovery]);
  function clear() { sessionStorage.removeItem(storageKey); setRecovery(null); pending.current = null; setCanRetry(false); setBroken(false); }
  function filter(change: () => void) { setPage(1); setSelected([]); change(); }
  function edit() { if (detail) { setEditing(detail.list); setModal("edit"); } }
  function plan() { if (detail) { setPlanSource({ row: detail.list, selected: [...selected] }); setModal("plan"); } }
  async function execute(values?: Omit<BooklistCommand, "list_id" | "request_id" | "expected_version">, lookup = false) {
    if (sending.current || !controller.current || controller.current.signal.aborted || broken) return;
    const original = pending.current || (values ? { ...values, list_id: id || createRequestKey(), request_id: createRequestKey(), expected_version: (values.action === "edit" ? editing?.version : detail?.list.version) || "0" } : null);
    const identity = lookup ? recovery : original;
    if (!identity) return;
    sending.current = true; setBusy(true); setMessage("");
    const signal = AbortSignal.any([controller.current.signal, AbortSignal.timeout(30000)]);
    try {
      sessionStorage.setItem(storageKey, JSON.stringify({ list_id: identity.list_id, request_id: identity.request_id }));
      setRecovery(identity); if (original && !lookup) { pending.current = original; setCanRetry(true); }
      const result = await withPrivateOwner(owner, () => booklistRequest<BooklistResult>(owner,
        lookup ? `/reading/lists/receipt/?${new URLSearchParams({ list_id: identity.list_id, request_id: identity.request_id })}` : "/reading/lists/command/",
        { signal, ...(lookup ? {} : { method: "POST", body: JSON.stringify(original) }) }), signal);
      if (result.owner_id !== owner || result.id !== identity.list_id || result.receipt.request_id !== identity.request_id) throw Error("操作结果与原操作不符，请先核对原结果。");
      clear(); setModal(null); setSelected([]); resource.reload();
      setMessage(result.exists ? "书单操作已保存。" : "书单已删除，馆藏、阅读进度和独立笔记仍保留。");
      if (!result.exists && id) router.push("/account/collections");
      else if (!id && result.exists) router.push(`/account/collections/${result.id}`);
    } catch (reason) {
      if (controller.current.signal.aborted) return;
      if (!lookup && reason instanceof ApiRequestError && [400, 403, 404, 409].includes(reason.status)) { clear(); resource.reload(); }
      setMessage(reason instanceof Error ? reason.message : "操作结果暂未确认，请核对原操作结果。");
    } finally { sending.current = false; if (!controller.current.signal.aborted) setBusy(false); }
  }
  function removeTopic(topic_id: string) { if (!blocked && window.confirm("只移除本书单的主动关联，主题与馆藏正式关系保留。是否继续？")) void execute({ action: "topic_remove", topic_id }); }
  const toggle = (value: string) => setSelected(current => current.includes(value) ? current.filter(item => item !== value) : [...current, value]);
  return <Frame>
    <nav className={styles.breadcrumb} aria-label="面包屑"><Link href="/">首页</Link><span>›</span><Link href="/account">读者中心</Link><span>›</span><Link href="/account/collections">我的书单</Link>{detail ? <><span>›</span><span>{detail.list.title}</span></> : null}</nav>
    <header className={styles.heading}><div><h1>{detail?.list.title || (id ? "书单与材料集合" : "我的书单")}</h1><span className={styles.private}><LockKeyhole size={14} />私人 · 仅自己可见</span>{detail ? <p>{detail.list.description || "尚未填写书单说明。"}</p> : null}<small>{name}{detail ? ` · 创建于 ${stamp(detail.list.created_at)} · ${detail.active_count} 部作品` : ""}</small></div><div className={styles.actions}>{id ? <><button className={styles.primary} disabled={!detail || blocked || trash || !detail.active_count} onClick={plan}><BookOpen size={15} />开始阅读计划</button><button disabled={!detail || blocked || trash} onClick={() => setModal("export")}><Download size={15} />导出</button><Link href={`/account/sharing/new?kind=booklist&source=${id}`}>分享</Link><details className={styles.moreMenu}><summary aria-label="更多书单操作"><MoreHorizontal size={20}/></summary><div><button disabled={!detail || blocked} onClick={edit}>编辑书单</button><button onClick={() => setTable(value=>!value)}>{table?"查看目标与关联资料":"显示作品表格"}</button><Link href={`/account/sharing/new?kind=booklist&source=${id}`}>提交策划</Link></div></details></> : <button className={styles.primary} disabled={blocked} onClick={() => setModal("create")}><Plus size={15} />创建书单</button>}</div></header>
    {!id ? <ResearchCenterNav active="lists" /> : null}
    {message ? <div role="status" className={styles.notice}>{message}</div> : null}
    {recovery || broken ? <div className={styles.notice}><p>为避免重复写入，先处理上次操作。</p>{recovery ? <button disabled={busy || broken} onClick={() => void execute(undefined, true)}>核对原结果</button> : null}{canRetry ? <button disabled={busy || broken} onClick={() => void execute()}>重试原请求</button> : null}<Link href="/account/collections" target="_blank" rel="noopener">在新页面核对书单</Link><button disabled={busy} onClick={() => { if (window.confirm("确认已经核对服务端书单？清除这里只移除本机请求记录，不撤销已经保存的操作。")) { clear(); resource.reload(); } }}>核对后清除本机记录</button></div> : null}
    {resource.error ? <div role="alert" className={styles.empty}><h2>暂时无法读取书单</h2><p>{resource.error}</p><button onClick={() => { setPage(1); resource.reload(); }}>重新读取</button></div> : !data ? <div className={styles.empty} role="status">正在读取书单…</div> : <div className={id ? styles.columns : undefined} data-layout={table ? "table" : "detailed"}><section>
      {detail && !table ? <nav className={styles.sectionNav} aria-label="书单内容"><button aria-pressed={view === "works"} disabled={blocked} onClick={() => show("works")}>书单作品 {detail.active_count}</button><button aria-pressed={view === "plans"} disabled={blocked} onClick={() => show("plans")}>阅读计划</button><button aria-pressed={view === "notes"} disabled={blocked} onClick={() => show("notes")}>笔记</button><button aria-pressed={view === "related"} disabled={blocked} onClick={() => show("related")}>相关推荐</button></nav> : null}
      {!detail || table || view === "works" ? <>
      <div className={styles.toolbar}>{id ? <><div className={styles.typeTabs}>{[["", "全部"],["book","图书"],["journal_article","论文"],["chapter","章节"]].map(([value,label])=><button key={value} aria-pressed={!trash&&kind===value} disabled={blocked} onClick={()=>filter(()=>{setKind(value);setTrash(false);})}>{label} {value ? detail?.kind_counts?.[value] ?? "" : detail?.active_count}</button>)}</div><details className={styles.moreMenu}><summary>更多</summary><div><button aria-pressed={!trash} disabled={blocked} onClick={() => filter(() => setTrash(false))}>作品 {detail?.active_count}</button><button aria-pressed={trash} disabled={blocked} onClick={() => filter(() => setTrash(true))}>回收站 {detail?.trash_count}</button></div></details></> : null}<form onKeyDown={event => { if (event.key === "Enter" && event.nativeEvent.isComposing) event.preventDefault(); }} onSubmit={event => { event.preventDefault(); const form = new FormData(event.currentTarget); filter(() => setQ(String(form.get("q") || ""))); }}><Search size={15} /><input type="search" name="q" aria-label={id ? "在本书单中搜索题名" : "搜索我的书单"} placeholder={id ? "在本书单中搜索…" : "搜索我的书单…"} maxLength={180} disabled={blocked} /><button disabled={blocked} type="submit">搜索</button></form>{detail?<button className={styles.layoutToggle} aria-label={table?"查看带目标与关联的详细布局":"查看作品表格"} aria-pressed={table} onClick={()=>setTable(value=>!value)}><List size={17}/></button>:null}{id && !trash ? <button disabled={blocked} className={styles.primary} onClick={() => setModal("add")}><Plus size={14} />添加作品</button> : null}</div>
      {detail ? <><div className={styles.filters}><select aria-label="作品类型" value={kind} disabled={blocked} onChange={event => filter(() => setKind(event.target.value))}><option value="">全部类型</option><option value="book">图书</option><option value="journal_article">论文</option><option value="journal_issue">整期期刊</option><option value="thesis">学位论文</option><option value="report">报告</option><option value="chapter">章节</option><option value="other">其他资料</option></select><select aria-label="排序方式" value={order} disabled={blocked} onChange={event => filter(() => setOrder(event.target.value))}><option value="manual">自定义顺序</option><option value="newest">加入时间（新 → 旧）</option><option value="oldest">加入时间（旧 → 新）</option><option value="title">按书名（A → Z）</option><option value="author">按作者（A → Z）</option></select><label><input type="checkbox" disabled={blocked || !detail.items.length} checked={detail.items.length > 0 && detail.items.every(row => selected.includes(row.id))} onChange={event => setSelected(event.target.checked ? detail.items.map(row => row.id) : [])} />本页全选</label><span>已选 {selected.length} 项</span>{selected.length ? trash ? <><button disabled={blocked} onClick={() => void execute({ action: "restore", item_ids: selected })}><RotateCcw size={14} />恢复</button><button disabled={blocked} onClick={() => setModal("purge")}>彻底移除</button></> : <button disabled={blocked} onClick={() => setModal("remove")}><Trash2 size={14} />移除</button> : null}</div>
        {order === "title" || order === "author" ? <p className={styles.hint}>按当前公开版题名或首位作者排序，中文使用拼音、其他文字使用转写；同名以固定编号保持顺序。缺失信息置后，自定义顺序保留。</p> : null}
        {kind === "chapter" ? <p className={styles.hint}>这里列出已独立编目的章节作品。书内目录仍在原文阅读器中。</p> : null}
        {trash ? <p className={styles.hint}>移除后保留30天。到期后不可恢复，后台定时清理书单关联；馆藏与独立笔记保留。</p> : null}
        {detail.items.length ? <div className={styles.rows}>{table?<div className={styles.tableHeader}><span/><span>#</span><span>作品信息</span><span>版本／来源</span><span>加入时间</span><span>状态与操作</span></div>:null}{detail.items.map((item, index) => {
          const work = item.work ? adaptApiWork(item.work) : null;
          const ratio = item.progress_ratio === null ? null : Math.max(0, Math.min(100, Math.round(item.progress_ratio * 100)));
          return <article key={item.id} className={selected.includes(item.id) ? styles.selected : undefined}><label><input type="checkbox" aria-label={`选择${work?.title || "来源暂不可用的作品"}`} checked={selected.includes(item.id)} disabled={blocked} onChange={() => toggle(item.id)} /></label><span className={styles.ordinal}>{(page - 1) * 20 + index + 1}</span>{work ? <BookCover work={work} /> : <div className={styles.missingCover}><BookOpen size={24} /></div>}<div className={styles.copy}><h2>{work ? <Link href={`/works/${work.slug}`}>{work.title}</Link> : "来源暂不可用"}</h2><p>{work ? `${work.author} · ${work.year}` : "这部作品当前未公开，书单中的关联仍保留。"}</p>{work?.version?.publisher ? <small>{work.version.publisher}</small> : null}<small>加入于 {stamp(item.created_at)}</small>{item.expires_at ? <small>恢复截止 {stamp(item.expires_at)}</small> : null}</div><div className={styles.versionInfo}>{work ? <><span>{work.year}{work.version?.publisher?` · ${work.version.publisher}`:""}</span><small>{work.version?.isbn13||work.version?.isbn||work.version?.isbn10?`ISBN ${work.version?.isbn13||work.version?.isbn||work.version?.isbn10}`:work.kind}</small></>:<span>来源当前不可用</span>}</div><time className={styles.addedDate} dateTime={item.created_at}>{stamp(item.created_at)}</time><div className={styles.rowActions}>{!trash ? <><span data-state={ratio===null?"unknown":ratio>=100?"complete":ratio>0?"reading":"unread"}>{ratio === null ? "未记录进度" : ratio>=100?"已读":ratio>0?`已读 ${ratio}%`:"未读"}</span>{ratio !== null ? <progress aria-label="阅读进度" max={100} value={ratio} /> : null}{item.reader_url ? <Link className={styles.primary} href={item.reader_url}>{ratio !== null ? "继续阅读" : "打开原文"}</Link> : work ? <Link href={`/works/${work.slug}`}>查看详情</Link> : null}<details className={styles.move}><summary aria-label="作品操作"><MoreHorizontal size={17}/></summary><div>{work?<Link href={`/works/${work.slug}`}>查看详情</Link>:null}<button aria-label={`上移${work?.title || "作品"}`} disabled={blocked || order !== "manual" || Boolean(q || kind) || page === 1 && index === 0} onClick={() => void execute({ action: "move", item_id: item.id, direction: -1 })}><ArrowUp size={14} /></button><button aria-label={`下移${work?.title || "作品"}`} disabled={blocked || order !== "manual" || Boolean(q || kind) || page === detail.total_pages && index === detail.items.length - 1} onClick={() => void execute({ action: "move", item_id: item.id, direction: 1 })}><ArrowDown size={14} /></button></div></details></> : <button disabled={blocked} onClick={() => void execute({ action: "restore", item_ids: [item.id] })}>恢复</button>}</div></article>;
        })}</div> : <div className={styles.empty}><img className={styles.emptyBooks} src="/brand/stl-booklists-empty-final-r2.png" width={81} height={32} alt=""/><h2>{trash ? "回收站里没有可恢复的作品" : q || kind ? "没有符合条件的作品" : "这份书单还是空的"}</h2><p>{q || kind ? "调整题名或类型筛选后继续查找。" : "从馆藏中选择作品，按自己的研究方向组织阅读。"}</p>{!trash ? <button disabled={blocked} onClick={() => setModal("add")}>添加作品</button> : null}</div>}</> : directory ? <div className={styles.listRows}>{directory.results.length ? directory.results.map(list => <article key={list.id}><BookOpen size={24} /><div><h2><Link href={`/account/collections/${list.id}`}>{list.title}</Link></h2><p>{list.description || "尚未填写说明"}</p><small>{list.item_count} 部作品 · 更新于 {stamp(list.updated_at)}</small></div><Link href={`/account/collections/${list.id}`}>打开 →</Link></article>) : <div className={styles.empty}><h2>{q ? "没有匹配的书单" : "还没有创建书单"}</h2><button disabled={blocked} onClick={() => setModal("create")}>创建第一份书单</button></div>}</div> : null}
      <nav className={styles.paging} aria-label="书单分页"><span>共 {data.count} 项</span><button disabled={blocked || page <= 1} onClick={() => { setSelected([]); setPage(value => value - 1); }}>上一页</button><span>{data.page} / {data.total_pages}</span><button disabled={blocked || page >= data.total_pages} onClick={() => { setSelected([]); setPage(value => value + 1); }}>下一页</button></nav>
      </> : <BooklistLinkedPanel busy={blocked} onAddTopic={() => setModal("topics")} onRemoveTopic={removeTopic} onRefresh={resource.reload} owner={owner} row={detail.list} view={view} />}
    </section>{detail ? <aside className={styles.sidebar}><section><h2>书单信息</h2><dl><dt>作品数量</dt><dd>{detail.active_count}</dd><dt>创建时间</dt><dd>{stamp(detail.list.created_at)}</dd><dt>最近更新</dt><dd>{stamp(detail.list.updated_at)}</dd><dt>可见范围</dt><dd><LockKeyhole size={13} />仅自己可见</dd></dl></section><section><h2>阅读目标<button disabled={blocked} onClick={edit}>编辑</button></h2><p>{detail.list.goal || "写下希望通过阅读理解的问题。"}</p></section>{view !== "related" ? <BooklistPublicSidebar busy={blocked} onAddTopic={() => setModal("topics")} onRemoveTopic={removeTopic} onRefresh={resource.reload} owner={owner} row={detail.list} onMore={() => { if (!blocked) show("related"); }} /> : null}<section><h2>标签</h2><div className={styles.tags}>{detail.list.tags.length ? detail.list.tags.map(tag => <span key={tag}>{tag}</span>) : <p>暂无标签</p>}</div></section><section><h2>研究与阅读</h2><p>从当前作品生成独立的私人计划，保留书单顺序。</p><button className={styles.primary} disabled={blocked || trash || !detail.active_count} onClick={plan}>生成阅读计划 →</button><button disabled={blocked} onClick={() => show("plans")}>本书单的阅读计划 →</button><button disabled={blocked} onClick={() => show("notes")}>这些作品下的本人笔记 →</button></section><section><button disabled={blocked} onClick={() => setModal("export")}><Download size={14} />导出书单</button><button disabled={blocked} onClick={() => { writeClipboardText(window.location.href).then(() => setMessage("已复制私人入口。其他账号不能通过此链接读取你的书单。"), () => setMessage("未能复制链接，可手动复制浏览器地址。")); }}>复制私人入口</button><button className={styles.danger} disabled={blocked} onClick={() => setModal("delete")}><Trash2 size={14} />删除书单</button></section></aside> : null}</div>}
    <Dialog open={Boolean(modal)} className={styles.dialog} aria-label="书单操作" onRequestClose={() => { if (!blocked) setModal(null); }}><header><h2>{{ create: "创建书单", edit: "编辑书单", add: "添加作品", export: "导出书单", delete: "删除书单", remove: "移除所选作品", purge: "彻底移除关联", plan: "生成阅读计划", topics: "关联公开主题" }[modal || "edit"]}</h2><button aria-label="关闭" disabled={blocked} onClick={() => setModal(null)}><X size={18} /></button></header>
      {modal === "create" || modal === "edit" ? <BooklistEditor key={`${modal}:${id}`} row={editing} busy={blocked} onSave={values => void execute({ action: modal === "create" ? "create" : "edit", ...values })} /> : null}
      {modal === "plan" && planSource ? <BooklistPlanForm owner={owner} row={planSource.row} selected={planSource.selected} onBusy={setBusy} onClose={() => setModal(null)} /> : null}
      {modal === "topics" && detail ? <BooklistTopicPicker owner={owner} selected={detail.list.topic_ids} busy={blocked} onAdd={topic_id => void execute({ action: "topic_add", topic_id })} /> : null}
      {modal === "add" && detail ? <WorkPicker owner={owner} presentWorkIds={detail.items.map(item=>item.work_id)} busy={blocked} onAdd={work_id => void execute({ action: "add", work_id })} /> : null}
      {modal === "export" && detail ? <ExportForm owner={owner} row={detail.list} selected={selected} controllerRef={controller} busy={blocked} onBusy={setBusy} onMessage={setMessage} /> : null}
      {modal === "delete" || modal === "remove" || modal === "purge" ? <><p>{modal === "delete" ? "将删除整份私人书单、作品顺序和回收站关联。这项操作不可撤销；馆藏、阅读进度、独立笔记和计划保留。" : modal === "remove" ? `将${selected.length}部作品移到书单回收站，30天内可恢复。` : `将彻底移除回收站中所选${selected.length}条关联，不能恢复；馆藏和笔记保留。`}</p><button className={styles.danger} disabled={blocked} onClick={() => void execute({ action: modal === "delete" ? "delete" : modal, ...(modal !== "delete" ? { item_ids: selected } : {}) })}>确认{modal === "delete" ? "删除书单" : "移除"}</button></> : null}
      {message ? <p role="status">{message}</p> : null}{recovery ? <button disabled={busy} onClick={() => void execute(undefined, true)}>核对原结果</button> : null}
    </Dialog>
    {detail && !table ? <div className={styles.mobileNav}><ReaderMobileNav variant="booklist" /></div> : null}
  </Frame>;
}

function BooklistEditor({ row, busy, onSave }: { row?: BooklistSummary; busy: boolean; onSave: (value: { title: string; description: string; goal?: string; tags?: string[] }) => void }) {
  function save(event: FormEvent<HTMLFormElement>) { event.preventDefault(); const data = new FormData(event.currentTarget); onSave({ title: String(data.get("title")).trim(), description: String(data.get("description") || ""), ...(row ? { goal: String(data.get("goal") || ""), tags: String(data.get("tags") || "").split(/[，,]/).map(value => value.trim()).filter(Boolean) } : {}) }); }
  return <form onSubmit={save}><fieldset disabled={busy}><label>书单名称<input name="title" defaultValue={row?.title} required maxLength={240} /></label><label>我的说明<textarea name="description" defaultValue={row?.description} maxLength={6000} rows={4} /></label>{row ? <><label>阅读目标<textarea name="goal" defaultValue={row.goal} maxLength={2000} rows={3} /></label><label>标签，逗号分隔<input name="tags" defaultValue={row.tags.join("，")} maxLength={491} /></label><small>最多12个标签，每个不超过40字。</small></> : null}<button className={styles.primary} type="submit">{busy ? "正在保存…" : "保存书单"}</button></fieldset></form>;
}

function WorkPicker({ owner, busy, onAdd, presentWorkIds }: { owner: string; presentWorkIds:string[]; busy: boolean; onAdd: (id: string) => void }) {
  const [q, setQ] = useState(""), [page, setPage] = useState(1);
  const load = useCallback((path: string, signal: AbortSignal) => apiRequest<{ results: ApiWork[]; next: string | null; previous: string | null }>(path, { signal, cache: "no-store" }, getServerSessionCredential()), []);
  const resource = usePersistentWorkspace(`/catalog/works/?q=${encodeURIComponent(q)}&page=${page}`, owner, undefined, load);
  return <div><form onSubmit={event => { event.preventDefault(); setPage(1); setQ(String(new FormData(event.currentTarget).get("q") || "")); }}><label>在公开馆藏中查找<input name="q" type="search" maxLength={180} placeholder="输入作品题名或作者" /></label><button type="submit">查找</button></form><p>同一作品只保留一条。</p>{resource.error ? <p role="alert">{resource.error}<button onClick={resource.reload}>重试</button></p> : !resource.data ? <p role="status">正在读取馆藏…</p> : <><div className={styles.picker}>{resource.data.results.map(raw => { const work = adaptApiWork(raw); return <article key={raw.id}><BookCover work={work} /><div><strong>{work.title}</strong><small>{work.author} · {work.year}</small></div><button disabled={busy||presentWorkIds.includes(raw.id)} onClick={() => onAdd(raw.id)}>{presentWorkIds.includes(raw.id)?"已在书单中":"加入"}</button></article>; })}{!resource.data.results.length ? <p>没有找到公开作品。</p> : null}</div><div className={styles.paging}><button disabled={busy || !resource.data.previous} onClick={() => setPage(value => value - 1)}>上一页</button><span>{page}</span><button disabled={busy || !resource.data.next} onClick={() => setPage(value => value + 1)}>下一页</button></div></>}</div>;
}

function ExportForm({ owner, row, selected, controllerRef, busy, onBusy, onMessage }: { owner: string; row: BooklistSummary; selected: string[]; controllerRef: RefObject<AbortController | null>; busy: boolean; onBusy: (value: boolean) => void; onMessage: (value: string) => void }) {
  const guard = useRef(false);
  const [format,setFormat]=useState("pdf");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const controller = controllerRef.current; if (!controller || controller.signal.aborted || guard.current) return;
    guard.current = true; onBusy(true); onMessage("");
    const data = new FormData(event.currentTarget);
    try { await downloadBooklist(owner, row.id, { expected_version: row.version, format: String(data.get("format")), include_notes: data.get("notes") === "on", include_progress: data.get("progress") === "on", include_covers: format==="pdf"&&data.get("covers")==="on", ...(selected.length ? { item_ids: selected } : {}) }, AbortSignal.any([controller.signal, AbortSignal.timeout(30000)])); if (!controller.signal.aborted) onMessage("导出文件已准备并交给浏览器下载。"); }
    catch (reason) { if (!controller.signal.aborted) onMessage(reason instanceof Error ? reason.message : "导出未完成。"); }
    finally { guard.current = false; if (!controller.signal.aborted) onBusy(false); }
  }
  return <form onSubmit={submit}><fieldset disabled={busy}><p>{selected.length ? `仅导出所选 ${selected.length} 部作品。` : "导出书单中的全部作品，每次最多200部。"}</p>{[["pdf", "PDF · 阅读书目"], ["bibtex", "BibTeX · 学术引用"], ["ris", "RIS · 文献管理"], ["csv", "CSV · 书目信息"]].map(([value, label]) => <label className={styles.option} key={value}><input type="radio" name="format" value={value} checked={value===format} onChange={()=>setFormat(value)} />{label}</label>)}<label className={styles.option}><input type="checkbox" name="covers" defaultChecked disabled={format!=="pdf"}/>PDF包含公开封面与版本信息</label><small>缺失或无法读取的封面会注明原因。非PDF格式只导出文字与书目信息。</small><label className={styles.option}><input type="checkbox" name="progress" />包含个人阅读状态</label><label className={styles.option}><input type="checkbox" name="notes" />包含个人笔记</label><p>勾选后，这些私人内容会进入你下载的文件。书单仍保持私人。</p><button className={styles.primary}>{busy ? "正在准备…" : "导出"}</button></fieldset></form>;
}
