import { loadSiteChromeConfig } from "@/lib/api/site.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export async function SiteFooter({ compact = false }: { compact?: boolean } = {}) {
  const { config } = await loadSiteChromeConfig();
  return <SiteFooterView config={config} compact={compact} />;
}
