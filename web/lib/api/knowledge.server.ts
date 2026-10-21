// Server-side public API domain. Browser components use pure adapters and type-only imports.
import type { TheorySystemOverview, KnowledgeNodeListItem, KnowledgeNodeDetail, TheoryDisciplinePage, NormalizedTimelineEvent, NormalizedReadingPath } from "./knowledge.types";
import { directoryPage, type DirectoryPage, type Paginated } from "./pagination";
import { serverRequest, ServerApiError } from "./server-request";
import { loadPublicGraph } from "./graph.server";
import type { PublicTheoryGraph } from "./graph.types";
import type { PublishedEvidenceCuration } from "./evidence-curation.types";

export async function loadTheorySystemOverview(): Promise<TheorySystemOverview | null> {
  try {
    return await serverRequest<TheorySystemOverview>("/catalog/theory-system/overview/");
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    throw error;
  }
}

export async function loadTheorySystemNodes(filters: {
  type?: string;
  discipline?: string;
  q?: string;
} = {}): Promise<KnowledgeNodeListItem[]> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<KnowledgeNodeListItem>>(
      `/catalog/theory-system/nodes/${suffix}`,
    );
    return payload.results;
  } catch (error) {
    throw error;
  }
}

export async function loadTheorySystemNodesPage(filters: {type?: string; discipline?: string; q?: string; sort?: string; has_works?: string}, page = 1): Promise<DirectoryPage<KnowledgeNodeListItem>> {
  const parameters = new URLSearchParams({page: String(page)});
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  const payload = await serverRequest<Paginated<KnowledgeNodeListItem>>(`/catalog/theory-system/nodes/?${parameters}`);
  return directoryPage(payload, page);
}

export async function loadKnowledgeNode(slug: string): Promise<KnowledgeNodeDetail | null> {
  try {
    const payload = await serverRequest<KnowledgeNodeDetail>(
      `/catalog/theory-system/nodes/${encodeURIComponent(slug)}/`,
    );
    const [evidenceCuration, placements] = await Promise.all([
      serverRequest<PublishedEvidenceCuration>(`/catalog/evidence-curation/node/${payload.id}/`),
      serverRequest<{public_detail: NonNullable<KnowledgeNodeDetail["public_detail"]>}>(`/catalog/content-placements/node/${payload.id}/`),
    ]);
    return { ...payload, evidenceCuration, public_detail: placements.public_detail };
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404 && error.path === `/catalog/theory-system/nodes/${encodeURIComponent(slug)}/`) return null;
    throw error;
  }
}

export async function loadTheoryDisciplinePage(
  slug: string,
  nodeType = "theory_tradition",
): Promise<TheoryDisciplinePage | null> {
  try {
    return await serverRequest<TheoryDisciplinePage>(
      `/catalog/theory-system/disciplines/${encodeURIComponent(slug)}/?type=${encodeURIComponent(nodeType)}`,
    );
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    throw error;
  }
}

export async function loadNormalizedTheoryTimeline(filters: {
  discipline?: string;
  node?: string;
  event_type?: string;
  has_collection?: string;
  q?: string;
} = {}): Promise<NormalizedTimelineEvent[]> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    const payload = await serverRequest<Paginated<NormalizedTimelineEvent>>(
      `/catalog/theory-system/timeline/${suffix}`,
    );
    return payload.results;
  } catch (error) {
    throw error;
  }
}

export async function loadNormalizedTheoryTimelinePage(filters: {
  discipline?: string;
  node?: string;
  event_type?: string;
  has_collection?: string;
  q?: string;
  page?: string;
  year_from?: string;
  year_to?: string;
} = {}): Promise<Paginated<NormalizedTimelineEvent>> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return await serverRequest<Paginated<NormalizedTimelineEvent>>(
      `/catalog/theory-system/timeline/${suffix}`,
    );
  } catch (error) {
    throw error;
  }
}

export async function loadLocalTheoryGraph(filters: {
  center?: string;
  discipline?: string;
  node_type?: string;
  relation_type?: string;
  start_year?: number;
  end_year?: number;
  has_collection?: string;
  depth?: number;
  limit?: number;
} = {}): Promise<PublicTheoryGraph> {
  return loadPublicGraph(Object.fromEntries(Object.entries(filters)
    .filter(([, value]) => value !== undefined && value !== "")
    .map(([key, value]) => [key, String(value)])));
}

export async function loadNormalizedReadingPaths(discipline = ""): Promise<NormalizedReadingPath[]> {
  try {
    const suffix = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    const payload = await serverRequest<Paginated<NormalizedReadingPath>>(
      `/catalog/theory-system/reading-paths/${suffix}`,
    );
    return payload.results;
  } catch (error) {
    throw error;
  }
}

export async function loadNormalizedReadingPathsPage(filters: {discipline?: string; node?: string} = {}, page = 1): Promise<DirectoryPage<NormalizedReadingPath>> {
  const parameters = new URLSearchParams({page: String(page)});
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  const payload = await serverRequest<Paginated<NormalizedReadingPath>>(`/catalog/theory-system/reading-paths/?${parameters}`);
  return directoryPage(payload, page);
}

export async function loadNormalizedReadingPath(slug: string): Promise<NormalizedReadingPath | null> {
  try {
    return await serverRequest<NormalizedReadingPath>(
      `/catalog/theory-system/reading-paths/${encodeURIComponent(slug)}/`,
    );
  } catch (error) {
    if (error instanceof ServerApiError && error.status === 404) return null;
    throw error;
  }
}
