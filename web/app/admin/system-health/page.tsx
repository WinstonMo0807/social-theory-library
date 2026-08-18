import type { Metadata } from "next";
import { AdminSystemHealth } from "@/components/admin-system-health";

export const metadata: Metadata = { title: "系统健康检查" };

export default function SystemHealthPage() {
  return <AdminSystemHealth />;
}
