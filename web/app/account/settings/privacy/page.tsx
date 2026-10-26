import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { PrivacyWorkspace } from "@/components/research/privacy-workspace";

export const metadata: Metadata = { title: "隐私与资料" };
export default function PrivacyPage() { return <><PrivacyWorkspace /><SiteFooter reference="privacy" /></>; }
