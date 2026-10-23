import type { Metadata } from "next";
import { AccountActivation } from "@/components/account-activation";
import { SiteFooter } from "@/components/site-footer";

export const metadata: Metadata = { title: "激活账户", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function ActivatePage() {
  return <><AccountActivation /><SiteFooter /></>;
}
