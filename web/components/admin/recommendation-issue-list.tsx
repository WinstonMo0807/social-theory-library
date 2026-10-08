"use client";
import { RecycleControl } from "./recycle-control";
import Link from "next/link";
import { useRef, useState } from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Monitor, Plus, Search, Smartphone } from "lucide-react";
import { useActionGuard } from "@/lib/use-action-guard";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { IssuePage, RecommendationIssue } from "@/lib/api/recommendation-issues.types";
import { RecommendationHomeCuration } from "@/components/admin/recommendation-home-curation";
import { DailyReadingIndexView } from "@/components/public/recommendation-issue-view";
import { PreviewViewport } from "@/components/admin/curation/fixed-page-editor";
import { SiteHeader } from "@/components/site-header";
import type { HomeViewData } from "@/components/public/home-public-view";

function dateKey(value: string) { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Hong_Kong", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value)); }
function dateLabel(value?: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Hong_Kong" }) : "尚未安排"; }
function issueDate(issue: RecommendationIssue) { return issue.display_from || issue.published_at; }
export function RecommendationIssueList({ initialTab = "calendar", home }: { initialTab?: "issues" | "calendar" | "placements"; home: HomeViewData }) {
  const { startAction, finishAction } = useActionGuard();
  const tab = initialTab;
  const [query, setQuery] = useState(""), [page, setPage] = useState(1), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const [day, setDay] = useState(() => dateKey(new Date().toISOString()));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dayPage, setDayPage] = useState(1), [upcomingPage, setUpcomingPage] = useState(1), [publishedPage, setPublishedPage] = useState(1);
  const [mode, setMode] = useState<"draft" | "live">("draft"), [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const enlarged = useRef<HTMLDialogElement>(null);
  const credential = getServerSessionCredential();
  const resource = useApiResource<IssuePage>(tab === "issues" ? "/catalog/admin/recommendation-issues/?" + new URLSearchParams({ q: query, page: String(page) }) : "", credential);
  const data = resource.data;
  const dayResource = useApiResource<IssuePage>(tab === "calendar" ? `/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"day",q:query,page:String(dayPage)})}` : "", credential);
  const upcomingResource = useApiResource<IssuePage>(tab === "calendar" ? `/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"upcoming",q:query,page:String(upcomingPage)})}` : "", credential);
  const publishedResource = useApiResource<IssuePage>(tab === "calendar" ? `/catalog/admin/recommendation-issues/?${new URLSearchParams({day,bucket:"published",q:query,page:String(publishedPage)})}` : "", credential);
  const publicResource = useApiResource<IssuePage>(tab === "calendar" ? "/catalog/recommendation-issues/" : "", credential);
  const calendarLoading = dayResource.loading || upcomingResource.loading || publishedResource.loading;
  const calendarError = dayResource.error || upcomingResource.error || publishedResource.error;
  function refresh() {resource.retry();dayResource.retry();upcomingResource.retry();publishedResource.retry();publicResource.retry();}
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
  const calendarPages = (data:IssuePage|undefined|null,pageNumber:number,change:(page:number)=>void,label:string) => data && (data.next || data.previous) ? <nav className="issue-pagination" aria-label={`${label}分页`}><button type="button" disabled={!data.previous || calendarLoading} onClick={()=>change(pageNumber-1)}>上一页</button><span>共 {data.count} 期 · {pageNumber}</span><button type="button" disabled={!data.next || calendarLoading} onClick={()=>change(pageNumber+1)}>下一页</button></nav> : null;
  const selectedState = (issue: RecommendationIssue) => issue.has_unpublished_changes ? "草稿" : issue.public_url ? "已发布" : issue.published_at ? "已安排" : "草稿";
  const issueCard = (issue: RecommendationIssue) => <button type="button" className={`recommendation-calendar-card${selected?.id === issue.id ? " selected" : ""}`} aria-pressed={selected?.id === issue.id} onClick={() => { setSelectedId(issue.id); setMode("draft"); }} key={issue.id}><div className="recommendation-calendar-image">{issue.cover_url ? <img src={issue.cover_url} alt="" /> : null}</div><div><span className={`recommendation-calendar-status ${selectedState(issue) === "已发布" ? "published" : selectedState(issue) === "已安排" ? "scheduled" : "draft"}`}>{selectedState(issue)}</span><h3>{issue.title || "未命名文章"}</h3><p>{issue.public_byline}</p><time>{dateLabel(issueDate(issue))}</time></div></button>;
  const publishedLead = publicResource.data?.current || publicResource.data?.results[0] || null;
  const previewLead = mode === "live" ? publishedLead : selected;
  const previewContent = <div inert><SiteHeader preview previewPath="/recommendations"/>{mode === "live" && publicResource.error ? <p role="alert">{publicResource.error}</p> : mode === "live" && publicResource.loading ? <p role="status">正在读取当前公开内容…</p> : <DailyReadingIndexView lead={previewLead} cards={(publicResource.data?.results || []).filter(issue => issue.id !== previewLead?.id)} />}</div>;
  const tools = <div className="recommendation-v2-view-tools"><div role="group" aria-label="预览内容"><button type="button" aria-pressed={mode === "draft"} onClick={() => setMode("draft")}>修改后</button><button type="button" aria-pressed={mode === "live"} onClick={() => setMode("live")}>当前线上</button></div><div role="group" aria-label="预览尺寸"><button type="button" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}><Monitor size={16}/>电脑</button><button type="button" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}><Smartphone size={16}/>手机</button></div><button type="button" onClick={() => enlarged.current?.showModal()}><Search size={16}/>放大查看</button></div>;
  const shiftedDay = (offset:number) => { const date = new Date(`${day}T12:00:00+08:00`); date.setUTCDate(date.getUTCDate()+offset); return dateKey(date.toISOString()); };
  const rangeDate = (value:string) => new Intl.DateTimeFormat("zh-CN",{month:"long",day:"numeric",timeZone:"Asia/Hong_Kong"}).format(new Date(`${value}T12:00:00+08:00`));
  if(tab === "placements") return <RecommendationHomeCuration home={home} initialPlacement="home_scholars" />;
  return <div className="v307-admin-editor recommendation-calendar-v2">
    <header className="v307-editor-heading"><div><h1>{tab === "calendar" ? "编辑日历" : "文章列表"}</h1><p>{tab === "calendar" ? "按日期安排每日荐读文章" : "管理每日荐读文章与已保存的草稿"}</p></div><div><button className="button" onClick={create} disabled={busy}><Plus size={19}/>新建荐读文章</button><form className="recommendation-calendar-search" onSubmit={event => { event.preventDefault(); setQuery(String(new FormData(event.currentTarget).get("q") || "").trim()); setPage(1); setDayPage(1); setUpcomingPage(1); setPublishedPage(1); setSelectedId(null); }}><button type="submit" aria-label="查找推荐期"><Search size={18}/></button><input name="q" aria-label="搜索文章标题、作者或关键词" placeholder="搜索文章标题、作者或关键词"/></form></div></header>
    {message ? <p role="alert">{message}</p> : null}
    {tab === "calendar" ? <>
      {resource.error || calendarError || publicResource.error ? <p role="alert">{resource.error || calendarError || publicResource.error} <button type="button" onClick={refresh}>重试读取推荐期</button></p> : null}
      {calendarLoading ? <p role="status">正在读取推荐与排期…</p> : null}
      <div className="recommendation-calendar-layout">
        <section className="recommendation-calendar-board" aria-label="每日荐读日期安排">
          <header className="recommendation-calendar-date"><button type="button" aria-label="上一个日期" onClick={() => moveDay(-1)}><ChevronLeft size={20}/></button><strong>{new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Hong_Kong" }).format(new Date(`${day}T12:00:00+08:00`))}</strong><button type="button" aria-label="下一个日期" onClick={() => moveDay(1)}><ChevronRight size={20}/></button></header>
          <div className="recommendation-calendar-columns"><div><h2>{day === dateKey(new Date().toISOString()) ? "今天" : "所选日期"}</h2><small>{rangeDate(day)} · {new Intl.DateTimeFormat("zh-CN",{weekday:"short",timeZone:"Asia/Hong_Kong"}).format(new Date(`${day}T12:00:00+08:00`))}</small>{today.map(issueCard)}{calendarPages(dayResource.data,dayPage,setDayPage,"所选日期")}{!calendarLoading && !today.length ? <p className="empty-state">当天暂无文章</p> : null}</div><div><h2>接下来</h2><small>{rangeDate(shiftedDay(1))}及以后</small>{upcoming.map(issueCard)}{calendarPages(upcomingResource.data,upcomingPage,setUpcomingPage,"接下来")}<div className="recommendation-calendar-empty"><CalendarDays size={16}/>{!calendarLoading && !upcoming.length ? <p>暂无安排</p> : null}<button type="button" className="recommendation-calendar-add" onClick={create} disabled={busy}><Plus size={16}/>安排文章</button></div></div><div><h2>已发布</h2><small>{rangeDate(shiftedDay(-1))}及之前</small>{published.map(issueCard)}{calendarPages(publishedResource.data,publishedPage,setPublishedPage,"已发布")}{!calendarLoading && !published.length ? <p className="empty-state">暂无已发布文章</p> : null}<Link className="recommendation-calendar-more" href="/admin/recommendations">查看更多已发布文章 →</Link></div></div>
        </section>
        <section className="recommendation-calendar-preview" aria-label="每日荐读首页预览"><header><h2>已保存内容预览</h2>{tools}</header><PreviewViewport device={device}>{previewContent}</PreviewViewport>{selected ? <footer className="recommendation-v2-actions"><Link className="button secondary" href={`/admin/recommendations/issues/${selected.id}`}>编辑这篇文章 →</Link></footer> : null}</section>
      </div>
      <dialog ref={enlarged} className="recommendation-preview-dialog"><header><strong>每日荐读预览</strong><button type="button" onClick={() => enlarged.current?.close()}>关闭</button></header><PreviewViewport device={device}>{previewContent}</PreviewViewport></dialog>
    </> : <section className="recommendation-calendar-archive" aria-label="每日荐读文章列表">{resource.error ? <p role="alert">{resource.error}<button type="button" onClick={resource.retry}>重试</button></p> : null}{resource.loading ? <p role="status">正在读取文章…</p> : null}<div>{data?.results.map(issue => <article key={issue.id}><span>{issue.issue_label || "每日荐读"}</span><Link href={`/admin/recommendations/issues/${issue.id}`}><strong>{issue.title}</strong></Link><small>{selectedState(issue)}</small><RecycleControl kind="recommendation-issue" id={issue.id} name={issue.title} onDeleted={refresh} /></article>)}</div>{data?.count === 0 ? <p className="empty-state">没有匹配的文章。</p> : null}<nav className="issue-pagination" aria-label="后台推荐归档分页"><button disabled={!data?.previous || resource.loading} onClick={() => setPage(page - 1)}>上一页</button><span>{data ? `共 ${data.count} 期 · 第 ${page} 页` : "正在读取"}</span><button disabled={!data?.next || resource.loading} onClick={() => setPage(page + 1)}>下一页</button></nav></section>}
  </div>;
}
