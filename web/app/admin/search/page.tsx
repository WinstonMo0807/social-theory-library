import type { Metadata } from "next";
import { AdminDashboard } from "@/components/admin-dashboard";

export const metadata: Metadata = { title: "搜索工作与资料" };

export default function AdminSearchPage() {
  return <AdminDashboard searchMode />;
}
