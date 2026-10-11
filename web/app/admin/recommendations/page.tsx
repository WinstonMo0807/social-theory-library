import type { Metadata } from "next";
import { RecommendationIssueList } from "@/components/admin/recommendation-issue-list";
import { loadHomeViewData } from "@/lib/api/home.server";

export const metadata: Metadata = { title: "推荐管理" };
export default async function Page({ searchParams }: { searchParams: Promise<{ view?: string; placement?: string }> }) {
  const params = await searchParams;
  return <RecommendationIssueList home={await loadHomeViewData()} initialPlacement={params.placement} initialTab={params.view === "home" ? "placements" : params.view === "calendar" ? "calendar" : "issues"} />;
}
