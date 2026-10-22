import type { Metadata } from "next";
import { AdminDashboard } from "@/components/admin-dashboard";

export const metadata: Metadata = { title: "今日工作与继续处理" };

export default function AdminPage() {
  return <AdminDashboard />;
}
