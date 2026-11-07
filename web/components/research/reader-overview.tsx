"use client";


import { LoadingState } from "@/components/ui/loading-state";
import Link from "next/link";
import { ArrowRight, BookOpen, Bookmark, Box, CalendarDays, ChartPie, ChevronLeft, ChevronRight, FileText, RefreshCw, Search } from "lucide-react";
import { useCallback, useState, type FormEvent } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import type { ApiWork } from "@/lib/api/public-catalog";
import { usePersistentWorkspace } from "@/lib/api/use-persistent-workspace";
import { adaptApiWork } from "@/lib/public-data-adapters";
import { BookCover } from "@/components/ui";
import { ReaderMaterials, type ReaderMaterial } from "./reader-materials";
import { LocalResearchTransfer } from "./local-research-transfer";
import styles from "./reader-overview.module.css";

type Kind = "research" | "notes" | "bookmarks" | "plans" | "lists" | "audits" | "confirmed" | "saved";
type Material = ReaderMaterial;
type Progress = { id: string; asset: string; work: ApiWork | null; current_page: number; progress_ratio: number; updated_at: string };
type Pending = { id: string; title: string; question: string; status: string; updated_at: string; href: string };
type Overview = { owner_id: string; counts: Record<Kind, number>; count: number; page: number; page_size: number; total_pages: number; results: Material[]; recent_reading: Progress[]; pending_tasks: Pending[] };
const sections: Array<[Kind, string, string]> = [
  ["research", "我的研究", "/account/research"], ["notes", "笔记", "/account/notes"], ["plans", "阅读计划", "/account/plans"],
  ["lists", "书单", "/account/collections"], ["audits", "引文体检", "/account/citation-audits"], ["confirmed", "已确认笔记", "/account/confirmed-notes"],
];
const sectionIcons = { research: Box, notes: FileText, plans: CalendarDays, lists: BookOpen, audits: ChartPie, confirmed: Bookmark, bookmarks: Bookmark, saved: Bookmark };
const statusNames: Record<string, string> = { saved: "已保存", archived: "已归档", confirmed: "已确认", reading: "进行中", pending: "待开始", queued: "待处理", running: "处理中", completed: "已完成", complete: "已完成", partial: "部分完成", failed: "处理失败", cancelled: "已取消", canceled: "已取消", source_unavailable: "来源待核对" };
const dateLabel = (value: string) => Number.isNaN(Date.parse(value)) ? "时间未记录" : new Date(value).toLocaleDateString("zh-CN");

export function ReaderOverview({ ownerId, archive=false }: { ownerId: string; archive?:boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const kind = params.get("material") || "all";
  const search = params.get("q") || "";
  const visibility = ["active", "archived"].includes(params.get("visibility") || "") ? params.get("visibility")! : "all";
  const order = params.get("order") === "oldest" ? "oldest" : "newest";
  const pageText = params.get("page") || "1";
  const page = /^\d{1,9}$/.test(pageText) && Number(pageText) > 0 ? Number(pageText) : 1;
  const [materialGuard, setMaterialGuard] = useState(false);
  const [view, setView] = useState<"list" | "cards">("list");
  const query = new URLSearchParams({ kind, q: search, order, visibility, page: String(page), overview:archive?"false":"true" });
  const load = useCallback(async (path: string, signal: AbortSignal) => {
    const value = await apiRequest<Overview>(path, { cache: "no-store", signal: AbortSignal.any([signal, AbortSignal.timeout(30000)]), headers: { "X-Reader-Owner": ownerId } }, getServerSessionCredential());
    if (value.owner_id !== ownerId) throw new Error("登录账户已变化，请重新读取资料。");
    return value;
  }, [ownerId]);
  const workspace = usePersistentWorkspace<Overview>(`/reading/reader-center/?${query}`, ownerId, undefined, load);
  const data = workspace.error ? null : workspace.data;
  function filter(values: Record<string, string>) {
    if (materialGuard && !window.confirm("原资料操作尚未完成。切换筛选不会取消请求，选择及恢复编号会保留。确定继续吗？")) return;
    const next = new URLSearchParams(params.toString());
    next.delete("page");
    for (const [key, value] of Object.entries(values)) { if (!value || value === "all") next.delete(key); else next.set(key, value); }
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    filter({ q: String(new FormData(event.currentTarget).get("q") || "").trim() });
  }
  return <div className={`${styles.overview} ${archive?styles.archive:""}`}>
    <div className={styles.navigation}>{!archive?<nav className={styles.sections} aria-label="我的资料类型">{sections.map(([key, label, href]) => { const Icon=sectionIcons[key]; return <Link key={key} href={href} data-overview-current={key==="research"||undefined}><Icon size={19} /><span>{label}</span><small>{data ? data.counts[key] + (key === "notes" ? data.counts.bookmarks : 0) : "—"}</small></Link>; })}</nav>:null}<form className={styles.search} onSubmit={submit} key={search}><Search size={18} /><input aria-label="搜索我的资料" name="q" type="search" maxLength={180} defaultValue={search} placeholder="搜索我的资料…" /><button type="submit" aria-label="搜索我的资料">搜索</button></form></div>
    {archive?<nav className={styles.archiveTabs} aria-label="资料类别">{[["all","全部"],["research","研究"],["saved","选材"],["notes","笔记"],["lists","书单"],["plans","计划"],["audits","体检"],["confirmed","记忆"]].map(([value,label])=><button key={value} aria-pressed={kind===value} onClick={()=>filter({material:value})}>{label}</button>)}</nav>:null}
    {!archive||data?.results.length?<details className={styles.localTransfer}><summary>本机记录</summary><div><p>本机研究记录只有在你选择并确认后才会转存。</p><LocalResearchTransfer ownerId={ownerId} onChanged={workspace.reload} /></div></details>:null}
    {workspace.error ? <section className={styles.state} role="alert"><h2>私人资料暂时无法读取</h2><p>{workspace.error}</p><div><button onClick={workspace.reload}><RefreshCw size={15} />重新读取</button>{page > 1 ? <button onClick={() => filter({ page: "1" })}>返回第一页</button> : null}{search || kind !== "all" || visibility !== "all" ? <button onClick={() => filter({ q: "", material: "all", visibility: "all" })}>清除筛选</button> : null}</div></section> : workspace.loading || !data ? <section className={styles.state} role="status"><LoadingState>正在读取你的资料…</LoadingState></section> : <>
      {!archive?<><section className={styles.section}><header><div><h2>继续阅读</h2></div><Link href="/account?section=history">查看全部 <ArrowRight size={14} /></Link></header>
        {data.recent_reading.length ? <div className={styles.reading}>{data.recent_reading.map(row => {
          if (!row.work) return <article key={row.id}><div><h3>来源当前不可用</h3><p>阅读位置仍保留，作品公开后可继续阅读。</p></div></article>;
          const work = adaptApiWork(row.work), ratio = Math.max(0, Math.min(100, Math.round(row.progress_ratio * 100)));
          return <article key={row.id}><BookCover work={work} /><div><h3><Link href={`/works/${work.slug}`}>{work.title}</Link></h3><p>{work.author}</p><small>上次阅读：第 {row.current_page} 页</small><div className={styles.progress}><progress max={100} value={ratio} aria-label={`《${work.title}》阅读进度`} /><span>{ratio}%</span></div><Link className={styles.continue} href={`/reader/${row.asset}?page=${row.current_page}`}>继续阅读 <ChevronRight size={14} /></Link></div></article>;
        })}</div> : <div className={styles.empty}><BookOpen size={24} /><strong>从一本书开始</strong><p>开始阅读后，这里会保留继续阅读的位置。</p><Link href="/explore/original">探索原文 <ArrowRight size={14} /></Link></div>}
      </section>
      <section className={styles.section}><header><div><h2>继续计划</h2></div><Link href="/account/plans">查看全部 <ArrowRight size={14} /></Link></header>
        {data.pending_tasks.length ? <div className={styles.tasks}>{data.pending_tasks.map(row => <article key={row.id}><FileText size={17} /><div><Link href={row.href}><strong>{row.title}</strong></Link><small>{row.question}</small></div><time dateTime={row.updated_at}>{dateLabel(row.updated_at)}</time><span className={styles.status} data-state={row.status}>{statusNames[row.status] || "待核对"}</span><Link href={row.href} aria-label={`继续${row.title}`}><ArrowRight size={15} /></Link></article>)}</div> : <div className={styles.empty}><p>当前没有待继续的阅读计划条目。</p><Link href="/account/plans">创建或查看阅读计划 <ArrowRight size={14} /></Link></div>}
      </section>
    </>:null}</>}
    <section className={styles.section}><header><div><h2>我的资料</h2>{!archive?<Link className={styles.archiveLink} href="/account?view=archive">查看全部 <ArrowRight size={14}/></Link>:null}</div><div className={styles.view}><label><span className="sr-only">排序</span><select value={order} onChange={event => filter({ order: event.target.value })}><option value="newest">排序：最近更新</option><option value="oldest">排序：最早更新</option></select></label><label><span className="sr-only">查看方式</span><select value={view} onChange={event => setView(event.target.value as "list" | "cards")}><option value="list">查看方式：列表</option><option value="cards">查看方式：卡片</option></select></label></div></header>
      <div className={styles.filters}><label><span className="sr-only">资料类型</span><select value={kind} onChange={event => filter({ material: event.target.value })}><option value="all">全部资料</option>{sections.map(([key, label]) => <option key={key} value={key}>{label}</option>)}<option value="saved">选材收藏</option></select></label><label><span className="sr-only">归档范围</span><select value={visibility} onChange={event => filter({ visibility: event.target.value })}><option value="all">全部状态</option><option value="active">未归档</option><option value="archived">已归档</option></select></label></div>
      <ReaderMaterials key={ownerId} rows={data?.results || []} ownerId={ownerId} cards={view === "cards"} onChanged={workspace.reload} onGuardChange={setMaterialGuard} />
      {data ? data.results.length ? <><nav className={styles.paging} aria-label="资料分页"><span>共 {data.count} 项</span><button disabled={data.page <= 1} onClick={() => filter({ page: String(data.page - 1) })} aria-label="上一页"><ChevronLeft size={16} /></button><span>{data.page} / {data.total_pages}</span><button disabled={data.page >= data.total_pages} onClick={() => filter({ page: String(data.page + 1) })} aria-label="下一页"><ChevronRight size={16} /></button></nav></> : <div className={styles.empty}>{archive&&!search&&kind==="all"&&visibility==="all"?<img className={styles.archiveEmpty} src="/brand/stl-reader-archive-empty-final-r2.png" alt="" width={123} height={68}/>:<FileText size={24} />}<strong>{search || kind !== "all" || visibility !== "all" ? "没有匹配的资料" : archive?"开始你的研究档案":"这里还没有资料"}</strong><p>{search || kind !== "all" || visibility !== "all" ? "可以调整关键词或资料类型，现有资料没有被删除。" : "保存研究、笔记、计划或书单后，就能在这里继续。"}</p>{search || kind !== "all" || visibility !== "all" ? <button onClick={() => filter({ q: "", material: "all", visibility: "all" })}>查看全部资料</button> : archive?<><div className={styles.emptyActions}><LocalResearchTransfer ownerId={ownerId} onChanged={workspace.reload}/><Link href="/explore/original">新建笔记</Link></div><Link href="/explore">或从探索开始 <ArrowRight size={14}/></Link></>:<Link href="/explore">从探索开始 <ArrowRight size={14} /></Link>}</div> : null}
    </section>
  </div>;
}
