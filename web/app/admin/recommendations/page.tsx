import type { Metadata } from "next";
import { RecommendationIssueList } from "@/components/admin/recommendation-issue-list";

export const metadata: Metadata = { title: "推荐管理" };
export default async function Page({ searchParams }: { searchParams: Promise<{ view?: string }> }) {
  const params = await searchParams;
  return <RecommendationIssueList initialTab={params.view === "home" ? "placements" : "issues"} />;
}
