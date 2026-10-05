"use client";
import { RecycleControl } from "./recycle-control";
import Link from "next/link";
import { useRef, useState } from "react";
import { useActionGuard } from "@/lib/use-action-guard";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { IssuePage, RecommendationIssue } from "@/lib/api/recommendation-issues.types";
import { RecommendationHomeCuration } from "@/components/admin/recommendation-home-curation";
import { DailyReadingContent } from "@/components/public/recommendation-issue-view";
import { PreviewViewport } from "@/components/admin/curation/fixed-page-editor";
import { SiteHeader } from "@/components/site-header";
import type { HomeViewData } from "@/components/public/home-public-view";

function dateKey(value: string) { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Hong_Kong", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)); }
function dateLabel(value?: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Hong_Kong" }) : "尚未安排"; }
function issueDate(issue: RecommendationIssue) { return issue.display_from || issue.published_at; }
export function RecommendationIssueList({ initialTab = "issues", home }: { initialTab?: "issues" | "placements"; home: HomeViewData }) {
  const { startAction, finishAction } = useActionGuard();
  const [tab, setTab] = useState(initialTab);
  const [query, setQuery] = useState(""), [page, setPage] = useState(1), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const [day, setDay] = useState(() => dateKey(new Date().toISOString()));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dayPage, setDayPage] = useState(1), [upcomingPage, setUpcomingPage] = useState(1), [publishedPage, setPublishedPage] = useState(1);
  const [mode, setMode] = useState<"draft" | "live">("draft"), [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const enlarged = useRef<HTMLDialogElement>(null);
  const credential = getServerSessionCredential();
  const resource = useApiResource<IssuePage>("/catalog/admin/recommendation-issues/?" + new URLSearchParams({ q: query, page: String(page) }), credential);
  const data = resource.data;
  const dayResource = useApiResource<IssuePage>(`/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"day",page:String(dayPage)})}`, credential);
  const upcomingResource = useApiResource<IssuePage>(`/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"upcoming",page:String(upcomingPage)})}`, credential);
  const publishedResource = useApiResource<IssuePage>(`/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"published",page:String(publishedPage)})}`, credential);
  const calendarLoading = dayResource.loading || upcomingResource.loading || publishedResource.loading;
  const calendarError = dayResource.error || upcomingResource.error || publishedResource.error;
  function refresh() {resource.retry();dayResource.retry();upcomingResource.retry();publishedResource.retry();}
  function moveDay(offset: number) { const date = new Date(`${day}T12:00:00+08:00`); date.setUTCDate(date.getUTCDate() + offset); setDay(dateKey(date.toISOString())); setSelectedId(null);setDayPage(1);setUpcomingPage(1);setPublishedPage(1); }
  async function create() {
    if (!startAction("create")) return;
    setBusy(true); setMessage("");
    try {
      const issue = await apiRequest<RecommendationIssue>("/catalog/admin/recommendation-issues/", { method: "POST", body: JSON.stringify({ title: "新一期书库推荐", display_from: `${day}T08:00:00+08:00` }) }, credential);
      window.location.assign("/admin/recommendations/issues/" + issue.id);
    } catch (error) { setMessage(error instanceof Error ? error.message : "创建失败"); setBusy(false); finishAction("create"); }
  }
  const today = dayResource.data?.results || [];
  const upcoming = upcomingResource.data?.results || [];
  const published = publishedResource.data?.results || [];
  const calendar = [...today,...upcoming,...published];
  const selected = calendar.find(issue => issue.id === selectedId) || today[0] || upcoming[0] || published[0] || null;
  const calendarPages = (data:IssuePage|undefined|null,pageNumber:number,change:(page:number)=>void) => <nav className="issue-pagination" aria-label="日期范围分页"><button type="button" disabled={!data?.previous} onClick={()=>change(pageNumber-1)}>上一页</button><span>{data ? `共 ${data.count} 期 · ${pageNumber}` : "—"}</span><button type="button" disabled={!data?.next} onClick={()=>change(pageNumber+1)}>下一页</button></nav>;
  const selectedState = (issue: RecommendationIssue) => issue.has_unpublished_changes ? "草稿" : issue.public_url ? "已发布" : issue.published_at ? "已安排" : "草稿";
  const issueCard = (issue: RecommendationIssue) => <button type="button" className={`recommendation-calendar-card${selected?.id === issue.id ? " selected" : ""}`} aria-pressed={selected?.id === issue.id} onClick={() => { setSelectedId(issue.id); setMode("draft"); }} key={issue.id}><div className="recommendation-calendar-image">{issue.cover_url ? <img src={issue.cover_url} alt="" /> : null}</div><div><span className={`recommendation-calendar-status ${selectedState(issue) === "已发布" ? "published" : selectedState(issue) === "已安排" ? "scheduled" : "draft"}`}>{selectedState(issue)}</span><h3>{issue.title || "未命名文章"}</h3><p>{issue.public_byline}</p><time>{dateLabel(issueDate(issue))}</time></div></button>;
  const previewContent = mode === "live" ? <iframe title="当前公开每日荐读" src="/recommendations" className="recommendation-live-frame" /> : selected ? <><SiteHeader preview previewPath="/recommendations"/><DailyReadingContent lead={selected} cards={published.filter(issue => issue.id !== selected.id).slice(0, 4)} preview /></> : <p className="empty-state">选择一篇文章查看已保存内容。</p>;
  const tools = <div className="recommendation-v2-view-tools"><button type="button" className={mode === "draft" ? "active" : ""} aria-pressed={mode === "draft"} onClick={() => setMode("draft")}>修改后</button><button type="button" className={mode === "live" ? "active" : ""} aria-pressed={mode === "live"} onClick={() => setMode("live")}>当前线上</button><button type="button" className={device === "desktop" ? "active" : ""} aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>电脑</button><button type="button" className={device === "mobile" ? "active" : ""} aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>手机</button><button type="button" onClick={() => enlarged.current?.showModal()}>放大查看</button></div>;
  return <div className="v307-admin-editor recommendation-calendar-v2">
    <header className="v307-editor-heading"><div><p className="eyebrow">每日荐读 · 编辑日历</p><h1>编辑日历</h1><p>按日期安排每日荐读文章</p></div><div><button className="button" onClick={create} disabled={busy}>＋ 新建荐读文章</button><form className="recommendation-calendar-search" onSubmit={event => { event.preventDefault(); setQuery(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }}><input name="q" aria-label="查找推荐期" placeholder="搜索文章标题"/><button className="button secondary">查找</button></form></div></header>
    <nav className="v307-admin-tabs" aria-label="推荐管理范围"><button aria-current={tab === "issues" ? "page" : undefined} onClick={() => setTab("issues")}>编辑日历</button><button aria-current={tab === "placements" ? "page" : undefined} onClick={() => setTab("placements")}>首页推荐位置</button></nav>
    {message ? <p role="alert">{message}</p> : null}
    {tab === "placements" ? <RecommendationHomeCuration home={home} initialPlacement="home_scholars" /> : <>
      {resource.error || calendarError ? <p role="alert">{resource.error || calendarError} <button type="button" onClick={refresh}>重试读取推荐期</button></p> : null}
      {calendarLoading ? <p role="status">正在读取推荐与排期…</p> : null}
      <div className="recommendation-calendar-layout">
        <section className="recommendation-calendar-board" aria-label="每日荐读日期安排">
          <header className="recommendation-calendar-date"><button type="button" aria-label="上一个日期" onClick={() => moveDay(-1)}>‹</button><strong>{new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Hong_Kong" }).format(new Date(`${day}T12:00:00+08:00`))}</strong><button type="button" aria-label="下一个日期" onClick={() => moveDay(1)}>›</button></header>
          <div className="recommendation-calendar-columns"><div><h2>所选日期</h2><small>{dateLabel(day)}</small>{today.map(issueCard)}{calendarPages(dayResource.data,dayPage,setDayPage)}{!today.length ? <p className="empty-state">当天暂无文章</p> : null}</div><div><h2>接下来</h2><small>所选日期之后</small>{upcoming.map(issueCard)}{calendarPages(upcomingResource.data,upcomingPage,setUpcomingPage)}{!upcoming.length ? <p className="empty-state">暂无安排</p> : null}<button type="button" className="recommendation-calendar-add" onClick={create} disabled={busy}>＋ 安排文章</button></div><div><h2>已发布</h2><small>所选日期之前</small>{published.map(issueCard)}{calendarPages(publishedResource.data,publishedPage,setPublishedPage)}{!published.length ? <p className="empty-state">暂无已发布文章</p> : null}</div></div>
        </section>
        <section className="recommendation-calendar-preview" aria-label="每日荐读首页预览"><header><div><h2>已保存内容预览</h2><p>读者首页每日荐读区域</p></div>{tools}</header><PreviewViewport device={device}>{previewContent}</PreviewViewport>{selected ? <footer className="recommendation-v2-actions"><Link className="button secondary" href={`/admin/recommendations/issues/${selected.id}`}>编辑这篇文章 →</Link></footer> : null}</section>
      </div>
      <dialog ref={enlarged} className="recommendation-preview-dialog"><header><strong>每日荐读预览</strong><button type="button" onClick={() => enlarged.current?.close()}>关闭</button></header><PreviewViewport device={device}>{previewContent}</PreviewViewport></dialog>
      <section className="recommendation-calendar-archive"><header><h2>全部推荐期</h2>{resource.loading ? <span role="status">正在读取…</span> : null}</header><div>{data?.results.map(issue => <article key={issue.id}><span>{issue.issue_label || "每日荐读"}</span><Link href={`/admin/recommendations/issues/${issue.id}`}><strong>{issue.title}</strong></Link><small>{selectedState(issue)}</small><RecycleControl kind="recommendation-issue" id={issue.id} name={issue.title} onDeleted={refresh} /></article>)}</div><nav className="issue-pagination" aria-label="后台推荐归档分页"><button disabled={!data?.previous || resource.loading} onClick={() => setPage(page - 1)}>上一页</button><span>{data ? `共 ${data.count} 期 · 第 ${page} 页` : "正在读取"}</span><button disabled={!data?.next || resource.loading} onClick={() => setPage(page + 1)}>下一页</button></nav></section>
    </>}
  </div>;
}
