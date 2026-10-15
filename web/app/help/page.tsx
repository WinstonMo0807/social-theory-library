import { SiteFooter } from "@/components/site-footer";
import { SupportHub } from "@/components/public/support-hub";
import { loadSiteConfig } from "@/lib/api/site.server";
export const metadata = { title: "使用帮助与反馈" };
export default async function HelpPage() { return <><SupportHub config={await loadSiteConfig()} /><SiteFooter /></>; }
