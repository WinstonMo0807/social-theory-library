import { loadSiteConfig } from "@/lib/api/site.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export async function SiteFooter() {
  const config = await loadSiteConfig();
  return <SiteFooterView config={config} />;
}
