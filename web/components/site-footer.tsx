import { loadSiteChromeConfig } from "@/lib/api/site.server";
import { SiteFooterView } from "@/components/public/site-footer-view";

export async function SiteFooter({ compact = false, reference }: { compact?: boolean; reference?: "notebook" | "citation-issue" | "reading-plan" | "research-compare" | "research-workspace" | "auth" | "reader-center" | "sharing" | "editorial" | "about" | "support" | "article" | "catalog" | "opinion" | "work" | "journal" | "graph" | "theory-timeline" | "reading-paths" | "reading-path" } = {}) {
  const { config } = await loadSiteChromeConfig();
  return <SiteFooterView config={config} compact={compact} reference={reference} />;
}
