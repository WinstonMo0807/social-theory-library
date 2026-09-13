// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { works as demoWorks } from "../data";
import { adaptApiWork as adaptWork } from "../public-data-adapters";
import type { ReaderManifest, ReaderManifestPayload } from "./public-catalog";
import { serverRequest, allowDemoFallback } from "./server-request";

export async function loadReaderManifest(assetId: string): Promise<ReaderManifest | null> {
  try {
    const payload = await serverRequest<ReaderManifestPayload>(`/catalog/assets/${encodeURIComponent(assetId)}/manifest/`);
    return {
      work: {
        ...adaptWork(payload.work),
        id: payload.asset_id,
        editionId: payload.edition_id,
        pages: payload.page_count,
      },
      outline: payload.outline,
      scholars: payload.related_scholars.flatMap((scholar) => typeof scholar.slug === "string" && scholar.slug ? [{ ...scholar, slug: scholar.slug }] : []),
      theories: payload.related_theories,
      topics: payload.related_topics,
    };
  } catch {
    if (!allowDemoFallback) return null;
    const fallback = demoWorks.find((item) => item.id === assetId) ?? demoWorks[0];
    return fallback ? {
      work: { ...fallback, id: assetId },
      outline: [],
      scholars: [],
      theories: [],
      topics: [],
    } : null;
  }
}
