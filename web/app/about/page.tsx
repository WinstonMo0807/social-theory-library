import { SiteFooter } from "@/components/site-footer";
import { AboutPublicView } from "@/components/public/about-public-view";
import { loadAboutBlocks, loadSiteConfig, loadSiteStats } from "@/lib/api/site.server";
export const metadata = { title: "关于书库" };
export default async function AboutPage() {
  const [config, stats, about] = await Promise.all([loadSiteConfig(), loadSiteStats(), loadAboutBlocks()]);
  return <><AboutPublicView config={config} stats={stats} about={about} /><SiteFooter /></>;
}
