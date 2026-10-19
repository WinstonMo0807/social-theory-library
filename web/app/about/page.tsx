import { SiteFooter } from "@/components/site-footer";
import { AboutPublicView } from "@/components/public/about-public-view";
import { loadAboutBlocks, loadSiteChromeConfig } from "@/lib/api/site.server";
export const metadata = { title: "关于书库" };
export default async function AboutPage() {
  const [chrome, about] = await Promise.allSettled([loadSiteChromeConfig(), loadAboutBlocks()]);
  // Chrome's established fallback is navigation copy, never replacement library data.
  if (chrome.status === "rejected") throw chrome.reason;
  return <><AboutPublicView config={chrome.value.config} about={about.status === "fulfilled" ? about.value : null} unavailable={chrome.value.unavailable || about.status === "rejected"} /><SiteFooter /></>;
}
