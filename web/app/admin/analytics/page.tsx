import type { Metadata } from "next";
import { AdminAnalytics } from "@/components/admin-analytics";

export const metadata: Metadata = { title: "阅读与搜索统计" };

export default function AnalyticsPage() {
  return <AdminAnalytics />;
}
