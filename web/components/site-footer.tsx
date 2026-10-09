import { loadSiteConfig } from "@/lib/api/site.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export async function SiteFooter({ readingLayout = false }: { readingLayout?: boolean } = {}) {
  const config = await loadSiteConfig();
  return <SiteFooterView config={config} readingLayout={readingLayout} />;
}
