"use client";
import Link from "next/link";
import { useState } from "react";
import { ArrowRight, CalendarDays, Users } from "lucide-react";
import { useActionGuard } from "@/lib/use-action-guard";
import { apiRequest, getServerSessionCredential } from "@/lib/api";
import { useApiResource } from "@/lib/api/use-api-resource";
import type { IssuePage, RecommendationIssue } from "@/lib/api/recommendation-issues.types";
import type { RecommendationPlacement, RecommendationItem } from "@/lib/api/recommendations.types";
import { RecommendationsAdmin } from "@/components/knowledge-admin";

function dateLabel(value?: string | null) { return value ? new Date(value).toLocaleDateString("zh-CN", { timeZone: "Asia/Shanghai" }) : "尚未安排"; }
function itemLabel(item: RecommendationItem) { return "name" in item.target ? item.target.name : item.target.title; }
function itemImage(item: RecommendationItem) {
  const target = item.target as Record<string, unknown>;
  return item.image_override || String(target.portrait || target.hero_image || "");
}
export function RecommendationIssueList() {
  const { startAction, finishAction } = useActionGuard();
  const [tab, setTab] = useState("issues"), [placement, setPlacement] = useState("");
  const [query, setQuery] = useState(""), [page, setPage] = useState(1), [message, setMessage] = useState(""), [busy, setBusy] = useState(false);
  const credential = getServerSessionCredential();
  const resource = useApiResource<IssuePage>("/catalog/admin/recommendation-issues/?" + new URLSearchParams({ q: query, page: String(page) }), credential);
  const policies = useApiResource<RecommendationPlacement[]>("/catalog/admin/recommendations/", credential);
  const data = resource.data;
  const scholars = policies.data?.find(item => item.placement === "home_scholars");
  const topics = policies.data?.find(item => item.placement === "home_topics");
  function editPlacement(value: string) { setPlacement(value); setTab("placements"); }
  async function create() {
    if (!startAction("create")) return;
    setBusy(true); setMessage("");
    try {
      const issue = await apiRequest<RecommendationIssue>("/catalog/admin/recommendation-issues/", { method: "POST", body: JSON.stringify({ title: "新一期书库推荐" }) }, credential);
      window.location.assign("/admin/recommendations/issues/" + issue.id);
    } catch (error) { setMessage(error instanceof Error ? error.message : "创建失败"); setBusy(false); finishAction("create"); }
  }
  return <div className="v307-admin-editor">
    <header className="v307-editor-heading"><div><p className="eyebrow">公开展示 · 策展</p><h1>推荐与随机</h1><p>管理本期导语、阅读书目、排期，以及首页精选。</p></div><div><Link className="button secondary" href="/" target="_blank">预览首页 ↗</Link><button className="button" onClick={create} disabled={busy}>新建一期推荐</button></div></header>
    <nav className="v307-admin-tabs" aria-label="推荐管理范围"><button aria-current={tab === "issues" ? "page" : undefined} onClick={() => setTab("issues")}>总览与归档</button><button aria-current={tab === "placements" ? "page" : undefined} onClick={() => setTab("placements")}>精选与随机设置</button></nav>
    {message ? <p role="alert">{message}</p> : null}
    {tab === "placements" ? <RecommendationsAdmin key={placement} initialPlacement={placement} /> : <>
      {resource.error ? <p role="alert">{resource.error} <button type="button" onClick={resource.retry}>重试读取推荐期</button></p> : null}
      {resource.loading ? <p role="status">正在读取推荐与排期…</p> : null}
      <div className="issue-admin-metrics" aria-label="全库推荐统计">{[
        ["推荐期总数", data?.summary?.total], ["已公开推荐", data?.summary?.published], ["有待发布修改", data?.summary?.drafts], ["已确认排期", data?.summary?.scheduled],
      ].map(([label, value]) => <div key={label}><span>{label}</span><strong>{value ?? "—"}</strong></div>)}</div>
      <div className="issue-admin-overview">
        <section className="issue-admin-panel"><header><h2>当前本期推荐</h2><Link href="/recommendations">查看归档 <ArrowRight size={14}/></Link></header>
          {data?.current ? <><div className="issue-admin-current"><img src={data.current.cover_url || "/editorial/library-architecture-hero.webp"} alt=""/><div><p className="eyebrow">{data.current.issue_label}</p><h3>{data.current.title}</h3><p>{data.current.introduction}</p><small>{data.current.public_byline}</small></div></div><footer><span>{dateLabel(data.current.published_at)} 发布</span><Link className="button secondary" href={"/admin/recommendations/issues/" + data.current.id}>编辑本期</Link></footer></> : data ? <p className="empty-state">尚无已生效的本期推荐。确认发布后会显示在这里。</p> : null}
        </section>
        <section className="issue-admin-panel"><header><h2><CalendarDays size={20}/> 下一期排期</h2><button className="button secondary" onClick={create} disabled={busy}>新建推荐</button></header><p className="issue-admin-hint">显示已确认排期，后续草稿修改不会自动发布。</p>
          {data?.upcoming?.map((issue, index) => <Link className="issue-admin-scheduled" href={"/admin/recommendations/issues/" + issue.id} key={issue.id}><span>{String(index + 1).padStart(2, "0")}</span><div><h3>{issue.title}</h3><p>{issue.issue_label} · {issue.items.length} 项阅读物</p></div><time>{dateLabel(issue.display_from)}</time><ArrowRight size={16}/></Link>)}
          {data && !data.upcoming?.length ? <p className="empty-state">暂无已确认的后续排期。</p> : null}
        </section>
      </div>
      {policies.error ? <p role="alert">{policies.error} <button onClick={policies.retry}>重试读取精选内容</button></p> : null}
      <div className="issue-admin-overview">
        <section className="issue-admin-panel"><header><h2><Users size={20}/> 首页学者聚焦</h2><button className="button secondary" onClick={() => editPlacement("home_scholars")}>管理学者</button></header><div className="issue-admin-scholars">{scholars?.current?.items.slice(0, 6).map(item => <Link key={item.id} href={"/admin/scholars/" + item.target.id}>{itemImage(item) ? <img src={itemImage(item)} alt=""/> : <div className="issue-admin-placeholder"><Users size={26}/></div>}<strong>{itemLabel(item)}</strong><small>{item.reason || "当前展示"}</small></Link>)}</div>{scholars && !scholars.current?.items.length ? <p className="empty-state">当前尚无已发布的学者推荐。</p> : null}</section>
        <section className="issue-admin-panel"><header><h2>随机认识一位学者</h2><button className="button secondary" onClick={() => editPlacement("home_scholars")}>管理随机规则</button></header><p>从符合原推荐规则的公开学者中展示，读者点击随机只改变本次浏览。</p><div className="issue-admin-pool"><Users size={30}/><div><strong>{scholars?.current?.items.length ?? "—"} 位</strong><span>当前已发布名单</span></div></div><p className="issue-admin-hint">下一次计划更新：{dateLabel(scholars?.next_refresh_at)}</p></section>
      </div>
      <section className="issue-admin-panel"><header><h2>精选主题</h2><button className="button secondary" onClick={() => editPlacement("home_topics")}>管理主题</button></header><div className="issue-admin-topics">{topics?.current?.items.map(item => <Link href={"/admin/topics/" + item.target.id} key={item.id}>{itemImage(item) ? <img src={itemImage(item)} alt=""/> : <div className="issue-admin-placeholder"/>}<h3>{itemLabel(item)}</h3><p>{item.reason}</p></Link>)}</div>{topics && !topics.current?.items.length ? <p className="empty-state">当前尚无已发布的主题推荐。</p> : null}</section>
      <section className="issue-admin-panel"><header><h2>全部推荐期</h2><span>草稿、已发布与后续排期</span></header><form className="issue-admin-search" onSubmit={event => { event.preventDefault(); setQuery(String(new FormData(event.currentTarget).get("q") || "")); setPage(1); }}><input name="q" aria-label="查找推荐期" placeholder="按标题查找推荐期"/><button className="button secondary">查找</button></form>
        <div className="v307-admin-issue-list">{data?.results.map(issue => <Link href={"/admin/recommendations/issues/" + issue.id} key={issue.id}><div><p className="eyebrow">{issue.issue_label}</p><h3>{issue.title}</h3><p>{issue.public_byline}</p></div><span>{issue.has_unpublished_changes ? "有待发布修改" : issue.published_at ? "已发布" : "草稿"}</span><span>{issue.display_from ? dateLabel(issue.display_from) : "手动发布"}</span><span>继续编辑 →</span></Link>)}</div>
        {data?.count === 0 ? <p className="empty-state">没有符合条件的推荐期。</p> : null}<nav className="issue-pagination" aria-label="后台推荐归档分页"><button disabled={!data?.previous || resource.loading} onClick={() => setPage(page - 1)}>上一页</button><span>{data ? "共 " + data.count + " 期 · 第 " + page + " 页" : "正在读取"}</span><button disabled={!data?.next || resource.loading} onClick={() => setPage(page + 1)}>下一页</button></nav>
      </section>
    </>}
  </div>;
}
