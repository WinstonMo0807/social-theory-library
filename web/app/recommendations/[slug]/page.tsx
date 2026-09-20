import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import { SiteFooter } from "@/components/site-footer";
import { loadRecommendationIssue } from "@/lib/api/recommendation-issues.server";
import { notFound } from "next/navigation";
import { ServerApiError } from "@/lib/api/server-request";
export const metadata = { title: "书库推荐" };
export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const issue = await loadRecommendationIssue(slug).catch(error => { if (error instanceof ServerApiError && error.status === 404) notFound(); throw error; });
  return <><div className="page-shell"><RecommendationIssueView issue={issue} /></div><SiteFooter /></>;
}
