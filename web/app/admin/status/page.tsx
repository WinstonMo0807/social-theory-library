import type { Metadata } from "next";
import { SystemStatusCenter } from "@/components/system-status-center";

export const metadata: Metadata = { title: "System Status Center" };

export default function StatusPage() {
  return <SystemStatusCenter />;
}
