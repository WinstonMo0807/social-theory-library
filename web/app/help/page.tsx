import { SiteFooter } from "@/components/site-footer";
import { SupportHub } from "@/components/public/support-hub";
import { loadSiteChromeConfig, loadAboutBlocks } from "@/lib/api/site.server";
import { supportSection } from "@/lib/support-content";
import { redirect } from "next/navigation";
export const metadata = { title: "使用帮助与反馈" };
export default async function HelpPage({ searchParams }: { searchParams: Promise<{ section?: string }> }) { const params=await searchParams; const section=supportSection(params.section); if(section==="feedback")redirect("/feedback"); const [chrome,about]=await Promise.all([loadSiteChromeConfig(),["content","updates"].includes(section)?loadAboutBlocks().catch(()=>null):Promise.resolve(null)]); return <><SupportHub key={section} config={chrome.config} unavailable={chrome.unavailable} section={section} about={about} /><SiteFooter reference="support" /></>; }
