import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { loadRecommendationIssues } from "@/lib/api/recommendation-issues.server";
export const metadata = { title: "本期书库推荐与归档" };
export default async function Page({ searchParams }: { searchParams: Promise<{ q?: string; page?: string }> }) {
  const query = await searchParams, page = Math.max(1, Number(query.page) || 1);
  const data = await loadRecommendationIssues(query.q || "", page);
  const href = (next: number) => `/recommendations?${new URLSearchParams({ q: query.q || "", page: String(next) })}`;
  return <><div className="page-shell issue-archive"><header><p className="eyebrow">Reading together</p><h1>本期书库推荐</h1><p>沿着一份有导语的阅读书单，走进具体的问题与文献。</p><form><input name="q" aria-label="搜索推荐期" placeholder="搜索期名、标题" defaultValue={query.q} /><button className="button">搜索</button></form></header><div className="issue-archive-grid">{data.results.map(issue => <article key={issue.id}><Link href={`/recommendations/${issue.slug}`}><img src={issue.cover_url || "/editorial/library-architecture-hero.webp"} alt="" loading="lazy" /><p className="eyebrow">{issue.issue_label}</p><h2>{issue.title}</h2><p>{issue.introduction}</p><span>{issue.public_byline}</span></Link></article>)}</div>{!data.count ? <p className="empty-state">暂时没有符合条件的已发布推荐。</p> : null}<nav className="issue-pagination" aria-label="推荐归档分页">{data.previous ? <Link href={href(page - 1)}>上一页</Link> : null}<span>共 {data.count} 期 · 第 {page} 页</span>{data.next ? <Link href={href(page + 1)}>下一页</Link> : null}</nav></div><SiteFooter /></>;
}
