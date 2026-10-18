import type { Metadata } from "next";
import { SiteFooter } from "@/components/site-footer";
import { PrivacyWorkspace } from "@/components/research/privacy-workspace";

export const metadata: Metadata = { title: "导出与删除资料" };
export default function PrivacyExportPage() { return <><PrivacyWorkspace exportOnly /><SiteFooter /></>; }
