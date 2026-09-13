// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { type SiteConfig, defaultSiteConfig } from "../site-config";
import { WEB_APP_VERSION } from "../version";
import type { Paginated } from "./pagination";
import { serverRequest, allowDemoFallback } from "./server-request";
import type { SiteStats, AboutPageBlock } from "./site.types";

export async function loadSiteConfig(): Promise<SiteConfig> {
  try {
    return await serverRequest<SiteConfig>("/catalog/site-config/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return defaultSiteConfig;
  }
}

export async function loadSiteStats(): Promise<SiteStats> {
  try {
    return await serverRequest<SiteStats>("/catalog/site-stats/");
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      documents: 0,
      scholars: 0,
      knowledge_objects: 0,
      last_updated: null,
      last_updated_label: "尚未发布",
      version: WEB_APP_VERSION,
    };
  }
}

export async function loadAboutBlocks(): Promise<{ configured: boolean; blocks: AboutPageBlock[] }> {
  try {
    const payload = await serverRequest<Paginated<AboutPageBlock> & { configured?: boolean }>("/catalog/about-blocks/");
    return { configured: payload.configured ?? payload.results.length > 0, blocks: payload.results };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return { configured: false, blocks: [] };
  }
}
