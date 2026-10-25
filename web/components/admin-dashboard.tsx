"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDownUp, ArrowRight, BookOpen, CircleAlert, FileText, LockKeyhole, MoreHorizontal, RefreshCw, Search } from "lucide-react";
import { useState } from "react";
import { getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import { useAdminSession } from "@/lib/admin-session";
import { adminListHref, safeAdminHref, withAdminReturn } from "@/lib/admin-route-context";
import type { components } from "@/lib/api/generated/schema";
import styles from "./admin/today-work.module.css";

type TodayWork = components["schemas"]["TodayWorkPage"];
type WorkItem = components["schemas"]["TodayWorkItem"];
const categories = [["all", "全部"], ["editing", "最近编辑"], ["intake", "待继续收件"], ["catalog", "待校准目录"], ["problems", "待处理问题"], ["publication", "待发布核对"]] as const;
const kinds = [["", "任务类型"], ["catalog", "书目处理"], ["curation", "策划与知识"], ["processing", "数字化处理"]];
const states = [["", "状态"], ["draft", "已保存 · 未发布"], ["changes_pending", "已发布 · 有草稿"], ["pending", "等待处理"], ["running", "处理中"], ["paused", "已暂停"], ["partial", "部分完成"], ["attention", "待核对"], ["failed", "处理失败"], ["ready", "待发布核对"]];
const options = ["q", "category", "kind", "state", "owner", "ordering", "page"];
function formatDate(value: string, full = false) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间待核对" : new Intl.DateTimeFormat("zh-CN", { year: full ? "numeric" : undefined, month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(date);
}

function WorkRow({ row, returnTo }: { row: WorkItem; returnTo: string }) {
  const [failedImage, setFailedImage] = useState("");
  const [copied, setCopied] = useState("");
  const destination = safeAdminHref(row.url, "");
  const href = destination ? withAdminReturn(destination, returnTo) : "";
  async function copy() {
    try { await navigator.clipboard.writeText(row.object_id); setCopied("编号已复制"); }
    catch { setCopied("复制未完成，请选择下方编号复制。"); }
  }
  return <li className={styles.row}>
    <div className={styles.thumbnail}>{row.category === "editing" ? <span className={styles.thumbnailBadge}>继续编辑</span> : null}{row.thumbnail_url && failedImage !== row.thumbnail_url ? <img src={row.thumbnail_url} alt="" loading="lazy" decoding="async" onError={() => setFailedImage(row.thumbnail_url)} /> : <BookOpen size={32} strokeWidth={1} aria-hidden="true" />}</div>
    <div className={styles.copy}>
      <h2>{href ? <Link href={href} prefetch={false}>{row.title || "未命名条目"}</Link> : row.title || "未命名条目"}</h2>
      <div className={styles.identity}><span>{row.label}</span><code title={row.object_id}>{row.object_id.slice(0, 8)}</code><strong className={styles.rowStatus} data-state={row.state}><i aria-hidden="true" />{row.state_label}</strong></div>
      <p>{row.summary}</p>
    </div>
    <div className={styles.state}>
      <time dateTime={row.updated_at}>更新：{formatDate(row.updated_at)}</time>
    </div>
    <div className={styles.actions}>
      {href ? <Link className={row.category === "editing" ? styles.primary : styles.secondary} href={href} prefetch={false}>{row.action_label}<ArrowRight size={13} /></Link> : <span>工作位置待核对</span>}
      <details className={styles.more} onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
        <summary aria-label={`${row.title || "条目"}的更多操作`}><MoreHorizontal size={18} /></summary>
        <div><button type="button" onClick={() => void copy()}>复制条目编号</button><code>{row.object_id}</code><span role="status">{copied}</span>{href ? <Link href={href} prefetch={false}>打开完整工作页</Link> : null}</div>
      </details>
    </div>
  </li>;
}

export function AdminDashboard({ searchMode = false }: { searchMode?: boolean }) {
  const user = useAdminSession();
  const router = useRouter();
  const search = useSearchParams();
  const params = new URLSearchParams();
  options.forEach(key => { const value = search.get(key); if (value && (!searchMode || key !== "category")) params.set(key, value); });
  const query = params.toString();
  const base = searchMode ? "/admin/search" : "/admin";
  const resource = useApiResource<TodayWork>(`/catalog/admin/${searchMode ? "search" : "today-work"}/?${query}`, user ? getServerSessionCredential() : null, String(user?.id || ""));
  const data = resource.data;
  const tabKey = searchMode ? "kind" : "category";
  const tabs = searchMode ? [["all", "全部"], ["catalog", "馆藏与收件"], ["curation", "策划与知识"], ["processing", "处理任务"]] : categories;
  const current = search.get(tabKey) || "all";
  const returnTo = `${base}${query ? `?${query}` : ""}`;
  const blankSearch = searchMode && !search.get("q")?.trim();
  const filtered = ["q", "kind", "state"].some(key => Boolean(search.get(key))) || search.get("owner") === "me" || current !== "all";
  function change(updates: Record<string, string | number | null>) { router.push(adminListHref(base, query, { page: null, ...updates }), { scroll: false }); }
  return <div className={styles.page} data-admin-today={!searchMode}>
    <header className={styles.heading}><div><p>{searchMode ? "管理工作区" : "今日工作"}</p><h1>{searchMode ? "搜索工作与资料" : "今日工作与继续处理"}</h1><span>{searchMode ? "按书名、作者、主题或完整任务编号，查找有权访问的资料和处理记录。" : "从待办事项继续出发，完成编目、整理与发布。"}</span></div><div className={styles.refresh}>{data ? <time dateTime={data.checked_at}>{formatDate(data.checked_at, true)}</time> : null}<button type="button" onClick={resource.retry} disabled={resource.loading}><RefreshCw size={16} />{resource.loading ? "读取中" : "刷新"}</button></div></header>
    <nav className={styles.tabs} aria-label={searchMode ? "搜索结果分类" : "今日工作分类"}>{tabs.filter(([key]) => key !== "processing" || !data?.restricted).map(([key, title]) => <Link key={key} href={adminListHref(base, query, { [tabKey]: key === "all" ? null : key, page: null })} aria-current={current === key ? "page" : undefined} scroll={false}>{title}<span>{data ? data.counts[key] ?? 0 : "—"}</span></Link>)}</nav>
    <div className={styles.filters}>
      {!searchMode ? <label><span className="sr-only">任务类型</span><select value={search.get("kind") || ""} onChange={event => change({ kind: event.target.value })}>{kinds.filter(([key]) => key !== "processing" || !data?.restricted).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label> : null}
      <label><span className="sr-only">任务状态</span><select value={search.get("state") || ""} onChange={event => change({ state: event.target.value })}>{[...states, ...(searchMode ? [["published", "已发布"], ["withdrawn", "已撤回"], ["approved", "已确认"], ["succeeded", "文件任务已完成"], ["completed", "索引任务已完成"], ["canceled", "已取消"]] : [])].map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
      <label className={styles.ownerFilter} title={data?.owner_basis}><span className="sr-only">工作范围</span><select value={search.get("owner") || "all"} onChange={event => change({ owner: event.target.value })}><option value="all">工作范围：全部</option><option value="me">我发起或编辑的</option></select></label>
      <form className={`${styles.search} ${searchMode ? "" : styles.secondarySearch}`} key={search.get("q") || ""} onSubmit={event => { event.preventDefault(); change({ q: String(new FormData(event.currentTarget).get("q") || "").trim() }); }}><label><Search size={15} /><input name="q" type="search" defaultValue={search.get("q") || ""} maxLength={200} aria-label={searchMode ? "搜索书名、作者、主题或任务编号" : "搜索待办题名或完整编号"} placeholder={searchMode ? "查找工作与资料…" : "查找待办…"} /></label><button type="submit">查找</button></form>
      <button className={styles.sort} type="button" aria-label={search.get("ordering") === "updated_at" ? "按更新时间从新到旧排序" : "按更新时间从旧到新排序"} onClick={() => change({ ordering: search.get("ordering") === "updated_at" ? "-updated_at" : "updated_at" })}><span>更新时间</span><ArrowDownUp size={16} /></button>
    </div>
    {data?.restricted ? <aside className={styles.permission}><LockKeyhole size={17} /><p>以下为你有权访问的工作。运行维护与处理任务需相应权限，未授权内容不计入列表。</p><Link href="/feedback?category=usage">申请权限</Link></aside> : null}
    {search.get("owner") === "me" && data ? <p className={styles.scopeNote}>{data.owner_basis}</p> : null}
    {resource.loading ? <div className={styles.loading} role="status"><FileText size={28} strokeWidth={1} /><p>正在读取工作记录…</p></div> : resource.error ? <section className={styles.empty} role="alert"><CircleAlert size={36} strokeWidth={1.2} /><h2>{searchMode ? "暂时无法获取搜索结果" : "暂时无法获取任务列表"}</h2><p>{resource.error}</p><div><button className={styles.primary} type="button" onClick={resource.retry}>重新加载</button><Link className={styles.secondary} href="/help">查看帮助</Link></div></section> : data && data.results.length === 0 ? <section className={styles.empty}><img className={styles.emptyIllustration} src="/visual/stl4/admin/today-empty-final-r2.png" alt="" /><h2>{blankSearch ? "输入关键词开始查找" : searchMode ? "没有找到符合条件的资料" : filtered ? "没有符合当前筛选的任务" : "暂无待处理的任务"}</h2><p>{searchMode ? "可查找馆藏、策划、学者、主题和处理记录。调整关键词或筛选范围后重试。" : filtered ? "调整任务类型、状态或工作范围，查看其他待办。" : "当前没有需要继续的任务，可以从以下入口开始。"}</p><div>{filtered ? <Link className={styles.primary} href={base}>清除筛选</Link> : null}{!searchMode && data.can_upload ? <Link className={styles.primary} href="/admin/uploads">收件与编目</Link> : null}{!searchMode && data.can_create_issue ? <Link className={styles.secondary} href="/admin/recommendations#create-issue">创建特别策划</Link> : null}<Link className={styles.secondary} href="/admin/library">浏览馆藏目录</Link></div></section> : data ? <><ul className={styles.list} aria-label={searchMode ? "搜索结果" : "待处理任务"}>{data.results.map(row => <WorkRow key={row.id} row={row} returnTo={returnTo} />)}</ul><footer className={styles.pagination}><span>共 {data.count} 项{searchMode ? "结果" : "工作"} · 第 {data.page} / {data.total_pages} 页</span><div>{data.page > 1 ? <Link href={adminListHref(base, query, { page: data.page - 1 })}>上一页</Link> : null}{data.page < data.total_pages ? <Link href={adminListHref(base, query, { page: data.page + 1 })}>下一页</Link> : null}</div></footer></> : null}
  </div>;
}
