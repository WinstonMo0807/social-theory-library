import { loadSiteChromeConfig } from "@/lib/api/site.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export async function SiteFooter({ compact = false, reference }: { compact?: boolean; reference?: "about" | "support" | "article" | "catalog" | "opinion" | "work" | "journal" } = {}) {
  const { config } = await loadSiteChromeConfig();
  return <SiteFooterView config={config} compact={compact} reference={reference} />;
}
