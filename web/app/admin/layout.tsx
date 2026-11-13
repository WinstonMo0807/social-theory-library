import type { ReactNode } from "react";
import { AdminShell } from "@/components/admin-shell";
import "@/styles/features/center-layout.css";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
