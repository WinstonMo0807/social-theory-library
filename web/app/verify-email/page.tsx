
import { LoadingState } from "@/components/ui/loading-state";
import type { Metadata } from "next";
import { Suspense } from "react";
import { EmailVerificationPage } from "@/components/account-email-link";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = { title: "验证邮箱", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function VerifyEmailPage() {
  return <><Suspense fallback={<LoadingState variant="screen">正在准备邮箱验证…</LoadingState>}><EmailVerificationPage /></Suspense><SiteFooter /></>;
}
