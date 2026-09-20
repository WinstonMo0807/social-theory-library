import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Compass } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ScopedSearchPagination } from "@/components/scoped-search";
import { ArchitecturalImage, SearchField, SectionHeading } from "@/components/ui";
import { loadRecommendations, recommendationSlugs } from "@/lib/api/recommendations.server";
import { loadTopic, loadTopicPage } from "@/lib/api/topics.server";
import { searchPage } from "@/lib/search-context";
export const metadata: Metadata = {title: "主题"};
export default async function TopicsPage({searchParams}: {searchParams: Promise<{q?: string; discipline?: string; sort?: "name" | "works"; page?: string}>}) {
  const params = await searchParams;
  const q = params.q?.trim() || "";
  const page = searchPage(params.page);
  const sort = params.sort === "works" ? "works" : "name";
  const [result, recommendations] = await Promise.all([loadTopicPage(q, {discipline: params.discipline || "", sort}, page), loadRecommendations()]);
  const featured = (await Promise.all(recommendationSlugs(recommendations, "home_topics", "topic").slice(0,4).map(slug => loadTopic(slug)))).filter(row => row !== null);
  return <><main className="page-shell v307-knowledge topics-hub-v307">
    <section className="knowledge-hero"><div><p className="eyebrow">思想连接世界</p><h1>主题</h1><h2>从不同的主题，进入社会理论的多重视角。</h2><p>围绕具体的社会议题，阅读经典观点、核心概念与相关原文。</p><form action="/topics" className="knowledge-search"><input type="hidden" name="context" value="topics"/><SearchField defaultValue={q} placeholder="搜索主题、关键词或相关内容…"/><button type="submit">搜索</button></form></div><div className="knowledge-hero-image"><ArchitecturalImage compact/></div></section>
    {!q && page === 1 && featured.length ? <section className="knowledge-section panel"><SectionHeading title="精选主题" href="/topics?sort=name"/><div className="knowledge-topic-featured">{featured.map(row => <Link href={`/topics/${row.slug}`} key={row.id}><div className="knowledge-card-image" style={row.heroImage ? {backgroundImage: `url("${row.heroImage}")`} : undefined}>{!row.heroImage ? <ArchitecturalImage compact/> : null}</div><h2>{row.name}</h2><p>{row.description || row.problemStatement}</p><ArrowRight size={16}/></Link>)}</div></section> : null}
    <section className="knowledge-section panel"><SectionHeading title={q ? "主题搜索结果" : "全部主题"} action={`${result.count} 个主题`}/><form className="knowledge-sort" action="/topics"><input type="hidden" name="q" value={q}/>{params.discipline ? <input type="hidden" name="discipline" value={params.discipline}/> : null}<label>排序 <select name="sort" defaultValue={sort}><option value="name">按名称</option><option value="works">按关联馆藏数</option></select></label><button type="submit">应用</button></form><div className="knowledge-topic-directory">{result.results.map(row => <Link href={`/topics/${row.slug}`} key={row.id}><Compass size={34}/><span><h2>{row.name}</h2><p>{row.description || row.problemStatement}</p></span><ArrowRight size={16}/></Link>)}</div>{!result.results.length ? <p className="empty-state">没有找到匹配的公开主题。</p> : null}<ScopedSearchPagination path="/topics" context="topics" page={page} totalPages={result.totalPages} params={{q, sort, discipline: params.discipline || ""}}/></section>
  </main><SiteFooter/></>;
}
