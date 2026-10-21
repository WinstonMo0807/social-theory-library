import { RecommendationIssueView } from "@/components/public/recommendation-issue-view";
import { SiteFooter } from "@/components/site-footer";
import { loadRecommendationIssue } from "@/lib/api/recommendation-issues.server";
import { notFound } from "next/navigation";
import { ServerApiError } from "@/lib/api/server-request";
export const metadata = { title: "专题文章与原文展览" };
export default async function Page({ params, searchParams }: { params: Promise<{ slug: string }>; searchParams: Promise<{exhibit?:string}> }) {
  const { slug } = await params;
  const issue = await loadRecommendationIssue(slug).catch(error => { if (error instanceof ServerApiError && error.status === 404) notFound(); throw error; });
  const query = await searchParams;
  return <><RecommendationIssueView key={`${issue.public_revision_id}:${query.exhibit || ""}`} issue={issue} selectedExhibit={query.exhibit} /><SiteFooter /></>;
}
