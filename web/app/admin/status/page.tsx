import type { Metadata } from "next";
import { SystemStatusCenter } from "@/components/system-status-center";

export const metadata: Metadata = { title: "系统状态中心" };

export default function StatusPage() {
  return <SystemStatusCenter />;
}
