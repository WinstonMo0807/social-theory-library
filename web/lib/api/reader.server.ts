// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { works as demoWorks } from "../data";
import { adaptApiWork as adaptWork } from "../public-data-adapters";
import type { ReaderManifest, ReaderManifestPayload } from "./public-catalog";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";
import { readerFailure, type ReaderFailure } from "./reader-failure";

export type ReaderManifestResult = { ok: true; manifest: ReaderManifest } | { ok: false; failure: ReaderFailure };

export async function loadReaderManifestResult(assetId: string): Promise<ReaderManifestResult> {
  try {
    const payload = await serverRequest<ReaderManifestPayload>(`/catalog/assets/${encodeURIComponent(assetId)}/manifest/`);
    return { ok: true, manifest: {
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
    } };
  } catch (reason) {
    const failure = readerFailure(reason instanceof ServerApiError ? reason.status : undefined);
    if (!allowDemoFallback) return { ok: false, failure };
    // Even development fixtures must never substitute a different document.
    const fallback = demoWorks.find((item) => item.id === assetId);
    return fallback ? { ok: true, manifest: {
      work: { ...fallback, id: assetId },
      outline: [],
      scholars: [],
      theories: [],
      topics: [],
    } } : { ok: false, failure };
  }
}

/** Legacy server-client export; the Reader route uses the classified result. */
export async function loadReaderManifest(assetId: string): Promise<ReaderManifest | null> {
  const result = await loadReaderManifestResult(assetId);
  return result.ok ? result.manifest : null;
}
