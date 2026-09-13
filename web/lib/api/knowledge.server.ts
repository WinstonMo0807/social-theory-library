// Server-side public API domain. Browser components use pure adapters and type-only imports.
import type { TheoryDisciplineCompact, TheorySystemOverview, KnowledgeNodeListItem, KnowledgeNodeDetail, TheoryDisciplinePage, NormalizedTimelineEvent, LocalTheoryGraph, NormalizedReadingPath } from "./knowledge.types";
import type { Paginated } from "./pagination";
import { serverRequest, allowDemoFallback } from "./server-request";

const fallbackTheoryDisciplines: Record<string, TheoryDisciplineCompact> = {
  sociology: {
    id: "fallback-sociology",
    code: "SOC",
    name: "社会学",
    foreign_name: "Sociology",
    slug: "sociology",
    description: "研究社会关系、制度、结构及其变迁。",
    hero_image: "",
  },
  anthropology: {
    id: "fallback-anthropology",
    code: "ANTH",
    name: "人类学",
    foreign_name: "Anthropology",
    slug: "anthropology",
    description: "从文化、实践与比较视角理解人类生活。",
    hero_image: "",
  },
  ethnology: {
    id: "fallback-ethnology",
    code: "ETH",
    name: "民族学",
    foreign_name: "Ethnology",
    slug: "ethnology",
    description: "研究族群、民族关系及其历史与现实变化。",
    hero_image: "",
  },
};

export async function loadTheorySystemOverview(): Promise<TheorySystemOverview | null> {
  try {
    return await serverRequest<TheorySystemOverview>("/catalog/theory-system/overview/");
  } catch {
    return null;
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
  } catch {
    return [];
  }
}

export async function loadKnowledgeNode(slug: string): Promise<KnowledgeNodeDetail | null> {
  try {
    return await serverRequest<KnowledgeNodeDetail>(
      `/catalog/theory-system/nodes/${encodeURIComponent(slug)}/`,
    );
  } catch {
    return null;
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
    if (!allowDemoFallback) throw error;
    const discipline = fallbackTheoryDisciplines[slug];
    if (!discipline) return null;
    return {
      discipline,
      counts: {},
      active_type: nodeType,
      nodes: [],
      lineage: [],
      reading_paths: [],
    };
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
  } catch {
    return [];
  }
}

export async function loadNormalizedTheoryTimelinePage(filters: {
  discipline?: string;
  node?: string;
  event_type?: string;
  has_collection?: string;
  q?: string;
  page?: string;
} = {}): Promise<Paginated<NormalizedTimelineEvent>> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => value && parameters.set(key, value));
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return await serverRequest<Paginated<NormalizedTimelineEvent>>(
      `/catalog/theory-system/timeline/${suffix}`,
    );
  } catch {
    return { count: 0, next: null, previous: null, results: [] };
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
} = {}): Promise<LocalTheoryGraph> {
  const parameters = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value !== undefined && value !== "") parameters.set(key, String(value));
  });
  try {
    const suffix = parameters.size ? `?${parameters.toString()}` : "";
    return await serverRequest<LocalTheoryGraph>(`/catalog/theory-system/graph/${suffix}`);
  } catch {
    return { center: null, nodes: [], edges: [], depth: 1, limit: 20, truncated: false };
  }
}

export async function loadNormalizedReadingPaths(discipline = ""): Promise<NormalizedReadingPath[]> {
  try {
    const suffix = discipline ? `?discipline=${encodeURIComponent(discipline)}` : "";
    const payload = await serverRequest<Paginated<NormalizedReadingPath>>(
      `/catalog/theory-system/reading-paths/${suffix}`,
    );
    return payload.results;
  } catch {
    return [];
  }
}

export async function loadNormalizedReadingPath(slug: string): Promise<NormalizedReadingPath | null> {
  try {
    return await serverRequest<NormalizedReadingPath>(
      `/catalog/theory-system/reading-paths/${encodeURIComponent(slug)}/`,
    );
  } catch {
    return null;
  }
}
