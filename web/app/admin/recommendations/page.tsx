import type { Metadata } from "next";
import { RecommendationIssueList } from "@/components/admin/recommendation-issue-list";

export const metadata: Metadata = { title: "推荐管理" };
export default function Page() { return <RecommendationIssueList />; }
