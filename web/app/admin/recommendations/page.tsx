import type { Metadata } from "next";
import { RecommendationIssueList } from "@/components/admin/recommendation-issue-list";
import { CurationProjectWorkspace } from "@/components/admin/curation-project-workspace";

export const metadata: Metadata = { title: "策划项目与文章管理" };
export default async function Page({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const params = await searchParams;
  return params.view === "home" || params.view === "legacy" ? <RecommendationIssueList initialTab={params.view === "home" ? "placements" : "issues"} /> : <CurationProjectWorkspace />;
}
