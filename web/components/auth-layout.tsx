
import { LoadingState } from "@/components/ui/loading-state";
import { Suspense } from "react";
import { AuthPageFrame } from "./auth-page-frame";
import { SiteFooter } from "./site-footer";
import type { AuthMode } from "./auth-form";

export function AuthLayout({ mode }: { mode: AuthMode }) {
  return <><Suspense fallback={<LoadingState variant="screen">正在准备账户页面…</LoadingState>}><AuthPageFrame mode={mode} /></Suspense><SiteFooter reference="auth" /></>;
}
