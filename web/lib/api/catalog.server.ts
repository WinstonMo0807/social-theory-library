// Server-side public API domain. Browser components use pure adapters and type-only imports.
import { type Work, works as demoWorks, scholars as demoScholars, theorySchools as demoTheorySchools } from "../data";
import { adaptApiWork } from "../public-data-adapters";
import type { Paginated } from "./pagination";
import type { ApiScholar } from "./people.types";
import type { ApiWork } from "./public-catalog";
import { serverRequest, allowDemoFallback, ServerApiError } from "./server-request";

export const adaptWork = adaptApiWork;

export async function loadWorks(): Promise<Work[]> {
  try {
    const payload = await serverRequest<Paginated<ApiWork>>("/catalog/works/?ordering=-editions__first_published_at");
    return payload.results.map(adaptWork);
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return demoWorks;
  }
}

export async function loadCatalogOverview(): Promise<{
  works: number;
  scholars: number;
  theories: number;
}> {
  try {
    const [worksPayload, scholarsPayload, theoriesPayload] = await Promise.all([
      serverRequest<Paginated<ApiWork>>("/catalog/works/"),
      serverRequest<Paginated<ApiScholar>>("/catalog/scholars/"),
      serverRequest<Paginated<{ slug: string }>>("/catalog/theory-schools/"),
    ]);
    return {
      works: worksPayload.count,
      scholars: scholarsPayload.count,
      theories: theoriesPayload.count,
    };
  } catch (error) {
    if (!allowDemoFallback) throw error;
    return {
      works: demoWorks.length,
      scholars: demoScholars.length,
      theories: demoTheorySchools.length,
    };
  }
}

export async function loadWork(slug: string): Promise<Work | null> {
  try {
    return adaptWork(await serverRequest<ApiWork>(`/catalog/works/${encodeURIComponent(slug)}/`));
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    if (!allowDemoFallback) throw error;
    return demoWorks.find((item) => item.slug === slug) ?? null;
  }
}
