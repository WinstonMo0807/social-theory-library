import { RouteStyles } from "./route-styles";
import type { ReactNode } from "react";
import { AdminShell } from "@/components/admin-shell";

export default function AdminLayout({ children }: { children: ReactNode }) {
  return <AdminShell><RouteStyles />{children}</AdminShell>;
}
