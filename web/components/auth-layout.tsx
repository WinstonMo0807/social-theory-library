import { Suspense } from "react";
import { AuthPageFrame } from "./auth-page-frame";
import { SiteFooter } from "./site-footer";
import type { AuthMode } from "./auth-form";

export function AuthLayout({ mode }: { mode: AuthMode }) {
  return <><Suspense fallback={<div className="auth-atlas-page" role="status">正在准备账户页面…</div>}><AuthPageFrame mode={mode} /></Suspense><SiteFooter reference="auth" /></>;
}
