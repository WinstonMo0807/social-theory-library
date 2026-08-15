import type { Metadata } from "next";
import { AdminSystemHealth } from "@/components/admin-system-health";

export const metadata: Metadata = { title: "System Health" };

export default function SystemHealthPage() {
  return <AdminSystemHealth />;
}
