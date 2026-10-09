import Link from "next/link";
import { SiteFooter } from "@/components/site-footer";
import { DailyReadingPublicIndexView } from "@/components/public/recommendation-issue-view";
import { loadRecommendationIssues } from "@/lib/api/recommendation-issues.server";
export const metadata = {title:"每日荐读"};
export default async function Page({searchParams}: {searchParams:Promise<{q?:string;page?:string}>}) {
  const query = await searchParams;
  const requestedPage = Number(query.page);
  const page = Number.isSafeInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
  const data = await loadRecommendationIssues(query.q || "",page);
  const href = (next:number) => `/recommendations?${new URLSearchParams({q:query.q || "",page:String(next)})}`;
  const lead = query.q || page > 1 ? data.results[0] || null : data.current || data.results[0] || null;
  const cards = data.results.filter(issue=>issue.id!==lead?.id);
  return <><div className="page-shell daily-reading-page"><DailyReadingPublicIndexView lead={lead} cards={cards}/>{data.previous || data.next ? <nav className="issue-pagination" aria-label="推荐文章分页">{data.previous ? <Link href={href(page-1)}>上一页</Link> : <span aria-disabled="true">上一页</span>}<span>共 {data.count} 期 · 第 {page} 页</span>{data.next ? <Link href={href(page+1)}>下一页</Link> : <span aria-disabled="true">下一页</span>}</nav> : null}</div><SiteFooter readingLayout/></>;
}
